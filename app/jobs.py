from redis import Redis
from rq import Queue

from app.settings import settings


QUEUE_NAME = "csv-imports"


def get_redis_connection():
    return Redis.from_url(settings.redis_url)


def get_queue():
    return Queue(QUEUE_NAME, connection=get_redis_connection())


def enqueue_import(job_id):
    queue = get_queue()
    queue.enqueue("app.services.importer.process_import_job", job_id, job_timeout="24h")


def enqueue_import_chunk(chunk_id):
    queue = get_queue()
    queue.enqueue("app.services.importer.process_import_job_chunk", chunk_id, job_timeout="24h")
