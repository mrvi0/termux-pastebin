# src/app.py
import os
import logging
import logging.handlers # Для настройки логгера
from pathlib import Path
from flask import (
    Flask, request, redirect, url_for, render_template,
    abort, flash
)

from werkzeug.exceptions import HTTPException # Для перехвата стандартных ошибок Flask

# --- Импортируем наш модуль БД и инициализируем её ---
from . import database # Относительный импорт

# --- ДОБАВИМ ОТЛАДКУ ПУТЕЙ ---
current_file_path = Path(__file__).resolve()
src_dir = current_file_path.parent
project_root = src_dir.parent
templates_dir = src_dir / "templates"
static_dir = src_dir / "static"

# --- Настройка Приложения Flask ---
app = Flask(__name__,
            template_folder=str(templates_dir),
            static_folder=str(static_dir)
            )

# --- Конфигурация Flask ---
# Загружаем секретный ключ из переменной окружения (важно для flash и сессий)
app.config['SECRET_KEY'] = os.environ.get("FLASK_SECRET_KEY")
if not app.config['SECRET_KEY']:
    logging.warning("FLASK_SECRET_KEY не установлен! Flash-сообщения могут не работать безопасно.")
    app.config['SECRET_KEY'] = 'default-insecure-key' # Устанавливаем небезопасный ключ по умолчанию

# --- Настройка Логирования Flask ---
# Убираем стандартные обработчики Flask, если они есть
# for handler in app.logger.handlers[:]: app.logger.removeHandler(handler) # Будь осторожен с этим

# Настраиваем наш логгер (можно использовать тот же формат, что и для database)
log_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
log_level = logging.INFO # Уровень логгирования для Flask (можно INFO или DEBUG)

# Обработчик в консоль
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(log_formatter)
stream_handler.setLevel(log_level)
# app.logger.addHandler(stream_handler) # Добавляем к логгеру Flask
logging.getLogger().addHandler(stream_handler) # Или добавляем к корневому логгеру

# Опционально: Обработчик в файл (если нужен отдельный лог для веб-запросов)
log_file = Path(__file__).parent.parent / "logs" / "pastebin_app.log"
log_file.parent.mkdir(exist_ok=True)
file_handler = logging.handlers.RotatingFileHandler(
    log_file, maxBytes=2*1024*1024, backupCount=2, encoding='utf-8'
)
file_handler.setFormatter(log_formatter)
file_handler.setLevel(logging.DEBUG)
app.logger.addHandler(file_handler)
logging.getLogger().addHandler(file_handler) # Добавляем к корневому

# Устанавливаем уровень для логгера Flask
app.logger.setLevel(log_level)
logging.getLogger().setLevel(log_level) # Устанавливаем уровень для корневого логгера
logging.getLogger('waitress').setLevel(logging.WARNING) # Уменьшаем шум от waitress
logger = app.logger # Используем логгер Flask для сообщений из этого файла

# --- Инициализация Базы Данных ---
# Вызываем функцию инициализации из модуля database при старте приложения
try:
    database.init_db()
except Exception as e:
    logger.critical(f"КРИТИЧЕСКАЯ ОШИБКА: Не удалось инициализировать базу данных при старте! {e}")
    # Приложение, скорее всего, не сможет работать, но Flask продолжит запуск.
    # Можно добавить sys.exit(1) здесь, если нужно жестко остановить.

# --- Роуты Приложения ---

@app.route('/', methods=['GET'])

def home():
    """Отображает главную страницу с формой для создания пасты."""
    logger.info(f"Запрос главной страницы от {request.remote_addr}")
    return render_template('home.html', username=username)

@app.route('/', methods=['POST'])
def create_paste():
    """Принимает данные из формы и создает новую пасту."""
    logger.info(f"Попытка создания пасты от пользователя '{user}' ({request.remote_addr})")
    content = request.form.get('content')
    language = request.form.get('language') # Пока не используется

    if not content or not content.strip():
        flash("Содержимое пасты не может быть пустым!", "danger")
        logger.warning(f"Попытка создания пустой пасты от '{user}'.")
        return redirect(url_for('home'))

    # Ограничение размера
    MAX_PASTE_SIZE_BYTES = 1 * 1024 * 1024 # 1MB
    if len(content.encode('utf-8', errors='ignore')) > MAX_PASTE_SIZE_BYTES:
         flash(f"Ошибка: Максимальный размер пасты {MAX_PASTE_SIZE_BYTES // 1024 // 1024}MB.", "danger")
         logger.warning(f"Попытка создания слишком большой пасты от '{user}'.")
         return redirect(url_for('home'))

    paste_key = database.add_paste(content, language)

    if paste_key:
        paste_url = url_for('view_paste', paste_key=paste_key, _external=True)
        # Используем _external=True, чтобы получить полный URL
        logger.info(f"Паста {paste_key} создана пользователем '{user}'. URL: {paste_url}")
        flash(f"Паста создана! Ссылка: {paste_url}", "success")
        # Перенаправляем на страницу просмотра
        return redirect(url_for('view_paste', paste_key=paste_key))
    else:
        logger.error(f"Не удалось создать пасту для пользователя '{user}'.")
        flash("Произошла ошибка при создании пасты. Попробуйте снова.", "danger")
        return redirect(url_for('home'))

@app.route('/<paste_key>')

def view_paste(paste_key: str):
    """Отображает содержимое пасты по ее ключу."""
    logger.info(f"Запрос просмотра пасты '{paste_key}' от {request.remote_addr}")
    # Простая валидация ключа
    import re
    if not re.fullmatch(r'[a-zA-Z0-9]{5,12}', paste_key):
         logger.warning(f"Неверный формат ключа '{paste_key}' от {request.remote_addr}")
         abort(404)

    result = database.get_paste(paste_key)
    if result:
        content, language = result
        return render_template('view_paste.html',
                               paste_key=paste_key,
                               content=content,
                               language=language)
    else:
        # Если паста не найдена
        logger.warning(f"Паста '{paste_key}' не найдена (запрос от {request.remote_addr}).")
        abort(404) # Flask сам покажет стандартную страницу 404

# --- Обработчики Ошибок ---
@app.errorhandler(404)
def page_not_found(e: HTTPException):
    """Обработчик для ошибки 404 (Страница не найдена)."""
    logger.warning(f"Запрос к несуществующей странице: {request.url} (от {request.remote_addr})")
    # Можно отрендерить кастомный шаблон 404.html или просто текст
    return render_template('view_paste.html', paste_key='404 Не найдено', content=None), 404

@app.errorhandler(Exception)
def handle_exception(e: Exception):
    """Обработчик для всех остальных (неперехваченных) ошибок."""
    # Перехватываем стандартные HTTP исключения Flask/Werkzeug, чтобы не логировать их как 500
    if isinstance(e, HTTPException):
        # Для 404 и 401 у нас есть отдельные обработчики
        if e.code not in [404, 401]:
             logger.warning(f"Перехвачена HTTP ошибка {e.code}: {e.description} (Запрос: {request.method} {request.path} от {request.remote_addr})")
        return e # Возвращаем стандартный ответ Flask для HTTP ошибок

    # Для всех остальных ошибок логируем полный трейсбек
    logger.critical(f"Неперехваченное исключение: {e}", exc_info=True)
    # Возвращаем пользователю общую страницу ошибки 500
    # Можно создать шаблон 500.html
    return "Internal Server Error", 500

# --- Запуск (для waitress) ---
# Этот блок if __name__ == '__main__' больше не нужен,
# так как мы будем запускать через waitress или gunicorn, указывая app:app