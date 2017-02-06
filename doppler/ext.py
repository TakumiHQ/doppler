import time
import datetime as dt
import functools

import requests
from flask import Blueprint, json, request, url_for
from werkzeug.contrib.securecookie import SecureCookie


class JSONSecureCookie(SecureCookie):
    serialization_method = json


class Signer(object):

    def __init__(self, secret_key):
        self.secret_key = secret_key

    def sign(self, data):
        return JSONSecureCookie(data, self.secret_key).serialize()

    def unsign(self, data):
        return dict(JSONSecureCookie.unserialize(data, self.secret_key))


def seconds_to_epoch(seconds):
    if isinstance(seconds, dt.datetime):
        seconds = time.mktime(seconds.timetuple())
    return int(time.time() - seconds)


class NoSigner(object):

    def serialize(self, data):
        return data

    def unserialize(self, data):
        return data


class Job(object):

    def __init__(self, doppler, **kwargs):
        self.doppler = doppler
        for key, item in kwargs.iteritems():
            setattr(self, key, item)

    def cancel(self):
        response = requests.delete(self.doppler.url + '/{}'.format(self.request_id))
        response.raise_for_status()
        return response.json()

    def refresh(self):
        response = requests.get(self.doppler.url + '/{}'.format(self.request_id))
        response.raise_for_status()
        for key, item in response.json().iteritems():
            setattr(self, key, item)


class Callback(object):
    def __init__(self, doppler, fn, max_retries, retry_delay):
        self.doppler = doppler
        self.fn = fn
        self.max_retries = max_retries
        self.retry_delay = retry_delay

    def delay(self, seconds, **arguments):
        signed_data = self.doppler.signer.sign(arguments)
        callback_url = url_for('{}.{}'.format(
            self.doppler.blueprint.name,
            self.fn.__name__
        ), _external=True)
        response = requests.post(self.doppler.url, json={
            'message': signed_data,
            'callback_url': callback_url,
            'max_retries': self.max_retries,
            'retry_delay': self.retry_delay,
            'run_at': seconds_to_epoch(seconds),
        })
        response.raise_for_status()
        return Job(self.doppler, **response.json())

    def __call__(self, *args, **kwargs):
        return self.fn(*args, **kwargs)


class Doppler(object):

    def __init__(self, url, app=None):
        self.url = url.rstrip('/')
        self.blueprint = Blueprint('doppler', __name__)
        self._signer = None

    @property
    def signer(self):
        if not hasattr(self, 'app'):
            raise RuntimeError(u'Not registered. Use `register` to connect a '
                               u'Flask app before running')
        if self._signer is None:
            self._signer = self.get_signer()
        return self._signer

    def get_signer(self):
        if not self.app.secret_key:
            return NoSigner()
        else:
            return Signer(self.app.secret_key)

    def unsign_request_data(self, data):
        if not data:
            return u'Not supported', 415
        return self.signer.unsign(data)

    def listen(self, route, max_retries=0, retry_delay=10, **kwargs):
        def decorator(f):
            @functools.wraps(f)
            def inner(*args, **kwargs):
                arguments = self.unsign_request_data(request.data)
                return f(**arguments)
            self.blueprint.add_url_rule(route, inner.__name__, inner, methods=['POST'], **kwargs)
            return Callback(self, inner, max_retries, retry_delay)
        return decorator

    def get_job(self, request_id):
        response = requests.get(self.url + '/{}'.format(request_id))
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return Job(self, **response.json())

    def register(self, app, url_prefix='/_callbacks'):
        self.app = app
        app.register_blueprint(self.blueprint, url_prefix=url_prefix)
