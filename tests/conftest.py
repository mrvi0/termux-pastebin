# tests/conftest.py
import pytest
import tempfile
import os
from pathlib import Path
import sqlite3

# Импортируем наше Flask приложение и модуль базы данных
# Нужно убедиться, что src находится в PYTHONPATH при запуске тестов
# pytest обычно делает это автоматически, если запускать из корня проекта
from src import app as flask_app # Даем псевдоним, чтобы не конфликтовать
from src import database

@pytest.fixture(scope="function") # Фикстура будет создаваться для КАЖДОЙ тестовой функции
def test_db():
    """Фикстура, создающая временную SQLite базу данных в памяти."""
    # Используем БД в памяти для скорости и изоляции тестов
    # :memory: создает временную БД, которая исчезнет после закрытия соединения
    conn = sqlite3.connect(":memory:", detect_types=sqlite3.PARSE_DECLTYPES)
    # Применяем ту же схему, что и в основном приложении
    # Копируем SQL из database.init_db() или вызываем его, подменив DB_PATH
    cursor = conn.cursor()
    # Создаем таблицы
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS pastes (
            key TEXT PRIMARY KEY, content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            language TEXT, expires_at TIMESTAMP,
            user_id INTEGER,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
        )''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_pastes_key ON pastes (key);')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_pastes_user_id ON pastes (user_id);')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT, yandex_id TEXT UNIQUE NOT NULL,
            login TEXT, display_name TEXT, email TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, last_login TIMESTAMP
        )''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_yandex_id ON users (yandex_id);')
    conn.commit()

    # --- Подмена пути к БД в модуле database на время теста ---
    # Сохраняем оригинальный путь
    original_db_path = database.DB_PATH
    # Устанавливаем путь к БД в памяти (не путь к файлу, а указание для connect)
    # К сожалению, connect(":memory:") создает НОВУЮ БД каждый раз.
    # Поэтому лучше использовать временный файл.

    # --- Используем временный ФАЙЛ для БД ---
    db_fd, db_path = tempfile.mkstemp(suffix=".db", prefix="test_paste_")
    os.close(db_fd) # Закрываем дескриптор, нам нужен только путь
    db_path_obj = Path(db_path)
    print(f"\n[Fixture] Создана временная БД: {db_path_obj}")

    # Подменяем путь в модуле database
    database.DB_PATH = db_path_obj
    # Инициализируем таблицы в этом временном файле
    database.init_db()

    # Предоставляем путь к временной БД тестам (если им нужно)
    yield db_path_obj

    # --- Очистка после теста ---
    print(f"[Fixture] Удаление временной БД: {db_path_obj}")
    # Закрываем соединения (на всякий случай, если тесты оставили открытыми)
    # database._close_lingering_connections() # Если бы была такая функция
    db_path_obj.unlink() # Удаляем временный файл
    # Восстанавливаем оригинальный путь (хотя для тестов это не обязательно)
    # database.DB_PATH = original_db_path


@pytest.fixture(scope="function")
def client(test_db): # Эта фикстура зависит от фикстуры test_db
    """Фикстура, создающая тестовый клиент Flask."""
    # Устанавливаем режим тестирования
    flask_app.app.config['TESTING'] = True
    # Отключаем обработку ошибок Flask, чтобы видеть оригинальные исключения в тестах
    flask_app.app.config['PROPAGATE_EXCEPTIONS'] = True
    # Используем другой секретный ключ для тестов
    flask_app.app.config['SECRET_KEY'] = 'testing_secret_key'
    # Отключаем Basic Auth для большинства тестов (если нужно)
    # flask_app.app.config['BASIC_AUTH_ENABLED'] = False # Или можно мокировать basic_auth

    # Создаем тестовый клиент
    with flask_app.app.test_client() as test_client:
        # Устанавливаем контекст приложения, чтобы url_for и session работали
        with flask_app.app.app_context():
            # Вызываем инициализацию БД здесь еще раз (на всякий случай)
            # Но test_db фикстура уже должна была это сделать
            # database.init_db()
            yield test_client # Предоставляем клиент тестам

    # Очистка после теста (если нужна)