# tests/test_database.py
import pytest
import sqlite3
from pathlib import Path
from typing import List, Dict, Any

# Импортируем тестируемый модуль
from src import database

# --- Тесты для функций базы данных ---
# Фикстура test_db будет автоматически применена к функциям, где она указана как аргумент

def test_init_db(test_db: Path):
    """Тест: Проверяет, что init_db создает файл и таблицы."""
    assert test_db.exists() # Проверяем, что файл создан фикстурой
    conn = sqlite3.connect(test_db)
    cursor = conn.cursor()
    # Проверяем наличие таблиц
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='pastes'")
    assert cursor.fetchone() is not None
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
    assert cursor.fetchone() is not None
    conn.close()

def test_add_and_get_paste(test_db: Path):
    """Тест: Добавление и получение пасты."""
    content1 = "Test content 1"
    key1 = database.add_paste(content1, language="python")
    assert key1 is not None # Ключ должен быть сгенерирован
    assert len(key1) == 8

    # Получаем пасту
    result1 = database.get_paste(key1)
    assert result1 is not None
    res_content, res_lang, res_user_id = result1
    assert res_content == content1
    assert res_lang == "python"
    assert res_user_id is None # User ID не передавали

    # Проверяем получение несуществующей пасты
    assert database.get_paste("nonexistentkey") is None

    # Проверяем добавление пустой пасты
    assert database.add_paste("") is None
    assert database.add_paste("   ") is None

def test_add_paste_with_user(test_db: Path):
    """Тест: Добавление пасты с привязкой к пользователю."""
    user_id_mock = 123 # Просто фиктивный ID
    content = "User paste"
    key = database.add_paste(content, user_id=user_id_mock)
    assert key is not None

    result = database.get_paste(key)
    assert result is not None
    _, _, res_user_id = result
    assert res_user_id == user_id_mock

def test_get_or_create_user(test_db: Path):
    """Тест: Получение и создание пользователя."""
    yandex_data1 = {'id': '1111', 'login': 'user1', 'display_name': 'User One', 'default_email': 'u1@ya.ru'}
    yandex_data2 = {'id': '2222', 'login': 'user2', 'display_name': 'User Two', 'default_email': 'u2@ya.ru'}

    # 1. Создаем первого пользователя
    user1_id = database.get_or_create_user(yandex_data1)
    assert user1_id is not None
    assert user1_id == 1 # Первый ID должен быть 1

    # 2. Пытаемся получить его снова
    user1_id_again = database.get_or_create_user(yandex_data1)
    assert user1_id_again == user1_id # ID должен совпадать

    # 3. Создаем второго пользователя
    user2_id = database.get_or_create_user(yandex_data2)
    assert user2_id is not None
    assert user2_id == 2 # ID должен быть 2

    # Проверяем данные в базе (опционально)
    conn = sqlite3.connect(test_db)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE id = ?", (user1_id,))
    row1 = cur.fetchone()
    assert row1 is not None
    assert row1['yandex_id'] == '1111'
    assert row1['login'] == 'user1'
    cur.execute("SELECT COUNT(*) as cnt FROM users")
    assert cur.fetchone()['cnt'] == 2
    conn.close()

def test_get_user_pastes(test_db: Path):
    """Тест: Получение паст конкретного пользователя."""
    # Создаем пользователей
    user1_id = database.get_or_create_user({'id': 'user1'})
    user2_id = database.get_or_create_user({'id': 'user2'})

    # Добавляем пасты
    key1 = database.add_paste("User1 Paste 1", user_id=user1_id)
    key2 = database.add_paste("User2 Paste 1", user_id=user2_id)
    key3 = database.add_paste("User1 Paste 2", user_id=user1_id)
    key4 = database.add_paste("Anon Paste") # Анонимная паста

    # Получаем пасты user1
    pastes1 = database.get_user_pastes(user1_id)
    assert len(pastes1) == 2
    # Проверяем порядок (последняя добавленная - первая)
    assert pastes1[0]['key'] == key3
    assert pastes1[1]['key'] == key1
    assert pastes1[0]['content'] == "User1 Paste 2"

    # Получаем пасты user2
    pastes2 = database.get_user_pastes(user2_id)
    assert len(pastes2) == 1
    assert pastes2[0]['key'] == key2

    # Получаем пасты несуществующего пользователя
    pastes_none = database.get_user_pastes(999)
    assert len(pastes_none) == 0