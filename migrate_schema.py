from sqlalchemy import inspect, text

from app import app
from extensions import db


def execute(statement):
    db.session.execute(text(statement))


def column_exists(table_name, column_name):
    inspector = inspect(db.session.connection())
    if not inspector.has_table(table_name):
        return False
    return any(column['name'] == column_name for column in inspector.get_columns(table_name))


def scalar(statement):
    return db.session.execute(text(statement)).scalar()


def migrate_schema():
    execute("""
        CREATE TABLE IF NOT EXISTS lesson_types (
            lesson_type_id SERIAL PRIMARY KEY,
            name VARCHAR(20) UNIQUE NOT NULL
        )
    """)
    execute("""
        INSERT INTO lesson_types (name)
        VALUES ('Теория'), ('Вождение'), ('Площадка')
        ON CONFLICT (name) DO NOTHING
    """)

    execute("""
        CREATE TABLE IF NOT EXISTS grounds (
            ground_id SERIAL PRIMARY KEY,
            instructor_id INTEGER REFERENCES instructors(instructor_id),
            address VARCHAR(200),
            surface_type VARCHAR(50),
            area INTEGER
        )
    """)
    execute("""
        ALTER TABLE grounds
        ADD COLUMN IF NOT EXISTS instructor_id INTEGER REFERENCES instructors(instructor_id)
    """)
    execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS grounds_instructor_id_uq
        ON grounds (instructor_id)
        WHERE instructor_id IS NOT NULL
    """)

    execute("""
        ALTER TABLE automobiles
        ADD COLUMN IF NOT EXISTS instructor_id INTEGER REFERENCES instructors(instructor_id)
    """)
    execute("""
        ALTER TABLE automobiles
        ADD COLUMN IF NOT EXISTS photo_filename VARCHAR(255)
    """)
    execute("""
        ALTER TABLE instructors
        ADD COLUMN IF NOT EXISTS phone VARCHAR(20)
    """)

    execute("""
        ALTER TABLE registration_requests
        ADD COLUMN IF NOT EXISTS login_username VARCHAR(50)
    """)
    execute("""
        ALTER TABLE registration_requests
        ADD COLUMN IF NOT EXISTS temporary_password VARCHAR(100)
    """)
    execute("""
        ALTER TABLE registration_requests
        ADD COLUMN IF NOT EXISTS reviewed_by_user_id INTEGER REFERENCES users(id)
    """)
    if column_exists('registration_requests', 'reviewed_by'):
        execute("""
            UPDATE registration_requests rr
            SET reviewed_by_user_id = u.id
            FROM users u
            WHERE rr.reviewed_by_user_id IS NULL
              AND rr.reviewed_by = u.username
        """)

    execute("""
        CREATE TABLE IF NOT EXISTS lesson_tariffs (
            tariff_id SERIAL PRIMARY KEY,
            lesson_type_id INTEGER REFERENCES lesson_types(lesson_type_id),
            price NUMERIC(10, 2) NOT NULL
        )
    """)
    execute("""
        ALTER TABLE lesson_tariffs
        ADD COLUMN IF NOT EXISTS lesson_type_id INTEGER REFERENCES lesson_types(lesson_type_id)
    """)
    if column_exists('lesson_tariffs', 'lesson_type'):
        execute("""
            UPDATE lesson_tariffs lt
            SET lesson_type_id = lty.lesson_type_id
            FROM lesson_types lty
            WHERE lt.lesson_type_id IS NULL
              AND lty.name = CASE
                  WHEN lt.lesson_type = 'Практика' THEN 'Вождение'
                  ELSE lt.lesson_type
              END
        """)
    execute("""
        DELETE FROM lesson_tariffs a
        USING lesson_tariffs b
        WHERE a.lesson_type_id IS NOT NULL
          AND b.lesson_type_id IS NOT NULL
          AND a.lesson_type_id = b.lesson_type_id
          AND a.tariff_id > b.tariff_id
    """)
    execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS lesson_tariffs_lesson_type_id_uq
        ON lesson_tariffs (lesson_type_id)
        WHERE lesson_type_id IS NOT NULL
    """)
    execute("""
        INSERT INTO lesson_tariffs (lesson_type_id, price)
        SELECT lt.lesson_type_id,
               CASE lt.name WHEN 'Теория' THEN 300 ELSE 500 END
        FROM lesson_types lt
        WHERE NOT EXISTS (
            SELECT 1
            FROM lesson_tariffs existing
            WHERE existing.lesson_type_id = lt.lesson_type_id
        )
    """)

    execute("""
        CREATE TABLE IF NOT EXISTS cancellation_history (
            cancellation_id SERIAL PRIMARY KEY,
            lesson_id INTEGER NOT NULL REFERENCES lessons(lesson_id),
            cancelled_by_user_id INTEGER REFERENCES users(id),
            reason VARCHAR(255),
            cancelled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    execute("""
        ALTER TABLE cancellation_history
        ADD COLUMN IF NOT EXISTS cancelled_by_user_id INTEGER REFERENCES users(id)
    """)
    if column_exists('cancellation_history', 'cancelled_by_name'):
        execute("""
            UPDATE cancellation_history ch
            SET cancelled_by_user_id = u.id
            FROM users u
            WHERE ch.cancelled_by_user_id IS NULL
              AND ch.cancelled_by_name = u.username
        """)
    if (
        column_exists('cancellation_history', 'cancelled_by_role')
        and column_exists('cancellation_history', 'cancelled_by_name')
    ):
        execute("""
            UPDATE cancellation_history ch
            SET cancelled_by_user_id = u.id
            FROM users u
            JOIN kursanty k ON u.kursant_id = k.kursant_id
            WHERE ch.cancelled_by_user_id IS NULL
              AND ch.cancelled_by_role = 'student'
              AND ch.cancelled_by_name = k.fullname
        """)
        execute("""
            UPDATE cancellation_history ch
            SET cancelled_by_user_id = u.id
            FROM users u
            JOIN instructors i ON u.instructor_id = i.instructor_id
            WHERE ch.cancelled_by_user_id IS NULL
              AND ch.cancelled_by_role = 'instructor'
              AND ch.cancelled_by_name = i.fullname
        """)

    execute("""
        ALTER TABLE lessons
        ADD COLUMN IF NOT EXISTS lesson_type_id INTEGER REFERENCES lesson_types(lesson_type_id)
    """)
    if column_exists('lessons', 'lesson_type'):
        execute("""
            UPDATE lessons l
            SET lesson_type_id = lt.lesson_type_id
            FROM lesson_types lt
            WHERE l.lesson_type_id IS NULL
              AND lt.name = CASE
                  WHEN l.lesson_type = 'Практика' THEN 'Вождение'
                  ELSE l.lesson_type
              END
        """)
    execute("""
        UPDATE lessons
        SET lesson_type_id = (SELECT lesson_type_id FROM lesson_types WHERE name = 'Вождение')
        WHERE lesson_type_id IS NULL
    """)

    execute("""
        ALTER TABLE payments
        ADD COLUMN IF NOT EXISTS created_by_user_id INTEGER REFERENCES users(id)
    """)
    if column_exists('payments', 'created_by'):
        execute("""
            UPDATE payments p
            SET created_by_user_id = u.id
            FROM users u
            WHERE p.created_by_user_id IS NULL
              AND p.created_by = u.username
        """)

    execute("""
        DO $$
        BEGIN
            ALTER TABLE users
            ADD CONSTRAINT users_kursant_id_fkey
            FOREIGN KEY (kursant_id) REFERENCES kursanty(kursant_id);
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)
    execute("""
        DO $$
        BEGIN
            ALTER TABLE users
            ADD CONSTRAINT users_instructor_id_fkey
            FOREIGN KEY (instructor_id) REFERENCES instructors(instructor_id);
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)
    execute("""
        DO $$
        BEGIN
            ALTER TABLE lessons
            ADD CONSTRAINT lessons_kursant_id_fkey
            FOREIGN KEY (kursant_id) REFERENCES kursanty(kursant_id);
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)
    execute("""
        DO $$
        BEGIN
            ALTER TABLE lessons
            ADD CONSTRAINT lessons_instructor_id_fkey
            FOREIGN KEY (instructor_id) REFERENCES instructors(instructor_id);
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)
    execute("""
        DO $$
        BEGIN
            ALTER TABLE lessons
            ADD CONSTRAINT lessons_auto_id_fkey
            FOREIGN KEY (auto_id) REFERENCES automobiles(auto_id);
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)
    execute("""
        DO $$
        BEGIN
            ALTER TABLE lessons
            ADD CONSTRAINT lessons_lesson_type_id_fkey
            FOREIGN KEY (lesson_type_id) REFERENCES lesson_types(lesson_type_id);
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)
    execute("""
        DO $$
        BEGIN
            ALTER TABLE lesson_tariffs
            ADD CONSTRAINT lesson_tariffs_lesson_type_id_fkey
            FOREIGN KEY (lesson_type_id) REFERENCES lesson_types(lesson_type_id);
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)

    execute("ALTER TABLE lesson_tariffs DROP COLUMN IF EXISTS lesson_type")
    execute("ALTER TABLE lessons DROP COLUMN IF EXISTS lesson_type")
    execute("DROP VIEW IF EXISTS lessons_full")
    execute("ALTER TABLE lessons DROP COLUMN IF EXISTS ground_id")
    execute("DROP TRIGGER IF EXISTS trg_lessons_count ON lessons")
    execute("DROP FUNCTION IF EXISTS update_lesson_count()")
    execute("DROP PROCEDURE IF EXISTS calc_lesson_statistics()")
    execute("ALTER TABLE kursanty DROP COLUMN IF EXISTS lesson_count")
    execute("ALTER TABLE payments DROP COLUMN IF EXISTS lesson_id")
    execute("ALTER TABLE payments DROP COLUMN IF EXISTS created_by")
    execute("ALTER TABLE registration_requests DROP COLUMN IF EXISTS reviewed_by")
    execute("ALTER TABLE cancellation_history DROP COLUMN IF EXISTS cancelled_by_role")
    execute("ALTER TABLE cancellation_history DROP COLUMN IF EXISTS cancelled_by_name")

    if scalar("SELECT count(*) FROM lessons WHERE lesson_type_id IS NULL") == 0:
        execute("ALTER TABLE lessons ALTER COLUMN lesson_type_id SET NOT NULL")

    if scalar("SELECT count(*) FROM lesson_tariffs WHERE lesson_type_id IS NULL") == 0:
        execute("ALTER TABLE lesson_tariffs ALTER COLUMN lesson_type_id SET NOT NULL")

    execute("""
        CREATE OR REPLACE VIEW lessons_full AS
        SELECT l.lesson_id,
               l.lesson_date,
               k.fullname AS kursant,
               i.fullname AS instructor,
               a.brand,
               g.address
        FROM lessons l
        JOIN kursanty k ON l.kursant_id = k.kursant_id
        JOIN instructors i ON l.instructor_id = i.instructor_id
        JOIN automobiles a ON l.auto_id = a.auto_id
        LEFT JOIN grounds g ON i.instructor_id = g.instructor_id
    """)
    execute("""
        CREATE OR REPLACE FUNCTION lesson_count_by_type(p_type VARCHAR)
        RETURNS INTEGER
        LANGUAGE plpgsql
        AS $$
        DECLARE
            result INTEGER;
        BEGIN
            SELECT COUNT(*) INTO result
            FROM lessons l
            JOIN lesson_types lt ON l.lesson_type_id = lt.lesson_type_id
            WHERE lt.name = p_type;

            RETURN result;
        END;
        $$;
    """)


if __name__ == '__main__':
    with app.app_context():
        migrate_schema()
        db.session.commit()
        print('Схема базы данных обновлена')
