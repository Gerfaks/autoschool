from datetime import datetime

from flask import jsonify, render_template, request
from flask_login import current_user, login_required
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from extensions import db
from models import TodoCategory, TodoItem
from utils import get_menu_items, get_user_display_name


VALID_PRIORITIES = {'low', 'normal', 'high'}
PRIORITY_ORDER = {
    'high': 0,
    'normal': 1,
    'low': 2,
}


def parse_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in {'1', 'true', 'yes', 'on'}
    return bool(value)


def parse_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except ValueError:
        raise ValueError('Укажите срок в формате YYYY-MM-DD')


def payload_value(data, camel_key, snake_key=None, default=None):
    if camel_key in data:
        return data.get(camel_key)
    if snake_key and snake_key in data:
        return data.get(snake_key)
    return default


def serialize_category(category):
    return {
        'id': category.category_id,
        'name': category.name,
        'color': category.color or '#b84d3f',
    }


def serialize_item(item):
    today = datetime.now().date()
    category = item.category
    is_overdue = bool(item.due_date and item.due_date < today and not item.is_complete)
    return {
        'id': item.todo_id,
        'title': item.title,
        'description': item.description or '',
        'isComplete': item.is_complete,
        'priority': item.priority,
        'dueDate': item.due_date.strftime('%Y-%m-%d') if item.due_date else '',
        'dueDateLabel': item.due_date.strftime('%d.%m.%Y') if item.due_date else 'Без срока',
        'isOverdue': is_overdue,
        'categoryId': item.category_id,
        'category': serialize_category(category) if category else None,
        'createdAt': item.created_at.strftime('%d.%m.%Y %H:%M') if item.created_at else '',
        'updatedAt': item.updated_at.strftime('%d.%m.%Y %H:%M') if item.updated_at else '',
    }


def get_owned_category(category_id):
    if not category_id:
        return None
    try:
        category_id = int(category_id)
    except (TypeError, ValueError):
        return None
    return TodoCategory.query.filter_by(
        category_id=category_id,
        user_id=current_user.id,
    ).first()


def get_owned_item_or_404(item_id):
    return TodoItem.query.filter_by(
        todo_id=item_id,
        user_id=current_user.id,
    ).first_or_404()


def get_item_counts():
    today = datetime.now().date()
    items = TodoItem.query.filter_by(user_id=current_user.id).all()
    completed = sum(1 for item in items if item.is_complete)
    overdue = sum(1 for item in items if item.due_date and item.due_date < today and not item.is_complete)
    return {
        'total': len(items),
        'active': len(items) - completed,
        'completed': completed,
        'overdue': overdue,
    }


def build_items_query():
    query = TodoItem.query.filter_by(user_id=current_user.id)
    status = request.args.get('status', 'all')
    category_id = request.args.get('category_id', '').strip()
    priority = request.args.get('priority', '').strip()
    search = request.args.get('q', '').strip()
    today = datetime.now().date()

    if status == 'active':
        query = query.filter(TodoItem.is_complete.is_(False))
    elif status == 'completed':
        query = query.filter(TodoItem.is_complete.is_(True))
    elif status == 'overdue':
        query = query.filter(
            TodoItem.is_complete.is_(False),
            TodoItem.due_date.isnot(None),
            TodoItem.due_date < today,
        )

    if category_id:
        try:
            query = query.filter(TodoItem.category_id == int(category_id))
        except ValueError:
            query = query.filter(TodoItem.category_id.is_(None))

    if priority in VALID_PRIORITIES:
        query = query.filter(TodoItem.priority == priority)

    if search:
        pattern = f'%{search}%'
        query = query.filter(or_(
            TodoItem.title.ilike(pattern),
            TodoItem.description.ilike(pattern),
        ))

    return query


def sort_items(items):
    return sorted(items, key=lambda item: (
        item.is_complete,
        item.due_date is None,
        item.due_date or datetime.max.date(),
        PRIORITY_ORDER.get(item.priority, 1),
        item.created_at or datetime.min,
    ))


def register_todo_routes(app):
    @app.route('/todo')
    @login_required
    def todo_page():
        return render_template(
            'todo.html',
            title='Задачи',
            user_name=get_user_display_name(current_user),
            role=current_user.role,
            menu_items=get_menu_items('todo', current_user.role),
            today=datetime.now().strftime('%d.%m.%Y'),
        )

    @app.route('/api/todo/categories', methods=['GET', 'POST'])
    @login_required
    def todo_categories():
        if request.method == 'GET':
            categories = TodoCategory.query.filter_by(user_id=current_user.id).order_by(TodoCategory.name).all()
            return jsonify([serialize_category(category) for category in categories])

        data = request.get_json(silent=True) or {}
        name = (data.get('name') or '').strip()
        color = (data.get('color') or '#b84d3f').strip() or '#b84d3f'
        if not name:
            return jsonify({'error': 'Укажите название категории'}), 400

        category = TodoCategory(user_id=current_user.id, name=name, color=color)
        db.session.add(category)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            return jsonify({'error': 'Такая категория уже есть'}), 409

        return jsonify(serialize_category(category)), 201

    @app.route('/api/todo/categories/<int:category_id>', methods=['PUT', 'DELETE'])
    @login_required
    def todo_category_detail(category_id):
        category = get_owned_category(category_id)
        if not category:
            return jsonify({'error': 'Категория не найдена'}), 404

        if request.method == 'DELETE':
            TodoItem.query.filter_by(
                user_id=current_user.id,
                category_id=category.category_id,
            ).update({'category_id': None})
            db.session.delete(category)
            db.session.commit()
            return jsonify({'ok': True})

        data = request.get_json(silent=True) or {}
        name = (data.get('name') or '').strip()
        color = (data.get('color') or category.color or '#b84d3f').strip() or '#b84d3f'
        if not name:
            return jsonify({'error': 'Укажите название категории'}), 400

        category.name = name
        category.color = color
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            return jsonify({'error': 'Такая категория уже есть'}), 409

        return jsonify(serialize_category(category))

    @app.route('/api/todo/items', methods=['GET', 'POST'])
    @login_required
    def todo_items():
        if request.method == 'GET':
            items = sort_items(build_items_query().all())
            return jsonify({
                'items': [serialize_item(item) for item in items],
                'counts': get_item_counts(),
            })

        data = request.get_json(silent=True) or {}
        title = (data.get('title') or '').strip()
        if not title:
            return jsonify({'error': 'Укажите название дела'}), 400

        category_id = payload_value(data, 'categoryId', 'category_id')
        category = get_owned_category(category_id) if category_id else None
        if category_id and not category:
            return jsonify({'error': 'Категория не найдена'}), 404

        priority = data.get('priority') or 'normal'
        if priority not in VALID_PRIORITIES:
            priority = 'normal'

        try:
            due_date = parse_date(payload_value(data, 'dueDate', 'due_date'))
        except ValueError as error:
            return jsonify({'error': str(error)}), 400

        item = TodoItem(
            user_id=current_user.id,
            category_id=category.category_id if category else None,
            title=title,
            description=(data.get('description') or '').strip() or None,
            is_complete=parse_bool(payload_value(data, 'isComplete', 'is_complete', False)),
            priority=priority,
            due_date=due_date,
        )
        db.session.add(item)
        db.session.commit()
        return jsonify(serialize_item(item)), 201

    @app.route('/api/todo/items/<int:item_id>', methods=['PUT', 'DELETE'])
    @login_required
    def todo_item_detail(item_id):
        item = get_owned_item_or_404(item_id)

        if request.method == 'DELETE':
            db.session.delete(item)
            db.session.commit()
            return jsonify({'ok': True})

        data = request.get_json(silent=True) or {}
        title = (data.get('title') or '').strip()
        if not title:
            return jsonify({'error': 'Укажите название дела'}), 400

        category_id = payload_value(data, 'categoryId', 'category_id')
        category = get_owned_category(category_id) if category_id else None
        if category_id and not category:
            return jsonify({'error': 'Категория не найдена'}), 404

        priority = data.get('priority') or 'normal'
        if priority not in VALID_PRIORITIES:
            priority = 'normal'

        try:
            due_date = parse_date(payload_value(data, 'dueDate', 'due_date'))
        except ValueError as error:
            return jsonify({'error': str(error)}), 400

        item.category_id = category.category_id if category else None
        item.title = title
        item.description = (data.get('description') or '').strip() or None
        item.is_complete = parse_bool(payload_value(data, 'isComplete', 'is_complete', False))
        item.priority = priority
        item.due_date = due_date
        item.updated_at = datetime.utcnow()

        try:
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            return jsonify({'error': 'Не удалось сохранить дело'}), 500

        return jsonify(serialize_item(item))
