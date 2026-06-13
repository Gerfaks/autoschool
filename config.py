# config.py
# Настройки подключения к базе данных и секретные ключи

import os


def load_local_env():
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    try:
        with open(env_path, encoding='utf-8') as env_file:
            for line in env_file:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                key, value = line.split('=', 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value
    except FileNotFoundError:
        pass


load_local_env()


class Config:
    # Секретный ключ для защиты сессий (нужен для авторизации)
    # Для реального запуска задай SECRET_KEY в переменных окружения.
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-change-me'
    
    # Подключение к PostgreSQL
    # ФОРМАТ: postgresql://пользователь:пароль@хост:порт/имя_базы
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'postgresql://postgres:postgres@localhost:5432/drivingschool'
    
    # Отключаем отслеживание изменений (экономит ресурсы, убирает предупреждения)
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    DEBUG = os.environ.get('FLASK_DEBUG') == '1'
