from datetime import datetime

from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.security import generate_password_hash

from extensions import db
from models import Instructors, Kursanty, User
from utils import get_menu_items, get_user_display_name


ROLE_LABELS = {
    'admin': 'Администратор',
    'instructor': 'Инструктор',
    'student': 'Курсант',
}


def clean_value(name):
    return request.form.get(name, '').strip()


def get_profile_person(user):
    if user.role == 'student' and user.kursant_id:
        return db.session.get(Kursanty, user.kursant_id)
    if user.role == 'instructor' and user.instructor_id:
        return db.session.get(Instructors, user.instructor_id)
    return None


def update_personal_data(user, person, errors):
    if user.role == 'student' and person:
        fullname = clean_value('fullname')
        phone = clean_value('phone')
        email = clean_value('email')
        category_type = clean_value('category_type')

        if not fullname:
            errors.append('Укажите ФИО.')
        if not phone:
            errors.append('Укажите телефон.')
        if category_type not in {'A', 'B', 'C'}:
            errors.append('Выберите категорию обучения.')

        if not errors:
            person.fullname = fullname
            person.phone = phone
            person.email = email or None
            person.category_type = category_type

    if user.role == 'instructor' and person:
        fullname = clean_value('fullname')
        phone = clean_value('phone')
        experience_text = clean_value('experience')
        license_category = clean_value('license_category')

        if not fullname:
            errors.append('Укажите ФИО.')
        if not phone:
            errors.append('Укажите телефон.')
        if not license_category:
            errors.append('Укажите категорию прав.')

        experience = 0
        if experience_text:
            try:
                experience = int(experience_text)
                if experience < 0:
                    errors.append('Стаж не может быть отрицательным.')
            except ValueError:
                errors.append('Стаж должен быть целым числом.')

        if not errors:
            person.fullname = fullname
            person.phone = phone
            person.experience = experience
            person.license_category = license_category


def register_profile_routes(app):
    @app.route('/profile', methods=['GET', 'POST'])
    @login_required
    def profile():
        person = get_profile_person(current_user)

        if request.method == 'POST':
            username = clean_value('username')
            current_password = request.form.get('current_password', '')
            new_password = request.form.get('new_password', '')
            confirm_password = request.form.get('confirm_password', '')
            errors = []

            if not username:
                errors.append('Укажите логин.')
            elif len(username) < 3 or len(username) > 50:
                errors.append('Логин должен быть от 3 до 50 символов.')
            else:
                existing_user = User.query.filter(
                    User.username == username,
                    User.id != current_user.id,
                ).first()
                if existing_user:
                    errors.append('Такой логин уже занят.')

            if not current_password or not current_user.check_password(current_password):
                errors.append('Введите текущий пароль.')

            if new_password or confirm_password:
                if len(new_password) < 6:
                    errors.append('Новый пароль должен быть не короче 6 символов.')
                if new_password != confirm_password:
                    errors.append('Новый пароль и подтверждение не совпадают.')

            update_personal_data(current_user, person, errors)

            if errors:
                for error in errors:
                    flash(error)
            else:
                try:
                    current_user.username = username
                    if new_password:
                        current_user.password_hash = generate_password_hash(
                            new_password,
                            method='pbkdf2:sha256',
                        )
                    db.session.commit()
                    flash('Профиль обновлен')
                    return redirect(url_for('profile'))
                except SQLAlchemyError:
                    db.session.rollback()
                    flash('Не удалось сохранить профиль. Попробуйте еще раз.')

        return render_template(
            'profile.html',
            title='Профиль',
            user_name=get_user_display_name(current_user),
            role=current_user.role,
            role_label=ROLE_LABELS.get(current_user.role, current_user.role),
            menu_items=get_menu_items('profile', current_user.role),
            today=datetime.now().strftime('%d.%m.%Y'),
            person=person,
        )
