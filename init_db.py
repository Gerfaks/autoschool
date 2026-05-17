from werkzeug.security import generate_password_hash

from app import app
from extensions import db
from migrate_schema import migrate_schema
from models import User


DEFAULT_ADMIN_USERNAME = 'admin'
DEFAULT_ADMIN_PASSWORD = 'admin123'


with app.app_context():
    db.create_all()
    migrate_schema()

    admin = User.query.filter_by(username=DEFAULT_ADMIN_USERNAME).first()
    if not admin:
        admin = User(
            username=DEFAULT_ADMIN_USERNAME,
            password_hash=generate_password_hash(DEFAULT_ADMIN_PASSWORD, method='pbkdf2:sha256'),
            role='admin'
        )
        db.session.add(admin)
        print(f'Создан администратор: {DEFAULT_ADMIN_USERNAME} / {DEFAULT_ADMIN_PASSWORD}')
    else:
        print(f'Администратор {DEFAULT_ADMIN_USERNAME} уже существует')

    db.session.commit()
    print('База данных готова к работе')
