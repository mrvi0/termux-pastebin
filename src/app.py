# src/app.py
import logging
import logging.handlers
import os
from pathlib import Path

from authlib.integrations.flask_client import OAuth
from flask import (
    Flask,
    abort,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.exceptions import HTTPException

# Импортируем наш модуль БД
from . import database

# --- Определяем пути ---
# Важно: Убедись, что эти пути определяются корректно!
current_file_path = Path(__file__).resolve()
src_dir = current_file_path.parent
project_root = src_dir.parent
templates_dir = src_dir / "templates"
static_dir = src_dir / "static"
LOG_DIR = project_root / "logs"  # Папка для логов
LOG_DIR.mkdir(parents=True, exist_ok=True)  # Создаем папку, если надо

# --- НАСТРОЙКА КОРНЕВОГО ЛОГГЕРА ---
# Настраиваем один раз здесь, чтобы все модули (app, database, security) его использовали
log_formatter = logging.Formatter(
    "%(asctime)s - %(name)s:%(lineno)d - %(levelname)s - %(message)s"
)
log_level = logging.DEBUG  # Ставим DEBUG, чтобы видеть все подробно во время отладки

root_logger = logging.getLogger()  # Получаем корневой логгер
root_logger.setLevel(log_level)

# Убираем ВСЕ существующие обработчики с корневого логгера, чтобы избежать дублей
for handler in root_logger.handlers[:]:
    root_logger.removeHandler(handler)

# 1. Обработчик для вывода в консоль -> в файл nohup/waitress
console_handler = logging.StreamHandler()
console_handler.setFormatter(log_formatter)
# Уровень для консоли можно сделать INFO, чтобы не слишком шуметь
# но для отладки оставим DEBUG
console_handler.setLevel(log_level)
root_logger.addHandler(console_handler)

# 2. Обработчик для записи в отдельный ротируемый файл 'pastebin_app.log'
log_file_path = LOG_DIR / "pastebin_app.log"
try:
    file_handler = logging.handlers.RotatingFileHandler(
        log_file_path,
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",  # 5MB, 3 копии
    )
    file_handler.setFormatter(log_formatter)
    file_handler.setLevel(logging.DEBUG)  # Пишем все DEBUG сообщения в файл
    root_logger.addHandler(file_handler)
    root_logger.info(f"Логирование также настроено в файл: {log_file_path}")
except Exception as e:
    root_logger.error(
        f"Не удалось настроить файловый логгер для {log_file_path}: {e}", exc_info=True
    )

# Уменьшаем шум от сторонних библиотек
logging.getLogger("waitress").setLevel(logging.INFO)  # Оставляем INFO для waitress
logging.getLogger("werkzeug").setLevel(
    logging.WARNING
)  # Логи запросов Flask будут на уровне INFO/DEBUG нашего логгера

# --- Создание Приложения Flask ---
# logger_name можно не указывать, он возьмет имя модуля 'src.app'
# log_handler можно не указывать, т.к. мы настроили корневой логгер
app = Flask(__name__, template_folder=str(templates_dir), static_folder=str(static_dir))
# Отключать логгер Flask не нужно, он будет использовать настроенный корневой
# app.logger.disabled = True # <-- Закомментировано/Удалено
logger = (
    app.logger
)  # Можно продолжать использовать app.logger, он теперь настроен через root

# --- Конфигурация Flask (Secret Key) ---
app.config["SECRET_KEY"] = os.environ.get("FLASK_SECRET_KEY")
if not app.config["SECRET_KEY"]:
    logger.critical(
        "FLASK_SECRET_KEY не установлен! Работа flash и сессий НЕ ГАРАНТИРОВАНА!"
    )
    app.config["SECRET_KEY"] = "very-unsafe-default-key-for-emergency"

# --- Инициализация Базы Данных ---
# Вызываем функцию инициализации один раз при старте
try:
    database.init_db()
except Exception as e:
    # Логгер уже настроен, сообщение будет видно
    logger.critical(f"КРИТИЧЕСКАЯ ОШИБКА ИНИЦИАЛИЗАЦИИ БД! {e}", exc_info=True)
    # В реальном приложении здесь стоило бы завершить работу
    # import sys; sys.exit(1)

# --- Настройка OAuth с Authlib ---
oauth = OAuth(app)
yandex_client_id = os.environ.get("YANDEX_CLIENT_ID")
yandex_client_secret = os.environ.get("YANDEX_CLIENT_SECRET")

if not yandex_client_id or not yandex_client_secret:
    logger.error(
        "YANDEX_CLIENT_ID или YANDEX_CLIENT_SECRET не установлены! Авторизация Яндекс не будет работать."
    )
else:
    oauth.register(
        name="yandex",
        client_id=yandex_client_id,
        client_secret=yandex_client_secret,
        access_token_url="https://oauth.yandex.ru/token",
        access_token_params=None,
        authorize_url="https://oauth.yandex.ru/authorize",
        authorize_params=None,
        api_base_url="https://login.yandex.ru/",
        userinfo_endpoint="info?format=json",
        client_kwargs={"scope": "login:info login:email"},
    )
    logger.info("OAuth клиент для Yandex зарегистрирован.")


# --- Роуты Аутентификации ---
@app.route("/login")
def login():
    """Отображает страницу входа."""
    if "user_id" in session:
        return redirect(url_for("my_pastes"))  # Редирект на "мои пасты", если уже вошел
    logger.debug("Отображение страницы входа.")
    return render_template("login.html")


@app.route("/login/yandex")
def login_yandex():
    """Редирект на страницу авторизации Яндекса."""
    if not yandex_client_id or not yandex_client_secret:
        flash("Авторизация через Яндекс не настроена на сервере.", "danger")
        return redirect(url_for("login"))
    # Генерируем правильный callback URL с HTTPS
    redirect_uri = url_for("authorize_yandex", _external=True, _scheme="https")
    logger.info(f"Инициация входа через Яндекс. Redirect URI: {redirect_uri}")
    # Authlib сама сделает редирект
    return oauth.yandex.authorize_redirect(redirect_uri)


@app.route("/auth/yandex/callback")
def authorize_yandex():
    """Обрабатывает callback от Яндекса."""
    logger.debug("Получен callback от Яндекса.")
    try:
        # Получаем токен (Authlib берет 'code' из URL)
        token = oauth.yandex.authorize_access_token()
        if not token or "access_token" not in token:
            flash("Ошибка получения токена от Яндекса.", "danger")
            logger.error("Не удалось получить access_token от Яндекса при callback.")
            return redirect(url_for("login"))  # Возвращаем на логин

        # Запрашиваем информацию о пользователе
        logger.debug("Запрос информации о пользователе к Яндексу...")
        resp = oauth.yandex.get("info?format=json")
        resp.raise_for_status()  # Проверяем HTTP ошибки
        user_info = resp.json()
        yandex_id = user_info.get("id")
        login = user_info.get("login")
        logger.info(
            f"Получена информация о пользователе Яндекс ID: {yandex_id}, Login: {login}"
        )

        # Работаем с нашей БД: ищем или создаем пользователя
        user_id = database.get_or_create_user(user_info)

        if user_id:
            # Успех! Сохраняем нашего user_id и display_name в сессию
            session["user_id"] = user_id
            session["display_name"] = (
                user_info.get("display_name") or login
            )  # Используем логин, если нет display_name
            flash("Вход через Яндекс выполнен успешно!", "success")
            logger.info(
                f"Пользователь Yandex ID {yandex_id} ({login}) успешно авторизован как локальный user_id {user_id}"
            )
            # Перенаправляем на страницу "Мои пасты"
            return redirect(url_for("my_pastes"))
        else:
            # Ошибка работы с нашей БД
            flash("Ошибка сохранения данных пользователя.", "danger")
            logger.error(
                f"Не удалось найти или создать пользователя в БД для Yandex ID: {yandex_id}"
            )
            return redirect(url_for("login"))

    except Exception as e:
        # Ловим любые другие ошибки (сетевые, OAuth и т.д.)
        logger.error(f"Общая ошибка во время callback от Яндекса: {e}", exc_info=True)
        flash(
            f"Произошла ошибка авторизации через Яндекс: {type(e).__name__}", "danger"
        )
        return redirect(url_for("login"))


@app.route("/logout", methods=["POST"])  # Ожидаем только POST
def logout():
    """Выход пользователя из системы."""
    user_id = session.get("user_id")  # Получаем ID для лога перед очисткой
    session.pop("user_id", None)
    session.pop("display_name", None)
    flash("Вы успешно вышли из системы.", "info")
    logger.info(f"Пользователь user_id={user_id} вышел из системы.")
    return redirect(url_for("login"))  # Редирект на страницу входа


# --- Роуты Приложения ---


@app.route("/", methods=["GET"])
def home():
    """Отображает главную страницу с формой."""
    # Просто отображаем форму, имя пользователя берется из сессии в шаблоне base.html
    logger.debug(f"Запрос GET / от {request.remote_addr}")
    return render_template("home.html")


@app.route("/", methods=["POST"])
def create_paste():
    """Обрабатывает создание новой пасты."""
    user_id = session.get("user_id")  # Будет None для анонимов
    user_log_id = user_id if user_id else f"Anon_{request.remote_addr}"
    logger.info(f"Попытка создания пасты от '{user_log_id}'")

    content = request.form.get("content")
    is_public = request.form.get("is_public") == "yes"  # Чекбокс
    language = request.form.get("language") or None  # Язык пока не используем

    # Валидация контента
    if not content or not content.strip():
        flash("Содержимое пасты не может быть пустым!", "danger")
        return redirect(url_for("home"))
    MAX_PASTE_SIZE_BYTES = 1 * 1024 * 1024  # 1MB
    if len(content.encode("utf-8", errors="ignore")) > MAX_PASTE_SIZE_BYTES:
        flash(
            f"Ошибка: Максимальный размер пасты {MAX_PASTE_SIZE_BYTES // 1024 // 1024}MB.",
            "danger",
        )
        return redirect(url_for("home"))

    # Сохраняем пасту (функция сама зашифрует, если is_public=False)
    paste_key = database.add_paste(
        content, user_id=user_id, language=language, is_public=is_public
    )

    if paste_key:
        paste_url = url_for("view_paste", paste_key=paste_key, _external=True)
        logger.info(
            f"Паста {paste_key} создана (user_id={user_id}, public={is_public}). URL: {paste_url}"
        )
        flash(f"Паста создана! Ссылка: {paste_url}", "success")
        return redirect(url_for("view_paste", paste_key=paste_key))
    else:
        logger.error(
            f"Не удалось создать пасту для '{user_log_id}'. Ошибка БД или шифрования."
        )
        flash("Произошла ошибка при создании пасты. Попробуйте снова.", "danger")
        return redirect(url_for("home"))


@app.route("/my-pastes")
def my_pastes():
    """Отображает пасты текущего пользователя."""
    user_id = session.get("user_id")
    if not user_id:
        flash("Пожалуйста, войдите, чтобы просмотреть свои пасты.", "info")
        return redirect(url_for("login"))

    logger.debug(f"Запрос /my-pastes для user_id={user_id}")
    user_pastes = database.get_user_pastes(
        user_id
    )  # Функция возвращает список словарей с превью
    logger.debug(f"Получено {len(user_pastes)} паст для user_id={user_id}")
    return render_template("my_pastes.html", pastes=user_pastes)


@app.route("/<paste_key>")
def view_paste(paste_key: str):
    """Отображает одну пасту, проверяя права на приватные."""
    logger.debug(f"Запрос /view_paste для ключа '{paste_key}' от {request.remote_addr}")
    # Валидация формата ключа
    import re

    if not re.fullmatch(r"[a-zA-Z0-9]{5,12}", paste_key):
        logger.warning(f"Неверный формат ключа '{paste_key}'")
        return render_template(
            "view_paste.html",
            paste_key=paste_key,
            error_message="Неверный формат ключа пасты.",
            content=None,
        ), 404

    result = database.get_paste(
        paste_key
    )  # Возвращает (content, lang, author_id, is_public)

    if result:
        content, language, author_user_id, is_public = result
        current_user_id = session.get("user_id")

        # Проверка доступа
        if not is_public and current_user_id != author_user_id:
            logger.warning(
                f"Доступ запрещен к приватной пасте '{paste_key}' (user: {current_user_id}, author: {author_user_id})."
            )
            return render_template(
                "view_paste.html",
                paste_key=paste_key,
                error_message="Это приватная паста. Доступ есть только у автора.",
                content=None,
            ), 403

        logger.info(f"Отображение пасты '{paste_key}' (public={is_public})")
        # TODO: Получить имя автора по author_user_id для отображения в шаблоне
        author_name = None
        return render_template(
            "view_paste.html",
            paste_key=paste_key,
            content=content,
            language=language,
            is_public=is_public,
            author_name=author_name,
        )
    else:
        logger.warning(f"Паста '{paste_key}' не найдена в БД.")
        return render_template(
            "view_paste.html",
            paste_key=paste_key,
            error_message=f"Паста с ключом '{paste_key}' не найдена.",
            content=None,
        ), 404



@app.route("/delete/<paste_key>", methods=["POST"])
def delete_single_paste(paste_key: str):
    """Обрабатывает удаление одной пасты со страницы просмотра."""
    user_id = session.get("user_id")
    logger.info(
        f"Попытка удаления пасты '{paste_key}' пользователем {user_id or 'Аноним'}"
    )

    if not user_id:
        flash("Доступ запрещен: необходимо авторизоваться.", "danger")
        abort(403)  # Или редирект на логин

    # Сначала получаем пасту, чтобы убедиться, что она принадлежит пользователю
    # (хотя кнопка и так видна только автору, но лучше проверить на сервере)
    result = database.get_paste(paste_key)
    if not result:
        abort(404)  # Паста не найдена

    _content, _language, author_user_id, _is_public = result

    if author_user_id != user_id:
        logger.warning(
            f"Попытка удаления чужой пасты! User={user_id}, PasteKey={paste_key}, Author={author_user_id}"
        )
        flash("Ошибка: Вы можете удалять только свои пасты.", "danger")
        abort(403)  # Доступ запрещен

    # Если все проверки пройдены, удаляем пасту
    success = database.delete_paste(paste_key, user_id)

    if success:
        flash(f"Паста '{paste_key}' успешно удалена.", "success")
        # Перенаправляем на страницу "Мои пасты" после удаления
        return redirect(url_for("my_pastes"))
    else:
        flash(f"Не удалось удалить пасту '{paste_key}'. Ошибка базы данных.", "danger")
        # Возвращаем на страницу просмотра пасты, если удаление не удалось
        return redirect(url_for("view_paste", paste_key=paste_key))


@app.route("/delete-selected", methods=["POST"])
def delete_selected_pastes():
    """Обрабатывает удаление выбранных паст со страницы 'Мои пасты'."""
    user_id = session.get("user_id")
    if not user_id:
        flash("Доступ запрещен: необходимо авторизоваться.", "danger")
        return redirect(url_for("login"))  # Редирект на логин

    # Получаем список ключей паст из формы (чекбоксы с name="paste_keys")
    keys_to_delete = request.form.getlist("paste_keys")
    logger.info(
        f"Запрос на массовое удаление паст от user_id={user_id}. Ключи: {keys_to_delete}"
    )

    if not keys_to_delete:
        flash("Вы не выбрали ни одной пасты для удаления.", "warning")
        return redirect(url_for("my_pastes"))

    # Удаляем пасты, принадлежащие ЭТОМУ пользователю
    deleted_count, requested_count = database.delete_pastes(keys_to_delete, user_id)

    if deleted_count > 0:
        flash(
            f"Успешно удалено {deleted_count} из {requested_count} выбранных паст.",
            "success",
        )
    elif requested_count > 0:
        # Если запрошенные были, но ничего не удалено (ошибка БД или чужие пасты)
        flash(
            "Не удалось удалить выбранные пасты. Возможно, они уже удалены или произошла ошибка.",
            "warning",
        )
    else:
        # Сюда не должны попасть, т.к. есть проверка на keys_to_delete выше
        flash("Произошла странная ошибка при удалении.", "danger")

    return redirect(url_for("my_pastes"))  # Возвращаемся на страницу "Мои пасты"



@app.errorhandler(Exception)
def handle_exception(e: Exception):
    # Обрабатываем стандартные HTTP ошибки отдельно
    if isinstance(e, HTTPException):
        # Логируем только ошибки сервера (5xx) или непредвиденные клиентские
        if e.code >= 500 or e.code not in [401, 403, 404]:
            logger.error(
                f"HTTP ошибка {e.code}: {e.name} для {request.url}", exc_info=True
            )
        else:
            # Логируем 4xx как warning
            logger.warning(f"HTTP ошибка {e.code}: {e.name} для {request.url}")
        # Возвращаем стандартный обработчик Flask для HTTP ошибок
        return e
    # Для всех остальных - это 500 Internal Server Error
    logger.critical(f"Неперехваченное исключение на {request.url}: {e}", exc_info=True)
    # Можно показать кастомный шаблон 500.html
    # return render_template('500.html'), 500
    return "Internal Server Error", 500
