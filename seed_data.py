from datetime import datetime, time, timedelta

from werkzeug.security import generate_password_hash

from app import app
from extensions import db
from migrate_schema import migrate_schema
from models import (
    Automobiles,
    CancellationHistory,
    Grounds,
    InstructorSchedule,
    Instructors,
    Kursanty,
    LessonTariff,
    Lessons,
    LessonType,
    Payments,
    RegistrationRequest,
    StudentAssignmentProgress,
    StudentCourse,
    TodoCategory,
    TodoItem,
    TrainingAssignment,
    TrainingCourse,
    User,
)


STUDENT_PASSWORD = 'student123'
INSTRUCTOR_USERNAME = 'sergey.petrov'
INSTRUCTOR_PASSWORD = 'instructor123'
ADMIN_USERNAME = 'admin'
ADMIN_PASSWORD = 'admin123'


def get_or_create_admin():
    admin = User.query.filter_by(username=ADMIN_USERNAME).first()
    if not admin:
        admin = User(
            username=ADMIN_USERNAME,
        )
        db.session.add(admin)
    admin.password_hash = generate_password_hash(ADMIN_PASSWORD, method='pbkdf2:sha256')
    admin.role = 'admin'
    return admin


def get_or_create_lesson_type(name):
    lesson_type = LessonType.query.filter_by(name=name).first()
    if not lesson_type:
        lesson_type = LessonType(name=name)
        db.session.add(lesson_type)
        db.session.flush()
    return lesson_type


def set_tariff(lesson_type_name, price):
    lesson_type = get_or_create_lesson_type(lesson_type_name)
    tariff = LessonTariff.query.filter_by(lesson_type_id=lesson_type.lesson_type_id).first()
    if not tariff:
        tariff = LessonTariff(lesson_type_id=lesson_type.lesson_type_id)
        db.session.add(tariff)
    tariff.price = price
    return tariff


def get_or_create_student(username, fullname, phone, email, category_type, legacy_usernames=None, legacy_emails=None):
    legacy_usernames = legacy_usernames or []
    legacy_emails = legacy_emails or []
    user = User.query.filter(User.username.in_([username, *legacy_usernames])).first()
    student = None
    if user and user.kursant_id:
        student = db.session.get(Kursanty, user.kursant_id)

    if not student:
        student = Kursanty.query.filter(Kursanty.email.in_([email, *legacy_emails])).first()
    if not student:
        student = Kursanty(
            fullname=fullname,
            phone=phone,
            email=email,
            category_type=category_type,
        )
        db.session.add(student)
        db.session.flush()
    else:
        student.fullname = fullname
        student.phone = phone
        student.email = email
        student.category_type = category_type

    if not user:
        user = User(
            username=username,
            password_hash=generate_password_hash(STUDENT_PASSWORD, method='pbkdf2:sha256'),
            role='student',
            kursant_id=student.kursant_id,
        )
        db.session.add(user)
    else:
        user.username = username
        user.role = 'student'
        user.kursant_id = student.kursant_id
        user.password_hash = generate_password_hash(STUDENT_PASSWORD, method='pbkdf2:sha256')

    return student


def get_or_create_instructor(
    fullname='Сергей Петров',
    phone='+7 900 333-44-55',
    experience=8,
    license_category='B',
    username=INSTRUCTOR_USERNAME,
    password=INSTRUCTOR_PASSWORD,
):
    instructor = Instructors.query.filter_by(fullname=fullname).first()
    user = User.query.filter_by(username=username).first() if username else None

    if user and user.instructor_id:
        instructor = db.session.get(Instructors, user.instructor_id)

    if not instructor:
        instructor = Instructors(
            fullname=fullname,
            phone=phone,
            experience=experience,
            license_category=license_category,
        )
        db.session.add(instructor)
        db.session.flush()
    else:
        instructor.fullname = fullname
        instructor.phone = phone
        instructor.experience = experience
        instructor.license_category = license_category

    if username and not user:
        user = User(username=username)
        db.session.add(user)

    if user:
        user.password_hash = generate_password_hash(password, method='pbkdf2:sha256')
        user.role = 'instructor'
        user.instructor_id = instructor.instructor_id
        user.kursant_id = None
    return instructor


def get_or_create_car(plate, brand, model, vehicle_type, instructor=None):
    car = Automobiles.query.filter_by(plate=plate).first()
    if not car:
        car = Automobiles(plate=plate)
        db.session.add(car)
    car.brand = brand
    car.model = model
    car.vehicle_type = vehicle_type
    car.instructor_id = instructor.instructor_id if instructor else None
    return car


def get_or_create_ground(instructor, address, surface_type, area):
    ground = Grounds.query.filter_by(instructor_id=instructor.instructor_id).first()
    if not ground:
        ground = Grounds(instructor_id=instructor.instructor_id)
        db.session.add(ground)
    ground.address = address
    ground.surface_type = surface_type
    ground.area = area
    return ground


def get_or_create_schedule_slot(instructor, lesson_date, lesson_time, is_booked=False, student=None):
    slot = InstructorSchedule.query.filter_by(
        instructor_id=instructor.instructor_id,
        lesson_date=lesson_date,
        lesson_time=lesson_time,
    ).first()
    if not slot:
        slot = InstructorSchedule(
            instructor_id=instructor.instructor_id,
            lesson_date=lesson_date,
            lesson_time=lesson_time,
        )
        db.session.add(slot)

    slot.is_booked = is_booked
    slot.booked_by = student.kursant_id if student and is_booked else None
    return slot


def get_or_create_lesson(student, instructor, car, lesson_type_name, lesson_date, lesson_time, status, comments):
    lesson_type = get_or_create_lesson_type(lesson_type_name)
    lesson = Lessons.query.filter_by(
        kursant_id=student.kursant_id,
        instructor_id=instructor.instructor_id,
        lesson_date=lesson_date,
        lesson_time=lesson_time,
        lesson_type_id=lesson_type.lesson_type_id,
    ).first()
    if not lesson:
        lesson = Lessons(
            kursant_id=student.kursant_id,
            instructor_id=instructor.instructor_id,
            lesson_date=lesson_date,
            lesson_time=lesson_time,
            lesson_type_id=lesson_type.lesson_type_id,
        )
        db.session.add(lesson)

    lesson.auto_id = car.auto_id if car else None
    lesson.status = status
    lesson.comments = comments
    return lesson


def get_or_create_payment(student, amount, payment_date, payment_method, comment, admin):
    payment = Payments.query.filter_by(
        kursant_id=student.kursant_id,
        payment_date=payment_date,
        amount=amount,
        comment=comment,
    ).first()
    if not payment:
        payment = Payments(
            kursant_id=student.kursant_id,
            amount=amount,
            payment_date=payment_date,
            comment=comment,
        )
        db.session.add(payment)

    payment.payment_method = payment_method
    payment.created_by_user_id = admin.id
    return payment


def get_or_create_cancellation(lesson, cancelled_by_user, reason, cancelled_at):
    cancellation = CancellationHistory.query.filter_by(
        lesson_id=lesson.lesson_id,
        reason=reason,
    ).first()
    if not cancellation:
        cancellation = CancellationHistory(
            lesson_id=lesson.lesson_id,
            reason=reason,
        )
        db.session.add(cancellation)

    cancellation.cancelled_by_user_id = cancelled_by_user.id if cancelled_by_user else None
    cancellation.cancelled_at = cancelled_at
    return cancellation


def get_or_create_registration_request(phone, fullname, email, role, status, **kwargs):
    request = RegistrationRequest.query.filter_by(phone=phone).first()
    if not request:
        request = RegistrationRequest(phone=phone, fullname=fullname, role=role)
        db.session.add(request)

    request.fullname = fullname
    request.email = email
    request.role = role
    request.status = status
    request.category_type = kwargs.get('category_type')
    request.experience = kwargs.get('experience')
    request.license_category = kwargs.get('license_category')
    request.passport_number = kwargs.get('passport_number')
    request.driver_license_number = kwargs.get('driver_license_number')
    request.created_at = kwargs.get('created_at', datetime.utcnow())
    request.reviewed_by_user_id = kwargs.get('reviewed_by_user_id')
    request.reviewed_at = kwargs.get('reviewed_at')
    request.comment = kwargs.get('comment')
    return request


def get_or_create_todo_category(user, name, color):
    category = TodoCategory.query.filter_by(user_id=user.id, name=name).first()
    if not category:
        category = TodoCategory(user_id=user.id, name=name)
        db.session.add(category)
        db.session.flush()
    category.color = color
    return category


def get_or_create_todo_item(user, title, category, description, due_date, priority, is_complete=False):
    item = TodoItem.query.filter_by(user_id=user.id, title=title).first()
    if not item:
        item = TodoItem(user_id=user.id, title=title)
        db.session.add(item)

    item.category_id = category.category_id if category else None
    item.description = description
    item.due_date = due_date
    item.priority = priority
    item.is_complete = is_complete
    item.updated_at = datetime.utcnow()
    return item


def get_or_create_course(title, description, category, legacy_titles=None):
    legacy_titles = legacy_titles or []
    course = TrainingCourse.query.filter(TrainingCourse.title.in_([title, *legacy_titles])).first()
    if not course:
        course = TrainingCourse(title=title)
        db.session.add(course)
        db.session.flush()

    course.title = title
    course.description = description
    course.category = category
    return course


def get_or_create_assignment(course, title, description, deadline):
    assignment = TrainingAssignment.query.filter_by(
        course_id=course.course_id,
        title=title,
    ).first()
    if not assignment:
        assignment = TrainingAssignment(
            course_id=course.course_id,
            title=title,
        )
        db.session.add(assignment)
        db.session.flush()

    assignment.description = description
    assignment.deadline = deadline
    return assignment


def assign_course(course, student):
    enrollment = StudentCourse.query.filter_by(
        course_id=course.course_id,
        kursant_id=student.kursant_id,
    ).first()
    if not enrollment:
        enrollment = StudentCourse(
            course_id=course.course_id,
            kursant_id=student.kursant_id,
        )
        db.session.add(enrollment)
    return enrollment


def set_progress(assignment, student, status):
    progress = StudentAssignmentProgress.query.filter_by(
        assignment_id=assignment.assignment_id,
        kursant_id=student.kursant_id,
    ).first()
    if not progress:
        progress = StudentAssignmentProgress(
            assignment_id=assignment.assignment_id,
            kursant_id=student.kursant_id,
        )
        db.session.add(progress)

    progress.status = status
    progress.updated_at = datetime.utcnow()
    return progress


def seed_training_data():
    today = datetime.now().date()
    now = datetime.now()
    admin = get_or_create_admin()
    db.session.flush()

    set_tariff('Теория', 300)
    set_tariff('Вождение', 900)
    set_tariff('Площадка', 700)

    sergey = get_or_create_instructor()
    olga = get_or_create_instructor(
        fullname='Ольга Иванова',
        phone='+7 900 444-55-66',
        experience=6,
        license_category='B, C',
        username=None,
        password=None,
    )

    anna = get_or_create_student(
        username='anna.smirnova',
        fullname='Анна Смирнова',
        phone='+7 900 111-22-33',
        email='anna.smirnova@example.com',
        category_type='B',
        legacy_usernames=['demo_anna'],
        legacy_emails=['anna.demo@example.com'],
    )
    ivan = get_or_create_student(
        username='ivan.petrov',
        fullname='Иван Петров',
        phone='+7 900 222-33-44',
        email='ivan.petrov@example.com',
        category_type='B',
        legacy_usernames=['demo_ivan'],
        legacy_emails=['ivan.demo@example.com'],
    )
    maria = get_or_create_student(
        username='maria.sokolova',
        fullname='Мария Соколова',
        phone='+7 900 555-66-77',
        email='maria.sokolova@example.com',
        category_type='B',
    )
    alexey = get_or_create_student(
        username='alexey.orlov',
        fullname='Алексей Орлов',
        phone='+7 900 777-88-99',
        email='alexey.orlov@example.com',
        category_type='C',
    )

    car_sergey = get_or_create_car('А123ВС196', 'Hyundai', 'Solaris', 'Легковой', sergey)
    car_olga = get_or_create_car('В456ОР196', 'Kia', 'Rio', 'Легковой', olga)
    school_car = get_or_create_car('С789КМ196', 'Renault', 'Logan', 'Легковой', None)
    db.session.flush()

    get_or_create_ground(
        sergey,
        'ул. Учебная, 12, автодром автошколы',
        'асфальт',
        2400,
    )
    get_or_create_ground(
        olga,
        'ул. Маневровая, 4, площадка N2',
        'асфальт и разметка',
        1800,
    )

    get_or_create_schedule_slot(sergey, today + timedelta(days=1), time(10, 0), True, anna)
    get_or_create_schedule_slot(sergey, today + timedelta(days=1), time(12, 0), False)
    get_or_create_schedule_slot(sergey, today + timedelta(days=2), time(15, 30), True, ivan)
    get_or_create_schedule_slot(olga, today + timedelta(days=1), time(9, 30), False)
    get_or_create_schedule_slot(olga, today + timedelta(days=3), time(11, 0), True, maria)

    theory = get_or_create_course(
        title='Теория ПДД',
        description='Курс для проверки статусов, дедлайнов, фильтрации и отчетов лабораторной работы.',
        category='B',
        legacy_titles=['Демо: теория ПДД'],
    )
    practice = get_or_create_course(
        title='Подготовка к вождению',
        description='Дополнительный курс с будущими заданиями для проверки сортировки по дедлайнам.',
        category='B',
        legacy_titles=['Демо: подготовка к вождению'],
    )

    signs = get_or_create_assignment(
        theory,
        'Дорожные знаки',
        'Повторить предупреждающие, запрещающие и предписывающие знаки.',
        today - timedelta(days=3),
    )
    intersections = get_or_create_assignment(
        theory,
        'Проезд перекрестков',
        'Разобрать приоритеты, сигналы светофора и нерегулируемые перекрестки.',
        today + timedelta(days=2),
    )
    first_aid = get_or_create_assignment(
        theory,
        'Первая помощь',
        'Изучить базовые действия при ДТП и порядок вызова экстренных служб.',
        today + timedelta(days=8),
    )
    parking = get_or_create_assignment(
        practice,
        'Параллельная парковка',
        'Подготовить вопросы инструктору и посмотреть схему маневра.',
        today + timedelta(days=5),
    )

    for student in (anna, ivan):
        assign_course(theory, student)
        assign_course(practice, student)
    assign_course(theory, maria)

    set_progress(signs, anna, 'completed')
    set_progress(intersections, anna, 'in_progress')
    set_progress(first_aid, anna, 'not_started')
    set_progress(parking, anna, 'not_started')

    set_progress(signs, ivan, 'not_started')
    set_progress(intersections, ivan, 'not_started')
    set_progress(first_aid, ivan, 'in_progress')
    set_progress(parking, ivan, 'not_started')

    set_progress(signs, maria, 'in_progress')
    set_progress(intersections, maria, 'not_started')
    set_progress(first_aid, maria, 'not_started')

    completed_lesson = get_or_create_lesson(
        anna,
        sergey,
        car_sergey,
        'Вождение',
        today - timedelta(days=5),
        time(10, 0),
        'completed',
        'Городской маршрут, отработка перестроений',
    )
    confirmed_lesson = get_or_create_lesson(
        anna,
        sergey,
        car_sergey,
        'Площадка',
        today + timedelta(days=1),
        time(10, 0),
        'confirmed',
        'Эстакада и параллельная парковка',
    )
    pending_lesson = get_or_create_lesson(
        ivan,
        sergey,
        car_sergey,
        'Вождение',
        today + timedelta(days=2),
        time(15, 30),
        'pending',
        'Первое занятие в городе',
    )
    get_or_create_lesson(
        maria,
        olga,
        car_olga,
        'Теория',
        today + timedelta(days=3),
        time(11, 0),
        'confirmed',
        'Разбор экзаменационных билетов',
    )
    get_or_create_lesson(
        alexey,
        olga,
        school_car,
        'Площадка',
        today - timedelta(days=2),
        time(14, 0),
        'completed',
        'Змейка и разворот в ограниченном пространстве',
    )
    cancelled_lesson = get_or_create_lesson(
        ivan,
        olga,
        car_olga,
        'Вождение',
        today - timedelta(days=1),
        time(17, 0),
        'cancelled',
        'Занятие отменено по заявке курсанта',
    )
    db.session.flush()

    student_user = User.query.filter_by(username='ivan.petrov').first()
    get_or_create_cancellation(
        cancelled_lesson,
        student_user,
        'Курсант отменил запись',
        now - timedelta(days=1, hours=2),
    )

    get_or_create_payment(
        anna,
        3000,
        today - timedelta(days=10),
        'Карта',
        'Первый платеж за обучение',
        admin,
    )
    get_or_create_payment(
        anna,
        1500,
        today - timedelta(days=3),
        'Перевод',
        'Оплата практического занятия',
        admin,
    )
    get_or_create_payment(
        ivan,
        1200,
        today - timedelta(days=4),
        'Наличные',
        'Частичная оплата занятий',
        admin,
    )
    get_or_create_payment(
        maria,
        2000,
        today - timedelta(days=2),
        'Карта',
        'Оплата теоретического блока',
        admin,
    )

    get_or_create_registration_request(
        '+7 900 888-11-22',
        'Никита Волков',
        'nikita.volkov@example.com',
        'student',
        'pending',
        category_type='B',
        passport_number='6501 123456',
        driver_license_number='',
        created_at=now - timedelta(hours=5),
    )
    get_or_create_registration_request(
        '+7 900 888-33-44',
        'Елена Морозова',
        'elena.morozova@example.com',
        'instructor',
        'pending',
        experience=5,
        license_category='B',
        passport_number='6502 654321',
        driver_license_number='66 12 345678',
        created_at=now - timedelta(days=1, hours=3),
    )
    get_or_create_registration_request(
        '+7 900 888-55-66',
        'Павел Новиков',
        'pavel.novikov@example.com',
        'student',
        'rejected',
        category_type='C',
        passport_number='6503 456789',
        driver_license_number='',
        created_at=now - timedelta(days=4),
        reviewed_by_user_id=admin.id,
        reviewed_at=now - timedelta(days=3),
        comment='Не приложены документы для проверки личности.',
    )

    admin_category = get_or_create_todo_category(admin, 'Администрирование', '#b84d3f')
    admin_reports = get_or_create_todo_category(admin, 'Отчеты', '#2c6c9c')
    sergey_user = User.query.filter_by(username=INSTRUCTOR_USERNAME).first()
    anna_user = User.query.filter_by(username='anna.smirnova').first()
    ivan_user = User.query.filter_by(username='ivan.petrov').first()

    get_or_create_todo_item(
        admin,
        'Проверить новые заявки',
        admin_category,
        'Просмотреть заявки на регистрацию и принять решение.',
        today + timedelta(days=1),
        'high',
    )
    get_or_create_todo_item(
        admin,
        'Сформировать отчет по заданиям с истекшим сроком',
        admin_reports,
        'Скачать отчет по заданиям с истекшим сроком выполнения перед собранием.',
        today + timedelta(days=2),
        'normal',
    )
    get_or_create_todo_item(
        admin,
        'Обновить тарифы занятий',
        admin_category,
        'Проверить стоимость теории, вождения и площадки.',
        today - timedelta(days=1),
        'high',
    )

    if sergey_user:
        instructor_category = get_or_create_todo_category(sergey_user, 'Занятия', '#2f7d5c')
        instructor_docs = get_or_create_todo_category(sergey_user, 'Документы', '#b7791f')
        get_or_create_todo_item(
            sergey_user,
            'Подготовить автомобиль к занятию',
            instructor_category,
            'Проверить документы, чистоту салона и уровень топлива.',
            today + timedelta(days=1),
            'normal',
        )
        get_or_create_todo_item(
            sergey_user,
            'Отметить проведенные занятия',
            instructor_docs,
            'Закрыть занятия после подтверждения курсантов.',
            today,
            'high',
        )

    if anna_user:
        student_study = get_or_create_todo_category(anna_user, 'Обучение', '#b84d3f')
        student_docs = get_or_create_todo_category(anna_user, 'Документы', '#2c6c9c')
        get_or_create_todo_item(
            anna_user,
            'Повторить дорожные знаки',
            student_study,
            'Подготовиться к занятию по теории.',
            today + timedelta(days=2),
            'normal',
            True,
        )
        get_or_create_todo_item(
            anna_user,
            'Принести медицинскую справку',
            student_docs,
            'Передать документ администратору после занятия.',
            today + timedelta(days=3),
            'high',
        )

    if ivan_user:
        student_study = get_or_create_todo_category(ivan_user, 'Обучение', '#b84d3f')
        get_or_create_todo_item(
            ivan_user,
            'Разобрать проезд перекрестков',
            student_study,
            'Повторить правила приоритета перед тестом.',
            today - timedelta(days=2),
            'high',
        )


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        migrate_schema()
        seed_training_data()
        db.session.commit()

    print('Учебные данные готовы.')
    print(f'Администратор: {ADMIN_USERNAME} / {ADMIN_PASSWORD}')
    print(f'Инструктор: {INSTRUCTOR_USERNAME} / {INSTRUCTOR_PASSWORD}')
    print(f'Курсант 1: anna.smirnova / {STUDENT_PASSWORD}')
    print(f'Курсант 2: ivan.petrov / {STUDENT_PASSWORD}')
    print(f'Курсант 3: maria.sokolova / {STUDENT_PASSWORD}')
    print(f'Курсант 4: alexey.orlov / {STUDENT_PASSWORD}')
