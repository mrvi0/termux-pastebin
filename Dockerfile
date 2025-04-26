# --- Стейдж сборки (Builder) ---
# Используйте соответствующий базовый образ для вашего языка и версии
# Python:
# FROM python:3.11-slim as builder
# Node.js:
# FROM node:18-alpine as builder
FROM python:3.11-slim as builder

# Установка системных зависимостей, если нужно (например, для сборки Python-пакетов или Node-gyp)
# RUN apt-get update && apt-get install -y --no-install-recommends build-essential libpq-dev && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# --- Python ---
# Копируем файлы зависимостей
COPY pyproject.toml poetry.lock* ./
# Или для requirements.txt:
# COPY requirements.txt ./

# Устанавливаем зависимости (используя Poetry)
# RUN pip install poetry && poetry config virtualenvs.create false && poetry install --no-dev --no-interaction --no-ansi
# Или для requirements.txt:
# RUN pip wheel --no-cache-dir --no-deps --wheel-dir /wheels -r requirements.txt
# RUN pip install --no-cache-dir -r requirements.txt

# --- Node.js (Раскомментируйте и адаптируйте, если используете Node.js) ---
# COPY package.json package-lock.json* ./
# Установка только production зависимостей
# RUN npm ci --only=production

# Копируем исходный код
COPY src/ ./src/
# Копируем другие нужные директории (например, config)
# COPY config/ ./config/

# --- Финальный стейдж (Runtime) ---
# Используйте соответствующий легковесный образ
# Python:
# FROM python:3.11-slim as final
# Node.js:
# FROM node:18-alpine as final
FROM python:3.11-slim as final

# Установка системных зависимостей, необходимых только для рантайма (если отличаются от сборки)
# RUN apt-get update && apt-get install -y --no-install-recommends libpq5 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Создаем непривилегированного пользователя
ARG APP_USER=appuser
ARG APP_GROUP=appgroup
RUN groupadd -r ${APP_GROUP} && useradd -r -g ${APP_GROUP} ${APP_USER}

# Копируем собранные зависимости со стейджа builder
# Python (Poetry):
# COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
# COPY --from=builder /app /app # Копируем все приложение, если Poetry установил в /app
# Python (requirements.txt):
# COPY --from=builder /wheels /wheels
# COPY --from=builder /app/requirements.txt .
# RUN pip install --no-cache /wheels/*
# RUN pip install --no-cache-dir -r requirements.txt
# Node.js:
# COPY --from=builder /app/node_modules ./node_modules
# COPY --from=builder /app/package.json ./package.json

# Копируем исходный код со стейджа builder
COPY --from=builder /app/src ./src
# COPY --from=builder /app/config ./config # Если нужно

# Устанавливаем владельца файлов приложения
RUN chown -R ${APP_USER}:${APP_GROUP} /app

# Переключаемся на непривилегированного пользователя
USER ${APP_USER}

# Открываем порт, если это веб-сервис (замените на ваш порт)
# EXPOSE 8000

# Команда для запуска приложения
# Python:
CMD ["python", "src/main.py"]
# Node.js:
# CMD ["node", "src/index.js"]