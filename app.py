import os

from flask import Flask

from config import Config
from extensions import csrf, db, login_manager
from models import User
from routes.admin import register_admin_routes
from routes.auth import register_auth_routes
from routes.instructor import register_instructor_routes
from routes.profile import register_profile_routes
from routes.student import register_student_routes
from routes.todo import register_todo_routes
from utils import forbidden, restrict_role_sections


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    login_manager.login_view = 'login'
    login_manager.login_message = 'Пожалуйста, войдите в аккаунт'

    login_manager.user_loader(load_user)
    app.before_request(restrict_role_sections)
    app.register_error_handler(403, forbidden)

    register_auth_routes(app)
    register_admin_routes(app)
    register_instructor_routes(app)
    register_student_routes(app)
    register_profile_routes(app)
    register_todo_routes(app)

    return app


def load_user(uid):
    return db.session.get(User, int(uid))


app = create_app()


if __name__ == '__main__':
    os.makedirs('uploads', exist_ok=True)
    port = int(os.environ.get('PORT', 5001))
    host = os.environ.get('HOST', '127.0.0.1')
    print('=' * 50)
    print('Автошкола запущена')
    print(f'http://{host}:{port}')
    print('=' * 50)
    app.run(debug=app.config['DEBUG'], host=host, port=port)
