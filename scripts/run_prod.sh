#!/usr/bin/env bash

# Скрипт для запуска Termux Pastebin в продакшен-режиме с помощью Waitress

# Определяем директорию, где находится сам скрипт
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
# Определяем корневую директорию проекта (на уровень выше scripts)
PROJECT_ROOT="$( dirname "$SCRIPT_DIR" )"

# Переходим в корневую директорию проекта
cd "$PROJECT_ROOT" || { echo "Ошибка: Не удалось перейти в $PROJECT_ROOT"; exit 1; }

# --- Настройки ---
VENV_DIR="venv" # Имя папки виртуального окружения
ENV_FILE=".env" # Имя файла с переменными окружения
APP_MODULE="src.app:app" # Путь к Flask приложению (папка.файл:объект)

# --- Проверка наличия venv ---
if [ ! -d "$VENV_DIR" ]; then
    echo "Ошибка: Виртуальное окружение '$VENV_DIR' не найдено."
    echo "Пожалуйста, создайте его: python3 -m venv $VENV_DIR && source $VENV_DIR/bin/activate && pip install -r requirements.txt"
    exit 1
fi

# --- Активация venv ---
echo "Активация виртуального окружения..."
source "$VENV_DIR/bin/activate" || { echo "Ошибка: Не удалось активировать $VENV_DIR"; exit 1; }
echo "Виртуальное окружение активировано."

# --- Загрузка переменных окружения из .env файла ---
if [ -f "$ENV_FILE" ]; then
    echo "Загрузка переменных окружения из $ENV_FILE..."
    # Используем set -a для экспорта всех переменных, определенных в файле
    # и grep -v '^#' для игнорирования комментариев
    set -a
    source "$ENV_FILE"
    set +a
    echo "Переменные окружения загружены."
else
    echo "Предупреждение: Файл $ENV_FILE не найден. Используются системные переменные окружения или значения по умолчанию."
fi

# --- Получаем настройки хоста и порта для Waitress ---
# Используем значения из env или дефолтные, если не заданы
HOST=${PASTEBIN_HOST:-"0.0.0.0"} # Дефолт 0.0.0.0
PORT=${PASTEBIN_PORT:-"5005"}    # Дефолт 5005

# --- Проверка наличия waitress ---
if ! command -v waitress-serve &> /dev/null; then
    echo "Ошибка: Команда 'waitress-serve' не найдена."
    echo "Убедитесь, что waitress установлен в виртуальном окружении: pip install waitress"
    exit 1
fi

# --- Запуск Waitress ---
echo "Запуск Pastebin на http://${HOST}:${PORT} через Waitress..."
# waitress-serve --host <host> --port <port> <путь_к_приложению>
waitress-serve --host "$HOST" --port "$PORT" "$APP_MODULE"

# Сюда выполнение дойдет только если waitress завершится (например, по Ctrl+C)
echo "Waitress сервер остановлен."
exit 0