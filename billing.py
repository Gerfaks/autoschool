from decimal import Decimal

from models import LessonTariff, LessonType


DEFAULT_TARIFFS = {
    'Теория': Decimal('300.00'),
    'Вождение': Decimal('500.00'),
    'Площадка': Decimal('500.00'),
}


def get_lesson_price(lesson_type):
    if not isinstance(lesson_type, str):
        lesson_type = lesson_type.name

    tariff = LessonTariff.query.join(LessonType).filter(LessonType.name == lesson_type).first()
    if tariff:
        return tariff.price
    return DEFAULT_TARIFFS.get(lesson_type, Decimal('500.00'))


def calculate_lessons_total(lessons):
    return sum((get_lesson_price(lesson.lesson_type) for lesson in lessons), Decimal('0.00'))
