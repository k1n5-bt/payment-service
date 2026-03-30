import asyncio
import logging
from collections.abc import Awaitable, Callable
from contextlib import suppress

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from payment_service.db.repository import PaymentRepository

logger = logging.getLogger(__name__)


class OutboxPublisher:
    def __init__(
        self,
        session_maker: async_sessionmaker[AsyncSession],
        publish_handler: Callable[[str, dict], Awaitable[None]],
        poll_interval_seconds: float = 1.0,
    ) -> None:
        self._session_maker = session_maker
        self._publish_handler = publish_handler
        self._poll_interval_seconds = poll_interval_seconds
        self._task: asyncio.Task | None = None
        self._stopped = False

    async def start(self) -> None:
        self._stopped = False
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._stopped = True
        if self._task:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task

    async def _run(self) -> None:
        while not self._stopped:
            try:
                async with self._session_maker() as session:
                    repository = PaymentRepository(session)
                    outbox_items = await repository.get_unpublished_outbox()
                    for outbox_item in outbox_items:
                        await self._publish_handler(outbox_item.event_name, outbox_item.payload)
                        await repository.mark_outbox_published(outbox_item)
                    if outbox_items:
                        logger.info('Published %d outbox events', len(outbox_items))
            except Exception:
                logger.exception('Outbox publisher error')
            await asyncio.sleep(self._poll_interval_seconds)
