#!/usr/bin/env bash

# Скрипт для остановки Termux Pastebin (процесса waitress)

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
PROJECT_ROOT="$( dirname "$SCRIPT_DIR" )"
cd "$PROJECT_ROOT" || { echo "Ошибка: Не удалось перейти в $PROJECT_ROOT"; exit 1; }

PID_FILE="data/pastebin.pid"

echo "Попытка остановить Pastebin waitress..."

if [ ! -f "$PID_FILE" ]; then
  echo "Предупреждение: PID файл '$PID_FILE' не найден. Возможно, процесс не запущен или PID не был сохранен."
  # Дополнительно попробуем убить по имени команды, если PID файла нет
  echo "Попытка остановить процесс waitress по имени..."
  pkill -f "waitress-serve.*src.app:app"
  if [ $? -eq 0 ]; then
     echo "Процесс waitress (найденный по имени) остановлен."
  else
     echo "Процесс waitress (по имени) не найден или не удалось остановить."
  fi
  exit 0 # Выходим, так как PID файла нет
fi

# Читаем PID из файла
PID=$(cat "$PID_FILE")

if [ -z "$PID" ]; then
  echo "Ошибка: PID файл '$PID_FILE' пуст."
  exit 1
fi

# Проверяем, существует ли процесс с таким PID
if ps -p "$PID" > /dev/null; then
   echo "Найден процесс с PID $PID. Отправка сигнала TERM..."
   kill "$PID" # Отправляем сигнал TERM (вежливая остановка)
   # Ждем немного и проверяем снова
   sleep 2
   if ps -p "$PID" > /dev/null; then
      echo "Процесс $PID все еще работает. Отправка сигнала KILL..."
      kill -9 "$PID" # Принудительная остановка
      sleep 1
      if ps -p "$PID" > /dev/null; then
         echo "Ошибка: Не удалось остановить процесс $PID даже с KILL -9."
         exit 1
      else
         echo "Процесс $PID принудительно остановлен (KILL)."
      fi
   else
      echo "Процесс $PID успешно остановлен (TERM)."
   fi
else
   echo "Процесс с PID $PID (из файла $PID_FILE) не найден. Возможно, он уже остановлен."
fi

# Удаляем PID файл после успешной (или предполагаемой) остановки
rm -f "$PID_FILE"
echo "PID файл '$PID_FILE' удален."

exit 0