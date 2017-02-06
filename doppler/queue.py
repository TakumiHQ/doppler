import os
import time

import requests
import rpqueue
from redis import from_url as redis_from_url

redis = redis_from_url(os.environ.get("REDIS_URL", "redis://localhost:6379"))

rpqueue.set_redis_connection(redis)


DEFAULT_RETRY_DELAY = 10


@rpqueue.task()
def callback(request_id, message, callback_url, scheduled_at, last_retry=None, retry_delay=None, _attempts=None):
    if retry_delay is None:
        retry_delay = DEFAULT_RETRY_DELAY
    try:
        response = requests.post(callback_url, data=message)
        response.raise_for_status()
    except requests.RequestException:
        callback.retry(
            request_id=request_id,
            message=message,
            callback_url=callback_url,
            scheduled_at=scheduled_at,
            last_retry=int(time.time()),
            retry_delay=retry_delay,
            delay=retry_delay,
            taskid=request_id,
            _attempts=_attempts
        )
