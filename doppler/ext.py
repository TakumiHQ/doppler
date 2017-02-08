import time
import inspect
import datetime as dt
import functools

from simplejson import JSONDecodeError

import requests
from flask import Blueprint, json, request, url_for, abort
from werkzeug.contrib.securecookie import SecureCookie


class UnsignError(Exception):
    pass


class ArgumentMismatchError(Exception):
    pass


class JSONSecureCookie(SecureCookie):
    serialization_method = json


class Signer(object):

    def __init__(self, secret_key):
        self.secret_key = secret_key

    def sign(self, data):
        return JSONSecureCookie(data, self.secret_key).serialize()

    def unsign(self, data):
        try:
            return dict(JSONSecureCookie.unserialize(data, self.secret_key))
        except JSONDecodeError:
            raise UnsignError


def seconds_to_epoch(subject):
    if isinstance(subject, dt.datetime):
        subject = subject - dt.datetime.now(subject.tzinfo)
    if isinstance(subject, dt.timedelta):
        subject = int(round(subject.total_seconds()))
    return int(time.time() + subject)


class NoSigner(object):

    def sign(self, data):
        return json.dumps(data)

    def unsign(self, data):
        try:
            return json.loads(data)
        except JSONDecodeError:
            raise UnsignError


class Job(object):

    def __init__(self, doppler, **kwargs):
        self.doppler = doppler
        for key, item in kwargs.iteritems():
            setattr(self, key, item)

    def cancel(self):
        """ Returns boolean to indicate if job was found and deleted (`True`) or
        not found and will not run (`False`). """
        response = requests.delete(self.doppler.url + '/{}'.format(self.request_id))
        response.raise_for_status()
        return response.json()['was_cancelled']

    def refresh(self):
        response = requests.get(self.doppler.url + '/{}'.format(self.request_id))
        response.raise_for_status()
        for key, item in response.json().iteritems():
            setattr(self, key, item)


class Callback(object):
    def __init__(self, doppler, fn, max_retries, retry_delay, _inner):
        self.doppler = doppler
        self.fn = fn
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self._inner = _inner

    @property
    def url(self):
        return url_for('{}.{}'.format(
            self.doppler.blueprint.name,
            self.fn.__name__,
        ), _external=True)

    def _validate_callback_argument_list(self, arguments):
        function_args = set(inspect.getargspec(self._inner).args)
        delay_args = set(arguments.keys())
        if function_args != delay_args:
            raise ArgumentMismatchError()

    def delay(self, seconds, **arguments):
        self._validate_callback_argument_list(arguments)

        signed_data = self.doppler.signer.sign(arguments)
        response = requests.post(self.doppler.url, json={
            'message': signed_data,
            'callback_url': self.url,
            'max_retries': self.max_retries,
            'retry_delay': self.retry_delay,
            'run_at': seconds_to_epoch(seconds),
        })
        response.raise_for_status()
        return Job(self.doppler, **response.json())

    def __call__(self, *args, **kwargs):
        return self.fn(*args, **kwargs)


class Doppler(object):

    def __init__(self, url=None, app=None):
        self.blueprint = Blueprint('doppler', __name__)
        self.set_url(url)
        self._signer = None

    def set_url(self, url):
        if url is not None:
            self._url = url.rstrip('/')
        else:
            self._url = None

    @property
    def url(self):
        if self._url is None:
            raise RuntimeError(u'No Doppler service URL set. Set at Doppler '
                               u'init or via `register`')
        return self._url

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

    def get_arguments(self, data):
        try:
            return self.signer.unsign(data)
        except UnsignError:
            abort(400, u'Unsign error')

    def listen(self, route, max_retries=0, retry_delay=10, **kwargs):
        def decorator(f):
            @functools.wraps(f)
            def inner(*args, **kwargs):
                arguments = self.get_arguments(request.data)
                # Do not accept webhooks without required arguments
                for f_argument in inspect.getargspec(f).args:
                    if f_argument not in arguments:
                        abort(400, u'Argument mismatch')
                return f(**arguments)
            self.blueprint.add_url_rule(route, inner.__name__, inner, methods=['POST'], **kwargs)
            return Callback(self, inner, max_retries, retry_delay, _inner=f)
        return decorator

    def get_job(self, request_id):
        response = requests.get(self.url + '/{}'.format(request_id))
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return Job(self, **response.json())

    def register(self, app, doppler_url=None, url_prefix='/_callbacks'):
        self.app = app
        if doppler_url is not None:
            self.set_url(doppler_url)
        elif self._url is None:
            raise RuntimeError(u'No Doppler service URL set. Set at Doppler '
                               u'init or via `register`')
        app.register_blueprint(self.blueprint, url_prefix=url_prefix)
