import os
import re
import secrets
from calendar import monthrange
from datetime import datetime

from flask import current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError
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
    User,
)
from utils import get_lesson_type_id, get_menu_items, get_user_display_name


LESSON_STATUS_COMMENT_RE = re.compile(
    r'\s*[✅❌]\s*(?:Подтверждено|Проведено|Отменено(?: курсантом)?)'
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


def register_admin_routes(app):
    def save_car_photo(file):
        if not file or not file.filename:
            return None

        os.makedirs('uploads', exist_ok=True)
        filename = secure_filename(file.filename)
        unique_filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{filename}"
        file.save(os.path.join('uploads', unique_filename))
        return unique_filename

    @app.route('/admin')
    @login_required
    def admin_dashboard():
        if current_user.role != 'admin':
            return "Доступ запрещен", 403
        
        # Статистика
        students_count = Kursanty.query.count()
        instructors_count = Instructors.query.count()
        cars_count = Automobiles.query.count()
        lessons_count = Lessons.query.filter_by(status='completed').count()

        current_day = datetime.now().date()
        month_end = current_day.replace(day=monthrange(current_day.year, current_day.month)[1])
        month_labels = [str(day) for day in range(1, month_end.day + 1)]
        month_title = current_day.strftime('%m.%Y')

        lessons_by_day = []
        payments_by_day = []
        for day in range(1, month_end.day + 1):
            day_date = current_day.replace(day=day)
            lessons_count_for_day = Lessons.query.filter(
                Lessons.lesson_date == day_date,
                Lessons.status == 'completed'
            ).count()
            payments_total_for_day = db.session.query(func.sum(Payments.amount)).filter(
                Payments.payment_date == day_date
            ).scalar() or 0

            lessons_by_day.append(lessons_count_for_day)
            payments_by_day.append(float(payments_total_for_day))

        month_completed_lessons = sum(lessons_by_day)
        month_revenue = sum(payments_by_day)
        
        # Должники
        debtors = []
        for student in Kursanty.query.all():
            debt_data = get_student_debt_data(student)
            if debt_data['debt'] > 0:
                debtors.append({'name': student.fullname, 'debt': debt_data['debt']})
        
        return render_template('admin/dashboard.html',
            title="Панель управления",
            user_name=get_user_display_name(current_user),
            role=current_user.role,
            menu_items=get_menu_items('dashboard', 'admin'),
            today=datetime.now().strftime("%d.%m.%Y"),
            students_count=students_count,
            instructors_count=instructors_count,
            cars_count=cars_count,
            lessons_count=lessons_count,
            month_labels=month_labels,
            month_title=month_title,
            lessons_by_day=lessons_by_day,
            payments_by_day=payments_by_day,
            month_completed_lessons=month_completed_lessons,
            month_revenue=month_revenue,
            debtors=debtors
        )

    @app.route('/admin/students')
    @login_required
    def admin_students():
        if current_user.role != 'admin':
            return "Доступ запрещен", 403
        return render_template('admin/students.html',
            title="Курсанты",
            user_name=get_user_display_name(current_user),
            role=current_user.role,
            menu_items=get_menu_items('students', 'admin'),
            today=datetime.now().strftime("%d.%m.%Y"),
            students=Kursanty.query.all()
        )

    @app.route('/admin/student/add', methods=['GET', 'POST'])
    @login_required
    def admin_add_student():
        if current_user.role != 'admin':
            return "Доступ запрещен", 403
        if request.method == 'POST':
            s = Kursanty(
                fullname=request.form['fullname'],
                phone=request.form['phone'],
                email=request.form['email'],
                category_type=request.form['category_type']
            )
            db.session.add(s)
            db.session.commit()
            flash('Курсант добавлен')
            return redirect(url_for('admin_students'))
        return render_template('admin/student_form.html',
            title="Добавить курсанта",
            user_name=get_user_display_name(current_user),
            role=current_user.role,
            menu_items=get_menu_items('students', 'admin'),
            today=datetime.now().strftime("%d.%m.%Y"),
            student=None
        )

    @app.route('/admin/student/edit/<int:id>', methods=['GET', 'POST'])
    @login_required
    def admin_edit_student(id):
        if current_user.role != 'admin':
            return "Доступ запрещен", 403
        s = Kursanty.query.get_or_404(id)
        if request.method == 'POST':
            s.fullname = request.form['fullname']
            s.phone = request.form['phone']
            s.email = request.form['email']
            s.category_type = request.form['category_type']
            db.session.commit()
            flash('Курсант обновлен')
            return redirect(url_for('admin_students'))
        return render_template('admin/student_form.html',
            title="Редактировать курсанта",
            user_name=get_user_display_name(current_user),
            role=current_user.role,
            menu_items=get_menu_items('students', 'admin'),
            today=datetime.now().strftime("%d.%m.%Y"),
            student=s
        )

    @app.route('/admin/student/delete/<int:id>', methods=['POST'])
    @login_required
    def admin_delete_student(id):
        if current_user.role != 'admin':
            return "Доступ запрещен", 403
        s = Kursanty.query.get_or_404(id)
        db.session.delete(s)
        db.session.commit()
        flash('Курсант удален')
        return redirect(url_for('admin_students'))

    @app.route('/admin/instructors')
    @login_required
    def admin_instructors():
        if current_user.role != 'admin':
            return "Доступ запрещен", 403
        return render_template('admin/instructors.html',
            title="Инструкторы",
            user_name=get_user_display_name(current_user),
            role=current_user.role,
            menu_items=get_menu_items('instructors', 'admin'),
            today=datetime.now().strftime("%d.%m.%Y"),
            instructors=Instructors.query.all()
        )

    @app.route('/admin/instructor/add', methods=['GET', 'POST'])
    @login_required
    def admin_add_instructor():
        if current_user.role != 'admin':
            return "Доступ запрещен", 403
        if request.method == 'POST':
            try:
                i = Instructors(
                    fullname=request.form['fullname'],
                    phone=request.form.get('phone'),
                    experience=request.form['experience'],
                    license_category=request.form['license_category']
                )
                db.session.add(i)
                db.session.commit()
                flash('Инструктор добавлен')
                return redirect(url_for('admin_instructors'))
            except Exception as e:
                flash(f'Ошибка: {e}')
                return redirect(url_for('admin_instructors'))
        return render_template('admin/instructor_form.html',
            title="Добавить инструктора",
            user_name=get_user_display_name(current_user),
            role=current_user.role,
            menu_items=get_menu_items('instructors', 'admin'),
            today=datetime.now().strftime("%d.%m.%Y"),
            instructor=None
        )

    @app.route('/admin/instructor/edit/<int:id>', methods=['GET', 'POST'])
    @login_required
    def admin_edit_instructor(id):
        if current_user.role != 'admin':
            return "Доступ запрещен", 403
        i = Instructors.query.get_or_404(id)
        if request.method == 'POST':
            i.fullname = request.form['fullname']
            i.phone = request.form.get('phone')
            i.experience = request.form['experience']
            i.license_category = request.form['license_category']
            db.session.commit()
            flash('Инструктор обновлен')
            return redirect(url_for('admin_instructors'))
        return render_template('admin/instructor_form.html',
            title="Редактировать инструктора",
            user_name=get_user_display_name(current_user),
            role=current_user.role,
            menu_items=get_menu_items('instructors', 'admin'),
            today=datetime.now().strftime("%d.%m.%Y"),
            instructor=i
        )

    @app.route('/admin/instructor/delete/<int:id>', methods=['POST'])
    @login_required
    def admin_delete_instructor(id):
        if current_user.role != 'admin':
            return "Доступ запрещен", 403
        i = Instructors.query.get_or_404(id)
        db.session.delete(i)
        db.session.commit()
        flash('Инструктор удален')
        return redirect(url_for('admin_instructors'))

    @app.route('/admin/cars')
    @login_required
    def admin_cars():
        if current_user.role != 'admin':
            return "Доступ запрещен", 403
        return render_template('admin/cars.html',
            title="Автомобили",
            user_name=get_user_display_name(current_user),
            role=current_user.role,
            menu_items=get_menu_items('cars', 'admin'),
            today=datetime.now().strftime("%d.%m.%Y"),
            cars=Automobiles.query.all()
        )

    @app.route('/admin/car/add', methods=['GET', 'POST'])
    @login_required
    def admin_add_car():
        if current_user.role != 'admin':
            return "Доступ запрещен", 403
        if request.method == 'POST':
            try:
                c = Automobiles(
                    instructor_id=request.form.get('instructor_id') or None,
                    brand=request.form['brand'],
                    model=request.form['model'],
                    plate=request.form['plate'],
                    vehicle_type=request.form['vehicle_type'],
                    photo_filename=save_car_photo(request.files.get('photo'))
                )
                db.session.add(c)
                db.session.commit()
                flash('Автомобиль добавлен')
                return redirect(url_for('admin_cars'))
            except Exception as e:
                flash(f'Ошибка: {e}')
                return redirect(url_for('admin_cars'))
        return render_template('admin/car_form.html',
            title="Добавить автомобиль",
            user_name=get_user_display_name(current_user),
            role=current_user.role,
            menu_items=get_menu_items('cars', 'admin'),
            today=datetime.now().strftime("%d.%m.%Y"),
            instructors=Instructors.query.order_by(Instructors.fullname).all(),
            car=None
        )

    @app.route('/admin/car/edit/<int:id>', methods=['GET', 'POST'])
    @login_required
    def admin_edit_car(id):
        if current_user.role != 'admin':
            return "Доступ запрещен", 403

        c = Automobiles.query.get_or_404(id)
        if request.method == 'POST':
            try:
                c.instructor_id = request.form.get('instructor_id') or None
                c.brand = request.form['brand']
                c.model = request.form['model']
                c.plate = request.form['plate']
                c.vehicle_type = request.form['vehicle_type']

                photo_filename = save_car_photo(request.files.get('photo'))
                if photo_filename:
                    c.photo_filename = photo_filename

                db.session.commit()
                flash('Автомобиль обновлен')
                return redirect(url_for('admin_cars'))
            except Exception as e:
                flash(f'Ошибка: {e}')
                return redirect(url_for('admin_cars'))

        return render_template('admin/car_form.html',
            title="Редактировать автомобиль",
            user_name=get_user_display_name(current_user),
            role=current_user.role,
            menu_items=get_menu_items('cars', 'admin'),
            today=datetime.now().strftime("%d.%m.%Y"),
            instructors=Instructors.query.order_by(Instructors.fullname).all(),
            car=c
        )

    @app.route('/admin/car/delete/<int:id>', methods=['POST'])
    @login_required
    def admin_delete_car(id):
        if current_user.role != 'admin':
            return "Доступ запрещен", 403
        c = Automobiles.query.get_or_404(id)
        db.session.delete(c)
        db.session.commit()
        flash('Автомобиль удален')
        return redirect(url_for('admin_cars'))

    @app.route('/admin/grounds')
    @login_required
    def admin_grounds():
        if current_user.role != 'admin':
            return "Доступ запрещен", 403
        return render_template('admin/grounds.html',
            title="Площадки",
            user_name=get_user_display_name(current_user),
            role=current_user.role,
            menu_items=get_menu_items('grounds', 'admin'),
            today=datetime.now().strftime("%d.%m.%Y"),
            grounds=Grounds.query.order_by(Grounds.ground_id).all()
        )

    @app.route('/admin/ground/add', methods=['GET', 'POST'])
    @login_required
    def admin_add_ground():
        if current_user.role != 'admin':
            return "Доступ запрещен", 403

        if request.method == 'POST':
            data, errors = get_ground_form_data()
            if errors:
                for error in errors:
                    flash(error)
                return render_template('admin/ground_form.html',
                    title="Добавить площадку",
                    user_name=get_user_display_name(current_user),
                    role=current_user.role,
                    menu_items=get_menu_items('grounds', 'admin'),
                    today=datetime.now().strftime("%d.%m.%Y"),
                    ground=data,
                    instructors=Instructors.query.order_by(Instructors.fullname).all()
                )

            ground = Grounds(
                instructor_id=data['instructor_id'],
                address=data['address'],
                surface_type=data['surface_type'],
                area=data['area']
            )
            db.session.add(ground)
            db.session.commit()
            flash('Площадка добавлена')
            return redirect(url_for('admin_grounds'))

        return render_template('admin/ground_form.html',
            title="Добавить площадку",
            user_name=get_user_display_name(current_user),
            role=current_user.role,
            menu_items=get_menu_items('grounds', 'admin'),
            today=datetime.now().strftime("%d.%m.%Y"),
            ground=None,
            instructors=Instructors.query.order_by(Instructors.fullname).all()
        )

    @app.route('/admin/ground/edit/<int:id>', methods=['GET', 'POST'])
    @login_required
    def admin_edit_ground(id):
        if current_user.role != 'admin':
            return "Доступ запрещен", 403

        ground = Grounds.query.get_or_404(id)
        if request.method == 'POST':
            data, errors = get_ground_form_data(ground.ground_id)
            if errors:
                for error in errors:
                    flash(error)
                data['ground_id'] = ground.ground_id
                return render_template('admin/ground_form.html',
                    title="Редактировать площадку",
                    user_name=get_user_display_name(current_user),
                    role=current_user.role,
                    menu_items=get_menu_items('grounds', 'admin'),
                    today=datetime.now().strftime("%d.%m.%Y"),
                    ground=data,
                    instructors=Instructors.query.order_by(Instructors.fullname).all()
                )

            ground.instructor_id = data['instructor_id']
            ground.address = data['address']
            ground.surface_type = data['surface_type']
            ground.area = data['area']
            db.session.commit()
            flash('Площадка обновлена')
            return redirect(url_for('admin_grounds'))

        return render_template('admin/ground_form.html',
            title="Редактировать площадку",
            user_name=get_user_display_name(current_user),
            role=current_user.role,
            menu_items=get_menu_items('grounds', 'admin'),
            today=datetime.now().strftime("%d.%m.%Y"),
            ground=ground,
            instructors=Instructors.query.order_by(Instructors.fullname).all()
        )

    @app.route('/admin/lessons')
    @login_required
    def admin_lessons():
        if current_user.role != 'admin':
            return "Доступ запрещен", 403

        student_filter = request.args.get('student_id', '').strip()
        instructor_filter = request.args.get('instructor_id', '').strip()
        status_filter = request.args.get('status', '').strip()
        date_filter = request.args.get('lesson_date', '').strip()
        
        # Получаем все занятия с именами
        lessons_query = db.session.query(
            Lessons.lesson_id,
            Lessons.lesson_date,
            Lessons.lesson_time,
            LessonType.name.label('lesson_type'),
            Lessons.status,
            Lessons.comments,
            Kursanty.fullname.label('kursant_name'),
            Instructors.fullname.label('instructor_name'),
            db.func.concat(Automobiles.brand, ' ', Automobiles.model).label('car_name')
        ).outerjoin(Kursanty, Lessons.kursant_id == Kursanty.kursant_id)\
         .join(LessonType, Lessons.lesson_type_id == LessonType.lesson_type_id)\
         .outerjoin(Instructors, Lessons.instructor_id == Instructors.instructor_id)\
         .outerjoin(Automobiles, Lessons.auto_id == Automobiles.auto_id)

        if student_filter:
            lessons_query = lessons_query.filter(Lessons.kursant_id == int(student_filter))
        if instructor_filter:
            lessons_query = lessons_query.filter(Lessons.instructor_id == int(instructor_filter))
        if status_filter:
            lessons_query = lessons_query.filter(Lessons.status == status_filter)
        if date_filter:
            lessons_query = lessons_query.filter(Lessons.lesson_date == datetime.strptime(date_filter, '%Y-%m-%d').date())

        lesson_rows = lessons_query.order_by(Lessons.lesson_date, Lessons.lesson_time).all()

        lessons = [
            {
                'lesson_id': lesson.lesson_id,
                'lesson_date': lesson.lesson_date,
                'lesson_time': lesson.lesson_time,
                'lesson_type': lesson.lesson_type,
                'status': lesson.status or 'pending',
                'comments': clean_lesson_comment(lesson.comments),
                'kursant_name': lesson.kursant_name,
                'instructor_name': lesson.instructor_name,
                'car_name': lesson.car_name,
            }
            for lesson in lesson_rows
        ]
        
        return render_template('admin/lessons.html',
            title="Занятия",
            user_name=get_user_display_name(current_user),
            role=current_user.role,
            menu_items=get_menu_items('lessons', 'admin'),
            today=datetime.now().strftime("%d.%m.%Y"),
            lessons=lessons,
            students=Kursanty.query.order_by(Kursanty.fullname).all(),
            instructors=Instructors.query.order_by(Instructors.fullname).all(),
            filters={
                'student_id': student_filter,
                'instructor_id': instructor_filter,
                'status': status_filter,
                'lesson_date': date_filter,
            }
        )

    @app.route('/admin/lesson/add', methods=['GET', 'POST'])
    @login_required
    def admin_add_lesson():
        if current_user.role != 'admin':
            return "Доступ запрещен", 403
        if request.method == 'POST':
            try:
                l = Lessons(
                    lesson_date=datetime.strptime(request.form['lesson_date'], '%Y-%m-%d'),
                    lesson_time=datetime.strptime(request.form['lesson_time'], '%H:%M').time(),
                    lesson_type_id=get_lesson_type_id(request.form['lesson_type']),
                    kursant_id=request.form['kursant_id'],
                    instructor_id=request.form['instructor_id'],
                    auto_id=request.form['auto_id'],
                    comments=request.form.get('comments', '')
                )
                db.session.add(l)
                db.session.commit()
                flash('Занятие добавлено')
                return redirect(url_for('admin_lessons'))
            except Exception as e:
                flash(f'Ошибка: {e}')
                return redirect(url_for('admin_lessons'))
        return render_template('admin/lesson_form.html',
            title="Добавить занятие",
            user_name=get_user_display_name(current_user),
            role=current_user.role,
            menu_items=get_menu_items('lessons', 'admin'),
            today=datetime.now().strftime("%d.%m.%Y"),
            students=Kursanty.query.all(),
            instructors=Instructors.query.all(),
            cars=Automobiles.query.all()
        )

    @app.route('/admin/tariffs', methods=['GET', 'POST'])
    @login_required
    def admin_tariffs():
        if current_user.role != 'admin':
            return "Доступ запрещен", 403

        if request.method == 'POST':
            for tariff in LessonTariff.query.order_by(LessonTariff.tariff_id).all():
                price_text = request.form.get(f'price_{tariff.tariff_id}', '').strip()
                if price_text:
                    tariff.price = price_text
            db.session.commit()
            flash('Тарифы обновлены')
            return redirect(url_for('admin_tariffs'))

        return render_template('admin/tariffs.html',
            title="Тарифы",
            user_name=get_user_display_name(current_user),
            role=current_user.role,
            menu_items=get_menu_items('tariffs', 'admin'),
            today=datetime.now().strftime("%d.%m.%Y"),
            tariffs=LessonTariff.query.join(LessonType).order_by(LessonType.name).all()
        )

    @app.route('/admin/payments')
    @login_required
    def admin_payments():
        if current_user.role != 'admin':
            return "Доступ запрещен", 403

        student_filter = request.args.get('student_id', '').strip()
        method_filter = request.args.get('payment_method', '').strip()
        date_from = request.args.get('date_from', '').strip()
        date_to = request.args.get('date_to', '').strip()
        
        # Получаем всех курсантов с долгами
        students_data = []
        for student in Kursanty.query.all():
            debt_data = get_student_debt_data(student)
            
            students_data.append({
                'kursant_id': student.kursant_id,  # ← ЭТО ВАЖНО! id, а не 'id'
                'name': student.fullname,
                'lessons_count': debt_data['lessons_count'],
                'expected': debt_data['expected'],
                'paid': float(debt_data['paid']),
                'debt': debt_data['debt']
            })
        
        # История платежей
        payments_query = db.session.query(
            Payments.payment_id,
            Payments.amount,
            Payments.payment_date,
            Payments.payment_method,
            Payments.comment,
            User.username.label('created_by'),
            Kursanty.fullname.label('student_name')
        ).join(Kursanty, Payments.kursant_id == Kursanty.kursant_id)\
         .outerjoin(User, Payments.created_by_user_id == User.id)

        if student_filter:
            payments_query = payments_query.filter(Payments.kursant_id == int(student_filter))
        if method_filter:
            payments_query = payments_query.filter(Payments.payment_method == method_filter)
        if date_from:
            payments_query = payments_query.filter(Payments.payment_date >= datetime.strptime(date_from, '%Y-%m-%d').date())
        if date_to:
            payments_query = payments_query.filter(Payments.payment_date <= datetime.strptime(date_to, '%Y-%m-%d').date())

        payments = payments_query.order_by(Payments.payment_date.desc()).all()
        
        return render_template('admin/payments.html',
            title="Платежи и задолженности",
            user_name=get_user_display_name(current_user),
            role=current_user.role,
            menu_items=get_menu_items('payments', 'admin'),
            today=datetime.now().strftime("%d.%m.%Y"),
            students=students_data,
            payments=payments,
            debtors=[s for s in students_data if s['debt'] > 0],
            filters={
                'student_id': student_filter,
                'payment_method': method_filter,
                'date_from': date_from,
                'date_to': date_to,
            }
        )

    @app.route('/admin/payment/add', methods=['POST'])
    @login_required
    def admin_add_payment():
        if current_user.role != 'admin':
            return "Доступ запрещен", 403
        
        # --- НАЧАЛО: ДОБАВЛЕННАЯ ПРОВЕРКА ---
        kursant_id_str = request.form.get('kursant_id')
        if not kursant_id_str or kursant_id_str == '':
            flash('❌ Ошибка: не выбран курсант. Пожалуйста, выберите курсанта из списка.')
            return redirect(url_for('admin_payments'))
        
        try:
            kursant_id = int(kursant_id_str)
        except ValueError:
            flash('❌ Ошибка: ID курсанта должен быть числом.')
            return redirect(url_for('admin_payments'))
        # --- КОНЕЦ ДОБАВЛЕННОЙ ПРОВЕРКИ ---
        
        try:
            payment = Payments(
                kursant_id=kursant_id,
                amount=request.form['amount'],
                payment_method=request.form['payment_method'],
                comment=request.form.get('comment', ''),
                created_by_user_id=current_user.id
            )
            db.session.add(payment)
            db.session.commit()
            flash(f'✅ Платеж на сумму {request.form["amount"]} руб. добавлен')
        except Exception as e:
            db.session.rollback()
            flash(f'❌ Ошибка при сохранении: {e}')
        
        return redirect(url_for('admin_payments'))

    @app.route('/admin/payment/remind/<int:student_id>', methods=['POST'])
    @login_required
    def admin_remind_payment(student_id):
        if current_user.role != 'admin':
            return "Доступ запрещен", 403
        
        student = Kursanty.query.get_or_404(student_id)
        debt = get_student_debt_data(student)['debt']
        
        flash(f'📢 Уведомление для {student.fullname}: Ваша задолженность составляет {debt} руб. Пожалуйста, оплатите!')
        return redirect(url_for('admin_payments'))

    @app.route('/admin/cancellations')
    @login_required
    def admin_cancellations():
        if current_user.role != 'admin':
            return "Доступ запрещен", 403

        cancellations = db.session.query(
            CancellationHistory.cancelled_at,
            User.role.label('cancelled_by_role'),
            User.username.label('cancelled_by_name'),
            CancellationHistory.reason,
            Lessons.lesson_date,
            Lessons.lesson_time,
            LessonType.name.label('lesson_type'),
            Kursanty.fullname.label('student_name'),
            Instructors.fullname.label('instructor_name')
        ).join(Lessons, CancellationHistory.lesson_id == Lessons.lesson_id)\
         .join(LessonType, Lessons.lesson_type_id == LessonType.lesson_type_id)\
         .outerjoin(User, CancellationHistory.cancelled_by_user_id == User.id)\
         .outerjoin(Kursanty, Lessons.kursant_id == Kursanty.kursant_id)\
         .outerjoin(Instructors, Lessons.instructor_id == Instructors.instructor_id)\
         .order_by(CancellationHistory.cancelled_at.desc()).all()

        return render_template('admin/cancellations.html',
            title="История отмен",
            user_name=get_user_display_name(current_user),
            role=current_user.role,
            menu_items=get_menu_items('cancellations', 'admin'),
            today=datetime.now().strftime("%d.%m.%Y"),
            cancellations=cancellations
        )

    @app.route('/admin/test-cars')
    @login_required
    def admin_test_cars():
        cars = Automobiles.query.all()
        return f"Найдено автомобилей: {len(cars)}"
    @app.route('/admin/requests')
    @login_required
    def admin_requests():
        if current_user.role != 'admin':
            return "Доступ запрещен", 403

        status_filter = request.args.get('status', '').strip()
        role_filter = request.args.get('role', '').strip()
        requests_query = RegistrationRequest.query
        if status_filter:
            requests_query = requests_query.filter(RegistrationRequest.status == status_filter)
        if role_filter:
            requests_query = requests_query.filter(RegistrationRequest.role == role_filter)
        requests = requests_query.order_by(RegistrationRequest.created_at.desc()).all()

        return render_template('admin/requests.html',
            title="Заявки",
            user_name=get_user_display_name(current_user),
            role=current_user.role,
            menu_items=get_menu_items('requests', 'admin'),
            today=datetime.now().strftime("%d.%m.%Y"),
            requests=requests,
            filters={'status': status_filter, 'role': role_filter}
        )

    @app.route('/admin/request/<int:id>')
    @login_required
    def admin_request_view(id):
        if current_user.role != 'admin':
            return "Доступ запрещен", 403
        req = RegistrationRequest.query.get_or_404(id)
        return render_template('admin/request_view.html',
            title="Просмотр заявки",
            user_name=get_user_display_name(current_user),
            role=current_user.role,
            menu_items=get_menu_items('requests', 'admin'),
            today=datetime.now().strftime("%d.%m.%Y"),
            req=req,
            account_user=get_request_user(req) if req.status == 'approved' else None
        )

    @app.route('/admin/request/<int:id>/approve', methods=['POST'])
    @login_required
    def admin_approve_request(id):
        if current_user.role != 'admin':
            return "Доступ запрещен", 403
        
        req = RegistrationRequest.query.get_or_404(id)
        action = request.form.get('action')

        if req.status != 'pending':
            flash('Эта заявка уже обработана')
            return redirect(url_for('admin_request_view', id=id))

        if action not in {'approve', 'reject'}:
            flash('Выберите действие: одобрить или отклонить заявку')
            return redirect(url_for('admin_request_view', id=id))
        
        try:
            if action == 'approve':
                username = re.sub(r'\D+', '', req.phone or '')[:20] or f'user{req.request_id}'
                base_username = username
                counter = 1
                
                while User.query.filter_by(username=username).first():
                    username = f"{base_username}{counter}"
                    counter += 1
                
                temporary_password = secrets.token_urlsafe(8)
                
                user = User(
                    username=username,
                    password_hash=generate_password_hash(temporary_password, method='pbkdf2:sha256'),
                    role=req.role
                )
                
                if req.role == 'student':
                    student = Kursanty(
                        fullname=req.fullname,
                        phone=req.phone,
                        email=req.email,
                        category_type=req.category_type
                    )
                    db.session.add(student)
                    db.session.flush()
                    user.kursant_id = student.kursant_id
                else:
                    instructor = Instructors(
                        fullname=req.fullname,
                        phone=req.phone,
                        experience=req.experience or 0,
                        license_category=req.license_category or ''
                    )
                    db.session.add(instructor)
                    db.session.flush()
                    user.instructor_id = instructor.instructor_id
                
                db.session.add(user)
                req.status = 'approved'
                req.reviewed_by_user_id = current_user.id
                req.reviewed_at = datetime.now()
                req.login_username = username
                req.temporary_password = temporary_password
                req.comment = request.form.get('comment', '')
                
                db.session.commit()
                
                flash(f'✅ Заявка одобрена! Логин: {username}, временный пароль: {temporary_password}')
                
            elif action == 'reject':
                req.status = 'rejected'
                req.reviewed_by_user_id = current_user.id
                req.reviewed_at = datetime.now()
                req.comment = request.form.get('comment', '')
                db.session.commit()
                flash('❌ Заявка отклонена')
        except SQLAlchemyError:
            db.session.rollback()
            current_app.logger.exception('Registration request review failed')
            flash('Не удалось обработать заявку. Проверьте данные заявки и попробуйте еще раз.')
            return redirect(url_for('admin_request_view', id=id))
        
        return redirect(url_for('admin_requests'))

    @app.route('/admin/request/<int:id>/reset-password', methods=['POST'])
    @login_required
    def admin_reset_request_password(id):
        if current_user.role != 'admin':
            return "Доступ запрещен", 403

        req = RegistrationRequest.query.get_or_404(id)
        if req.status != 'approved':
            flash('Сбросить пароль можно только для одобренной заявки')
            return redirect(url_for('admin_request_view', id=id))

        user = get_request_user(req)
        if not user:
            flash('Не удалось найти созданный аккаунт для этой заявки')
            return redirect(url_for('admin_request_view', id=id))

        try:
            temporary_password = secrets.token_urlsafe(8)
            user.password_hash = generate_password_hash(temporary_password, method='pbkdf2:sha256')
            req.login_username = user.username
            req.temporary_password = temporary_password
            db.session.commit()
            flash(f'Новый временный пароль выдан. Логин: {user.username}, пароль: {temporary_password}')
        except SQLAlchemyError:
            db.session.rollback()
            current_app.logger.exception('Registration request password reset failed')
            flash('Не удалось сбросить пароль. Попробуйте еще раз.')

        return redirect(url_for('admin_request_view', id=id))
