#!/bin/bash

# Скрипт для запуска тестов

# Переходим в директорию скрипта, затем в корень проекта
cd "$(dirname "$0")"/..

echo "Запуск тестов..."

# --- Выберите команду для вашего языка ---

# Python (с pytest)
# Убедитесь, что PYTHONPATH установлен для поиска модулей в src
# PYTHONPATH=src pytest tests/ -v
# -v для подробного вывода

# Node.js (с npm test)
# npm test

# --- Замените на вашу реальную команду запуска тестов ---
echo "Замените эту строку на вашу команду запуска тестов в scripts/run_tests.sh"
# Пример для Python с pytest:
PYTHONPATH=src pytest tests/ -v

# Сохраняем код выхода тестов
EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
  echo "✅ Тесты успешно пройдены!"
else
  echo "❌ Тесты не пройдены (Код выхода: $EXIT_CODE)"
fi

exit $EXIT_CODE