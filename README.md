# Termux Pastebin

<!-- Бейджи пока уберем, так как нет CI/CD и публичного репозитория -->
[![CI Status](https://github.com/mrvi0/termux-pastebin/actions/workflows/deploy-termux.yml/badge.svg)](https://github.com/mrvi0/termux-pastebin/actions/workflows/deploy-termux.yml)
[![Lint Status](https://github.com/mrvi0/termux-pastebin/actions/workflows/lint.yml/badge.svg)](https://github.com/mrvi0/termux-pastebin/actions/workflows/lint.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT) <!-- Заменил на MIT, т.к. AGPL может быть избыточен -->

Простой сервис для обмена текстовыми фрагментами (пастами), предназначенный для запуска на устройстве с Termux. Позволяет быстро создавать пасты и делиться ими по ссылке в локальной сети или через VPN (WireGuard).

## ✨ Основные возможности

*   Создание **публичных** (доступных всем по ссылке) и **приватных** (доступных только автору) текстовых паст.
*   **Шифрование** содержимого приватных паст в базе данных (AES-GCM).
*   Авторизация через **Яндекс.OAuth** для создания паст и доступа к приватным.
*   Просмотр **своих паст** (публичных и приватных) на отдельной странице.
*   Генерация коротких, уникальных ссылок для каждой пасты.
*   Просмотр публичных паст по ссылке без авторизации.
*   Хранение паст и пользователей в локальной базе данных SQLite.
*   Легковесность, оптимизация для запуска в Termux.

## 🚀 Установка (на Termux)

### Требования

*   **Termux:** Среда Linux на Android.
*   **Termux:Boot (Рекомендуется):** Для автозапуска сервиса (из F-Droid).
*   **Python 3.10+:**
    ```bash
    pkg update && pkg upgrade
    pkg install python git ffmpeg libsndfile sqlite # Устанавливаем Python и нужные системные пакеты
    pkg install rust # Нужно для Authlib, иначе не соберается колесо
    ```
*   **pip:** Менеджер пакетов Python (обычно идет с Python).

### Установка приложения

1.  **Клонируйте репозиторий (или скопируйте файлы):**
    (Пока репозиторий приватный, будем считать, что код скопирован в `~/termux-pastebin`)
    ```bash
    cd ~
    # git clone ... # Если будет репозиторий
    # Или просто убедитесь, что папка ~/termux-pastebin существует и содержит код
    cd termux-pastebin
    ```

2.  **Создайте и активируйте виртуальное окружение:**
    ```bash
    python -m venv venv
    source venv/bin/activate
    ```

3.  **Установите зависимости:**
    ```bash
    pip install --upgrade pip
    pip install -r requirements.txt
    ```

4.  **Создайте и настройте файл `.env`:**
    Скопируйте `.env.example` в `.env` и **обязательно** установите свои значения.
    ```bash
    cp .env.example .env
    nano .env
    ```
    *   Установите надежный `FLASK_SECRET_KEY` (сгенерируйте: `python -c 'import secrets; print(secrets.token_hex(16))'`).
    *   Установите желаемые `BASIC_AUTH_USERNAME` и `BASIC_AUTH_PASSWORD`.
    *   При необходимости измените `PASTEBIN_HOST` или `PASTEBIN_PORT`.
    *   **ВАЖНО:** Защитите файл: `chmod 600 .env`

## ⚙️ Конфигурация

Приложение конфигурируется с помощью переменных окружения в файле `.env` в корневой директории проекта.

*   `FLASK_SECRET_KEY`: **Обязательно.** Секретный ключ для Flask.
*   `YANDEX_CLIENT_ID`: **Обязательно.** ID приложения Яндекс.OAuth.
*   `YANDEX_CLIENT_SECRET`: **Обязательно.** Пароль приложения Яндекс.OAuth.
*   `PASTE_ENCRYPTION_KEY`: **Обязательно.** Ключ для шифрования приватных паст (32 байта, кодированные в URL-safe Base64). Сгенерируйте с помощью `python -c 'import os, base64; print(base64.urlsafe_b64encode(os.urandom(32)).decode())'`.
*   `PASTEBIN_HOST`: IP-адрес для сервера (по умолчанию `0.0.0.0`).
*   `PASTEBIN_PORT`: Порт для сервера (по умолчанию `5005`).

## ⚡ Использование

### Запуск Сервера

Рекомендуется запускать через скрипт `run_prod.sh`, который использует Waitress:

```bash
# Убедитесь, что вы НЕ в venv (скрипт сам активирует)
deactivate # Если были в venv

# Запуск из корневой папки проекта
bash scripts/run_prod.sh
```
Сервер будет запущен на хосте и порту, указанных в .env (или по умолчанию на 0.0.0.0:5005). Нажмите Ctrl+C для остановки.

### Автозапуск (с Termux:Boot)

1. Установите приложение Termux:Boot из F-Droid.
2. Убедитесь, что для Termux отключена оптимизация батареи в настройках Android.
3. Создайте скрипт запуска в ~/.termux/boot/:
```
mkdir -p ~/.termux/boot
nano ~/.termux/boot/start-pastebin.sh
```
4. Скопируйте в него содержимое скрипта автозапуска (см. предыдущие шаги нашей переписки, убедитесь, что пути и ключ PASTEBIN_SECRET_KEY верны). Примерное содержимое:
```
#!/data/data/com.termux/files/usr/bin/bash

sleep 15 # Даем сети подняться
termux-wake-lock & # Держим телефон активным

PASTEBIN_DIR="/data/data/com.termux/files/home/termux-pastebin"
cd "$PASTEBIN_DIR" || exit 1
source "$PASTEBIN_DIR/venv/bin/activate" || exit 1

if [ -f ".env" ]; then
    set -a; source ".env"; set +a
fi

if [ -z "$FLASK_SECRET_KEY" ]; then exit 1; fi

HOST=${PASTEBIN_HOST:-"0.0.0.0"}
PORT=${PASTEBIN_PORT:-"5005"}

nohup waitress-serve --host "$HOST" --port "$PORT" "src.app:app" >> "$PASTEBIN_DIR/pastebin-waitress.log" 2>&1 &

echo "$(date): Pastebin service start initiated (PID: $!)" >> "$PASTEBIN_DIR/pastebin-boot.log"
exit 0
```
5. Сделайте скрипт исполняемым:
```
chmod +x ~/.termux/boot/start-pastebin.sh
```
6. После перезагрузки телефона или перезапуска Termux сервис должен запуститься автоматически. Проверяйте логи в ~/termux-pastebin/pastebin-waitress.log и ~/termux-pastebin/pastebin-boot.log.

## Доступ к веб-интерфейсу

Откройте браузер на устройстве в той же сети (Wi-Fi/WireGuard), что и ваш телефон с Termux. Перейдите по адресу:

`http://<IP-адрес_телефона>:<Порт>`
(Например: `http://192.168.0.15:5005`)

*   На главной странице вы увидите форму для создания пасты.
*   Используйте чекбокс **"Сделать пасту публичной"**, чтобы контролировать доступ к создаваемой пасте. Если галочка снята, паста будет приватной.
*   Для создания пасты и просмотра списка своих паст необходимо **войти через Яндекс**.
*   Перейдите по ссылке **"Мои пасты"**, чтобы увидеть список ваших паст (публичных и приватных).
*   Ссылки на **публичные** пасты (`http://<IP>:<Порт>/<ключ_пасты>`) доступны всем.
*   Ссылки на **приватные** пасты доступны только вам после авторизации.
*   Используйте кнопку **"Выйти"** для завершения сеанса.

## 🧪 Тестирование

(Раздел пока пуст, тесты не реализованы)

## 📜 Лицензия
Этот проект распространяется под лицензией MIT. Подробности смотрите в файле LICENSE. (Не забудьте добавить файл LICENSE с текстом лицензии).
📞 Контакты
Создатель: [Mr Vi](https://t.me/B4DCAT) - [dev@b4dcat.ru]()
GitHub Issues: https://github.com/mrvi0/termux-pastebin/issues