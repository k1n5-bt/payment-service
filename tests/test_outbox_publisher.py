import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from payment_service.outbox_publisher import OutboxPublisher


@pytest.fixture
def mock_session_maker():
    session = AsyncMock()
    session_maker = MagicMock()
    session_maker.return_value.__aenter__ = AsyncMock(return_value=session)
    session_maker.return_value.__aexit__ = AsyncMock(return_value=False)
    return session_maker


@pytest.fixture
def mock_publish_handler():
    return AsyncMock()


class TestOutboxPublisher:
    async def test_start_creates_task(self, mock_session_maker, mock_publish_handler):
        publisher = OutboxPublisher(
            session_maker=mock_session_maker,
            publish_handler=mock_publish_handler,
        )

        await publisher.start()

        assert publisher._task is not None
        assert not publisher._task.done()

        await publisher.stop()

    async def test_stop_cancels_task(self, mock_session_maker, mock_publish_handler):
        publisher = OutboxPublisher(
            session_maker=mock_session_maker,
            publish_handler=mock_publish_handler,
        )

        await publisher.start()
        await publisher.stop()

        assert publisher._stopped is True

    async def test_publishes_outbox_items(self, mock_session_maker, mock_publish_handler, sample_outbox):
        with patch('payment_service.outbox_publisher.PaymentRepository') as mock_repo_cls:
            repo_instance = AsyncMock()
            mock_repo_cls.return_value = repo_instance
            repo_instance.get_unpublished_outbox.side_effect = [[sample_outbox], []]

            publisher = OutboxPublisher(
                session_maker=mock_session_maker,
                publish_handler=mock_publish_handler,
                poll_interval_seconds=0.01,
            )
            await publisher.start()
            await asyncio.sleep(0.05)
            await publisher.stop()

        mock_publish_handler.assert_called_once_with(
            sample_outbox.event_name,
            sample_outbox.payload,
        )
        repo_instance.mark_outbox_published.assert_called_once_with(sample_outbox)

    async def test_continues_on_error(self, mock_session_maker, mock_publish_handler):
        with patch('payment_service.outbox_publisher.PaymentRepository') as mock_repo_cls:
            repo_instance = AsyncMock()
            mock_repo_cls.return_value = repo_instance
            repo_instance.get_unpublished_outbox.side_effect = [RuntimeError('db error'), []]

            publisher = OutboxPublisher(
                session_maker=mock_session_maker,
                publish_handler=mock_publish_handler,
                poll_interval_seconds=0.01,
            )
            await publisher.start()
            await asyncio.sleep(0.05)
            await publisher.stop()

        assert repo_instance.get_unpublished_outbox.call_count >= 2
