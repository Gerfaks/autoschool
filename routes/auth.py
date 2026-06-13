import os
from datetime import datetime

from flask import current_app, flash, redirect, render_template, request, send_from_directory, url_for
from flask_login import login_required, login_user, logout_user
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.utils import secure_filename

from extensions import db
from models import RegistrationRequest, User


VALID_ROLES = {'student', 'instructor'}
VALID_CATEGORIES = {'A', 'B', 'C'}


def clean_form_value(name):
    value = request.form.get(name, '').strip()
    return value or None


def build_registration_data():
    role = clean_form_value('role')
    experience_text = clean_form_value('experience')
    experience = None
    errors = []

    data = {
        'fullname': clean_form_value('fullname'),
        'phone': clean_form_value('phone'),
        'email': clean_form_value('email'),
        'role': role,
        'experience': experience_text,
        'license_category': clean_form_value('license_category'),
        'category_type': clean_form_value('category_type'),
        'passport_number': clean_form_value('passport_number'),
        'driver_license_number': clean_form_value('driver_license_number'),
    }

    if not data['fullname']:
        errors.append('Укажите ФИО.')
    if not data['phone']:
        errors.append('Укажите телефон.')
    if role not in VALID_ROLES:
        errors.append('Выберите, кто вы: курсант или инструктор.')
    if not data['passport_number']:
        errors.append('Укажите серию и номер паспорта.')

    if role == 'student':
        if data['category_type'] not in VALID_CATEGORIES:
            errors.append('Выберите категорию обучения: A, B или C.')
        data['experience'] = None
        data['license_category'] = None
    elif role == 'instructor':
        if not experience_text:
            errors.append('Укажите стаж инструктора в годах.')
        else:
            try:
                experience = int(experience_text)
                if experience < 0:
                    errors.append('Стаж не может быть отрицательным.')
            except ValueError:
                errors.append('Стаж должен быть целым числом, например 3.')

        if not data['license_category']:
            errors.append('Укажите категорию прав инструктора, например B или BC.')

        data['experience'] = experience
        data['category_type'] = None

    return data, errors


def register_auth_routes(app):
    @app.route('/')
    def index():
        return render_template('index.html')

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if request.method == 'POST':
            user = User.query.filter_by(username=request.form['username']).first()
            if user and user.check_password(request.form['password']):
                login_user(user)
                if user.role == 'admin':
                    return redirect(url_for('admin_dashboard'))
                elif user.role == 'instructor':
                    return redirect(url_for('instructor_dashboard'))
                else:
                    return redirect(url_for('student_dashboard'))
            flash('Неверный логин или пароль')
        return render_template('login.html')

    @app.route('/logout')
    @login_required
    def logout():
        logout_user()
        return redirect(url_for('index'))

    @app.route('/register', methods=['GET', 'POST'])
    def register():
        if request.method == 'POST':
            data, errors = build_registration_data()
            if errors:
                for error in errors:
                    flash(error, 'danger')
                return render_template('register.html', form_data=data)

            try:
                req = RegistrationRequest(
                    fullname=data['fullname'],
                    phone=data['phone'],
                    email=data['email'],
                    role=data['role'],
                    experience=data['experience'],
                    license_category=data['license_category'],
                    category_type=data['category_type'],
                    passport_number=data['passport_number'],
                    driver_license_number=data['driver_license_number'],
                    status='pending'
                )
                
                if 'documents' in request.files:
                    file = request.files['documents']
                    if file.filename:
                        os.makedirs('uploads', exist_ok=True)
                        filename = secure_filename(file.filename)
                        filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{filename}"
                        file.save(os.path.join('uploads', filename))
                        req.documents_photo = filename
                
                db.session.add(req)
                db.session.commit()
                flash('Ваша заявка отправлена на рассмотрение! Мы свяжемся с вами.', 'success')
                return redirect(url_for('index'))
            except SQLAlchemyError:
                db.session.rollback()
                current_app.logger.exception('Registration request save failed')
                flash(
                    'Не удалось отправить заявку. Проверьте, что все обязательные поля заполнены, '
                    'а стаж указан целым числом. Затем попробуйте отправить форму еще раз.',
                    'danger'
                )
                return render_template('register.html', form_data=data)
            except Exception:
                db.session.rollback()
                current_app.logger.exception('Unexpected registration error')
                flash(
                    'Не удалось отправить заявку. Проверьте заполненные данные и фото документов, '
                    'затем попробуйте еще раз.',
                    'danger'
                )
                return render_template('register.html', form_data=data)
        
        return render_template('register.html')

    @app.route('/uploads/<filename>')
    def uploaded_file(filename):
        return send_from_directory('uploads', filename)

    @app.route('/check')
    def check():
        try:
            db.session.execute(text('SELECT 1'))
            db.session.commit()
            return "База данных работает"
        except Exception as e:
            return f"Ошибка: {e}"
