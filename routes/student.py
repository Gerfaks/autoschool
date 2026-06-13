from datetime import datetime, timedelta

from flask import flash, jsonify, redirect, render_template, request, send_file, url_for
from flask_login import current_user, login_required
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError

from billing import calculate_lessons_total
from extensions import db
from models import (
    Automobiles,
    CancellationHistory,
    InstructorSchedule,
    Instructors,
    Lessons,
    LessonType,
    Payments,
    StudentAssignmentProgress,
    StudentCourse,
    TrainingAssignment,
    TrainingCourse,
)
from reports import build_docx_report, build_xlsx_report
from utils import (
    ASSIGNMENT_STATUS_LABELS,
    get_instructors_lesson_locations,
    get_lesson_location,
    get_lesson_locations,
    get_lesson_type_id,
    get_menu_items,
    get_user_display_name,
)


REPORT_MIME_TYPES = {
    'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
}


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

    def ensure_student_course_progress(enrollments):
        created = False
        for enrollment in enrollments:
            assignments = TrainingAssignment.query.filter_by(course_id=enrollment.course_id).all()
            for assignment in assignments:
                progress = StudentAssignmentProgress.query.filter_by(
                    assignment_id=assignment.assignment_id,
                    kursant_id=enrollment.kursant_id,
                ).first()
                if not progress:
                    db.session.add(StudentAssignmentProgress(
                        assignment_id=assignment.assignment_id,
                        kursant_id=enrollment.kursant_id,
                        status='not_started',
                    ))
                    created = True

        if created:
            db.session.commit()

    def get_deadline_badge(assignment, status):
        if status == 'completed':
            return {
                'class': 'deadline-done',
                'icon': 'fas fa-check',
                'label': 'Выполнено',
            }

        if not assignment.deadline:
            return {
                'class': 'deadline-none',
                'icon': 'fas fa-calendar-minus',
                'label': 'Без дедлайна',
            }

        today = datetime.now().date()
        days_left = (assignment.deadline - today).days
        if days_left < 0:
            return {
                'class': 'deadline-overdue',
                'icon': 'fas fa-triangle-exclamation',
                'label': f'Срок истек на {abs(days_left)} дн.',
            }
        if days_left <= 3:
            return {
                'class': 'deadline-soon',
                'icon': 'fas fa-hourglass-half',
                'label': 'Скоро',
            }

        return {
            'class': 'deadline-planned',
            'icon': 'fas fa-calendar-check',
            'label': f'Через {days_left} дн.',
        }

    def get_student_course_groups(status_filter, deadline_sort):
        enrollments = StudentCourse.query.filter_by(kursant_id=current_user.kursant_id)\
            .join(TrainingCourse, StudentCourse.course_id == TrainingCourse.course_id)\
            .order_by(TrainingCourse.title).all()
        ensure_student_course_progress(enrollments)

        groups = {
            enrollment.course_id: {
                'course': enrollment.course,
                'assignments': [],
            }
            for enrollment in enrollments
        }
        if not groups:
            return []

        query = db.session.query(
            StudentAssignmentProgress,
            TrainingAssignment,
        ).join(
            TrainingAssignment,
            StudentAssignmentProgress.assignment_id == TrainingAssignment.assignment_id,
        ).filter(
            StudentAssignmentProgress.kursant_id == current_user.kursant_id,
            TrainingAssignment.course_id.in_(list(groups.keys())),
        )

        if status_filter:
            query = query.filter(StudentAssignmentProgress.status == status_filter)

        if deadline_sort == 'asc':
            query = query.order_by(
                TrainingAssignment.course_id,
                TrainingAssignment.deadline.is_(None),
                TrainingAssignment.deadline.asc(),
                TrainingAssignment.title,
            )
        elif deadline_sort == 'desc':
            query = query.order_by(
                TrainingAssignment.course_id,
                TrainingAssignment.deadline.is_(None),
                TrainingAssignment.deadline.desc(),
                TrainingAssignment.title,
            )
        else:
            query = query.order_by(
                TrainingAssignment.course_id,
                TrainingAssignment.created_at,
                TrainingAssignment.title,
            )

        for progress, assignment in query.all():
            groups[assignment.course_id]['assignments'].append({
                'progress': progress,
                'assignment': assignment,
                'deadline_badge': get_deadline_badge(assignment, progress.status),
            })

        return list(groups.values())

    def get_student_assignment_report_rows(status_filter, deadline_sort):
        rows = []
        for group in get_student_course_groups(status_filter, deadline_sort):
            for item in group['assignments']:
                rows.append([
                    group['course'].title,
                    item['assignment'].title,
                    item['assignment'].deadline,
                    ASSIGNMENT_STATUS_LABELS.get(item['progress'].status, item['progress'].status),
                    item['assignment'].description,
                ])
        return rows

    def get_course_filter_params():
        status_filter = request.args.get('status', '').strip()
        if status_filter not in ASSIGNMENT_STATUS_LABELS:
            status_filter = ''

        deadline_sort = request.args.get('deadline_sort', 'none').strip()
        if deadline_sort not in {'none', 'asc', 'desc'}:
            deadline_sort = 'none'

        return status_filter, deadline_sort

    def send_report(stream, filename, file_format):
        return send_file(
            stream,
            as_attachment=True,
            download_name=filename,
            mimetype=REPORT_MIME_TYPES[file_format],
        )

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

    @app.route('/student/courses')
    @login_required
    def student_courses():
        if current_user.role != 'student':
            return "Доступ запрещен", 403

        status_filter, deadline_sort = get_course_filter_params()

        return render_template('student/courses.html',
            title="Мои курсы",
            user_name=get_user_display_name(current_user),
            role=current_user.role,
            menu_items=get_menu_items('courses', 'student'),
            today=datetime.now().strftime("%d.%m.%Y"),
            course_groups=get_student_course_groups(status_filter, deadline_sort),
            status_labels=ASSIGNMENT_STATUS_LABELS,
            filters={
                'status': status_filter,
                'deadline_sort': deadline_sort,
            }
        )

    @app.route('/student/courses/report/<file_format>')
    @login_required
    def student_courses_report(file_format):
        if current_user.role != 'student':
            return "Доступ запрещен", 403
        if file_format not in REPORT_MIME_TYPES:
            return "Формат отчета не поддерживается", 404

        status_filter, deadline_sort = get_course_filter_params()
        headers = ['Курс', 'Задание', 'Дедлайн', 'Статус', 'Описание']
        rows = get_student_assignment_report_rows(status_filter, deadline_sort)
        student_name = get_user_display_name(current_user)
        title = f'Задания курсанта: {student_name}'
        subtitle = 'Отчет по назначенным учебным курсам'
        filename = f'my_assignments_{datetime.now().strftime("%Y%m%d_%H%M")}.{file_format}'

        if file_format == 'docx':
            stream = build_docx_report(title, subtitle, headers, rows)
        else:
            stream = build_xlsx_report(title, headers, rows, 'Мои задания')

        return send_report(stream, filename, file_format)

    @app.route('/student/assignment/<int:progress_id>/status', methods=['POST'])
    @login_required
    def student_update_assignment_status(progress_id):
        if current_user.role != 'student':
            return "Доступ запрещен", 403

        progress = StudentAssignmentProgress.query.get_or_404(progress_id)
        if progress.kursant_id != current_user.kursant_id:
            return "Доступ запрещен", 403

        status = request.form.get('status', '').strip()
        redirect_params = {
            'deadline_sort': request.form.get('current_deadline_sort', 'none').strip() or 'none',
        }
        current_status_filter = request.form.get('current_status_filter', '').strip()
        if current_status_filter:
            redirect_params['status'] = current_status_filter

        if status not in ASSIGNMENT_STATUS_LABELS:
            flash('Выберите корректный статус задания')
            return redirect(url_for('student_courses', **redirect_params))

        try:
            progress.status = status
            progress.updated_at = datetime.utcnow()
            db.session.commit()
            flash('Статус задания обновлен')
        except SQLAlchemyError:
            db.session.rollback()
            flash('Не удалось обновить статус задания. Попробуйте еще раз.')

        return redirect(url_for('student_courses', **redirect_params))

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
                    flash('Извините, это время уже занято')
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
                flash('Вы успешно записались на занятие')
                return redirect(url_for('student_dashboard'))
                
            except Exception as e:
                db.session.rollback()
                flash(f'Ошибка: {e}')
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
