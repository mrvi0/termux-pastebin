#!/usr/bin/env bash
set -e # Выход при ошибке

echo "Running tests..."
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
PROJECT_ROOT="$( dirname "$SCRIPT_DIR" )"
# НЕ переходим в корень проекта здесь

# Активируем venv (путь от корня проекта)
source "$PROJECT_ROOT/venv/bin/activate" || { echo "Ошибка активации venv"; exit 1; }

# --- Устанавливаем PYTHONPATH ---
# Добавляем корневую директорию проекта в PYTHONPATH,
# чтобы Python мог найти пакет 'src'
export PYTHONPATH="${PYTHONPATH}:${PROJECT_ROOT}"
echo "PYTHONPATH set to: $PYTHONPATH"

# --- Запускаем pytest как модуль ---
# Pytest сам найдет тесты в директории tests/
# Запускаем из КОРНЯ проекта
echo "Running pytest from $PROJECT_ROOT..."
python -m pytest -v -s "$PROJECT_ROOT/tests/"

echo "Tests finished."