import os
from datetime import datetime, timedelta

from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from werkzeug.utils import secure_filename

from extensions import db
from models import Automobiles, CancellationHistory, InstructorSchedule, Kursanty, Lessons, LessonType
from utils import get_lesson_location, get_lesson_locations, get_menu_items, get_user_display_name


def register_instructor_routes(app):
    def save_car_photo(file):
        if not file or not file.filename:
            return None

        os.makedirs('uploads', exist_ok=True)
        filename = secure_filename(file.filename)
        unique_filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{filename}"
        file.save(os.path.join('uploads', unique_filename))
        return unique_filename

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

    @app.route('/instructor')
    @login_required
    def instructor_dashboard():
        if current_user.role != 'instructor':
            return "Доступ запрещен", 403
        
        today = datetime.now().date()
        
        # Получаем занятия с именами курсантов
        lessons = db.session.query(
            Lessons.lesson_id,
            Lessons.lesson_date,
            Lessons.lesson_time,
            LessonType.name.label('lesson_type'),
            Lessons.status,
            Kursanty.fullname.label('kursant_name'),
            Kursanty.phone.label('kursant_phone')
        ).join(Kursanty, Lessons.kursant_id == Kursanty.kursant_id)\
         .join(LessonType, Lessons.lesson_type_id == LessonType.lesson_type_id)\
         .filter(Lessons.instructor_id == current_user.instructor_id)\
         .order_by(Lessons.lesson_date, Lessons.lesson_time).all()
        
        return render_template('instructor/dashboard.html',
            title="Панель инструктора",
            user_name=get_user_display_name(current_user),
            role=current_user.role,
            menu_items=get_menu_items('dashboard', 'instructor'),
            today=datetime.now().strftime("%d.%m.%Y"),
            lessons=lessons,
            lesson_locations={
                lesson.lesson_id: get_lesson_location(lesson.lesson_type, current_user.instructor_id)
                for lesson in lessons
            }
        )

    @app.route('/instructor/lesson/confirm/<int:id>', methods=['POST'])
    @login_required
    def instructor_confirm_lesson(id):
        if current_user.role != 'instructor':
            return "Доступ запрещен", 403

        lesson = Lessons.query.get_or_404(id)
        if lesson.instructor_id != current_user.instructor_id:
            return "Доступ запрещен", 403

        if lesson.status != 'pending':
            flash('Это занятие уже обработано')
            return redirect(url_for('instructor_dashboard'))

        lesson.status = 'confirmed'
        db.session.commit()
        flash('Занятие подтверждено')
        return redirect(url_for('instructor_dashboard'))

    @app.route('/instructor/lesson/complete/<int:id>', methods=['POST'])
    @login_required
    def instructor_complete_lesson(id):
        if current_user.role != 'instructor':
            return "Доступ запрещен", 403
        
        lesson = Lessons.query.get_or_404(id)
        if lesson.instructor_id != current_user.instructor_id:
            return "Доступ запрещен", 403

        if lesson.status != 'confirmed':
            flash('Сначала подтвердите занятие')
            return redirect(url_for('instructor_dashboard'))
        
        lesson.status = 'completed'
        db.session.commit()
        flash('Занятие отмечено как проведенное')
        return redirect(url_for('instructor_dashboard'))

    @app.route('/instructor/car', methods=['GET', 'POST'])
    @login_required
    def instructor_car():
        if current_user.role != 'instructor':
            return "Доступ запрещен", 403

        car = Automobiles.query.filter_by(instructor_id=current_user.instructor_id).first()

        if request.method == 'POST':
            if not car:
                car = Automobiles(instructor_id=current_user.instructor_id)
                db.session.add(car)

            car.brand = request.form['brand']
            car.model = request.form['model']
            car.plate = request.form['plate']
            car.vehicle_type = request.form['vehicle_type']

            photo_filename = save_car_photo(request.files.get('photo'))
            if photo_filename:
                car.photo_filename = photo_filename

            db.session.commit()
            flash('Автомобиль сохранен')
            return redirect(url_for('instructor_car'))

        return render_template('instructor/car.html',
            title="Мой автомобиль",
            user_name=get_user_display_name(current_user),
            role=current_user.role,
            menu_items=get_menu_items('car', 'instructor'),
            today=datetime.now().strftime("%d.%m.%Y"),
            car=car
        )

    @app.route('/instructor/lesson/cancel/<int:id>', methods=['POST'])
    @login_required
    def instructor_cancel_lesson(id):
        if current_user.role != 'instructor':
            return "Доступ запрещен", 403
        
        lesson = Lessons.query.get_or_404(id)
        if lesson.instructor_id != current_user.instructor_id:
            return "Доступ запрещен", 403

        if lesson.status == 'completed':
            flash('Проведенное занятие нельзя отменить')
            return redirect(url_for('instructor_dashboard'))
        
        lesson.status = 'cancelled'
        db.session.add(CancellationHistory(
            lesson_id=lesson.lesson_id,
            cancelled_by_user_id=current_user.id,
            reason='Инструктор отменил занятие'
        ))
        release_lesson_slot(lesson)
        db.session.commit()
        flash('Занятие отменено')
        return redirect(url_for('instructor_dashboard'))

    @app.route('/instructor/lesson/<int:id>')
    @login_required
    def instructor_mark_lesson(id):
        if current_user.role != 'instructor':
            return "Доступ запрещен", 403
        l = Lessons.query.get_or_404(id)
        if l.instructor_id != current_user.instructor_id:
            return "Доступ запрещен", 403
        l.status = 'completed'
        db.session.commit()
        flash('Занятие отмечено')
        return redirect(url_for('instructor_dashboard'))
    @app.route('/instructor/schedule')
    @login_required
    def instructor_schedule():
        if current_user.role != 'instructor':
            return "Доступ запрещен", 403
        
        slots = db.session.query(
            InstructorSchedule.schedule_id,
            InstructorSchedule.lesson_date,
            InstructorSchedule.lesson_time,
            InstructorSchedule.is_booked,
            Kursanty.fullname.label('student_name')
        ).outerjoin(Kursanty, InstructorSchedule.booked_by == Kursanty.kursant_id)\
         .filter(InstructorSchedule.instructor_id == current_user.instructor_id)\
         .order_by(InstructorSchedule.lesson_date, InstructorSchedule.lesson_time).all()
        
        min_date = (datetime.now().date() + timedelta(days=1)).strftime('%Y-%m-%d')
        
        return render_template('instructor/schedule.html',
            title="Мое расписание",
            user_name=get_user_display_name(current_user),
            role=current_user.role,
            menu_items=get_menu_items('schedule', 'instructor'),
            today=datetime.now().strftime("%d.%m.%Y"),
            slots=slots,
            min_date=min_date
        )

    @app.route('/instructor/schedule/add', methods=['POST'])
    @login_required
    def instructor_schedule_add():
        if current_user.role != 'instructor':
            return "Доступ запрещен", 403
        
        try:
            lesson_date = datetime.strptime(request.form['lesson_date'], '%Y-%m-%d').date()
            lesson_time = datetime.strptime(request.form['lesson_time'], '%H:%M').time()
            
            # Проверка на дубликат
            existing = InstructorSchedule.query.filter_by(
                instructor_id=current_user.instructor_id,
                lesson_date=lesson_date,
                lesson_time=lesson_time
            ).first()
            
            if existing:
                flash('Такой слот уже существует')
                return redirect(url_for('instructor_schedule'))
            
            slot = InstructorSchedule(
                instructor_id=current_user.instructor_id,
                lesson_date=lesson_date,
                lesson_time=lesson_time,
                is_booked=False
            )
            db.session.add(slot)
            db.session.commit()
            flash('Слот добавлен')
        except Exception as e:
            flash(f'Ошибка: {e}')
        
        return redirect(url_for('instructor_schedule'))

    @app.route('/instructor/schedule/delete/<int:id>', methods=['POST'])
    @login_required
    def instructor_schedule_delete(id):
        if current_user.role != 'instructor':
            return "Доступ запрещен", 403
        
        slot = InstructorSchedule.query.get_or_404(id)
        if slot.instructor_id != current_user.instructor_id:
            return "Доступ запрещен", 403
        
        if slot.is_booked:
            flash('Нельзя удалить забронированный слот')
            return redirect(url_for('instructor_schedule'))
        
        db.session.delete(slot)
        db.session.commit()
        flash('Слот удален')
        return redirect(url_for('instructor_schedule'))
