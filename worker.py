from rq import Worker

from app.database import init_db
from app.jobs import QUEUE_NAME, get_redis_connection


def main():
    init_db()
    worker = Worker([QUEUE_NAME], connection=get_redis_connection())
    worker.work()


if __name__ == "__main__":
    main()
