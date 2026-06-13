from datetime import datetime

from flask_login import UserMixin
from werkzeug.security import check_password_hash

from extensions import db


class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True)
    password_hash = db.Column(db.String(256))
    role = db.Column(db.String(20), default='student')
    kursant_id = db.Column(db.Integer, db.ForeignKey('kursanty.kursant_id'), nullable=True)
    instructor_id = db.Column(db.Integer, db.ForeignKey('instructors.instructor_id'), nullable=True)

    def check_password(self, pwd):
        return check_password_hash(self.password_hash, pwd)


class RegistrationRequest(db.Model):
    __tablename__ = 'registration_requests'

    request_id = db.Column(db.Integer, primary_key=True)
    fullname = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    email = db.Column(db.String(100))
    role = db.Column(db.String(20), nullable=False)
    experience = db.Column(db.Integer)
    license_category = db.Column(db.String(10))
    category_type = db.Column(db.String(10))
    passport_number = db.Column(db.String(50))
    driver_license_number = db.Column(db.String(50))
    documents_photo = db.Column(db.String(255))
    status = db.Column(db.String(20), default='pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    reviewed_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    reviewed_at = db.Column(db.DateTime)
    login_username = db.Column(db.String(50))
    temporary_password = db.Column(db.String(100))
    comment = db.Column(db.Text)

    reviewer = db.relationship('User', foreign_keys=[reviewed_by_user_id])


class InstructorSchedule(db.Model):
    __tablename__ = 'instructor_schedule'

    schedule_id = db.Column(db.Integer, primary_key=True)
    instructor_id = db.Column(db.Integer, db.ForeignKey('instructors.instructor_id'))
    lesson_date = db.Column(db.Date, nullable=False)
    lesson_time = db.Column(db.Time, nullable=False)
    is_booked = db.Column(db.Boolean, default=False)
    booked_by = db.Column(db.Integer, db.ForeignKey('kursanty.kursant_id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Kursanty(db.Model):
    __tablename__ = 'kursanty'

    kursant_id = db.Column(db.Integer, primary_key=True)
    fullname = db.Column(db.String(100))
    phone = db.Column(db.String(20))
    category_type = db.Column(db.String(10))
    email = db.Column(db.String(100))


class Instructors(db.Model):
    __tablename__ = 'instructors'

    instructor_id = db.Column(db.Integer, primary_key=True)
    fullname = db.Column(db.String(100))
    phone = db.Column(db.String(20))
    experience = db.Column(db.Integer)
    license_category = db.Column(db.String(10))


class Grounds(db.Model):
    __tablename__ = 'grounds'

    ground_id = db.Column(db.Integer, primary_key=True)
    instructor_id = db.Column(db.Integer, db.ForeignKey('instructors.instructor_id'), nullable=True)
    address = db.Column(db.String(200))
    surface_type = db.Column(db.String(50))
    area = db.Column(db.Integer)

    instructor = db.relationship('Instructors', backref='grounds')


class Automobiles(db.Model):
    __tablename__ = 'automobiles'

    auto_id = db.Column(db.Integer, primary_key=True)
    instructor_id = db.Column(db.Integer, db.ForeignKey('instructors.instructor_id'), nullable=True)
    brand = db.Column(db.String(50))
    model = db.Column(db.String(50))
    plate = db.Column(db.String(20))
    vehicle_type = db.Column(db.String(30))
    photo_filename = db.Column(db.String(255))

    instructor = db.relationship('Instructors', backref='cars')


class Lessons(db.Model):
    __tablename__ = 'lessons'

    lesson_id = db.Column(db.Integer, primary_key=True)
    lesson_date = db.Column(db.Date)
    lesson_time = db.Column(db.Time)
    lesson_type_id = db.Column(db.Integer, db.ForeignKey('lesson_types.lesson_type_id'), nullable=False)
    kursant_id = db.Column(db.Integer, db.ForeignKey('kursanty.kursant_id'))
    instructor_id = db.Column(db.Integer, db.ForeignKey('instructors.instructor_id'))
    auto_id = db.Column(db.Integer, db.ForeignKey('automobiles.auto_id'))
    comments = db.Column(db.String(255))
    status = db.Column(db.String(20), default='pending')

    lesson_type = db.relationship('LessonType')
    kursant = db.relationship('Kursanty')
    instructor = db.relationship('Instructors')
    automobile = db.relationship('Automobiles')


class LessonType(db.Model):
    __tablename__ = 'lesson_types'

    lesson_type_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(20), unique=True, nullable=False)


class LessonTariff(db.Model):
    __tablename__ = 'lesson_tariffs'

    tariff_id = db.Column(db.Integer, primary_key=True)
    lesson_type_id = db.Column(db.Integer, db.ForeignKey('lesson_types.lesson_type_id'), unique=True, nullable=False)
    price = db.Column(db.Numeric(10, 2), nullable=False)

    lesson_type = db.relationship('LessonType')


class CancellationHistory(db.Model):
    __tablename__ = 'cancellation_history'

    cancellation_id = db.Column(db.Integer, primary_key=True)
    lesson_id = db.Column(db.Integer, db.ForeignKey('lessons.lesson_id'), nullable=False)
    cancelled_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    reason = db.Column(db.String(255))
    cancelled_at = db.Column(db.DateTime, default=datetime.utcnow)

    lesson = db.relationship('Lessons', backref='cancellations')
    cancelled_by = db.relationship('User')


class Payments(db.Model):
    __tablename__ = 'payments'

    payment_id = db.Column(db.Integer, primary_key=True)
    kursant_id = db.Column(db.Integer, db.ForeignKey('kursanty.kursant_id'))
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    payment_date = db.Column(db.Date, default=datetime.utcnow)
    payment_method = db.Column(db.String(20), default='cash')
    comment = db.Column(db.String(255))
    created_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    created_by_user = db.relationship('User')


class TrainingCourse(db.Model):
    __tablename__ = 'training_courses'

    course_id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text)
    category = db.Column(db.String(20))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    assignments = db.relationship(
        'TrainingAssignment',
        back_populates='course',
        cascade='all, delete-orphan',
    )
    enrollments = db.relationship(
        'StudentCourse',
        back_populates='course',
        cascade='all, delete-orphan',
    )


class TrainingAssignment(db.Model):
    __tablename__ = 'training_assignments'

    assignment_id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey('training_courses.course_id', ondelete='CASCADE'), nullable=False)
    title = db.Column(db.String(160), nullable=False)
    description = db.Column(db.Text)
    deadline = db.Column(db.Date)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    course = db.relationship('TrainingCourse', back_populates='assignments')
    progress_entries = db.relationship(
        'StudentAssignmentProgress',
        back_populates='assignment',
        cascade='all, delete-orphan',
    )


class StudentCourse(db.Model):
    __tablename__ = 'student_courses'
    __table_args__ = (
        db.UniqueConstraint('course_id', 'kursant_id', name='student_courses_course_student_uq'),
    )

    enrollment_id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey('training_courses.course_id', ondelete='CASCADE'), nullable=False)
    kursant_id = db.Column(db.Integer, db.ForeignKey('kursanty.kursant_id', ondelete='CASCADE'), nullable=False)
    assigned_at = db.Column(db.DateTime, default=datetime.utcnow)

    course = db.relationship('TrainingCourse', back_populates='enrollments')
    student = db.relationship('Kursanty')


class StudentAssignmentProgress(db.Model):
    __tablename__ = 'student_assignment_progress'
    __table_args__ = (
        db.UniqueConstraint('assignment_id', 'kursant_id', name='student_assignment_progress_assignment_student_uq'),
    )

    progress_id = db.Column(db.Integer, primary_key=True)
    assignment_id = db.Column(db.Integer, db.ForeignKey('training_assignments.assignment_id', ondelete='CASCADE'), nullable=False)
    kursant_id = db.Column(db.Integer, db.ForeignKey('kursanty.kursant_id', ondelete='CASCADE'), nullable=False)
    status = db.Column(db.String(20), default='not_started', nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    assignment = db.relationship('TrainingAssignment', back_populates='progress_entries')
    student = db.relationship('Kursanty')


class TodoCategory(db.Model):
    __tablename__ = 'todo_categories'
    __table_args__ = (
        db.UniqueConstraint('user_id', 'name', name='todo_categories_user_name_uq'),
    )

    category_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    name = db.Column(db.String(80), nullable=False)
    color = db.Column(db.String(20), default='#b84d3f')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User')
    items = db.relationship('TodoItem', back_populates='category')


class TodoItem(db.Model):
    __tablename__ = 'todo_items'

    todo_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('todo_categories.category_id', ondelete='SET NULL'), nullable=True)
    title = db.Column(db.String(160), nullable=False)
    description = db.Column(db.Text)
    is_complete = db.Column(db.Boolean, default=False, nullable=False)
    priority = db.Column(db.String(20), default='normal', nullable=False)
    due_date = db.Column(db.Date)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = db.relationship('User')
    category = db.relationship('TodoCategory', back_populates='items')
