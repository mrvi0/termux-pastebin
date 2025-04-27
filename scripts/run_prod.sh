#!/usr/bin/env bash

# Скрипт для запуска Termux Pastebin в продакшен-режиме с помощью Waitress
# СОХРАНЯЕТ PID процесса waitress

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
PROJECT_ROOT="$( dirname "$SCRIPT_DIR" )"
cd "$PROJECT_ROOT" || { echo "Ошибка: Не удалось перейти в $PROJECT_ROOT"; exit 1; }

VENV_DIR="venv"
ENV_FILE=".env"
APP_MODULE="src.app:app"
PID_FILE="data/pastebin.pid" # Файл для хранения PID процесса waitress
LOG_FILE="pastebin-waitress.log" # Лог файл waitress

# --- Проверка наличия venv ---
if [ ! -d "$VENV_DIR" ]; then
    echo "Ошибка: Виртуальное окружение '$VENV_DIR' не найдено."
    echo "Пожалуйста, создайте его: python3 -m venv $VENV_DIR && source $VENV_DIR/bin/activate && pip install -r requirements.txt"
    exit 1
fi

# --- Создаем папку data, если нет ---
mkdir -p data

# --- Активация venv ---
echo "Активация виртуального окружения..."
source "$VENV_DIR/bin/activate" || { echo "Ошибка: Не удалось активировать $VENV_DIR"; exit 1; }

# --- Загрузка .env ---
if [ -f "$ENV_FILE" ]; then
    echo "Загрузка переменных окружения из $ENV_FILE..."
    set -a; source "$ENV_FILE"; set +a
else
    echo "Предупреждение: Файл $ENV_FILE не найден."
fi

# --- Получаем хост и порт ---
HOST=${PASTEBIN_HOST:-"0.0.0.0"}
PORT=${PASTEBIN_PORT:-"5005"}

# --- Проверка waitress ---
if ! command -v waitress-serve &> /dev/null; then
    echo "Ошибка: Команда 'waitress-serve' не найдена."; exit 1;
fi

# --- Запуск Waitress в фоне и сохранение PID ---
echo "Запуск Pastebin на http://${HOST}:${PORT} через Waitress..."
# Запускаем waitress, перенаправляем вывод и сохраняем PID (&! или $!)
nohup waitress-serve --host "$HOST" --port "$PORT" "$APP_MODULE" >> "$LOG_FILE" 2>&1 &
WAITRESS_PID=$! # Сохраняем PID последнего фонового процесса

# Проверяем, запустился ли процесс (опционально, может быть неточно)
sleep 1
if ! ps -p $WAITRESS_PID > /dev/null; then
     echo "Ошибка: Процесс waitress ($WAITRESS_PID) не запустился или завершился сразу."
     exit 1
fi

# Записываем PID в файл
echo $WAITRESS_PID > "$PID_FILE"
echo "Waitress запущен с PID: $WAITRESS_PID. PID сохранен в $PID_FILE."
echo "Логи пишутся в $LOG_FILE."

exit 0 # Скрипт завершается, waitress работает в фоне