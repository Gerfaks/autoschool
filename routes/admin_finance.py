from routes.admin_shared import *


def register_admin_finance_routes(app):
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
            flash('Ошибка: не выбран курсант. Пожалуйста, выберите курсанта из списка.')
            return redirect(url_for('admin_payments'))
        
        try:
            kursant_id = int(kursant_id_str)
        except ValueError:
            flash('Ошибка: ID курсанта должен быть числом.')
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
            flash(f'Платеж на сумму {request.form["amount"]} руб. добавлен')
        except Exception as e:
            db.session.rollback()
            flash(f'Ошибка при сохранении: {e}')
        
        return redirect(url_for('admin_payments'))

    @app.route('/admin/payment/remind/<int:student_id>', methods=['POST'])
    @login_required
    def admin_remind_payment(student_id):
        if current_user.role != 'admin':
            return "Доступ запрещен", 403
        
        student = Kursanty.query.get_or_404(student_id)
        debt = get_student_debt_data(student)['debt']
        
        flash(f'Уведомление для {student.fullname}: задолженность составляет {debt} руб. Пожалуйста, оплатите.')
        return redirect(url_for('admin_payments'))

    @app.route('/admin/cancellations')
    @login_required
    def admin_cancellations():
        if current_user.role != 'admin':
            return "Доступ запрещен", 403

        cancelled_student = aliased(Kursanty)
        cancelled_instructor = aliased(Instructors)
        cancellations = db.session.query(
            CancellationHistory.cancelled_at,
            User.role.label('cancelled_by_role'),
            func.coalesce(
                cancelled_student.fullname,
                cancelled_instructor.fullname,
                User.username,
            ).label('cancelled_by_name'),
            CancellationHistory.reason,
            Lessons.lesson_date,
            Lessons.lesson_time,
            LessonType.name.label('lesson_type'),
            Kursanty.fullname.label('student_name'),
            Instructors.fullname.label('instructor_name')
        ).join(Lessons, CancellationHistory.lesson_id == Lessons.lesson_id)\
         .join(LessonType, Lessons.lesson_type_id == LessonType.lesson_type_id)\
         .outerjoin(User, CancellationHistory.cancelled_by_user_id == User.id)\
         .outerjoin(cancelled_student, User.kursant_id == cancelled_student.kursant_id)\
         .outerjoin(cancelled_instructor, User.instructor_id == cancelled_instructor.instructor_id)\
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
