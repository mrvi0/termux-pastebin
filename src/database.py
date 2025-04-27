# src/database.py
import contextlib
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


# --- Конвертер для TIMESTAMP ---
# SQLite может хранить timestamp как строки ISO 8601 или Unix timestamp.
# Этот конвертер пытается распознать строку ISO 8601.
def adapt_datetime_iso(val):
    """Adapts datetime.datetime to timezone-naive ISO 8601 date."""
    return val.isoformat(" ")


def convert_timestamp(val):
    """Converts an ISO 8601 datetime string to a datetime object."""
    # val приходит как bytes, декодируем
    try:
        # Пытаемся распознать формат с микросекундами и без часового пояса
        # (как обычно сохраняет CURRENT_TIMESTAMP в SQLite)
        # Например: '2024-04-27 12:30:55.123456'
        dt = datetime.datetime.fromisoformat(val.decode())
        return dt
    except (ValueError, TypeError):
        logger.warning(
            f"Не удалось преобразовать значение timestamp '{val}' в datetime."
        )
        return None  # Возвращаем None в случае ошибки


# Регистрируем адаптер и конвертер
sqlite3.register_adapter(
    datetime.datetime, adapt_datetime_iso
)  # Пока не используем, но может пригодиться
sqlite3.register_converter(
    "timestamp", convert_timestamp
)  # Связываем тип TIMESTAMP с нашей функцией


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
        with contextlib.suppress(sqlite3.Error):  # Лучше ловить конкретную ошибку
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
            # --- Используем suppress ---
            with contextlib.suppress(sqlite3.Error):  # Ловим sqlite3.Error
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
    conn: sqlite3.Connection | None = None
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
        # Закрываем перед рекурсией (здесь suppress не нужен)
        if conn:
            with contextlib.suppress(sqlite3.Error):
                conn.close()
            conn = None  # Сбрасываем conn после закрытия
        # --- КОНЕЦ ИЗМЕНЕНИЯ ---
        return add_paste(content, user_id, language)  # Рекурсивный вызов
    except sqlite3.Error as e:
        logger.error(f"Ошибка добавления пасты в БД: {e}", exc_info=True)
        return None
    finally:
        if (
            conn
        ):  # Закрываем, только если он не был закрыт в блоке except IntegrityError
            with contextlib.suppress(sqlite3.Error):
                conn.close()


def get_paste(paste_key: str) -> tuple[str, str | None, int | None] | None:
    # ... (код функции без изменений, использует DB_PATH) ...
    if not isinstance(paste_key, str) or not paste_key:
        return None
    conn: sqlite3.Connection | None = None
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
            # --- Используем suppress ---
            with contextlib.suppress(sqlite3.Error):  # Ловим sqlite3.Error
                conn.close()


def get_user_pastes(user_id: int, limit: int = 50) -> list[dict[str, Any]]:
    """Получает последние N паст пользователя, преобразуя created_at в datetime."""
    if not user_id:
        return []
    conn: sqlite3.Connection | None = None
    pastes: list[dict[str, Any]] = []
    try:
        conn = sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES)
        if conn is None:
            return []
        conn.row_factory = sqlite3.Row
        cursor: Any = conn.cursor()
        logger.debug(f"Получение паст для user_id={user_id} (limit={limit})")
        cursor.execute(
            # Убедимся, что created_at имеет тип TIMESTAMP при создании таблицы
            "SELECT key, content, created_at, language FROM pastes WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit),
        )
        rows = cursor.fetchall()
        for row_raw in rows:
            # Преобразуем sqlite3.Row в словарь
            paste_dict = dict(row_raw)
            # created_at должен быть уже преобразован конвертером,
            # но на всякий случай проверим и преобразуем, если это строка
            created_at_val = paste_dict.get("created_at")
            if isinstance(created_at_val, str):
                converted_dt = convert_timestamp(
                    created_at_val.encode()
                )  # Пытаемся конвертировать строку
                if converted_dt:
                    paste_dict["created_at"] = converted_dt
                else:
                    logger.warning(
                        f"Повторная попытка конвертации created_at не удалась для {created_at_val}"
                    )
                    # Оставляем как есть или ставим None
                    # paste_dict['created_at'] = None
            elif not isinstance(created_at_val, datetime.datetime):
                logger.warning(
                    f"Неожиданный тип для created_at: {type(created_at_val)}"
                )
                # Можно оставить как есть или None
                # paste_dict['created_at'] = None

            pastes.append(paste_dict)
        return pastes
    except sqlite3.Error as e:
        logger.error(f"Ошибка получения паст для user_id={user_id}: {e}", exc_info=True)
        return []
    finally:
        if conn:
            # --- Используем suppress ---
            with contextlib.suppress(sqlite3.Error):  # Ловим sqlite3.Error
                conn.close()
