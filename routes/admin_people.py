from routes.admin_shared import *


def register_admin_people_routes(app):
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

        search = request.args.get('q', '').strip()
        page = request.args.get('page', 1, type=int)
        per_page = 20

        query = Kursanty.query
        if search:
            like_pattern = f'%{search}%'
            query = query.filter(
                db.or_(
                    Kursanty.fullname.ilike(like_pattern),
                    Kursanty.phone.ilike(like_pattern),
                    Kursanty.email.ilike(like_pattern),
                )
            )

        pagination = query.order_by(Kursanty.kursant_id).paginate(
            page=page, per_page=per_page, error_out=False
        )

        return render_template('admin/students.html',
            title="Курсанты",
            user_name=get_user_display_name(current_user),
            role=current_user.role,
            menu_items=get_menu_items('students', 'admin'),
            today=datetime.now().strftime("%d.%m.%Y"),
            students=pagination.items,
            pagination=pagination,
            search=search,
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

        search = request.args.get('q', '').strip()
        page = request.args.get('page', 1, type=int)
        per_page = 20

        query = Instructors.query
        if search:
            like_pattern = f'%{search}%'
            query = query.filter(
                db.or_(
                    Instructors.fullname.ilike(like_pattern),
                    Instructors.phone.ilike(like_pattern),
                )
            )

        pagination = query.order_by(Instructors.instructor_id).paginate(
            page=page, per_page=per_page, error_out=False
        )

        return render_template('admin/instructors.html',
            title="Инструкторы",
            user_name=get_user_display_name(current_user),
            role=current_user.role,
            menu_items=get_menu_items('instructors', 'admin'),
            today=datetime.now().strftime("%d.%m.%Y"),
            instructors=pagination.items,
            pagination=pagination,
            search=search,
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
