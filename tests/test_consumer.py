import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from payment_service.consumer import PaymentConsumer
from payment_service.db.schemas import PaymentStatus


@pytest.fixture
def consumer():
    with (
        patch('payment_service.consumer.create_async_engine'),
        patch('payment_service.consumer.async_sessionmaker') as mock_sm,
        patch('payment_service.consumer.RabbitBroker'),
        patch('payment_service.consumer.FastStream'),
    ):
        consumer = PaymentConsumer()
        session = AsyncMock()
        mock_sm.return_value.__aenter__ = AsyncMock(return_value=session)
        mock_sm.return_value.__aexit__ = AsyncMock(return_value=False)
        consumer._session_maker = mock_sm.return_value  # noqa: SLF001
        consumer._broker.publish = AsyncMock()  # noqa: SLF001
        yield consumer


class TestProcessPayment:
    async def test_processes_pending_payment(self, consumer, sample_payment):
        sample_payment.status = PaymentStatus.pending

        with (
            patch.object(PaymentConsumer, '_notify_webhook', return_value=True) as mock_webhook,
            patch.object(PaymentConsumer, '_emulate_processing') as mock_emulate,
            patch('payment_service.consumer.PaymentRepository') as mock_repo_cls,
        ):
            repo_instance = AsyncMock()
            mock_repo_cls.return_value = repo_instance
            repo_instance.get_by_id.return_value = sample_payment

            await consumer.process_payment({'payment_id': str(sample_payment.id)})

            mock_emulate.assert_called_once()
            mock_webhook.assert_called_once_with(sample_payment)

    async def test_skips_emulation_for_processed_payment(self, consumer, sample_payment):
        sample_payment.status = PaymentStatus.succeeded

        with (
            patch.object(PaymentConsumer, '_notify_webhook', return_value=True) as mock_webhook,
            patch.object(PaymentConsumer, '_emulate_processing') as mock_emulate,
            patch('payment_service.consumer.PaymentRepository') as mock_repo_cls,
        ):
            repo_instance = AsyncMock()
            mock_repo_cls.return_value = repo_instance
            repo_instance.get_by_id.return_value = sample_payment

            await consumer.process_payment({'payment_id': str(sample_payment.id)})

            mock_emulate.assert_not_called()
            mock_webhook.assert_called_once()

    async def test_drops_message_for_missing_payment(self, consumer):
        with patch('payment_service.consumer.PaymentRepository') as mock_repo_cls:
            repo_instance = AsyncMock()
            mock_repo_cls.return_value = repo_instance
            repo_instance.get_by_id.return_value = None

            await consumer.process_payment({'payment_id': str(uuid.uuid4())})

            consumer._broker.publish.assert_not_called()

    async def test_retries_on_webhook_failure(self, consumer, sample_payment):
        sample_payment.status = PaymentStatus.succeeded

        with (
            patch.object(PaymentConsumer, '_notify_webhook', side_effect=RuntimeError('fail')),
            patch('payment_service.consumer.PaymentRepository') as mock_repo_cls,
        ):
            repo_instance = AsyncMock()
            mock_repo_cls.return_value = repo_instance
            repo_instance.get_by_id.return_value = sample_payment

            await consumer.process_payment(
                {
                    'payment_id': str(sample_payment.id),
                    'delivery_attempt': 1,
                }
            )

            consumer._broker.publish.assert_called_once()
            call_args = consumer._broker.publish.call_args
            assert call_args[0][0]['delivery_attempt'] == 2
            assert call_args[1]['queue'] == 'payments.new'

    async def test_sends_to_dlq_after_max_retries(self, consumer, sample_payment):
        sample_payment.status = PaymentStatus.succeeded

        with (
            patch.object(PaymentConsumer, '_notify_webhook', side_effect=RuntimeError('fail')),
            patch('payment_service.consumer.PaymentRepository') as mock_repo_cls,
        ):
            repo_instance = AsyncMock()
            mock_repo_cls.return_value = repo_instance
            repo_instance.get_by_id.return_value = sample_payment

            await consumer.process_payment(
                {
                    'payment_id': str(sample_payment.id),
                    'delivery_attempt': 3,
                }
            )

            consumer._broker.publish.assert_called_once()
            call_args = consumer._broker.publish.call_args
            assert call_args[1]['queue'] == 'payments.dlq'


class TestNotifyWebhook:
    async def test_successful_webhook(self, sample_payment):
        sample_payment.status = PaymentStatus.succeeded

        with patch('payment_service.consumer.httpx.AsyncClient') as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_response = MagicMock(status_code=200)
            mock_client.post.return_value = mock_response

            result = await PaymentConsumer._notify_webhook(sample_payment)

        assert result is True
        mock_client.post.assert_called_once()

    async def test_failed_webhook_retries(self, sample_payment):
        sample_payment.status = PaymentStatus.succeeded

        with (
            patch('payment_service.consumer.httpx.AsyncClient') as mock_client_cls,
            patch('payment_service.consumer.asyncio.sleep', new_callable=AsyncMock),
        ):
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.post.side_effect = [
                MagicMock(status_code=500),
                MagicMock(status_code=500),
                MagicMock(status_code=200),
            ]

            result = await PaymentConsumer._notify_webhook(sample_payment)

        assert result is True
        assert mock_client.post.call_count == 3

    async def test_all_attempts_fail(self, sample_payment):
        sample_payment.status = PaymentStatus.succeeded

        with (
            patch('payment_service.consumer.httpx.AsyncClient') as mock_client_cls,
            patch('payment_service.consumer.asyncio.sleep', new_callable=AsyncMock),
        ):
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.post.return_value = MagicMock(status_code=500)

            result = await PaymentConsumer._notify_webhook(sample_payment)

        assert result is False
        assert mock_client.post.call_count == 3
