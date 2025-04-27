# src/database.py
import sqlite3
import logging
import datetime
from pathlib import Path
from typing import Optional, Tuple
import shortuuid # Для генерации коротких ключей

# --- Настройка Логгера ---
# Используем стандартный логгер, т.к. основная настройка будет в app.py
logger = logging.getLogger(__name__)
# Установим базовый уровень, чтобы видеть сообщения из этого модуля
# logging.basicConfig(level=logging.INFO) # Лучше настроить в app.py

# --- Определение Путей ---
# Определяем путь к директории 'src', где лежит этот файл
SRC_DIR = Path(__file__).parent.resolve()
# Путь к директории 'data' на уровень выше 'src'
DATA_DIR = SRC_DIR.parent / "data"
# Полный путь к файлу базы данных
DB_PATH = DATA_DIR / "pastes.db"

# --- Инициализация Базы Данных ---
def init_db():
    """
    Инициализирует файл БД и создает таблицу 'pastes', если они не существуют.
    Вызывается один раз при старте приложения.
    """
    try:
        # Убедимся, что папка 'data' существует
        DATA_DIR.mkdir(exist_ok=True)
        # Устанавливаем соединение (файл будет создан, если не существует)
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        logger.info(f"Проверка/создание таблицы 'pastes' в БД: {DB_PATH}")
        # Создаем таблицу, если ее нет
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS pastes (
                key TEXT PRIMARY KEY,    -- Уникальный короткий ключ (текстовый)
                content TEXT NOT NULL,   -- Содержимое пасты
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, -- Время создания
                -- Дополнительные поля (пока не используются активно):
                language TEXT,           -- Язык для подсветки синтаксиса
                expires_at TIMESTAMP     -- Время автоматического удаления
            )
        ''')
        # Создаем индекс для ускорения поиска по ключу (хотя PRIMARY KEY уже индексируется)
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_pastes_key ON pastes (key);
        ''')
        conn.commit() # Сохраняем изменения
        conn.close() # Закрываем соединение
        logger.info("Инициализация базы данных успешно завершена.")
    except sqlite3.Error as e:
        # Логируем критическую ошибку, если не удалось создать/открыть БД
        logger.critical(f"Критическая ошибка при инициализации БД '{DB_PATH}': {e}", exc_info=True)
        # Возможно, стоит прервать выполнение приложения здесь
        raise # Перевыбрасываем исключение, чтобы приложение не запустилось

# --- Функции для Работы с Пастами ---

def add_paste(content: str, language: Optional[str] = None) -> Optional[str]:
    """
    Добавляет новую пасту в базу данных.

    Args:
        content: Текст пасты.
        language: Язык программирования (опционально).

    Returns:
        Уникальный короткий ключ (str) для пасты в случае успеха, или None при ошибке.
    """
    if not isinstance(content, str) or not content.strip():
        logger.warning("Попытка добавить пустую пасту.")
        return None # Не добавляем пустые пасты

    # Генерируем уникальный короткий ключ
    # Используем алфавит без похожих символов для лучшей читаемости
    su = shortuuid.ShortUUID(alphabet="23456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghjkmnpqrstuvwxyz")
    paste_key = su.random(length=8) # Длина ключа (можно настроить)

    conn = None # Инициализируем переменную соединения
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        logger.debug(f"Попытка вставить пасту с ключом: {paste_key}")
        # Вставляем новую запись
        cursor.execute(
            "INSERT INTO pastes (key, content, language) VALUES (?, ?, ?)",
            (paste_key, content, language)
        )
        conn.commit() # Сохраняем
        logger.info(f"Паста успешно добавлена с ключом: {paste_key}")
        return paste_key
    except sqlite3.IntegrityError:
        # Эта ошибка возникает, если сгенерированный ключ уже существует (крайне маловероятно)
        logger.warning(f"Коллизия ключа shortuuid '{paste_key}', генерирую новый...")
        # Рекурсивно вызываем функцию еще раз, чтобы сгенерировать другой ключ
        # Важно закрыть соединение перед рекурсивным вызовом, чтобы избежать блокировок
        if conn: conn.close()
        return add_paste(content, language)
    except sqlite3.Error as e:
        # Логируем другие ошибки базы данных
        logger.error(f"Ошибка добавления пасты в БД: {e}", exc_info=True)
        return None
    finally:
        # Гарантированно закрываем соединение
        if conn:
            conn.close()
            logger.debug("Соединение с БД закрыто после добавления пасты.")


def get_paste(paste_key: str) -> Optional[Tuple[str, Optional[str]]]:
    """
    Извлекает содержимое пасты и ее язык (если есть) из БД по ключу.

    Args:
        paste_key: Уникальный ключ пасты.

    Returns:
        Кортеж (content, language) в случае успеха, или None, если паста не найдена или произошла ошибка.
    """
    # Простая валидация ключа (должен быть строкой, не пустой)
    if not isinstance(paste_key, str) or not paste_key:
        return None

    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        # Используем row_factory для удобного доступа к данным по имени колонки
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        logger.debug(f"Поиск пасты с ключом: {paste_key}")
        # Выбираем нужные поля по ключу
        cursor.execute(
            "SELECT content, language FROM pastes WHERE key = ?",
            (paste_key,)
        )
        row = cursor.fetchone() # Получаем одну строку (или None)

        if row:
            logger.info(f"Паста с ключом '{paste_key}' найдена.")
            # Возвращаем кортеж с содержимым и языком
            return row['content'], row['language']
        else:
            logger.warning(f"Паста с ключом '{paste_key}' не найдена в БД.")
            return None
    except sqlite3.Error as e:
        logger.error(f"Ошибка получения пасты '{paste_key}' из БД: {e}", exc_info=True)
        return None
    finally:
        if conn:
            conn.close()
            logger.debug(f"Соединение с БД закрыто после получения пасты '{paste_key}'.")

# --- Можно добавить функции для удаления старых паст по расписанию в будущем ---

# --- Вызов инициализации ---
# Лучше вызывать init_db() один раз при старте основного приложения (в app.py),
# а не при импорте этого модуля, чтобы избежать проблем с порядком инициализации
# и иметь возможность обработать ошибку инициализации на верхнем уровне.
# init_db() # <-- Закомментировано здесь