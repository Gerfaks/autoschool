from routes.admin_shared import *


def register_admin_course_routes(app):
    @app.route('/admin/courses')
    @login_required
    def admin_courses():
        if current_user.role != 'admin':
            return "Доступ запрещен", 403

        courses = TrainingCourse.query.order_by(TrainingCourse.title).all()
        course_stats = {}
        for course in courses:
            course_stats[course.course_id] = {
                'assignments': len(course.assignments),
                'students': len(course.enrollments),
            }

        return render_template('admin/courses.html',
            title="Учебные курсы",
            user_name=get_user_display_name(current_user),
            role=current_user.role,
            menu_items=get_menu_items('courses', 'admin'),
            today=datetime.now().strftime("%d.%m.%Y"),
            courses=courses,
            course_stats=course_stats
        )

    @app.route('/admin/reports/overdue/<file_format>')
    @login_required
    def admin_overdue_report(file_format):
        if current_user.role != 'admin':
            return "Доступ запрещен", 403
        if file_format not in REPORT_MIME_TYPES:
            return "Формат отчета не поддерживается", 404

        headers = [
            'Курсант',
            'Телефон',
            'Курс',
            'Задание',
            'Дедлайн',
            'Статус',
            'Дней после срока',
        ]
        rows = get_overdue_assignment_rows()
        title = 'Задания курсантов с истекшим сроком выполнения'
        subtitle = 'Административный отчет по назначенным учебным курсам'
        filename = f'assignment_deadline_report_{datetime.now().strftime("%Y%m%d_%H%M")}.{file_format}'

        if file_format == 'docx':
            stream = build_docx_report(title, subtitle, headers, rows)
        else:
            stream = build_xlsx_report(title, headers, rows, 'Истекшие сроки')

        return send_report(stream, filename, file_format)

    @app.route('/admin/course/add', methods=['GET', 'POST'])
    @login_required
    def admin_add_course():
        if current_user.role != 'admin':
            return "Доступ запрещен", 403

        if request.method == 'POST':
            data, errors = get_course_form_data()
            if errors:
                for error in errors:
                    flash(error)
                return render_template('admin/course_form.html',
                    title="Добавить курс",
                    user_name=get_user_display_name(current_user),
                    role=current_user.role,
                    menu_items=get_menu_items('courses', 'admin'),
                    today=datetime.now().strftime("%d.%m.%Y"),
                    course=data
                )

            try:
                course = TrainingCourse(**data)
                db.session.add(course)
                db.session.commit()
                flash('Курс добавлен')
                return redirect(url_for('admin_course_detail', id=course.course_id))
            except SQLAlchemyError:
                db.session.rollback()
                current_app.logger.exception('Training course create failed')
                flash('Не удалось сохранить курс. Проверьте данные и попробуйте еще раз.')

        return render_template('admin/course_form.html',
            title="Добавить курс",
            user_name=get_user_display_name(current_user),
            role=current_user.role,
            menu_items=get_menu_items('courses', 'admin'),
            today=datetime.now().strftime("%d.%m.%Y"),
            course=None
        )

    @app.route('/admin/course/edit/<int:id>', methods=['GET', 'POST'])
    @login_required
    def admin_edit_course(id):
        if current_user.role != 'admin':
            return "Доступ запрещен", 403

        course = TrainingCourse.query.get_or_404(id)
        if request.method == 'POST':
            data, errors = get_course_form_data()
            if errors:
                for error in errors:
                    flash(error)
                return render_template('admin/course_form.html',
                    title="Редактировать курс",
                    user_name=get_user_display_name(current_user),
                    role=current_user.role,
                    menu_items=get_menu_items('courses', 'admin'),
                    today=datetime.now().strftime("%d.%m.%Y"),
                    course={**data, 'course_id': course.course_id}
                )

            try:
                course.title = data['title']
                course.description = data['description']
                course.category = data['category']
                db.session.commit()
                flash('Курс обновлен')
                return redirect(url_for('admin_course_detail', id=course.course_id))
            except SQLAlchemyError:
                db.session.rollback()
                current_app.logger.exception('Training course update failed')
                flash('Не удалось обновить курс. Попробуйте еще раз.')

        return render_template('admin/course_form.html',
            title="Редактировать курс",
            user_name=get_user_display_name(current_user),
            role=current_user.role,
            menu_items=get_menu_items('courses', 'admin'),
            today=datetime.now().strftime("%d.%m.%Y"),
            course=course
        )

    @app.route('/admin/course/delete/<int:id>', methods=['POST'])
    @login_required
    def admin_delete_course(id):
        if current_user.role != 'admin':
            return "Доступ запрещен", 403

        course = TrainingCourse.query.get_or_404(id)
        try:
            db.session.delete(course)
            db.session.commit()
            flash('Курс удален')
        except SQLAlchemyError:
            db.session.rollback()
            current_app.logger.exception('Training course delete failed')
            flash('Не удалось удалить курс. Попробуйте еще раз.')

        return redirect(url_for('admin_courses'))

    @app.route('/admin/course/<int:id>')
    @login_required
    def admin_course_detail(id):
        if current_user.role != 'admin':
            return "Доступ запрещен", 403

        course = TrainingCourse.query.get_or_404(id)
        assignments = TrainingAssignment.query.filter_by(course_id=course.course_id)\
            .order_by(TrainingAssignment.deadline.is_(None), TrainingAssignment.deadline, TrainingAssignment.title).all()
        enrollments = StudentCourse.query.filter_by(course_id=course.course_id)\
            .join(Kursanty, StudentCourse.kursant_id == Kursanty.kursant_id)\
            .order_by(Kursanty.fullname).all()
        assigned_student_ids = [enrollment.kursant_id for enrollment in enrollments]
        available_students_query = Kursanty.query.order_by(Kursanty.fullname)
        if assigned_student_ids:
            available_students_query = available_students_query.filter(Kursanty.kursant_id.notin_(assigned_student_ids))

        progress_summary = {}
        for assignment in assignments:
            rows = db.session.query(
                StudentAssignmentProgress.status,
                func.count(StudentAssignmentProgress.progress_id)
            ).filter_by(assignment_id=assignment.assignment_id)\
             .group_by(StudentAssignmentProgress.status).all()
            progress_summary[assignment.assignment_id] = {
                status: count
                for status, count in rows
            }

        return render_template('admin/course_detail.html',
            title=course.title,
            user_name=get_user_display_name(current_user),
            role=current_user.role,
            menu_items=get_menu_items('courses', 'admin'),
            today=datetime.now().strftime("%d.%m.%Y"),
            course=course,
            assignments=assignments,
            enrollments=enrollments,
            available_students=available_students_query.all(),
            progress_summary=progress_summary,
            status_labels=ASSIGNMENT_STATUS_LABELS
        )

    @app.route('/admin/course/<int:course_id>/assignment/add', methods=['GET', 'POST'])
    @login_required
    def admin_add_assignment(course_id):
        if current_user.role != 'admin':
            return "Доступ запрещен", 403

        course = TrainingCourse.query.get_or_404(course_id)
        if request.method == 'POST':
            data, errors = get_assignment_form_data()
            if errors:
                for error in errors:
                    flash(error)
                return render_template('admin/assignment_form.html',
                    title="Добавить задание",
                    user_name=get_user_display_name(current_user),
                    role=current_user.role,
                    menu_items=get_menu_items('courses', 'admin'),
                    today=datetime.now().strftime("%d.%m.%Y"),
                    course=course,
                    assignment=data
                )

            try:
                assignment = TrainingAssignment(
                    course_id=course.course_id,
                    title=data['title'],
                    description=data['description'],
                    deadline=data['deadline'],
                )
                db.session.add(assignment)
                db.session.flush()
                ensure_assignment_progress_for_enrolled_students(assignment)
                db.session.commit()
                flash('Задание добавлено')
                return redirect(url_for('admin_course_detail', id=course.course_id))
            except SQLAlchemyError:
                db.session.rollback()
                current_app.logger.exception('Training assignment create failed')
                flash('Не удалось сохранить задание. Проверьте данные и попробуйте еще раз.')

        return render_template('admin/assignment_form.html',
            title="Добавить задание",
            user_name=get_user_display_name(current_user),
            role=current_user.role,
            menu_items=get_menu_items('courses', 'admin'),
            today=datetime.now().strftime("%d.%m.%Y"),
            course=course,
            assignment=None
        )

    @app.route('/admin/assignment/edit/<int:id>', methods=['GET', 'POST'])
    @login_required
    def admin_edit_assignment(id):
        if current_user.role != 'admin':
            return "Доступ запрещен", 403

        assignment = TrainingAssignment.query.get_or_404(id)
        if request.method == 'POST':
            data, errors = get_assignment_form_data()
            if errors:
                for error in errors:
                    flash(error)
                return render_template('admin/assignment_form.html',
                    title="Редактировать задание",
                    user_name=get_user_display_name(current_user),
                    role=current_user.role,
                    menu_items=get_menu_items('courses', 'admin'),
                    today=datetime.now().strftime("%d.%m.%Y"),
                    course=assignment.course,
                    assignment={**data, 'assignment_id': assignment.assignment_id}
                )

            try:
                assignment.title = data['title']
                assignment.description = data['description']
                assignment.deadline = data['deadline']
                db.session.commit()
                flash('Задание обновлено')
                return redirect(url_for('admin_course_detail', id=assignment.course_id))
            except SQLAlchemyError:
                db.session.rollback()
                current_app.logger.exception('Training assignment update failed')
                flash('Не удалось обновить задание. Попробуйте еще раз.')

        return render_template('admin/assignment_form.html',
            title="Редактировать задание",
            user_name=get_user_display_name(current_user),
            role=current_user.role,
            menu_items=get_menu_items('courses', 'admin'),
            today=datetime.now().strftime("%d.%m.%Y"),
            course=assignment.course,
            assignment=assignment
        )

    @app.route('/admin/assignment/delete/<int:id>', methods=['POST'])
    @login_required
    def admin_delete_assignment(id):
        if current_user.role != 'admin':
            return "Доступ запрещен", 403

        assignment = TrainingAssignment.query.get_or_404(id)
        course_id = assignment.course_id
        try:
            db.session.delete(assignment)
            db.session.commit()
            flash('Задание удалено')
        except SQLAlchemyError:
            db.session.rollback()
            current_app.logger.exception('Training assignment delete failed')
            flash('Не удалось удалить задание. Попробуйте еще раз.')

        return redirect(url_for('admin_course_detail', id=course_id))

    @app.route('/admin/course/<int:course_id>/assign', methods=['POST'])
    @login_required
    def admin_assign_course(course_id):
        if current_user.role != 'admin':
            return "Доступ запрещен", 403

        course = TrainingCourse.query.get_or_404(course_id)
        kursant_id = request.form.get('kursant_id', '').strip()
        if not kursant_id:
            flash('Выберите курсанта для назначения курса')
            return redirect(url_for('admin_course_detail', id=course.course_id))

        try:
            kursant_id = int(kursant_id)
        except ValueError:
            flash('Выберите курсанта из списка')
            return redirect(url_for('admin_course_detail', id=course.course_id))

        student = Kursanty.query.get_or_404(kursant_id)
        enrollment = StudentCourse.query.filter_by(
            course_id=course.course_id,
            kursant_id=student.kursant_id,
        ).first()
        if enrollment:
            flash('Этот курс уже назначен выбранному курсанту')
            return redirect(url_for('admin_course_detail', id=course.course_id))

        try:
            db.session.add(StudentCourse(
                course_id=course.course_id,
                kursant_id=student.kursant_id,
            ))
            ensure_course_progress_for_student(course.course_id, student.kursant_id)
            db.session.commit()
            flash('Курс назначен курсанту')
        except SQLAlchemyError:
            db.session.rollback()
            current_app.logger.exception('Training course assign failed')
            flash('Не удалось назначить курс. Попробуйте еще раз.')

        return redirect(url_for('admin_course_detail', id=course.course_id))

    @app.route('/admin/course/<int:course_id>/unassign/<int:kursant_id>', methods=['POST'])
    @login_required
    def admin_unassign_course(course_id, kursant_id):
        if current_user.role != 'admin':
            return "Доступ запрещен", 403

        course = TrainingCourse.query.get_or_404(course_id)
        enrollment = StudentCourse.query.filter_by(
            course_id=course.course_id,
            kursant_id=kursant_id,
        ).first_or_404()
        assignment_ids = [
            assignment.assignment_id
            for assignment in TrainingAssignment.query.filter_by(course_id=course.course_id).all()
        ]

        try:
            if assignment_ids:
                StudentAssignmentProgress.query.filter(
                    StudentAssignmentProgress.kursant_id == kursant_id,
                    StudentAssignmentProgress.assignment_id.in_(assignment_ids),
                ).delete(synchronize_session=False)
            db.session.delete(enrollment)
            db.session.commit()
            flash('Назначение курса снято')
        except SQLAlchemyError:
            db.session.rollback()
            current_app.logger.exception('Training course unassign failed')
            flash('Не удалось снять назначение. Попробуйте еще раз.')

        return redirect(url_for('admin_course_detail', id=course.course_id))
