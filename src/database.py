# src/database.py
import contextlib
import datetime
import logging
import sqlite3
from pathlib import Path
from typing import Any

import shortuuid

# --- Импортируем security ПОСЛЕ настройки логгера ---
# Это важно, т.к. security.py тоже использует logger = logging.getLogger(__name__)
# и он должен получить уже настроенный логгер
from . import security

# --- Настройка Логгера ---
# Получаем логгер с именем этого модуля ('src.database'),
# он будет использовать настройки корневого логгера из app.py
logger = logging.getLogger(__name__)

# --- Определение Путей ---
SRC_DIR = Path(__file__).parent.resolve()
DATA_DIR = SRC_DIR / "data"
DB_PATH = DATA_DIR / "pastes.db"

# --- Конвертеры Timestamp (остаются как есть) ---
def adapt_datetime_iso(val):
    return val.isoformat(" ")

def convert_timestamp(val):
    try:
        # Пробуем основной формат с микросекундами
        dt = datetime.datetime.fromisoformat(val.decode())
        return dt
    except ValueError:
        try:
             # Пробуем формат без микросекунд
             dt = datetime.datetime.strptime(val.decode(), '%Y-%m-%d %H:%M:%S')
             return dt
        except (ValueError, TypeError):
             logger.warning(f"Не удалось преобразовать timestamp '{val}' ни одним из способов.")
             return None

sqlite3.register_adapter(datetime.datetime, adapt_datetime_iso)
sqlite3.register_converter("timestamp", convert_timestamp)

# --- Инициализация Базы Данных ---
def init_db():
    """Инициализирует БД и таблицы pastes и users."""
    conn: sqlite3.Connection | None = None # Добавляем тип
    try:
        DATA_DIR.mkdir(exist_ok=True)
        conn = sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES) # Добавляем detect_types
        conn.row_factory = sqlite3.Row # Установим row_factory и здесь
        conn.execute("PRAGMA foreign_keys = ON;") # Включаем внешние ключи
        cursor: Any = conn.cursor()
        logger.info(f"Проверка/создание таблиц в БД: {DB_PATH}")

        # Создаем таблицы (код без изменений)
        cursor.execute('''CREATE TABLE IF NOT EXISTS pastes (...)''') # Сокращено для примера
        cursor.execute('''CREATE TABLE IF NOT EXISTS users (...)''')   # Сокращено для примера
        # ... (создание индексов) ...
        logger.debug("Таблицы 'pastes' и 'users' проверены/созданы.")

        # Пробуем добавить колонку is_public с suppress (код без изменений)
        with contextlib.suppress(sqlite3.OperationalError):
            cursor.execute("ALTER TABLE pastes ADD COLUMN is_public BOOLEAN DEFAULT 1 CHECK(is_public IN (0, 1))")
            logger.info("Попытка добавить колонку 'is_public' в 'pastes'.")

        conn.commit()
        logger.info("Инициализация базы данных успешно завершена.")
        return True # Возвращаем успех
    except sqlite3.Error as e:
        logger.critical(f"Критическая ошибка при инициализации БД '{DB_PATH}': {e}", exc_info=True)
        return False # Возвращаем неуспех
    finally:
        if conn:
            with contextlib.suppress(sqlite3.Error): conn.close()


# --- Функции для пользователей (логика без изменений, улучшено закрытие conn) ---
def get_or_create_user(yandex_data: dict[str, Any]) -> int | None:
    yandex_id = yandex_data.get('id')
    if not yandex_id: return None
    conn: sqlite3.Connection | None = None
    try:
        conn = sqlite3.connect(DB_PATH)
        if conn is None: return None
        conn.row_factory = sqlite3.Row # Установим здесь тоже
        cursor: Any = conn.cursor()
        now = datetime.datetime.now(datetime.timezone.utc) # Используем UTC
        cursor.execute("SELECT id FROM users WHERE yandex_id = ?", (yandex_id,))
        user_row = cursor.fetchone()
        if user_row:
            # ... (логика обновления) ...
            user_id = user_row[0]
            cursor.execute("UPDATE users SET last_login = ? WHERE id = ?", (now, user_id))
            conn.commit()
            logger.info(f"Пользователь найден (ID: {user_id}, Yandex ID: {yandex_id}), обновлен last_login.")
            return user_id
        else:
            # ... (логика создания) ...
            login = yandex_data.get('login')
            display_name = yandex_data.get('display_name')
            email = yandex_data.get('default_email')
            cursor.execute(
                "INSERT INTO users (yandex_id, login, display_name, email, last_login) VALUES (?, ?, ?, ?, ?)",
                (yandex_id, login, display_name, email, now)
            )
            user_id = cursor.lastrowid
            conn.commit()
            logger.info(f"Создан новый пользователь (ID: {user_id}, Yandex ID: {yandex_id}, Login: {login}).")
            return user_id
    except sqlite3.Error as e:
        logger.error(f"Ошибка при поиске/создании пользователя (Yandex ID: {yandex_id}): {e}", exc_info=True)
        return None
    finally:
        if conn:
            with contextlib.suppress(sqlite3.Error): conn.close()


# --- Функции для паст ---

def add_paste(content: str,
              user_id: int | None = None,
              language: str | None = None,
              is_public: bool = True) -> str | None:
    if not isinstance(content, str) or not content.strip(): return None
    su = shortuuid.ShortUUID(alphabet="...") # Алфавит
    paste_key = su.random(length=8)
    conn: sqlite3.Connection | None = None
    logger.debug(f"Вызов add_paste для key={paste_key}, user_id={user_id}, public={is_public}")

    content_to_save: str | bytes = content
    encrypted = False
    if not is_public:
        logger.info(f"Паста {paste_key} приватная, попытка шифрования...")
        encrypted_content = security.encrypt_content(content)
        if encrypted_content is None:
            logger.error(f"ШИФРОВАНИЕ НЕ УДАЛОСЬ для пасты {paste_key}! Паста не будет добавлена.")
            return None
        else:
            content_to_save = encrypted_content
            encrypted = True
            logger.info(f"Паста {paste_key} УСПЕШНО зашифрована ({len(content_to_save)} байт). Тип: {type(content_to_save)}")
    else:
         logger.debug(f"Паста {paste_key} публичная, шифрование не требуется.")

    logger.debug(f"Данные для записи в БД (key={paste_key}, encrypted={encrypted}): тип={type(content_to_save)}")

    try:
        conn = sqlite3.connect(DB_PATH)
        if conn is None: return None
        cursor: Any = conn.cursor()
        cursor.execute(
            "INSERT INTO pastes (key, content, language, user_id, is_public) VALUES (?, ?, ?, ?, ?)",
            (paste_key, content_to_save, language, user_id, 1 if is_public else 0)
        )
        conn.commit()
        logger.info(f"Паста {paste_key} успешно записана в БД (user_id={user_id}, public={is_public}, encrypted={encrypted}).")
        return paste_key
    except sqlite3.IntegrityError:
        logger.warning(f"Коллизия ключа '{paste_key}', генерирую новый...")
        if conn:
            with contextlib.suppress(sqlite3.Error): conn.close()
            conn = None
        return add_paste(content, user_id, language, is_public)
    except sqlite3.Error as e:
        logger.error(f"Ошибка добавления пасты в БД: {e}", exc_info=True)
        return None
    finally:
        if conn:
            with contextlib.suppress(sqlite3.Error): conn.close()


def get_paste(paste_key: str) -> tuple[str, str | None, int | None, bool] | None:
     # ... (логика без изменений, использует security.decrypt_content) ...
     if not isinstance(paste_key, str) or not paste_key: return None
     conn: sqlite3.Connection | None = None
     try:
        # Используем detect_types здесь тоже, чтобы сработал конвертер timestamp, если он понадобится
        conn = sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES)
        if conn is None: return None
        conn.row_factory = sqlite3.Row
        cursor: Any = conn.cursor()
        logger.debug(f"Поиск пасты с ключом: {paste_key}")
        cursor.execute("SELECT content, language, user_id, is_public, created_at FROM pastes WHERE key = ?", (paste_key,)) # Добавил created_at для лога
        row = cursor.fetchone()

        if row:
             is_public_flag = bool(row['is_public'])
             author_user_id = row['user_id']
             language = row['language']
             content_from_db = row['content']
             created_at = row['created_at'] # Получаем дату для лога
             logger.debug(f"Паста '{paste_key}' найдена в БД. is_public={is_public_flag}, тип контента={type(content_from_db)}, создана={created_at}")

             final_content: str | None = None
             if not is_public_flag:
                 logger.debug(f"Дешифрование приватной пасты {paste_key}...")
                 if isinstance(content_from_db, bytes):
                     decrypted_content = security.decrypt_content(content_from_db)
                     if decrypted_content is not None:
                         final_content = decrypted_content
                         logger.debug(f"Паста {paste_key} успешно дешифрована.")
                     else:
                         final_content = "[Ошибка дешифрования]"
                         logger.error(f"Ошибка дешифрования пасты {paste_key}.")
                 else:
                     final_content = "[Ошибка формата хранения]"
                     logger.error(f"Приватная паста {paste_key} хранится не как BLOB! Тип: {type(content_from_db)}")
             else: # Публичная паста
                 if isinstance(content_from_db, str):
                      final_content = content_from_db
                 elif isinstance(content_from_db, bytes):
                     try: final_content = content_from_db.decode('utf-8')
                     except UnicodeDecodeError: final_content = "[Ошибка декодирования]"
                 else: final_content = "[Неизвестный тип контента]"

             logger.info(f"Возврат данных для пасты '{paste_key}' (user_id={author_user_id}, public={is_public_flag}).")
             return final_content, language, author_user_id, is_public_flag
        else:
             logger.warning(f"Паста '{paste_key}' не найдена.")
             return None
     except sqlite3.Error as e:
        logger.error(f"Ошибка получения пасты '{paste_key}': {e}", exc_info=True)
        return None
     finally:
         if conn:
            with contextlib.suppress(sqlite3.Error): conn.close()


# --- ИСПРАВЛЕННАЯ get_user_pastes ---
def get_user_pastes(user_id: int, limit: int = 50, preview_len: int = 150) -> list[dict[str, Any]]:
    """
    Получает последние N паст пользователя.
    Для приватных паст ДЕШИФРУЕТ контент и берет превью.
    """
    if not user_id: return []
    conn: sqlite3.Connection | None = None
    pastes: list[dict[str, Any]] = []
    try:
        conn = sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES)
        if conn is None: return []
        conn.row_factory = sqlite3.Row
        cursor: Any = conn.cursor()
        logger.debug(f"Получение паст для user_id={user_id} (limit={limit})")

        cursor.execute(
            """SELECT key, content, created_at, language, is_public
               FROM pastes
               WHERE user_id = ?
               ORDER BY created_at DESC
               LIMIT ?""",
            (user_id, limit)
        )
        rows = cursor.fetchall()
        logger.debug(f"Найдено {len(rows)} строк паст для user_id={user_id} в БД.")

        for row_raw in rows:
            paste_dict = dict(row_raw) # Преобразуем в изменяемый словарь
            is_public = bool(paste_dict.get('is_public', 1))
            content_from_db = paste_dict['content']
            key = paste_dict['key'] # Получаем ключ для логов

            # --- ИСПРАВЛЕННАЯ ЛОГИКА ОБРАБОТКИ КОНТЕНТА ---
            final_content_preview = None # Инициализируем как None

            if is_public:
                if isinstance(content_from_db, str):
                    final_content_preview = content_from_db
                elif isinstance(content_from_db, bytes):
                    try: final_content_preview = content_from_db.decode('utf-8', errors='replace') # Заменяем ошибки декодирования
                    except Exception: final_content_preview = "[Ошибка декодирования]"
                else: final_content_preview = "[Неизвестный тип]"
            else: # Приватная паста
                if isinstance(content_from_db, bytes):
                    logger.debug(f"Дешифровка для превью (my_pastes) key={key}. Тип: {type(content_from_db)}")
                    decrypted_content = security.decrypt_content(content_from_db)
                    if decrypted_content is not None:
                        final_content_preview = decrypted_content # Возвращаем ПОЛНЫЙ дешифрованный текст
                        logger.debug(f"Превью для key={key} УСПЕШНО дешифровано.")
                    else:
                        final_content_preview = "[Ошибка дешифрования]"
                        logger.error(f"Ошибка дешифрования для превью key={key}.")
                else:
                    final_content_preview = "[Ошибка формата хранения]"
                    logger.error(f"Приватная паста {key} хранится не как BLOB для превью! Тип: {type(content_from_db)}")

            # Записываем обработанный (или дешифрованный) контент
            paste_dict['content'] = final_content_preview if final_content_preview is not None else "[Ошибка обработки]"
            # --- КОНЕЦ ИСПРАВЛЕННОЙ ЛОГИКИ ---

            # Обработка остальных полей (is_public, created_at)
            paste_dict['is_public'] = is_public
            created_at_val = paste_dict.get('created_at')
            if isinstance(created_at_val, str): # Если конвертер не сработал
                 converted_dt = convert_timestamp(created_at_val.encode())
                 paste_dict['created_at'] = converted_dt
            elif not isinstance(created_at_val, datetime.datetime):
                 paste_dict['created_at'] = None

            pastes.append(paste_dict)

        logger.info(f"Обработано {len(pastes)} паст для user_id={user_id}.")
        return pastes
    except sqlite3.Error as e:
        logger.error(f"Ошибка получения паст для user_id={user_id}: {e}", exc_info=True)
        return []
    finally:
        if conn:
            with contextlib.suppress(sqlite3.Error): conn.close()

# --- Конвертер Timestamp ---
# (остается без изменений)
# def convert_timestamp(val): ...
# sqlite3.register_converter("timestamp", convert_timestamp)
