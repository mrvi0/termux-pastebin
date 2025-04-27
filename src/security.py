# src/security.py
import base64
import logging
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

logger = logging.getLogger(__name__)

# --- Загрузка ключа шифрования ---
# Читаем ключ из переменной окружения
_encoded_key = os.environ.get("PASTE_ENCRYPTION_KEY")
_key = None
if _encoded_key:
    try:
        # Декодируем ключ из base64
        _key = base64.urlsafe_b64decode(_encoded_key)
        if len(_key) != 32:
            logger.error(
                "PASTE_ENCRYPTION_KEY должен быть длиной 32 байта после декодирования base64!"
            )
            _key = None  # Сбрасываем ключ, если длина неверна
        else:
            logger.info("Ключ шифрования паст успешно загружен.")
    except (ValueError, TypeError) as e:
        logger.error(f"Ошибка декодирования PASTE_ENCRYPTION_KEY из base64: {e}")
        _key = None
else:
    logger.error(
        "Переменная окружения PASTE_ENCRYPTION_KEY не установлена! Шифрование паст будет невозможно."
    )

# --- Функции шифрования/дешифрования ---


def encrypt_content(content: str) -> bytes | None:
    """Шифрует текстовое содержимое с использованием AES-GCM."""
    if _key is None:
        logger.error("Шифрование невозможно: ключ не загружен.")
        return None
    if not isinstance(content, str):  # Принимаем только строки
        logger.error("Шифрование невозможно: входные данные не являются строкой.")
        return None

    try:
        aesgcm = AESGCM(_key)
        # Генерируем случайный nonce (вектор инициализации) для каждого шифрования
        # Длина nonce для AES-GCM обычно 12 байт
        nonce = os.urandom(12)
        # Шифруем данные (предварительно кодируем строку в байты UTF-8)
        # associated_data можно использовать для доп. аутентификации (например, ID пасты), но пока не будем
        ciphertext = aesgcm.encrypt(nonce, content.encode("utf-8"), None)
        # Возвращаем nonce + зашифрованные данные (nonce нужен для дешифровки)
        # Сохраняем их вместе как одну байтовую строку
        return nonce + ciphertext
    except Exception:
        logger.exception("Ошибка при шифровании контента.")
        return None


def decrypt_content(encrypted_data: bytes) -> str | None:
    """Дешифрует данные, зашифрованные с помощью encrypt_content."""
    if _key is None:
        logger.error("Дешифрование невозможно: ключ не загружен.")
        return None
    if not isinstance(encrypted_data, bytes) or len(encrypted_data) <= 12:
        # Проверяем, что это байты и длина больше длины nonce
        logger.error(
            f"Дешифрование невозможно: неверный формат входных данных (тип: {type(encrypted_data)}, длина: {len(encrypted_data) if encrypted_data else 0})."
        )
        return None

    try:
        aesgcm = AESGCM(_key)
        # Извлекаем nonce (первые 12 байт)
        nonce = encrypted_data[:12]
        # Извлекаем сам шифротекст (все остальное)
        ciphertext = encrypted_data[12:]
        # Дешифруем и декодируем обратно в строку UTF-8
        plaintext_bytes = aesgcm.decrypt(nonce, ciphertext, None)
        return plaintext_bytes.decode("utf-8")
    except (
        Exception
    ) as e:  # Ловим ошибки дешифровки (например, неверный ключ или измененные данные)
        logger.error(f"Ошибка при дешифровании контента: {e}", exc_info=True)
        return None  # В случае ошибки дешифровки возвращаем None
