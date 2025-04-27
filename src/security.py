# src/security.py
import base64
import logging
import os
import secrets  # Используем secrets для генерации nonce
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# --- Настройка Логгера ---
# Получаем логгер с именем этого модуля ('src.security'),
# он будет использовать настройки корневого логгера из app.py
logger = logging.getLogger(__name__)

# --- Загрузка и проверка Ключа Шифрования ---
_key: bytes | None = None # Аннотируем тип
PASTE_ENCRYPTION_KEY_ENV = "PASTE_ENCRYPTION_KEY" # Имя переменной окружения

def _load_encryption_key() -> bytes | None:
    """Загружает и валидирует ключ шифрования из переменной окружения."""
    global _key
    if _key: # Если ключ уже загружен
        return _key

    encoded_key = os.environ.get(PASTE_ENCRYPTION_KEY_ENV)
    if not encoded_key:
        logger.critical(f"Переменная окружения {PASTE_ENCRYPTION_KEY_ENV} не установлена! Шифрование/дешифрование НЕВОЗМОЖНО.")
        return None
    try:
        decoded_key = base64.urlsafe_b64decode(encoded_key)
        # Ключ для AES-GCM должен быть 16, 24 или 32 байта. Используем 32 (AES-256).
        if len(decoded_key) != 32:
            logger.critical(f"{PASTE_ENCRYPTION_KEY_ENV} должен быть длиной 32 байта после декодирования base64 (получено: {len(decoded_key)} байт).")
            return None
        _key = decoded_key # Сохраняем ключ в глобальную переменную модуля
        logger.info("Ключ шифрования паст успешно загружен и валидирован.")
        return _key
    except (ValueError, TypeError) as e:
        logger.critical(f"Ошибка декодирования {PASTE_ENCRYPTION_KEY_ENV} из base64: {e}")
        return None

# Загружаем ключ при импорте модуля
_key = _load_encryption_key()

# --- Функции шифрования/дешифрования ---

def encrypt_content(content: str) -> bytes | None:
    """
    Шифрует текстовое содержимое с использованием AES-256-GCM.
    Возвращает байтовую строку: nonce (12 байт) + ciphertext + tag (16 байт).
    Возвращает None в случае ошибки.
    """
    if _key is None:
        logger.error("Шифрование невозможно: ключ не загружен или невалиден.")
        return None
    if not isinstance(content, str):
        logger.error("Шифрование невозможно: входные данные не являются строкой.")
        return None

    try:
        # Используем AESGCM напрямую - это проще и безопаснее
        aesgcm = AESGCM(_key)
        # Генерируем криптографически стойкий nonce (12 байт рекомендовано для GCM)
        nonce = secrets.token_bytes(12)
        # Шифруем данные (кодируем строку в UTF-8)
        # associated_data (AAD) можно не использовать, если не нужна доп. аутентификация
        ciphertext_and_tag = aesgcm.encrypt(nonce, content.encode('utf-8'), None)
        # Сохраняем nonce вместе с шифротекстом и тегом аутентификации
        encrypted_data = nonce + ciphertext_and_tag
        logger.debug(f"Контент успешно зашифрован (nonce: {len(nonce)}B, ctext+tag: {len(ciphertext_and_tag)}B, total: {len(encrypted_data)}B).")
        return encrypted_data
    except Exception:
        # Ловим любые ошибки во время шифрования
        logger.exception("Неожиданная ошибка при шифровании контента.")
        return None

def decrypt_content(encrypted_data: bytes) -> str | None:
    """
    Дешифрует данные, зашифрованные с помощью encrypt_content (AES-256-GCM).
    Ожидает байтовую строку: nonce (12 байт) + ciphertext + tag (16 байт).
    Возвращает исходную строку или None в случае ошибки (неверный ключ, данные повреждены).
    """
    if _key is None:
        logger.error("Дешифрование невозможно: ключ не загружен или невалиден.")
        return None

    # Ожидаемая минимальная длина = nonce (12) + tag (16) = 28 байт
    # (Шифротекст может быть пустым)
    nonce_len = 12
    if not isinstance(encrypted_data, bytes) or len(encrypted_data) < nonce_len:
        logger.error(f"Дешифрование невозможно: неверный формат входных данных (тип: {type(encrypted_data)}, длина: {len(encrypted_data) if encrypted_data else 0}). Ожидались байты длиной >= {nonce_len}.")
        return None

    try:
        aesgcm = AESGCM(_key)
        # Извлекаем nonce
        nonce = encrypted_data[:nonce_len]
        # Извлекаем шифротекст + тег
        ciphertext_and_tag = encrypted_data[nonce_len:]
        # Дешифруем. AESGCM.decrypt автоматически проверяет тег аутентификации.
        # Если ключ неверный или данные изменены, будет выброшено исключение InvalidTag.
        plaintext_bytes = aesgcm.decrypt(nonce, ciphertext_and_tag, None)
        # Декодируем в строку UTF-8
        decrypted_text = plaintext_bytes.decode('utf-8')
        logger.debug("Контент успешно дешифрован.")
        return decrypted_text
    # Ловим специфичные ошибки и общие ошибки
    except InvalidTag: # Импорт нужен: from cryptography.exceptions import InvalidTag (если не импортирован глобально)
        # Самая частая ошибка - неверный ключ или поврежденные данные
        logger.error("Ошибка дешифрования: Неверный тег аутентификации (возможно, неверный ключ или данные повреждены).", exc_info=False) # Не пишем полный трейсбек для этой частой ошибки
        return None
    except Exception as e:
        # Другие возможные ошибки (проблемы с nonce, внутренние ошибки cryptography)
        logger.error(f"Ошибка при дешифровании контента: {e}", exc_info=True)
        return None
