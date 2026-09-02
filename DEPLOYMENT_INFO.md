# NeoMarket — Информация о развёртывании

## Доступ к сервисам

### B2B-сервис (продавцы)
- API: `http://localhost:8001`
- Swagger UI: `http://localhost:8001/docs`

### B2C-сервис (покупатели)
- API: `http://localhost:8000`
- Swagger UI: `http://localhost:8000/docs`

## PostgreSQL базы данных

| Сервис | Порт | База |
|--------|------|------|
| B2B | `localhost:5432` | `neomarket_b2b` |
| B2C | `localhost:5433` | `neomarket_b2c` |

| Параметр | Значение |
|----------|----------|
| Пользователь | `neomarket` |
| Пароль | `neomarket_pass` |

## Проверка работоспособности

```bash
# Проверка B2B
curl http://localhost:8001/docs -I

# Проверка B2C
curl http://localhost:8000/docs -I
```

## Управление контейнерами

```bash
# B2B
cd /home/marceline/neomarket-b2b-service
docker-compose up -d          # Запуск
docker-compose down           # Остановка
docker-compose logs -f        # Логи

# B2C
cd /home/marceline/neomarket-b2c-service
docker-compose up -d          # Запуск
docker-compose down           # Остановка
docker-compose logs -f        # Логи
```

---

**Примечание:** Храните секреты (токены, пароли) в переменной окружения или `.env` файле, не коммитьте их в репозиторий.
