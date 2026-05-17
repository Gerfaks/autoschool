# config.py
# Настройки подключения к базе данных и секретные ключи

import os

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
