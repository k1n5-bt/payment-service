import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from payment_service.db.repository import PAYMENT_CREATED_EVENT, PaymentRepository
from payment_service.db.schemas import Outbox, Payment, PaymentStatus


@pytest.fixture
def repository(mock_session):
    return PaymentRepository(mock_session)


class TestGetById:
    async def test_returns_payment(self, repository, mock_session, sample_payment):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_payment
        mock_session.execute.return_value = mock_result

        result = await repository.get_by_id(sample_payment.id)

        assert result == sample_payment
        mock_session.execute.assert_called_once()

    async def test_returns_none_when_not_found(self, repository, mock_session):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await repository.get_by_id(uuid.uuid4())

        assert result is None


class TestGetByIdempotencyKey:
    async def test_returns_payment(self, repository, mock_session, sample_payment):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_payment
        mock_session.execute.return_value = mock_result

        result = await repository.get_by_idempotency_key('order-10001')

        assert result == sample_payment

    async def test_returns_none_when_not_found(self, repository, mock_session):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await repository.get_by_idempotency_key('nonexistent')

        assert result is None


class TestCreatePaymentWithOutbox:
    async def test_creates_payment_and_outbox(self, repository, mock_session, sample_payment_request):
        mock_session.refresh = AsyncMock()

        await repository.create_payment_with_outbox(sample_payment_request, 'key-001')

        assert mock_session.add.call_count == 2
        mock_session.flush.assert_called_once()
        mock_session.commit.assert_called_once()
        mock_session.refresh.assert_called_once()

        payment_arg = mock_session.add.call_args_list[0][0][0]
        assert isinstance(payment_arg, Payment)
        assert payment_arg.amount == sample_payment_request.amount
        assert payment_arg.currency == sample_payment_request.currency
        assert payment_arg.status == PaymentStatus.pending
        assert payment_arg.idempotency_key == 'key-001'

        outbox_arg = mock_session.add.call_args_list[1][0][0]
        assert isinstance(outbox_arg, Outbox)
        assert outbox_arg.event_name == PAYMENT_CREATED_EVENT


class TestGetUnpublishedOutbox:
    async def test_returns_unpublished_items(self, repository, mock_session, sample_outbox):
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_outbox]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.get_unpublished_outbox()

        assert len(result) == 1
        assert result[0] == sample_outbox

    async def test_returns_empty_list(self, repository, mock_session):
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.get_unpublished_outbox()

        assert result == []


class TestMarkOutboxPublished:
    async def test_marks_as_published(self, repository, mock_session, sample_outbox):
        await repository.mark_outbox_published(sample_outbox)

        assert sample_outbox.published is True
        assert sample_outbox.published_at is not None
        mock_session.commit.assert_called_once()
