import os
import re
import secrets
from calendar import monthrange
from datetime import datetime

from flask import current_app, flash, redirect, render_template, request, send_file, url_for
from flask_login import current_user, login_required
from sqlalchemy import and_, func, or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import aliased
from werkzeug.security import generate_password_hash
from werkzeug.utils import secure_filename

from billing import calculate_lessons_total
from extensions import db
from models import (
    Automobiles,
    CancellationHistory,
    Grounds,
    Instructors,
    Kursanty,
    LessonTariff,
    LessonType,
    Lessons,
    Payments,
    RegistrationRequest,
    StudentAssignmentProgress,
    StudentCourse,
    TrainingAssignment,
    TrainingCourse,
    User,
)
from reports import build_docx_report, build_xlsx_report
from utils import ASSIGNMENT_STATUS_LABELS, get_lesson_type_id, get_menu_items, get_user_display_name


REPORT_MIME_TYPES = {
    'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
}

LESSON_STATUS_COMMENT_RE = re.compile(
    r'\s*[\u2705\u274c]\s*(?:Подтверждено|Проведено|Отменено(?: курсантом)?)'
    r'\s+\d{2}\.\d{2}\.\d{4}\s+\d{2}:\d{2}'
)


def clean_lesson_comment(comment):
    if not comment:
        return ''
    return LESSON_STATUS_COMMENT_RE.sub('', comment).strip()


def get_student_debt_data(student):
    paid = db.session.query(func.sum(Payments.amount)).filter_by(kursant_id=student.kursant_id).scalar() or 0
    completed_lessons = Lessons.query.filter_by(
        kursant_id=student.kursant_id,
        status='completed'
    ).all()
    expected = calculate_lessons_total(completed_lessons)
    return {
        'lessons_count': len(completed_lessons),
        'expected': expected,
        'paid': paid,
        'debt': expected - paid,
    }


def get_request_user(registration_request):
    if registration_request.login_username:
        user = User.query.filter_by(username=registration_request.login_username).first()
        if user:
            return user

    if registration_request.role == 'student':
        student = Kursanty.query.filter_by(phone=registration_request.phone).first()
        if not student and registration_request.email:
            student = Kursanty.query.filter_by(email=registration_request.email).first()
        if student:
            return User.query.filter_by(kursant_id=student.kursant_id).first()

    if registration_request.role == 'instructor':
        instructor = Instructors.query.filter_by(phone=registration_request.phone).first()
        if not instructor:
            instructor = Instructors.query.filter_by(fullname=registration_request.fullname).first()
        if instructor:
            return User.query.filter_by(instructor_id=instructor.instructor_id).first()

    return None


def get_ground_form_data(current_ground_id=None):
    instructor_id_text = request.form.get('instructor_id', '').strip()
    address = request.form.get('address', '').strip()
    surface_type = request.form.get('surface_type', '').strip()
    area_text = request.form.get('area', '').strip()
    instructor_id = None
    area = None
    errors = []

    if instructor_id_text:
        try:
            instructor_id = int(instructor_id_text)
        except ValueError:
            errors.append('Выберите инструктора из списка')
        else:
            if not Instructors.query.get(instructor_id):
                errors.append('Выбранный инструктор не найден')
            else:
                existing_ground = Grounds.query.filter_by(instructor_id=instructor_id).first()
                if existing_ground and existing_ground.ground_id != current_ground_id:
                    errors.append('У этого инструктора уже есть назначенная площадка')

    if not address:
        errors.append('Укажите адрес площадки')

    if area_text:
        try:
            area = int(area_text)
            if area <= 0:
                errors.append('Площадь должна быть больше нуля')
        except ValueError:
            errors.append('Площадь должна быть целым числом')

    return {
        'instructor_id': instructor_id,
        'address': address,
        'surface_type': surface_type,
        'area': area,
        'area_text': area_text,
    }, errors


def get_course_form_data():
    title = request.form.get('title', '').strip()
    description = request.form.get('description', '').strip()
    category = request.form.get('category', '').strip()
    errors = []

    if not title:
        errors.append('Укажите название курса')

    return {
        'title': title,
        'description': description or None,
        'category': category or None,
    }, errors


def get_assignment_form_data():
    title = request.form.get('title', '').strip()
    description = request.form.get('description', '').strip()
    deadline_text = request.form.get('deadline', '').strip()
    deadline = None
    errors = []

    if not title:
        errors.append('Укажите название задания')

    if deadline_text:
        try:
            deadline = datetime.strptime(deadline_text, '%Y-%m-%d').date()
        except ValueError:
            errors.append('Укажите дедлайн в формате даты')

    return {
        'title': title,
        'description': description or None,
        'deadline': deadline,
        'deadline_text': deadline_text,
    }, errors


def ensure_assignment_progress(assignment_id, kursant_id):
    progress = StudentAssignmentProgress.query.filter_by(
        assignment_id=assignment_id,
        kursant_id=kursant_id,
    ).first()
    if not progress:
        db.session.add(StudentAssignmentProgress(
            assignment_id=assignment_id,
            kursant_id=kursant_id,
            status='not_started',
        ))


def ensure_course_progress_for_student(course_id, kursant_id):
    assignments = TrainingAssignment.query.filter_by(course_id=course_id).all()
    for assignment in assignments:
        ensure_assignment_progress(assignment.assignment_id, kursant_id)


def ensure_assignment_progress_for_enrolled_students(assignment):
    enrollments = StudentCourse.query.filter_by(course_id=assignment.course_id).all()
    for enrollment in enrollments:
        ensure_assignment_progress(assignment.assignment_id, enrollment.kursant_id)


def send_report(stream, filename, file_format):
    return send_file(
        stream,
        as_attachment=True,
        download_name=filename,
        mimetype=REPORT_MIME_TYPES[file_format],
    )


def get_overdue_assignment_rows():
    today = datetime.now().date()
    overdue_rows = db.session.query(
        Kursanty.fullname.label('student_name'),
        Kursanty.phone,
        TrainingCourse.title.label('course_title'),
        TrainingAssignment.title.label('assignment_title'),
        TrainingAssignment.deadline,
        StudentAssignmentProgress.status,
    ).join(
        StudentCourse,
        StudentCourse.kursant_id == Kursanty.kursant_id,
    ).join(
        TrainingCourse,
        TrainingCourse.course_id == StudentCourse.course_id,
    ).join(
        TrainingAssignment,
        TrainingAssignment.course_id == TrainingCourse.course_id,
    ).outerjoin(
        StudentAssignmentProgress,
        and_(
            StudentAssignmentProgress.assignment_id == TrainingAssignment.assignment_id,
            StudentAssignmentProgress.kursant_id == Kursanty.kursant_id,
        ),
    ).filter(
        TrainingAssignment.deadline.isnot(None),
        TrainingAssignment.deadline < today,
        or_(
            StudentAssignmentProgress.status.is_(None),
            StudentAssignmentProgress.status != 'completed',
        ),
    ).order_by(
        TrainingAssignment.deadline,
        Kursanty.fullname,
        TrainingCourse.title,
        TrainingAssignment.title,
    ).all()

    return [
        [
            row.student_name,
            row.phone,
            row.course_title,
            row.assignment_title,
            row.deadline,
            ASSIGNMENT_STATUS_LABELS.get(row.status or 'not_started', 'Не начато'),
            (today - row.deadline).days,
        ]
        for row in overdue_rows
    ]

def save_car_photo(file):
    if not file or not file.filename:
        return None

    os.makedirs('uploads', exist_ok=True)
    filename = secure_filename(file.filename)
    unique_filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{filename}"
    file.save(os.path.join('uploads', unique_filename))
    return unique_filename
