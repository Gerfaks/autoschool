from routes.admin_shared import *


def register_admin_request_routes(app):
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
                
                flash(f'Заявка одобрена. Логин: {username}, временный пароль: {temporary_password}')
                
            elif action == 'reject':
                req.status = 'rejected'
                req.reviewed_by_user_id = current_user.id
                req.reviewed_at = datetime.now()
                req.comment = request.form.get('comment', '')
                db.session.commit()
                flash('Заявка отклонена')
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
