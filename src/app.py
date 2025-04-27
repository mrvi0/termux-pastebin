# src/app.py
import logging
import logging.handlers  # Для настройки логгера
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
from werkzeug.exceptions import HTTPException  # Для перехвата стандартных ошибок Flask

# --- Импортируем наш модуль БД и инициализируем её ---
from . import database  # Относительный импорт

current_file_path = Path(__file__).resolve()
src_dir = current_file_path.parent
project_root = src_dir.parent
templates_dir = src_dir / "templates"
static_dir = src_dir / "static"

# --- Настройка Приложения Flask ---
app = Flask(__name__, template_folder=str(templates_dir), static_folder=str(static_dir))

# --- Добавить Middleware ProxyFix ---
# x_for=1: доверять одному прокси (твоему Nginx)
# x_proto=1: доверять заголовку X-Forwarded-Proto
# x_host=1: доверять заголовку X-Forwarded-Host
# app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
# --- Конец добавления Middleware ---

# --- Конфигурация Flask ---
# Загружаем секретный ключ из переменной окружения (важно для flash и сессий)
app.config["SECRET_KEY"] = os.environ.get("FLASK_SECRET_KEY")
if not app.config["SECRET_KEY"]:
    logging.warning(
        "FLASK_SECRET_KEY не установлен! Flash-сообщения могут не работать безопасно."
    )
    app.config["SECRET_KEY"] = (
        "default-insecure-key"  # Устанавливаем небезопасный ключ по умолчанию
    )

# --- Настройка Логирования Flask ---
# Убираем стандартные обработчики Flask, если они есть
# for handler in app.logger.handlers[:]: app.logger.removeHandler(handler) # Будь осторожен с этим

# Настраиваем наш логгер (можно использовать тот же формат, что и для database)
log_formatter = logging.Formatter(
    "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
log_level = logging.INFO  # Уровень логгирования для Flask (можно INFO или DEBUG)

# Обработчик в консоль
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(log_formatter)
stream_handler.setLevel(log_level)
# app.logger.addHandler(stream_handler) # Добавляем к логгеру Flask
logging.getLogger().addHandler(stream_handler)  # Или добавляем к корневому логгеру

# Опционально: Обработчик в файл (если нужен отдельный лог для веб-запросов)
log_file = Path(__file__).parent.parent / "logs" / "pastebin_app.log"
log_file.parent.mkdir(exist_ok=True)
file_handler = logging.handlers.RotatingFileHandler(
    log_file, maxBytes=2 * 1024 * 1024, backupCount=2, encoding="utf-8"
)
file_handler.setFormatter(log_formatter)
file_handler.setLevel(logging.DEBUG)
app.logger.addHandler(file_handler)
logging.getLogger().addHandler(file_handler)  # Добавляем к корневому

# Устанавливаем уровень для логгера Flask
app.logger.setLevel(log_level)
logging.getLogger().setLevel(log_level)  # Устанавливаем уровень для корневого логгера
logging.getLogger("waitress").setLevel(logging.WARNING)  # Уменьшаем шум от waitress
logger = app.logger  # Используем логгер Flask для сообщений из этого файла

# --- Инициализация Базы Данных ---
# Вызываем функцию инициализации из модуля database при старте приложения
try:
    database.init_db()
except Exception as e:
    logger.critical(
        f"КРИТИЧЕСКАЯ ОШИБКА: Не удалось инициализировать базу данных при старте! {e}"
    )
    # Приложение, скорее всего, не сможет работать, но Flask продолжит запуск.
    # Можно добавить sys.exit(1) здесь, если нужно жестко остановить.

# --- Настройка OAuth с Authlib ---
# Создаем объект OAuth и привязываем его к приложению Flask
oauth = OAuth(app)

# Регистрируем провайдера 'yandex'
# Читаем Client ID и Secret из переменных окружения
yandex_client_id = os.environ.get("YANDEX_CLIENT_ID")
yandex_client_secret = os.environ.get("YANDEX_CLIENT_SECRET")

if not yandex_client_id or not yandex_client_secret:
    logger.error(
        "Переменные окружения YANDEX_CLIENT_ID или YANDEX_CLIENT_SECRET не установлены! Авторизация через Яндекс не будет работать."
    )

oauth.register(
    name="yandex",
    client_id=yandex_client_id,
    client_secret=yandex_client_secret,
    access_token_url="https://oauth.yandex.ru/token",
    access_token_params=None,
    authorize_url="https://oauth.yandex.ru/authorize",
    authorize_params=None,
    api_base_url="https://login.yandex.ru/",  # Базовый URL для запроса информации о пользователе
    userinfo_endpoint="info?format=json",  # Конечная точка для получения инфо о пользователе
    client_kwargs={"scope": "login:info login:email"},  # Запрашиваемые права доступа
    # Для Яндекса userinfo обычно соответствует ответу от /info
    # Можно определить свою функцию userinfo, если нужно преобразовать ответ
    # userinfo_compliance_fix=lambda resp: resp.json() # Пример простейшего преобразования
)

# --- Роуты Аутентификации ---


@app.route("/login")
def login():
    """Страница с кнопкой входа через Яндекс."""
    # Если пользователь уже в сессии, редирект на главную или "мои пасты"
    if "user_id" in session:
        return redirect(url_for("home"))  # Или 'my_pastes' позже
    return render_template("login.html")  # Создадим этот шаблон


@app.route("/login/yandex")
def login_yandex():
    """Инициирует процесс OAuth-авторизации через Яндекс."""
    # Формируем URL, на который Яндекс должен вернуть пользователя ПОСЛЕ авторизации
    # Важно, чтобы этот URL был ДОБАВЛЕН в Redirect URI в настройках приложения Яндекс.OAuth!
    # Используем _external=True для получения полного URL
    redirect_uri = url_for("authorize_yandex", _external=True, _scheme="https")
    logger.info(f"Запрос авторизации Яндекс. Redirect URI: {redirect_uri}")
    return oauth.yandex.authorize_redirect(redirect_uri)


@app.route("/auth/yandex/callback")  # Этот путь должен совпадать с Redirect URI
def authorize_yandex():
    """Обрабатывает ответ от Яндекса после авторизации пользователя."""
    try:
        # Получаем токен доступа от Яндекса, обменивая код авторизации
        # Authlib автоматически берет 'code' из параметров запроса
        token = oauth.yandex.authorize_access_token()
        if not token or "access_token" not in token:
            flash("Ошибка получения токена от Яндекса.", "danger")
            logger.error("Не удалось получить access_token от Яндекса.")
            return redirect(url_for("home"))

        # Используем полученный токен для запроса информации о пользователе
        # Authlib автоматически использует userinfo_endpoint, указанный при регистрации
        resp = oauth.yandex.get("info?format=json")  # Эндпоинт Яндекса для инфо
        resp.raise_for_status()  # Проверяем на ошибки HTTP
        user_info = resp.json()  # Получаем данные пользователя в JSON
        logger.info(
            f"Получена информация о пользователе Яндекс: {user_info.get('login')}"
        )

        # Находим или создаем пользователя в нашей БД
        user_id = database.get_or_create_user(user_info)

        if user_id:
            # Сохраняем ID НАШЕГО пользователя в сессию Flask
            session["user_id"] = user_id
            # Сохраняем еще какую-нибудь информацию для отображения, если нужно
            session["display_name"] = user_info.get("display_name") or user_info.get(
                "login"
            )
            flash("Вход через Яндекс выполнен успешно!", "success")
            logger.info(
                f"Пользователь Yandex ID {user_info.get('id')} вошел как локальный user_id {user_id}"
            )
            # Перенаправляем на главную или страницу "мои пасты"
            return redirect(url_for("home"))  # Заменить на 'my_pastes', когда она будет
        else:
            flash("Не удалось найти или создать пользователя в базе данных.", "danger")
            logger.error(
                f"Не удалось обработать пользователя Yandex: {user_info.get('id')}"
            )
            return redirect(url_for("home"))

    except Exception as e:
        # Ловим ошибки обмена токенами, запроса userinfo и т.д.
        logger.error(f"Ошибка во время callback от Яндекса: {e}", exc_info=True)
        flash("Произошла ошибка авторизации через Яндекс.", "danger")
        return redirect(url_for("home"))


@app.route("/logout", methods=["POST"])
def logout():
    """Очищает сессию пользователя и выходит из системы."""
    # Проверяем, действительно ли был POST запрос (Flask делает это сам, но для ясности)
    if request.method == "POST":
        session.pop("user_id", None)
        session.pop("display_name", None)
        flash("Вы успешно вышли из системы.", "info")
        logger.info("Пользователь вышел из системы (POST /logout).")
        # Перенаправляем на главную или страницу входа
        return redirect(url_for("login"))  # Лучше на login после выхода
    else:
        # Если кто-то попытается зайти на /logout через GET, можно просто редиректнуть
        return redirect(url_for("home"))


# --- Роуты Приложения ---


@app.route("/", methods=["GET"])
def home():
    """Отображает главную страницу с формой для создания пасты."""
    user_display_name = session.get("display_name")
    return render_template("home.html", user_display_name=user_display_name)


@app.route("/", methods=["POST"])
def create_paste():
    """Принимает данные из формы и создает новую пасту."""
    content = request.form.get("content")
    language = request.form.get("language")
    is_public_from_form = request.form.get("is_public") == "yes"
    # Получаем ID пользователя из сессии (будет None, если не авторизован)
    user_id = session.get("user_id")
    user_log_id = user_id if user_id else request.remote_addr  # Для логов

    logger.info(
        f"Попытка создания пасты от '{user_log_id}'. is_public={is_public_from_form}"
    )

    if not content or not content.strip():
        flash("Содержимое пасты не может быть пустым!", "danger")
        logger.warning(f"Попытка создания пустой пасты от '{user_log_id}'.")
        return redirect(url_for("home"))

    # Ограничение размера
    max_paste_size_bytes = 1 * 1024 * 1024  # 1MB
    if len(content.encode("utf-8", errors="ignore")) > max_paste_size_bytes:
        flash(
            f"Ошибка: Максимальный размер пасты {max_paste_size_bytes // 1024 // 1024}MB.",
            "danger",
        )
        logger.warning(f"Попытка создания слишком большой пасты от '{user_log_id}'.")
        return redirect(url_for("home"))

    paste_key = database.add_paste(
        content, user_id=user_id, language=language, is_public=is_public_from_form
    )

    if paste_key:
        paste_url = url_for("view_paste", paste_key=paste_key, _external=True)
        logger.info(
            f"Паста {paste_key} создана (user_id={user_id}, public={is_public_from_form}). URL: {paste_url}"
        )
        flash(f"Паста создана! Ссылка: {paste_url}", "success")
        return redirect(url_for("view_paste", paste_key=paste_key))
    else:
        logger.error(f"Не удалось создать пасту для '{user_log_id}'.")
        flash("Произошла ошибка при создании пасты. Попробуйте снова.", "danger")
        return redirect(url_for("home"))


@app.route("/my-pastes")
def my_pastes():
    """Отображает список паст текущего авторизованного пользователя."""
    # Проверяем, есть ли пользователь в сессии
    user_id = session.get("user_id")
    if not user_id:
        flash("Пожалуйста, войдите, чтобы просмотреть свои пасты.", "info")
        return redirect(url_for("login"))

    user_pastes = database.get_user_pastes(user_id)  # Функция уже возвращает is_public

    return render_template("my_pastes.html", pastes=user_pastes)


@app.route("/<paste_key>")
def view_paste(paste_key: str):
    """Отображает содержимое пасты по ее ключу."""
    logger.info(f"Запрос просмотра пасты '{paste_key}' от {request.remote_addr}")
    # Простая валидация ключа
    import re

    if not re.fullmatch(r"[a-zA-Z0-9]{5,12}", paste_key):
        logger.warning(f"Неверный формат ключа '{paste_key}' от {request.remote_addr}")
        return render_template(
            "view_paste.html",
            paste_key=paste_key,
            error_message="Неверный формат ключа пасты.",
            content=None,
        ), 404

    result = database.get_paste(paste_key)
    if result:
        content, language, author_user_id, is_public = result
        current_user_id = session.get("user_id")

        # --- ПРОВЕРКА ДОСТУПА К ПРИВАТНОЙ ПАСТЕ ---
        access_denied = False
        if not is_public:  # Если паста приватная
            if current_user_id is None:  # А пользователь не авторизован
                logger.warning(
                    f"Анонимный доступ запрещен к приватной пасте '{paste_key}'."
                )
                access_denied = True
            elif current_user_id != author_user_id:  # И пользователь не автор
                logger.warning(
                    f"Доступ пользователя {current_user_id} запрещен к приватной пасте '{paste_key}' (автор: {author_user_id})."
                )
                access_denied = True

        # --- Если доступ запрещен, рендерим шаблон с ошибкой ---
        if access_denied:
            return render_template(
                "view_paste.html",
                paste_key=paste_key,
                error_message="Это приватная паста. Доступ есть только у автора.",
                content=None,
            ), 403  # Отдаем статус 403 Forbidden

        # --- Если доступ разрешен ---
        logger.info(
            f"Доступ к пасте '{paste_key}' разрешен (public={is_public}, user={current_user_id}, author={author_user_id})."
        )
        author_name = None
        # TODO: Получить имя автора по author_user_id

        return render_template(
            "view_paste.html",
            paste_key=paste_key,
            content=content,  # Передаем уже готовый контент
            language=language,
            is_public=is_public,
            author_name=author_name,
        )
    else:
        # Если паста не найдена в БД
        logger.warning(f"Паста '{paste_key}' не найдена.")
        # Рендерим шаблон с сообщением "Не найдено" и статусом 404
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
    """Обработчик для всех остальных (неперехваченных) ошибок."""
    # Перехватываем стандартные HTTP исключения Flask/Werkzeug, чтобы не логировать их как 500
    if isinstance(e, HTTPException):
        # Для 404 и 401 у нас есть отдельные обработчики
        if e.code not in [404, 401]:
            logger.warning(
                f"Перехвачена HTTP ошибка {e.code}: {e.description} (Запрос: {request.method} {request.path} от {request.remote_addr})"
            )
        return e  # Возвращаем стандартный ответ Flask для HTTP ошибок

    # Для всех остальных ошибок логируем полный трейсбек
    logger.critical(f"Неперехваченное исключение: {e}", exc_info=True)
    # Возвращаем пользователю общую страницу ошибки 500
    # Можно создать шаблон 500.html
    return "Internal Server Error", 500


# --- Запуск (для waitress) ---
# Этот блок if __name__ == '__main__' больше не нужен,
# так как мы будем запускать через waitress или gunicorn, указывая app:app
