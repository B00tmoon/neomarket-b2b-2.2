# NeoMarket B2B - Сессия 2026-05-22

## Что сделано
- Создан проект neomarket-b2b-service (FastAPI + PostgreSQL)
- Структура: models, routes, schemas, main.py
- Эндпоинты: products, skus, categories, invoices
- Зависимости установлены в venv

## Статус
- Docker не установлен (Arch Linux)
- Нужен запуск PostgreSQL без Docker

## Следующие шаги
1. Установить Docker ИЛИ запустить PostgreSQL вручную
2. Создать БД neomarket_b2b
3. Запустить uvicorn src.main:app
4. Проверить Swagger UI на /docs

## Команда
- Синдикат: QA Corps
- Команда: Синдикат потерянных
- Модуль: B2B Seller Cabinet
