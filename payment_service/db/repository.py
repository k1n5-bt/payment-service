import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from payment_service.api.models import PaymentCreateRequest
from payment_service.db.schemas import Outbox, Payment, PaymentStatus

PAYMENT_CREATED_EVENT = 'payments.new'


class PaymentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, payment_id: uuid.UUID) -> Payment | None:
        query = select(Payment).where(Payment.id == payment_id)
        result = await self._session.execute(query)
        return result.scalar_one_or_none()

    async def get_by_idempotency_key(self, idempotency_key: str) -> Payment | None:
        query = select(Payment).where(Payment.idempotency_key == idempotency_key)
        result = await self._session.execute(query)
        return result.scalar_one_or_none()

    async def create_payment_with_outbox(
        self,
        request_data: PaymentCreateRequest,
        idempotency_key: str,
    ) -> Payment:
        payment = Payment(
            amount=request_data.amount,
            currency=request_data.currency,
            description=request_data.description,
            metadata_json=request_data.metadata,
            status=PaymentStatus.pending,
            idempotency_key=idempotency_key,
            webhook_url=str(request_data.webhook_url),
        )
        self._session.add(payment)
        await self._session.flush()
        outbox_event = Outbox(
            event_name=PAYMENT_CREATED_EVENT,
            payload={'payment_id': str(payment.id)},
        )
        self._session.add(outbox_event)
        await self._session.commit()
        await self._session.refresh(payment)
        return payment

    async def get_unpublished_outbox(self, limit: int = 100) -> list[Outbox]:
        query = select(Outbox).where(Outbox.published.is_(False)).order_by(Outbox.created_at).limit(limit)
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def mark_outbox_published(self, outbox_event: Outbox) -> None:
        outbox_event.published = True
        outbox_event.published_at = datetime.now(timezone.utc)
        await self._session.commit()
