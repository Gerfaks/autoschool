from flask import abort, request
from flask_login import current_user

from models import Grounds, Instructors, Kursanty, LessonType


PROTECTED_PREFIX_ROLES = {
    '/admin': 'admin',
    '/instructor': 'instructor',
    '/student': 'student',
}

THEORY_LOCATION = 'Корпус 1, учебный класс'
DEFAULT_GROUND_LOCATION = 'Площадка автошколы'
NO_INSTRUCTOR_GROUND_LOCATION = 'Площадка инструктора не назначена'

ASSIGNMENT_STATUS_LABELS = {
    'not_started': 'Не начато',
    'in_progress': 'В процессе',
    'completed': 'Завершено',
}


def restrict_role_sections():
    if not current_user.is_authenticated:
        return None

    for prefix, required_role in PROTECTED_PREFIX_ROLES.items():
        if request.path == prefix or request.path.startswith(prefix + '/'):
            if current_user.role != required_role:
                abort(403)

    return None


def forbidden(_error):
    return "Доступ запрещен", 403


def get_user_display_name(user):
    if user.role == 'student' and user.kursant_id:
        student = Kursanty.query.get(user.kursant_id)
        return student.fullname if student and student.fullname else user.username
    if user.role == 'instructor' and user.instructor_id:
        instructor = Instructors.query.get(user.instructor_id)
        return instructor.fullname if instructor and instructor.fullname else user.username
    return user.username


def format_ground_location(ground):
    if not ground:
        return DEFAULT_GROUND_LOCATION

    details = []
    if ground.surface_type:
        details.append(ground.surface_type)
    if ground.area:
        details.append(f'{ground.area} м²')

    location = ground.address or DEFAULT_GROUND_LOCATION
    if details:
        return f'{location} ({", ".join(details)})'
    return location


def get_practice_location(instructor_id=None):
    if instructor_id:
        ground = Grounds.query.filter_by(instructor_id=instructor_id).order_by(Grounds.ground_id).first()
        return format_ground_location(ground) if ground else NO_INSTRUCTOR_GROUND_LOCATION

    grounds = Grounds.query.order_by(Grounds.ground_id).all()
    if not grounds:
        return DEFAULT_GROUND_LOCATION

    unique_grounds = []
    seen = set()
    for ground in grounds:
        key = (ground.address, ground.surface_type, ground.area)
        if key not in seen:
            unique_grounds.append(ground)
            seen.add(key)

    if len(unique_grounds) == 1:
        return format_ground_location(unique_grounds[0])

    return '; '.join(format_ground_location(ground) for ground in unique_grounds)


def get_lesson_location(lesson_type, instructor_id=None):
    if not isinstance(lesson_type, str):
        lesson_type = lesson_type.name

    if lesson_type == 'Теория':
        return THEORY_LOCATION
    if lesson_type in ('Вождение', 'Площадка'):
        return get_practice_location(instructor_id)
    return 'Место уточнит администратор'


def get_lesson_locations(instructor_id=None):
    practice_location = get_practice_location(instructor_id)
    return {
        'Теория': THEORY_LOCATION,
        'Вождение': practice_location,
        'Площадка': practice_location,
    }


def get_lesson_type_id(name):
    lesson_type = LessonType.query.filter_by(name=name).first()
    if not lesson_type:
        lesson_type = LessonType(name=name)
        from extensions import db
        db.session.add(lesson_type)
        db.session.flush()
    return lesson_type.lesson_type_id


def get_instructors_lesson_locations(instructors):
    return {
        str(instructor.instructor_id): get_lesson_locations(instructor.instructor_id)
        for instructor in instructors
    }


def get_menu_items(active_page, role):
    if role == 'admin':
        return [
            {'name': 'Главная', 'url': '/admin', 'icon': 'fas fa-tachometer-alt', 'active': active_page == 'dashboard'},
            {'name': 'Курсанты', 'url': '/admin/students', 'icon': 'fas fa-users', 'active': active_page == 'students'},
            {'name': 'Инструкторы', 'url': '/admin/instructors', 'icon': 'fas fa-chalkboard-user', 'active': active_page == 'instructors'},
            {'name': 'Автомобили', 'url': '/admin/cars', 'icon': 'fas fa-car', 'active': active_page == 'cars'},
            {'name': 'Площадки', 'url': '/admin/grounds', 'icon': 'fas fa-map-marker-alt', 'active': active_page == 'grounds'},
            {'name': 'Тарифы', 'url': '/admin/tariffs', 'icon': 'fas fa-tags', 'active': active_page == 'tariffs'},
            {'name': 'Занятия', 'url': '/admin/lessons', 'icon': 'fas fa-calendar', 'active': active_page == 'lessons'},
            {'name': 'Курсы', 'url': '/admin/courses', 'icon': 'fas fa-book-open', 'active': active_page == 'courses'},
            {'name': 'Задачи', 'url': '/todo', 'icon': 'fas fa-list-check', 'active': active_page == 'todo'},
            {'name': 'Платежи', 'url': '/admin/payments', 'icon': 'fas fa-ruble-sign', 'active': active_page == 'payments'},
            {'name': 'Отмены', 'url': '/admin/cancellations', 'icon': 'fas fa-ban', 'active': active_page == 'cancellations'},
            {'name': 'Заявки', 'url': '/admin/requests', 'icon': 'fas fa-clipboard-list', 'active': active_page == 'requests'},
        ]
    if role == 'instructor':
        return [
            {'name': 'Мои занятия', 'url': '/instructor', 'icon': 'fas fa-calendar', 'active': active_page == 'dashboard'},
            {'name': 'Мое расписание', 'url': '/instructor/schedule', 'icon': 'fas fa-clock', 'active': active_page == 'schedule'},
            {'name': 'Мой автомобиль', 'url': '/instructor/car', 'icon': 'fas fa-car', 'active': active_page == 'car'},
            {'name': 'Задачи', 'url': '/todo', 'icon': 'fas fa-list-check', 'active': active_page == 'todo'},
        ]
    return [
        {'name': 'Мои занятия', 'url': '/student', 'icon': 'fas fa-calendar', 'active': active_page == 'dashboard'},
        {'name': 'Записаться', 'url': '/student/booking', 'icon': 'fas fa-calendar-plus', 'active': active_page == 'booking'},
        {'name': 'Мои курсы', 'url': '/student/courses', 'icon': 'fas fa-book-open', 'active': active_page == 'courses'},
        {'name': 'Задачи', 'url': '/todo', 'icon': 'fas fa-list-check', 'active': active_page == 'todo'},
    ]
