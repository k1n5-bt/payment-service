from datetime import datetime, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from payment_service.api.models import PaymentCreateRequest, PaymentCreateResponse, PaymentDetailsResponse
from payment_service.db.schemas import Currency, PaymentStatus


class TestPaymentCreateRequest:
    def test_valid_request(self):
        request = PaymentCreateRequest(
            amount=Decimal('100.00'),
            currency=Currency.RUB,
            description='Тест',
            webhook_url='https://example.com/hook',
        )
        assert request.amount == Decimal('100.00')
        assert request.currency == Currency.RUB
        assert request.metadata == {}

    def test_zero_amount_rejected(self):
        with pytest.raises(ValidationError):
            PaymentCreateRequest(
                amount=Decimal('0'),
                currency=Currency.RUB,
                description='Тест',
                webhook_url='https://example.com/hook',
            )

    def test_negative_amount_rejected(self):
        with pytest.raises(ValidationError):
            PaymentCreateRequest(
                amount=Decimal('-10'),
                currency=Currency.RUB,
                description='Тест',
                webhook_url='https://example.com/hook',
            )

    def test_empty_description_rejected(self):
        with pytest.raises(ValidationError):
            PaymentCreateRequest(
                amount=Decimal('100'),
                currency=Currency.RUB,
                description='',
                webhook_url='https://example.com/hook',
            )

    def test_description_too_long_rejected(self):
        with pytest.raises(ValidationError):
            PaymentCreateRequest(
                amount=Decimal('100'),
                currency=Currency.RUB,
                description='x' * 256,
                webhook_url='https://example.com/hook',
            )

    def test_invalid_currency_rejected(self):
        with pytest.raises(ValidationError):
            PaymentCreateRequest(
                amount=Decimal('100'),
                currency='BTC',
                description='Тест',
                webhook_url='https://example.com/hook',
            )

    def test_invalid_webhook_url_rejected(self):
        with pytest.raises(ValidationError):
            PaymentCreateRequest(
                amount=Decimal('100'),
                currency=Currency.RUB,
                description='Тест',
                webhook_url='not-a-url',
            )

    def test_metadata_defaults_to_empty_dict(self):
        request = PaymentCreateRequest(
            amount=Decimal('50'),
            currency=Currency.USD,
            description='Тест',
            webhook_url='https://example.com/hook',
        )
        assert request.metadata == {}

    def test_metadata_preserves_values(self):
        request = PaymentCreateRequest(
            amount=Decimal('50'),
            currency=Currency.EUR,
            description='Тест',
            metadata={'order_id': '123'},
            webhook_url='https://example.com/hook',
        )
        assert request.metadata == {'order_id': '123'}


class TestPaymentCreateResponse:
    def test_from_orm_payment(self, sample_payment):
        response = PaymentCreateResponse.model_validate(sample_payment)
        assert response.payment_id == sample_payment.id
        assert response.status == sample_payment.status
        assert response.created_at == sample_payment.created_at


class TestPaymentDetailsResponse:
    def test_from_orm_payment(self, sample_payment):
        response = PaymentDetailsResponse.model_validate(sample_payment)
        assert response.id == sample_payment.id
        assert response.amount == sample_payment.amount
        assert response.currency == sample_payment.currency
        assert response.description == sample_payment.description
        assert response.metadata == sample_payment.metadata_json
        assert response.status == sample_payment.status
        assert response.webhook_url == sample_payment.webhook_url
        assert response.processed_at is None

    def test_from_orm_processed_payment(self, sample_payment):
        sample_payment.status = PaymentStatus.succeeded
        sample_payment.processed_at = datetime.now(timezone.utc)
        response = PaymentDetailsResponse.model_validate(sample_payment)
        assert response.status == PaymentStatus.succeeded
        assert response.processed_at is not None
