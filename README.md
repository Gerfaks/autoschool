# Autoschool

Flask-приложение для автошколы с ролями администратора, инструктора и курсанта.

## Локальный запуск

Нужно установить:

- Python 3.9 или новее
- PostgreSQL
- Git

## 1. Скачать проект

```bash
git clone https://github.com/Gerfaks/autoschool.git
cd autoschool
```

## 2. Создать виртуальное окружение

macOS / Linux:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Windows PowerShell:

```powershell
py -m venv venv
venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## 3. Создать базу PostgreSQL

В PostgreSQL нужно создать пустую базу:

```sql
CREATE DATABASE drivingschool;
```

## 4. Указать подключение к базе

macOS / Linux:

```bash
export DATABASE_URL='postgresql://postgres:YOUR_PASSWORD@localhost:5432/drivingschool'
```

Windows PowerShell:

```powershell
$env:DATABASE_URL = "postgresql://postgres:YOUR_PASSWORD@localhost:5432/drivingschool"
```

Замените `YOUR_PASSWORD` на пароль пользователя PostgreSQL.

## 5. Инициализировать таблицы

```bash
python init_db.py
```

Скрипт создаст таблицы, применит миграцию схемы и добавит администратора, если его ещё нет.

Данные для входа администратора по умолчанию:

```text
Логин: admin
Пароль: admin123
```

## 6. Запустить сайт

```bash
python app.py
```

После запуска открыть:

```text
http://127.0.0.1:5001
```

Остановить сервер можно сочетанием клавиш `Ctrl + C` в терминале.
