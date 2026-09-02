# NeoMarket B2B Seller Cabinet

Кабинет продавца для маркетплейса NeoMarket.

## Модуль

Управление товарами, SKU, категориями и накладными.

### Эндпоинты

| Метод | Путь | Описание |
|-------|------|----------|
| POST | `/api/v1/products` | Создать товар |
| GET | `/api/v1/products` | Список товаров (с фильтрами и пагинацией) |
| GET | `/api/v1/products/{id}` | Получить товар |
| PUT | `/api/v1/products/{id}` | Обновить товар |
| POST | `/api/v1/products/{id}/submit-moderation` | Отправить на модерацию |
| POST | `/api/v1/products/{id}/delete` | Удалить товар |
| POST | `/api/v1/skus` | Создать SKU |
| PUT | `/api/v1/skus/{id}` | Обновить SKU |
| POST | `/api/v1/skus/{id}/reserve` | Резервировать товар (для B2C) |
| POST | `/api/v1/skus/{id}/release` | Освободить резерв (для B2C) |
| GET | `/api/v1/categories` | Дерево категорий |
| POST | `/api/v1/invoices` | Создать накладную |
| POST | `/api/v1/invoices/{id}/submit` | Отправить накладную на склад |
| POST | `/api/v1/invoices/accept` | Склад принимает накладную |

## Стек

- Python 3.11
- FastAPI
- SQLAlchemy (async)
- PostgreSQL
- Alembic (миграции)
- Docker / Docker Compose

## Запуск

### Локально (без Docker)

```bash
# Установка зависимостей
pip install -e .

# Настройка БД
export DATABASE_URL="postgresql+asyncpg://user:pass@localhost:5432/neomarket_b2b"

# Запуск сервера
uvicorn src.main:app --reload --port 8000
```

### Через Docker Compose

```bash
docker-compose up --build
```

Сервис поднимется на `http://localhost:8000`

## Swagger UI

Откройте `http://localhost:8000/docs` для интерактивной документации.

## Структура

```
neomarket-b2b-service/
├── src/
│   ├── models/         # SQLAlchemy модели
│   ├── routes/         # API роутеры
│   ├── schemas/        # Pydantic схемы
│   ├── main.py         # Точка входа
│   └── settings.py     # Конфигурация
├── migrations/         # Alembic миграции
├── tests/              # Тесты
├── docker-compose.yml
├── Dockerfile
└── pyproject.toml
```

## Команда

**Синдикат:** QA Corps  
**Команда:** Синдикат потерянных
