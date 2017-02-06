# encoding=utf-8

import time
import urlparse
import uuid

from flask import Flask, abort, request, jsonify, json

from doppler.queue import callback, rpqueue


def _get_job(request_id):
    return rpqueue._EnqueuedTask(callback.name, request_id, 'default')


FORM = {
    'callback_url': basestring,
    'run_at': int,
    'max_retries': int,
    'retry_delay': int,
    'message': basestring,
}

REQUIRED_FIELDS = ('callback_url', 'message')


def validate():
    for key, item in request.json.iteritems():
        if key not in FORM:
            continue
        if not isinstance(item, FORM[key]):
            abort(422, u'{} not of type {}'.format(key, FORM[key]))
    for key in FORM:
        if key not in request.json and key in REQUIRED_FIELDS:
            abort(400, u'{} not found'.format(key))


def _get_delay():
    # Convert `run_at` (unix timestamp) to `delay` (seconds)
    run_at = request.json['run_at']
    if run_at is None:
        return None
    seconds = time.time() - run_at
    return max(0, int(seconds))


def post_job():
    if request.json is None:
        abort(415)

    validate()

    request_id = str(uuid.uuid4())
    callback_url = request.json['callback_url']
    message = request.json['message']
    max_retries = request.json.get('max_retries', 0)
    retry_delay = request.json.get('retry_delay')
    scheduled_at = int(time.time())

    url_parts = urlparse.urlparse(callback_url)
    if not (url_parts.scheme and url_parts.netloc):
        abort(422, u'{} is not a valid callback url'.format(callback_url))

    job = callback.execute(
        request_id=request_id,
        message=message,
        callback_url=callback_url,
        scheduled_at=scheduled_at,
        retry_delay=retry_delay,
        last_retry=None,
        taskid=request_id,
        delay=_get_delay(),
        _attempts=max_retries,
    )
    return jsonify({
        'request_id': job.taskid,
        'status': job.status,
        'run_at': request.json['run_at'],
        'scheduled_at': scheduled_at,
        'last_retry': None,
        'retries_left': max_retries,
    })


def get_job(request_id):
    job = _get_job(request_id)
    status = job.status
    scheduled_at = None
    last_retry = None
    retries_left = 0
    delay = 0

    if status != "done":
        args = json.loads(job.args)
        taskid, fname, args, kwargs, delay = args
        scheduled_at = kwargs['scheduled_at']
        last_retry = kwargs.get('last_retry')
        retries_left = kwargs['_attempts']

    return jsonify({
        'request_id': request_id,
        'status': status,
        'run_at': int(delay + time.time()),
        'scheduled_at': scheduled_at,
        'last_retry': last_retry,
        'retries_left': retries_left,
    })


def delete_job(request_id):
    job = _get_job(request_id)
    return jsonify({
        'was_cancelled': bool(job.cancel()),
    })


def get_service_app():
    app = Flask(__name__)
    app.add_url_rule('/', 'post_job', post_job, methods=['POST'])
    app.add_url_rule('/<request_id>', 'get_job', get_job)
    app.add_url_rule('/<request_id>', 'delete_job', delete_job, methods=['DELETE'])
    return app


if __name__ == "__main__":
    get_service_app().run()
