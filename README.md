# Termux Pastebin

<!-- Бейджи пока уберем, так как нет CI/CD и публичного репозитория -->
<!-- [![CI Status](...)](...) -->
<!-- [![Lint Status](...)](...) -->
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT) <!-- Заменил на MIT, т.к. AGPL может быть избыточен -->

Простой сервис для обмена текстовыми фрагментами (пастами), предназначенный для запуска на устройстве с Termux. Позволяет быстро создавать пасты и делиться ими по ссылке в локальной сети или через VPN (WireGuard).

## ✨ Основные возможности

*   Создание текстовых паст через веб-интерфейс.
*   Генерация коротких, уникальных ссылок для каждой пасты.
*   Просмотр паст по ссылке.
*   Базовая HTTP-аутентификация (Basic Auth) для создания паст.
*   Хранение паст в локальной базе данных SQLite.
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

*   `FLASK_SECRET_KEY`: **Обязательно.** Секретный ключ для Flask (для flash сообщений и др.). Сгенерируйте надежный ключ.
*   `BASIC_AUTH_USERNAME`: **Обязательно.** Имя пользователя для доступа к созданию паст.
*   `BASIC_AUTH_PASSWORD`: **Обязательно.** Пароль для доступа к созданию паст.
*   `PASTEBIN_HOST`: IP-адрес, на котором будет слушать сервер (по умолчанию `0.0.0.0` - все интерфейсы).
*   `PASTEBIN_PORT`: Порт, на котором будет слушать сервер (по умолчанию `5005`).

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

Откройте браузер на устройстве, которое находится в той же сети (Wi-Fi или WireGuard), что и ваш телефон с Termux. Перейдите по адресу:
```
http://<IP-адрес_телефона>:<Порт>
```
* Для создания пасты потребуется ввести логин и пароль (Basic Auth), которые вы указали в .env.
* Ссылки на созданные пасты (http://<IP>:<Порт>/<ключ_пасты>) будут доступны без авторизации.

## 🧪 Тестирование

(Раздел пока пуст, тесты не реализованы)

## 📜 Лицензия
Этот проект распространяется под лицензией MIT. Подробности смотрите в файле LICENSE. (Не забудьте добавить файл LICENSE с текстом лицензии).
📞 Контакты
Создатель: [Mr Vi](https://t.me/B4DCAT) - [dev@b4dcat.ru]()
GitHub Issues: https://github.com/mrvi0/termux-pastebin/issues