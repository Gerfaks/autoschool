from datetime import datetime, timedelta

from flask import flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func

from billing import calculate_lessons_total
from extensions import db
from models import Automobiles, CancellationHistory, InstructorSchedule, Instructors, Lessons, LessonType, Payments
from utils import (
    get_instructors_lesson_locations,
    get_lesson_location,
    get_lesson_locations,
    get_lesson_type_id,
    get_menu_items,
    get_user_display_name,
)


def register_student_routes(app):
    def release_lesson_slot(lesson):
        slot = InstructorSchedule.query.filter_by(
            instructor_id=lesson.instructor_id,
            lesson_date=lesson.lesson_date,
            lesson_time=lesson.lesson_time,
            booked_by=lesson.kursant_id,
        ).first()
        if slot:
            slot.is_booked = False
            slot.booked_by = None

    @app.route('/student')
    @login_required
    def student_dashboard():
        if current_user.role != 'student':
            return "Доступ запрещен", 403
        
        today = datetime.now().date()
        
        # Расчет задолженности
        paid = db.session.query(func.sum(Payments.amount)).filter_by(kursant_id=current_user.kursant_id).scalar() or 0
        completed_lessons = Lessons.query.filter_by(
            kursant_id=current_user.kursant_id,
            status='completed'
        ).all()
        lessons_count = len(completed_lessons)
        expected = calculate_lessons_total(completed_lessons)
        debt = expected - paid
        
        # Получаем занятия с именами инструкторов и статусом
        lessons = db.session.query(
            Lessons.lesson_id,
            Lessons.lesson_date,
            Lessons.lesson_time,
            LessonType.name.label('lesson_type'),
            Lessons.status,
            Instructors.fullname.label('instructor_name'),
            Instructors.phone.label('instructor_phone'),
            Lessons.instructor_id
        ).join(Instructors, Lessons.instructor_id == Instructors.instructor_id)\
         .join(LessonType, Lessons.lesson_type_id == LessonType.lesson_type_id)\
         .filter(Lessons.kursant_id == current_user.kursant_id)\
         .order_by(Lessons.lesson_date, Lessons.lesson_time).all()
        
        payments = Payments.query.filter_by(kursant_id=current_user.kursant_id).order_by(Payments.payment_date.desc()).all()
        
        return render_template('student/dashboard.html',
            title="Панель курсанта",
            user_name=get_user_display_name(current_user),
            role=current_user.role,
            menu_items=get_menu_items('dashboard', 'student'),
            today=datetime.now().strftime("%d.%m.%Y"),
            lessons=lessons,
            lesson_locations={
                lesson.lesson_id: get_lesson_location(lesson.lesson_type, lesson.instructor_id)
                for lesson in lessons
            },
            payments=payments,
            paid=float(paid),
            lessons_count=lessons_count,
            debt=debt
        )

    @app.route('/student/lesson/cancel/<int:id>', methods=['POST'])
    @login_required
    def student_cancel_lesson(id):
        if current_user.role != 'student':
            return "Доступ запрещен", 403

        lesson = Lessons.query.get_or_404(id)
        if lesson.kursant_id != current_user.kursant_id:
            return "Доступ запрещен", 403

        if lesson.status == 'completed':
            flash('Проведенное занятие нельзя отменить')
            return redirect(url_for('student_dashboard'))
        if lesson.status == 'cancelled':
            flash('Это занятие уже отменено')
            return redirect(url_for('student_dashboard'))

        lesson.status = 'cancelled'
        db.session.add(CancellationHistory(
            lesson_id=lesson.lesson_id,
            cancelled_by_user_id=current_user.id,
            reason='Курсант отменил запись'
        ))
        release_lesson_slot(lesson)
        db.session.commit()
        flash('Запись на занятие отменена')
        return redirect(url_for('student_dashboard'))

    @app.route('/student/booking', methods=['GET', 'POST'])
    @login_required
    def student_booking():
        if current_user.role != 'student':
            return "Доступ запрещен", 403
        
        if request.method == 'POST':
            try:
                schedule_id = request.form['schedule_id']
                slot = InstructorSchedule.query.get_or_404(schedule_id)
                
                if slot.is_booked:
                    flash('❌ Извините, это время уже занято')
                    return redirect(url_for('student_booking'))
                
                auto = Automobiles.query.filter_by(instructor_id=slot.instructor_id).first()
                if not auto:
                    auto = Automobiles.query.filter_by(instructor_id=None).first()

                lesson = Lessons(
                    lesson_date=slot.lesson_date,
                    lesson_time=slot.lesson_time,
                    lesson_type_id=get_lesson_type_id(request.form['lesson_type']),
                    kursant_id=current_user.kursant_id,
                    instructor_id=slot.instructor_id,
                    auto_id=auto.auto_id if auto else None,
                    comments=request.form.get('comments', ''),
                    status='pending'
                )
                db.session.add(lesson)
                
                slot.is_booked = True
                slot.booked_by = current_user.kursant_id
                
                db.session.commit()
                flash('✅ Вы успешно записались на занятие!')
                return redirect(url_for('student_dashboard'))
                
            except Exception as e:
                db.session.rollback()
                flash(f'❌ Ошибка: {e}')
                return redirect(url_for('student_booking'))
        
        instructors = Instructors.query.order_by(Instructors.fullname).all()
        instructor_cars = {
            car.instructor_id: car
            for car in Automobiles.query.filter(Automobiles.instructor_id.isnot(None)).all()
        }
        return render_template('student/booking.html',
            title="Запись на занятие",
            user_name=get_user_display_name(current_user),
            role=current_user.role,
            menu_items=get_menu_items('booking', 'student'),
            today=datetime.now().strftime("%d.%m.%Y"),
            instructors=instructors,
            instructor_cars=instructor_cars,
            lesson_locations=get_lesson_locations(),
            instructor_lesson_locations=get_instructors_lesson_locations(instructors)
        )

    @app.route('/student/get_slots/<int:instructor_id>')
    @login_required
    def get_slots(instructor_id):
        if current_user.role != 'student':
            return jsonify([])
        
        today = datetime.now().date()
        max_date = today + timedelta(days=30)
        
        slots = InstructorSchedule.query.filter_by(
            instructor_id=instructor_id,
            is_booked=False
        ).filter(InstructorSchedule.lesson_date >= today)\
         .filter(InstructorSchedule.lesson_date <= max_date)\
         .order_by(InstructorSchedule.lesson_date, InstructorSchedule.lesson_time).all()
        
        return jsonify([{
            'schedule_id': s.schedule_id,
            'lesson_date': s.lesson_date.strftime('%d.%m.%Y'),
            'lesson_time': s.lesson_time.strftime('%H:%M')
        } for s in slots])
