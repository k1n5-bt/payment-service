import uuid
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from payment_service.api.models import PaymentCreateRequest
from payment_service.api.routers.dependencies import get_db_session, verify_api_key
from payment_service.api.routers.payments import payments_router
from payment_service.db.schemas import Currency, Outbox, Payment, PaymentStatus


@pytest.fixture
def sample_payment() -> Payment:
    return Payment(
        id=uuid.uuid4(),
        amount=Decimal('1500.50'),
        currency=Currency.RUB,
        description='Оплата заказа',
        metadata_json={'order_id': '10001'},
        status=PaymentStatus.pending,
        idempotency_key='order-10001',
        webhook_url='https://example.com/webhook',
        created_at=datetime.now(timezone.utc),
        processed_at=None,
    )


@pytest.fixture
def sample_payment_request() -> PaymentCreateRequest:
    return PaymentCreateRequest(
        amount=Decimal('1500.50'),
        currency=Currency.RUB,
        description='Оплата заказа',
        metadata={'order_id': '10001'},
        webhook_url='https://example.com/webhook',
    )


@pytest.fixture
def sample_outbox() -> Outbox:
    return Outbox(
        id=uuid.uuid4(),
        event_name='payments.new',
        payload={'payment_id': str(uuid.uuid4())},
        published=False,
        created_at=datetime.now(timezone.utc),
        published_at=None,
    )


@pytest.fixture
def mock_session() -> AsyncMock:
    return AsyncMock(spec=AsyncSession)


@pytest.fixture
def test_app(mock_session: AsyncMock) -> FastAPI:
    app = FastAPI()
    app.include_router(payments_router)

    async def override_db_session():
        yield mock_session

    app.dependency_overrides[get_db_session] = override_db_session
    app.dependency_overrides[verify_api_key] = lambda: None

    return app


@pytest.fixture
def client(test_app: FastAPI) -> TestClient:
    return TestClient(test_app)


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {'X-API-Key': 'secret-api-key', 'Idempotency-Key': 'test-key-001'}
