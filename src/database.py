# src/database.py
import datetime
import logging
import sqlite3
from pathlib import Path
from typing import Any

import shortuuid  # Для генерации коротких ключей

# --- Настройка Логгера ---
# Используем стандартный логгер, т.к. основная настройка будет в app.py
logger = logging.getLogger(__name__)
# Установим базовый уровень, чтобы видеть сообщения из этого модуля
# logging.basicConfig(level=logging.INFO) # Лучше настроить в app.py

# --- Определение Путей ---
# Определяем путь к директории 'src', где лежит этот файл
SRC_DIR = Path(__file__).parent.resolve()
# Путь к директории 'data' на уровень выше 'src'
DATA_DIR = SRC_DIR / "data"
# Полный путь к файлу базы данных
DB_PATH = DATA_DIR / "pastes.db"


# --- Инициализация Базы Данных ---
# --- Инициализация Базы Данных ---
def init_db():
    """
    Инициализирует файл БД (внутри src/data) и создает таблицы pastes и users.
    """
    try:
        # Убедимся, что папка 'src/data' существует
        DATA_DIR.mkdir(exist_ok=True)
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        logger.info(
            f"Проверка/создание таблиц в БД: {DB_PATH}"
        )  # Путь теперь будет src/data/pastes.db

        # --- Таблица Паст ---
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pastes (
                key TEXT PRIMARY KEY, content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                language TEXT, expires_at TIMESTAMP,
                user_id INTEGER,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_pastes_key ON pastes (key);")
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_pastes_user_id ON pastes (user_id);"
        )
        logger.debug("Таблица 'pastes' проверена/создана.")

        # --- Таблица Пользователей ---
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT, yandex_id TEXT UNIQUE NOT NULL,
                login TEXT, display_name TEXT, email TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, last_login TIMESTAMP
            )
        """)
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_users_yandex_id ON users (yandex_id);"
        )
        logger.debug("Таблица 'users' проверена/создана.")

        conn.commit()
        conn.close()
        logger.info("Инициализация базы данных успешно завершена.")
    except sqlite3.Error as e:
        logger.critical(
            f"Критическая ошибка при инициализации БД '{DB_PATH}': {e}", exc_info=True
        )
        raise


# --- Функции для Работы с Пастами ---
# --- Функции для пользователей (без изменений) ---
def get_or_create_user(yandex_data: dict[str, Any]) -> int | None:
    # ... (код функции без изменений, использует DB_PATH) ...
    yandex_id = yandex_data.get("id")
    if not yandex_id:
        return None
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        now = datetime.datetime.now(datetime.timezone.utc)
        cursor.execute("SELECT id FROM users WHERE yandex_id = ?", (yandex_id,))
        user_row = cursor.fetchone()
        if user_row:
            user_id = user_row[0]
            cursor.execute(
                "UPDATE users SET last_login = ? WHERE id = ?", (now, user_id)
            )
            conn.commit()
            logger.info(
                f"Пользователь найден (ID: {user_id}, Yandex ID: {yandex_id}), обновлен last_login."
            )
            return user_id
        else:
            login = yandex_data.get("login")
            display_name = yandex_data.get("display_name")
            email = yandex_data.get("default_email")
            cursor.execute(
                "INSERT INTO users (yandex_id, login, display_name, email, last_login) VALUES (?, ?, ?, ?, ?)",
                (yandex_id, login, display_name, email, now),
            )
            user_id = cursor.lastrowid
            conn.commit()
            logger.info(
                f"Создан новый пользователь (ID: {user_id}, Yandex ID: {yandex_id}, Login: {login})."
            )
            return user_id
    except sqlite3.Error as e:
        logger.error(
            f"Ошибка при поиске/создании пользователя (Yandex ID: {yandex_id}): {e}",
            exc_info=True,
        )
        return None
    finally:
        if conn:
            conn.close()


# --- Функции для паст (без изменений в логике, только путь к БД) ---
def add_paste(
    content: str, user_id: int | None = None, language: str | None = None
) -> str | None:
    # ... (код функции без изменений, использует DB_PATH) ...
    if not isinstance(content, str) or not content.strip():
        return None
    su = shortuuid.ShortUUID(
        alphabet="23456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghjkmnpqrstuvwxyz"
    )
    paste_key = su.random(length=8)
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor: Any = conn.cursor()
        cursor.execute(
            "INSERT INTO pastes (key, content, language, user_id) VALUES (?, ?, ?, ?)",
            (paste_key, content, language, user_id),
        )
        conn.commit()
        logger.info(f"Паста {paste_key} добавлена (user_id={user_id}).")
        return paste_key
    except sqlite3.IntegrityError:
        logger.warning(f"Коллизия ключа '{paste_key}', генерирую новый...")
        if conn:
            conn.close()
        return add_paste(content, user_id, language)
    except sqlite3.Error as e:
        logger.error(f"Ошибка добавления пасты в БД: {e}", exc_info=True)
        return None
    finally:
        if conn:
            conn.close()


def get_paste(paste_key: str) -> tuple[str, str | None, int | None] | None:
    # ... (код функции без изменений, использует DB_PATH) ...
    if not isinstance(paste_key, str) or not paste_key:
        return None
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            "SELECT content, language, user_id FROM pastes WHERE key = ?", (paste_key,)
        )
        row = cursor.fetchone()
        if row:
            return row["content"], row["language"], row["user_id"]
        else:
            return None
    except sqlite3.Error as e:
        logger.error(f"Ошибка получения пасты '{paste_key}': {e}", exc_info=True)
        return None
    finally:
        if conn:
            conn.close()


def get_user_pastes(user_id: int, limit: int = 50) -> list[dict[str, Any]]:
    # ... (код функции без изменений, использует DB_PATH) ...
    if not user_id:
        return []
    conn = None
    pastes = []
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            "SELECT key, content, created_at, language FROM pastes WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit),
        )
        rows = cursor.fetchall()
        for row in rows:
            pastes.append(dict(row))
        return pastes
    except sqlite3.Error as e:
        logger.error(f"Ошибка получения паст для user_id={user_id}: {e}", exc_info=True)
        return []
    finally:
        if conn:
            conn.close()
