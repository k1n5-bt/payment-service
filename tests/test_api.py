from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from payment_service.api.routers.dependencies import get_db_session
from payment_service.api.routers.payments import payments_router
from payment_service.db.schemas import PaymentStatus


class TestCreatePayment:
    def test_create_payment_returns_202(self, client, mock_session, sample_payment, auth_headers):
        with patch('payment_service.api.routers.payments.PaymentRepository') as mock_repo_cls:
            repo_instance = AsyncMock()
            mock_repo_cls.return_value = repo_instance
            repo_instance.get_by_idempotency_key.return_value = None
            repo_instance.create_payment_with_outbox.return_value = sample_payment

            response = client.post(
                '/api/v1/payments',
                json={
                    'amount': '1500.50',
                    'currency': 'RUB',
                    'description': 'Оплата заказа',
                    'metadata': {'order_id': '10001'},
                    'webhook_url': 'https://example.com/webhook',
                },
                headers=auth_headers,
            )

        assert response.status_code == 202
        body = response.json()
        assert body['payment_id'] == str(sample_payment.id)
        assert body['status'] == PaymentStatus.pending.value

    def test_create_payment_idempotency(self, client, mock_session, sample_payment, auth_headers):
        with patch('payment_service.api.routers.payments.PaymentRepository') as mock_repo_cls:
            repo_instance = AsyncMock()
            mock_repo_cls.return_value = repo_instance
            repo_instance.get_by_idempotency_key.return_value = sample_payment

            response = client.post(
                '/api/v1/payments',
                json={
                    'amount': '1500.50',
                    'currency': 'RUB',
                    'description': 'Оплата заказа',
                    'webhook_url': 'https://example.com/webhook',
                },
                headers=auth_headers,
            )

        assert response.status_code == 202
        body = response.json()
        assert body['payment_id'] == str(sample_payment.id)
        repo_instance.create_payment_with_outbox.assert_not_called()

    def test_create_payment_missing_idempotency_key(self, client):
        response = client.post(
            '/api/v1/payments',
            json={
                'amount': '100',
                'currency': 'RUB',
                'description': 'Тест',
                'webhook_url': 'https://example.com/webhook',
            },
        )
        assert response.status_code == 422

    def test_create_payment_invalid_body(self, client, auth_headers):
        response = client.post(
            '/api/v1/payments',
            json={'amount': '-1', 'currency': 'RUB', 'description': 'Тест', 'webhook_url': 'https://example.com'},
            headers=auth_headers,
        )
        assert response.status_code == 422


class TestGetPayment:
    def test_get_payment_returns_200(self, client, mock_session, sample_payment):
        with patch('payment_service.api.routers.payments.PaymentRepository') as mock_repo_cls:
            repo_instance = AsyncMock()
            mock_repo_cls.return_value = repo_instance
            repo_instance.get_by_id.return_value = sample_payment

            response = client.get(
                f'/api/v1/payments/{sample_payment.id}',
                headers={'X-API-Key': 'secret-api-key'},
            )

        assert response.status_code == 200
        body = response.json()
        assert body['id'] == str(sample_payment.id)
        assert body['amount'] == '1500.50'
        assert body['currency'] == 'RUB'

    def test_get_payment_not_found(self, client, mock_session):
        with patch('payment_service.api.routers.payments.PaymentRepository') as mock_repo_cls:
            repo_instance = AsyncMock()
            mock_repo_cls.return_value = repo_instance
            repo_instance.get_by_id.return_value = None

            response = client.get(
                '/api/v1/payments/00000000-0000-0000-0000-000000000001',
                headers={'X-API-Key': 'secret-api-key'},
            )

        assert response.status_code == 404
        assert response.json()['detail'] == 'Payment not found'


class TestAuth:
    def _make_no_auth_client(self) -> TestClient:
        app = FastAPI()
        app.include_router(payments_router)

        async def override_db():
            yield AsyncMock()

        app.dependency_overrides[get_db_session] = override_db
        return TestClient(app)

    def test_missing_api_key_returns_error(self):
        no_auth_client = self._make_no_auth_client()
        response = no_auth_client.get('/api/v1/payments/00000000-0000-0000-0000-000000000001')
        assert response.status_code == 422

    def test_wrong_api_key_returns_401(self):
        no_auth_client = self._make_no_auth_client()
        response = no_auth_client.get(
            '/api/v1/payments/00000000-0000-0000-0000-000000000001',
            headers={'X-API-Key': 'wrong-key'},
        )
        assert response.status_code == 401
