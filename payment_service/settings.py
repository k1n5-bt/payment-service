from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    api_key: str = 'secret-api-key'

    postgres_user: str = 'payment_user'
    postgres_password: str = 'payment_password'  # noqa: S105
    postgres_db: str = 'payment_db'
    postgres_host: str = 'postgres'
    postgres_port: int = 5432

    rabbitmq_user: str = 'guest'
    rabbitmq_password: str = 'guest'  # noqa: S105
    rabbitmq_host: str = 'rabbitmq'
    rabbitmq_port: int = 5672

    model_config = SettingsConfigDict(env_file='.env', extra='ignore')

    @property
    def database_url(self) -> str:
        return (
            'postgresql+asyncpg://'
            f'{self.postgres_user}:{self.postgres_password}'
            f'@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}'
        )

    @property
    def rabbitmq_url(self) -> str:
        return f'amqp://{self.rabbitmq_user}:{self.rabbitmq_password}@{self.rabbitmq_host}:{self.rabbitmq_port}/'


settings = Settings()
