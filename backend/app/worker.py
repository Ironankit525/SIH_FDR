from celery import Celery
from celery.schedules import crontab
from .config import settings

celery = Celery("depositflow", broker=settings.redis_url)
celery.conf.update(task_acks_late=True, worker_prefetch_multiplier=1,
                   beat_schedule={"recover-queue-and-monitor": {"task": "depositflow.tick", "schedule": crontab(minute="*/5")}})


@celery.task(name="depositflow.extract", autoretry_for=(OSError,), retry_backoff=True, max_retries=3)
def extract_job(document_id):
    from .jobs import process_document
    process_document(document_id)


@celery.task(name="depositflow.tick")
def tick():
    from .jobs import periodic_tick
    periodic_tick()
