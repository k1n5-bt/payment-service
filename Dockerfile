FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /service

RUN pip install --no-cache-dir poetry

COPY pyproject.toml /service/pyproject.toml
COPY poetry.lock /service/poetry.lock

RUN poetry config virtualenvs.create false \
 && poetry install --only main --no-root --no-interaction --no-ansi

COPY . /service

CMD ["python", "-m", "payment_service.main"]
