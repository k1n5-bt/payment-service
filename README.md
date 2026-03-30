# Payment Service

Сервис асинхронной обработки платежей на FastAPI, PostgreSQL и RabbitMQ.

## Возможности

- Создание платежа `POST /api/v1/payments`
- Получение платежа `GET /api/v1/payments/{payment_id}`
- Защита API через `X-API-Key`
- Идемпотентность через заголовок `Idempotency-Key`
- Outbox pattern для гарантированной публикации событий
- Consumer для обработки платежей и отправки webhook
- Retry webhook с экспоненциальной задержкой
- Dead Letter Queue `payments.dlq` для сообщений после 3 неудачных попыток

## Запуск

```bash
docker compose up --build
```

API поднимается на `http://localhost:8000`.

## Пример создания платежа

```bash
curl -X POST "http://localhost:8000/api/v1/payments" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: secret-api-key" \
  -H "Idempotency-Key: order-10001" \
  -d '{
    "amount": 1500.50,
    "currency": "RUB",
    "description": "Оплата заказа",
    "metadata": {"order_id": "10001"},
    "webhook_url": "https://webhook.site/your-id"
  }'
```

## Пример получения платежа

```bash
curl "http://localhost:8000/api/v1/payments/<payment_id>" \
  -H "X-API-Key: secret-api-key"
```

## Очереди

- `payments.new` — очередь новых платежей
- `payments.dlq` — dead letter очередь

