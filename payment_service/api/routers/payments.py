import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from payment_service.api.models import PaymentCreateRequest, PaymentCreateResponse, PaymentDetailsResponse
from payment_service.api.routers.dependencies import get_db_session, verify_api_key
from payment_service.db.repository import PaymentRepository

payments_router = APIRouter(tags=['payments'])


@payments_router.post(
    '/api/v1/payments',
    status_code=status.HTTP_202_ACCEPTED,
    response_model=PaymentCreateResponse,
    dependencies=[Depends(verify_api_key)],
)
async def create_payment(
    payment_request: PaymentCreateRequest,
    idempotency_key: str = Header(..., alias='Idempotency-Key'),
    db_session: AsyncSession = Depends(get_db_session),
) -> PaymentCreateResponse:
    repository = PaymentRepository(db_session)
    existing_payment = await repository.get_by_idempotency_key(idempotency_key)
    if existing_payment:
        return PaymentCreateResponse.model_validate(existing_payment)

    payment = await repository.create_payment_with_outbox(payment_request, idempotency_key)
    return PaymentCreateResponse.model_validate(payment)


@payments_router.get(
    '/api/v1/payments/{payment_id}',
    response_model=PaymentDetailsResponse,
    dependencies=[Depends(verify_api_key)],
)
async def get_payment(
    payment_id: uuid.UUID,
    db_session: AsyncSession = Depends(get_db_session),
) -> PaymentDetailsResponse:
    repository = PaymentRepository(db_session)
    payment = await repository.get_by_id(payment_id)
    if not payment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Payment not found')
    return PaymentDetailsResponse.model_validate(payment)
