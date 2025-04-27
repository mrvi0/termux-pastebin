#!/usr/bin/env bash
set -e # Выход при ошибке

echo "Running Ruff formatter..."
ruff format src/ scripts/

echo "Code formatted successfully!"