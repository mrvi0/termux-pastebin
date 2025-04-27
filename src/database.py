# src/database.py
import contextlib
import datetime
import logging
import sqlite3
from pathlib import Path
from typing import Any

import shortuuid  # Для генерации коротких ключей

from . import security

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
def init_db():
    """Инициализирует БД и таблицы pastes и users."""
    try:
        DATA_DIR.mkdir(exist_ok=True)
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        logger.info(f"Проверка/создание таблиц в БД: {DB_PATH}")

        # --- Таблица Паст ---
        # Добавляем is_public
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pastes (
                key TEXT PRIMARY KEY, content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                language TEXT, expires_at TIMESTAMP,
                user_id INTEGER,
                is_public BOOLEAN DEFAULT 1 CHECK(is_public IN (0, 1)), -- <-- ДОБАВЛЕНО
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
            )
        """)
        # Попробуем добавить колонку, если таблица уже существует (может упасть, если колонка есть)
        with contextlib.suppress(sqlite3.OperationalError):
            cursor.execute(
                "ALTER TABLE pastes ADD COLUMN is_public BOOLEAN DEFAULT 1 CHECK(is_public IN (0, 1))"
            )
            logger.info("Добавлена колонка 'is_public' в таблицу 'pastes'.")

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_pastes_key ON pastes (key);")
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_pastes_user_id ON pastes (user_id);"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_pastes_public ON pastes (is_public);"
        )  # <-- Индекс для is_public
        logger.debug("Таблица 'pastes' проверена/обновлена.")

        # --- Таблица Пользователей (без изменений) ---
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
    content: str,
    user_id: int | None = None,
    language: str | None = None,
    is_public: bool = True,
) -> str | None:  # <-- Добавлен is_public
    """Добавляет пасту, опционально привязывая к user_id и указывая публичность."""
    if not isinstance(content, str) or not content.strip():
        return None
    su = shortuuid.ShortUUID(
        alphabet="23456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghjkmnpqrstuvwxyz"
    )
    paste_key = su.random(length=8)
    conn: sqlite3.Connection | None = None

    # --- ШИФРОВАНИЕ ПЕРЕД ЗАПИСЬЮ ---
    content_to_save: str | bytes = content  # По умолчанию сохраняем как есть
    if not is_public:  # Если паста приватная
        logger.debug(f"Шифрование приватной пасты {paste_key}...")
        encrypted_content = security.encrypt_content(content)
        if encrypted_content is None:
            logger.error("Не удалось зашифровать контент, паста не будет добавлена.")
            return None  # Ошибка шифрования
        content_to_save = encrypted_content  # Сохранять будем зашифрованные байты
        logger.debug(f"Паста {paste_key} зашифрована ({len(content_to_save)} байт).")
    # --- КОНЕЦ ШИФРОВАНИЯ ---

    try:
        conn = sqlite3.connect(DB_PATH)
        if conn is None:
            return None
        cursor: Any = conn.cursor()
        logger.debug(
            f"Попытка вставить пасту {paste_key} (user_id={user_id}, public={is_public})"
        )
        # --- ИЗМЕНЕНИЕ: Добавляем is_public ---
        cursor.execute(
            "INSERT INTO pastes (key, content, language, user_id, is_public) VALUES (?, ?, ?, ?, ?)",
            (paste_key, content_to_save, language, user_id, 1 if is_public else 0),
        )
        conn.commit()
        logger.info(
            f"Паста {paste_key} добавлена (user_id={user_id}, public={is_public})."
        )
        return paste_key
    except sqlite3.IntegrityError:
        logger.warning(f"Коллизия ключа '{paste_key}', генерирую новый...")
        if conn:
            with contextlib.suppress(sqlite3.Error):
                conn.close()
            conn = None
        # Передаем все аргументы в рекурсию
        return add_paste(content, user_id, language, is_public)
    except sqlite3.Error as e:
        logger.error(f"Ошибка добавления пасты в БД: {e}", exc_info=True)
        return None
    finally:
        if conn:
            with contextlib.suppress(sqlite3.Error):
                conn.close()


# Возвращаемый тип теперь включает bool для is_public
def get_paste(paste_key: str) -> tuple[str, str | None, int | None, bool] | None:
    """Получает пасту, ID ее автора и статус публичности."""
    if not isinstance(paste_key, str) or not paste_key:
        return None
    conn: sqlite3.Connection | None = None
    try:
        conn = sqlite3.connect(DB_PATH)
        if conn is None:
            return None
        conn.row_factory = sqlite3.Row
        cursor: Any = conn.cursor()
        logger.debug(f"Поиск пасты с ключом: {paste_key}")
        # --- ИЗМЕНЕНИЕ: Выбираем и is_public ---
        cursor.execute(
            "SELECT content, language, user_id, is_public FROM pastes WHERE key = ?",
            (paste_key,),
        )
        row = cursor.fetchone()
        if row:
            is_public_flag = bool(row["is_public"])
            author_user_id = row["user_id"]
            language = row["language"]
            content_from_db = row["content"]  # Это могут быть байты (BLOB) или строка

            final_content: str | None = None

            # --- ДЕШИФРОВАНИЕ ПРИ ЧТЕНИИ ---
            if not is_public_flag:  # Если паста приватная
                logger.debug(f"Дешифрование приватной пасты {paste_key}...")
                if isinstance(content_from_db, bytes):
                    decrypted_content = security.decrypt_content(content_from_db)
                    if decrypted_content is None:
                        logger.error(f"Не удалось дешифровать пасту {paste_key}!")
                        # Что возвращать в этом случае? Ошибку или спец. текст?
                        final_content = "[Ошибка дешифрования]"
                    else:
                        final_content = decrypted_content
                        logger.debug(f"Паста {paste_key} успешно дешифрована.")
                else:
                    # Если в БД для приватной пасты не байты - это ошибка
                    logger.error(
                        f"Приватная паста {paste_key} хранится в БД не как байты (BLOB)! Тип: {type(content_from_db)}"
                    )
                    final_content = "[Ошибка формата хранения]"
            else:  # Если паста публичная
                # Ожидаем строку, но на всякий случай декодируем, если это байты
                if isinstance(content_from_db, bytes):
                    try:
                        final_content = content_from_db.decode("utf-8")
                    except UnicodeDecodeError:
                        logger.error(
                            f"Не удалось декодировать публичную пасту {paste_key} из байтов."
                        )
                        final_content = "[Ошибка декодирования]"
                elif isinstance(content_from_db, str):
                    final_content = content_from_db
                else:
                    final_content = "[Неизвестный тип контента]"
            # --- КОНЕЦ ДЕШИФРОВАНИЯ ---

            logger.info(
                f"Паста '{paste_key}' найдена (user_id={author_user_id}, public={is_public_flag})."
            )
            # Возвращаем расшифрованный/исходный контент
            return final_content, language, author_user_id, is_public_flag
        else:
            logger.warning(f"Паста '{paste_key}' не найдена.")
            return None
    except sqlite3.Error as e:
        logger.error(f"Ошибка получения пасты '{paste_key}': {e}", exc_info=True)
        return None
    finally:
        if conn:
            with contextlib.suppress(sqlite3.Error):
                conn.close()


def get_user_pastes(
    user_id: int, limit: int = 50, preview_len: int = 100
) -> list[dict[str, Any]]:
    """
    Получает последние N паст пользователя.
    Для приватных паст ДЕШИФРУЕТ начало контента для превью.
    """
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

        # Выбираем все необходимые поля
        cursor.execute(
            """SELECT key, content, created_at, language, is_public
               FROM pastes
               WHERE user_id = ?
               ORDER BY created_at DESC
               LIMIT ?""",
            (user_id, limit),
        )
        rows = cursor.fetchall()

        for row_raw in rows:
            paste_dict = dict(row_raw)
            is_public = bool(paste_dict.get("is_public", 1))
            content_from_db = paste_dict["content"]
            final_content_preview = (
                "[Ошибка обработки контента]"  # Значение по умолчанию
            )

            # --- ОБРАБОТКА КОНТЕНТА ДЛЯ ПРЕВЬЮ ---
            if is_public:
                # Для публичных паст просто берем начало строки
                if isinstance(content_from_db, str):
                    final_content_preview = content_from_db[:preview_len]
                elif isinstance(content_from_db, bytes):  # Если вдруг байты
                    try:
                        final_content_preview = content_from_db.decode(
                            "utf-8", errors="ignore"
                        )[:preview_len]
                    except Exception:
                        final_content_preview = "[Ошибка декодирования]"
                else:
                    final_content_preview = "[Неизвестный тип контента]"
            else:
                # Для приватных паст ДЕШИФРУЕМ
                if isinstance(content_from_db, bytes):
                    decrypted_content = security.decrypt_content(content_from_db)
                    if decrypted_content is not None:
                        # Берем начало дешифрованного текста
                        final_content_preview = decrypted_content[:preview_len]
                    else:
                        final_content_preview = "[Ошибка дешифрования]"
                else:
                    # Приватная паста должна быть BLOB
                    final_content_preview = "[Ошибка формата хранения]"
            # --- КОНЕЦ ОБРАБОТКИ КОНТЕНТА ---

            # Обновляем поле content в словаре на превью
            paste_dict["content"] = final_content_preview
            # Убедимся, что is_public - это bool
            paste_dict["is_public"] = is_public
            # Обрабатываем timestamp
            created_at_val = paste_dict.get("created_at")
            if isinstance(created_at_val, str):
                converted_dt = convert_timestamp(created_at_val.encode())
                paste_dict["created_at"] = converted_dt
            elif not isinstance(created_at_val, datetime.datetime):
                paste_dict["created_at"] = None

            pastes.append(paste_dict)

        logger.info(f"Найдено и обработано {len(pastes)} паст для user_id={user_id}.")
        return pastes
    except sqlite3.Error as e:
        logger.error(f"Ошибка получения паст для user_id={user_id}: {e}", exc_info=True)
        return []
    finally:
        if conn:
            with contextlib.suppress(sqlite3.Error):
                conn.close()