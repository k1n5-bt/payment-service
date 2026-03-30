import logging
from contextlib import asynccontextmanager
from pathlib import Path

from alembic import command
from alembic.config import Config as AlembicConfig
from fastapi import FastAPI
from faststream.rabbit import RabbitBroker
from sqlalchemy.ext.asyncio.engine import create_async_engine
from sqlalchemy.ext.asyncio.session import AsyncSession, async_sessionmaker
from uvicorn import Config as UvicornConfig, Server

from payment_service.api.routers.payments import payments_router
from payment_service.outbox_publisher import OutboxPublisher
from payment_service.settings import settings

logger = logging.getLogger(__name__)

broker = RabbitBroker(settings.rabbitmq_url)


def run_migrations() -> None:
    migrations_path = str(Path(__file__).parent / 'db' / 'migrations')
    alembic_cfg = AlembicConfig()
    alembic_cfg.set_main_option('script_location', migrations_path)
    alembic_cfg.set_main_option('sqlalchemy.url', settings.database_url)

    logger.info('Running migrations')
    try:
        command.upgrade(alembic_cfg, 'head')
    except Exception as exc:
        logger.exception('Exception during db migration')
        raise RuntimeError(f'Error while executing migrations: {exc}') from exc
    logger.info('Migrations completed')


@asynccontextmanager
async def lifespan(app: FastAPI):
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    app.state.session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    await broker.connect()

    outbox_publisher = OutboxPublisher(
        session_maker=app.state.session_maker,
        publish_handler=lambda queue_name, payload: broker.publish(payload, queue=queue_name),
    )
    await outbox_publisher.start()

    yield

    await outbox_publisher.stop()
    await broker.close()
    await engine.dispose()


def create_app() -> FastAPI:
    app = FastAPI(title='PaymentService', version='0.1.0', lifespan=lifespan)
    app.include_router(payments_router)
    return app


if __name__ == '__main__':
    run_migrations()

    server = Server(
        UvicornConfig(
            app=create_app(),
            host='0.0.0.0',  # noqa: S104
            port=8080,
            log_level='debug',
            log_config=None,
            limit_concurrency=30,
            backlog=10,
            access_log=True,
        )
    )
    server.run()
