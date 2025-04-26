#!/bin/bash

# Скрипт для запуска линтеров и проверки форматирования

# Переходим в директорию скрипта, затем в корень проекта
cd "$(dirname "$0")"/..

echo "Запуск линтеров и проверки форматирования..."
EXIT_CODE=0

# --- Python (используйте Ruff или Flake8/Black) ---
echo "Проверка Python кода..."

# Ruff (рекомендуется)
# Убедитесь, что ruff установлен (pip install ruff или через poetry/requirements)
ruff check . || EXIT_CODE=$?
ruff format --check . || EXIT_CODE=$?

# Flake8 и Black (альтернатива)
# Убедитесь, что установлены (pip install flake8 black)
# flake8 . --count --show-source --statistics || EXIT_CODE=$?
# black --check . || EXIT_CODE=$?

# --- Node.js (раскомментируйте и адаптируйте) ---
# echo "Проверка Node.js кода..."
# npm run lint || EXIT_CODE=$? # Замените на вашу команду ESLint
# npm run format:check || EXIT_CODE=$? # Замените на вашу команду Prettier check

# --- Итог ---
if [ $EXIT_CODE -eq 0 ]; then
  echo "✅ Проверка стиля и форматирования успешно пройдена!"
else
  echo "❌ Обнаружены проблемы со стилем или форматированием (Код выхода: $EXIT_CODE)"
fi

exit $EXIT_CODE