"""
RACEJUDGE Celery application.

Three queues:
  high    — PDF parsing, individual decision ingest (latency-sensitive)
  default — text extraction, structured parsing, annotation updates
  bulk    — batch enrichment, season back-fills, R2 uploads

Start workers:
  # All queues on one worker (dev)
  celery -A packages.pipeline.workers.celery_app worker --loglevel=info -Q high,default,bulk

  # Separate workers per queue (prod)
  celery -A packages.pipeline.workers.celery_app worker -Q high     --concurrency=4 -n high@%h
  celery -A packages.pipeline.workers.celery_app worker -Q default  --concurrency=2 -n default@%h
  celery -A packages.pipeline.workers.celery_app worker -Q bulk     --concurrency=1 -n bulk@%h

Monitor (Flower):
  celery -A packages.pipeline.workers.celery_app flower --port=5555

Requires:
  REDIS_URL env var (e.g. redis://localhost:6379/0 or Upstash rediss:// URL)
"""

from __future__ import annotations

import os

from celery import Celery

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

app = Celery(
    "racejudge",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=[
        "packages.pipeline.workers.tasks.parse_pdf",
        "packages.pipeline.workers.tasks.extract_text",
        "packages.pipeline.workers.tasks.ocr_fallback",
    ],
)

app.conf.update(
    # Serialisation
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],

    # Routing — three named queues
    task_routes={
        "packages.pipeline.workers.tasks.parse_pdf.*":     {"queue": "high"},
        "packages.pipeline.workers.tasks.extract_text.*":  {"queue": "default"},
        "packages.pipeline.workers.tasks.ocr_fallback.*":  {"queue": "bulk"},
    },
    task_default_queue="default",

    # Reliability
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,

    # Result expiry (24 hours)
    result_expires=86400,

    # Retry policy defaults (tasks can override)
    task_max_retries=3,
    task_default_retry_delay=30,

    # Dead-letter: route failed tasks to a dedicated queue for inspection
    task_queues_from_memory=False,
)
