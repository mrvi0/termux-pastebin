#!/usr/bin/env bash
set -e # Выход при ошибке

echo "Running Ruff linter..."
# Проверяем код в src и сам скрипт запуска, если нужно
ruff check src/ scripts/ --fix # --fix попытается автоматически исправить простые ошибки

echo "Running Mypy type checker..."
mypy src/

echo "Linting and type checking passed!"