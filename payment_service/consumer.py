import asyncio
import logging
import random
import uuid
from datetime import datetime, timezone

import httpx
from faststream import FastStream
from faststream.rabbit import RabbitBroker, RabbitQueue
from sqlalchemy.ext.asyncio.engine import create_async_engine
from sqlalchemy.ext.asyncio.session import AsyncSession, async_sessionmaker

from payment_service.db.repository import PaymentRepository
from payment_service.db.schemas import Payment, PaymentStatus
from payment_service.settings import settings

logger = logging.getLogger(__name__)

payments_queue = RabbitQueue(
    'payments.new',
    durable=True,
    arguments={'x-dead-letter-exchange': '', 'x-dead-letter-routing-key': 'payments.dlq'},
)
dead_letter_queue = RabbitQueue('payments.dlq', durable=True)


class PaymentConsumer:
    def __init__(self) -> None:
        self._broker = RabbitBroker(settings.rabbitmq_url)
        self._broker.subscriber(payments_queue)(self.process_payment)
        self._application = FastStream(self._broker)

        engine = create_async_engine(settings.database_url, pool_pre_ping=True)
        self._session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    @staticmethod
    async def _notify_webhook(payment: Payment) -> bool:
        delays = [1, 2, 4]
        async with httpx.AsyncClient(timeout=10.0) as http_client:
            for attempt_index, delay_seconds in enumerate(delays, start=1):
                try:
                    response = await http_client.post(
                        payment.webhook_url,
                        json={
                            'payment_id': str(payment.id),
                            'status': payment.status.value,
                            'processed_at': (payment.processed_at.isoformat() if payment.processed_at else None),
                        },
                    )
                    if response.status_code < 400:
                        logger.info('Webhook delivered for payment %s', payment.id)
                        return True
                    logger.warning(
                        'Webhook attempt %d/%d failed for payment %s: HTTP %d',
                        attempt_index,
                        len(delays),
                        payment.id,
                        response.status_code,
                    )
                except Exception as exc:
                    logger.warning(
                        'Webhook attempt %d/%d error for payment %s: %s',
                        attempt_index,
                        len(delays),
                        payment.id,
                        exc,
                    )
                if attempt_index < len(delays):
                    await asyncio.sleep(delay_seconds)
        return False

    @staticmethod
    async def _emulate_processing(payment: Payment, session: AsyncSession) -> None:
        await asyncio.sleep(random.uniform(2, 5))  # noqa: S311
        payment.status = PaymentStatus.succeeded if random.random() < 0.9 else PaymentStatus.failed  # noqa: S311
        payment.processed_at = datetime.now(timezone.utc)
        await session.commit()
        logger.info('Payment %s processed with status %s', payment.id, payment.status.value)

    async def process_payment(self, message: dict) -> None:
        payment_id = uuid.UUID(message['payment_id'])
        delivery_attempt = int(message.get('delivery_attempt', 1))
        logger.info('Processing payment %s (attempt %d)', payment_id, delivery_attempt)
        try:
            async with self._session_maker() as session:
                repository = PaymentRepository(session)
                payment = await repository.get_by_id(payment_id)
                if not payment:
                    logger.error('Payment %s not found, dropping message', payment_id)
                    return

                if payment.status == PaymentStatus.pending:
                    await self._emulate_processing(payment, session)

                webhook_delivered = await self._notify_webhook(payment)
                if not webhook_delivered:
                    raise RuntimeError('Webhook delivery failed')
        except Exception:
            logger.exception('Error processing payment %s', payment_id)
            if delivery_attempt >= 3:
                logger.warning(
                    'Payment %s moved to DLQ after %d attempts',
                    payment_id,
                    delivery_attempt,
                )
                await self._broker.publish(
                    {'payment_id': str(payment_id), 'delivery_attempt': delivery_attempt},
                    queue=dead_letter_queue.name,
                )
                return
            await self._broker.publish(
                {'payment_id': str(payment_id), 'delivery_attempt': delivery_attempt + 1},
                queue=payments_queue.name,
            )

    def run(self) -> None:
        self._application.run()


if __name__ == '__main__':
    PaymentConsumer().run()
