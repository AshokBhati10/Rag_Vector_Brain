"""Celery application for VectorBrain background ingestion.

RabbitMQ is the broker. No result backend is configured on purpose: task
progress is tracked in PostgreSQL on the ``documents`` row (status column),
which the frontend polls. This keeps the stack to broker + DB only.
"""
import os

from celery import Celery

BROKER_URL = os.getenv("CELERY_BROKER_URL", "amqp://guest:guest@rabbitmq:5672//")

celery_app = Celery(
    "vectorbrain",
    broker=BROKER_URL,
    include=[
        "app.tasks.document_tasks",
        "app.tasks.embedding_tasks",
    ],
)

celery_app.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_default_queue="parse",
    task_routes={
        "app.tasks.document_tasks.*": {"queue": "parse"},
        "app.tasks.embedding_tasks.*": {"queue": "embed"},
    },
    timezone="UTC",
)
