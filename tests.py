import datetime as dt
import time
import pytest
import mock
import flask

from doppler.ext import NoSigner, Signer, Doppler, seconds_to_epoch


def test_signer_signature():
    payload = {'a': 1}
    assert Signer('a').sign(payload) != Signer('b').sign(payload)


def test_signer_unsign():
    signer = Signer('a')
    payload = {'a': 1}
    assert signer.unsign(signer.sign(payload)) == payload


def test_doppler_set_url():
    d = Doppler()
    d.set_url('foo/')
    assert d.url == 'foo'


def test_doppler_url_runtime_exc_raised_on_register():
    d = Doppler(url=None)
    with pytest.raises(RuntimeError):
        d.register(None, doppler_url=None)


def test_doppler_url_property_raises_runtime_exc_without_url():
    d = Doppler(url=None)
    with pytest.raises(RuntimeError):
        d.url


def test_doppler_signer_property_raises_runtime_exc_without_app():
    d = Doppler()
    with pytest.raises(RuntimeError):
        d.signer


def get_registered_doppler_and_app(**config):
    app = flask.Flask('foo')
    app.debug = True
    app.config.update(config or {})
    doppler = Doppler(app=app, url='')

    @doppler.listen('/foo')
    def callback(bar):
        return 'spam'

    doppler.register(app, url_prefix='/doppler')
    return doppler, app, callback


def test_doppler_without_secret_uses_no_signer():
    doppler, app, _ = get_registered_doppler_and_app()
    assert type(doppler.signer) == NoSigner


def test_doppler_endpoint_no_signer():
    doppler, app, _ = get_registered_doppler_and_app()
    response = app.test_client().post('/doppler/foo', data=flask.json.dumps({'bar': 1}))
    assert response.status_code == 200
    assert response.data == 'spam'


def test_doppler_endpoint_no_signer_non_json_raises_400():
    doppler, app, _ = get_registered_doppler_and_app()
    response = app.test_client().post('/doppler/foo', data='foo')
    assert response.status_code == 400


def test_doppler_endpoint_with_wrong_arguments():
    doppler, app, _ = get_registered_doppler_and_app()
    response = app.test_client().post('/doppler/foo', data=flask.json.dumps({'foo': 1}))
    assert response.status_code == 400


def test_doppler_endpoint_raises_400_with_missing_arguments():
    doppler, app, _ = get_registered_doppler_and_app(SECRET_KEY='foo')
    response = app.test_client().post('/doppler/foo', data='')
    assert response.status_code == 400


def test_doppler_endpoint_signer_correct_arguments():
    doppler, app, _ = get_registered_doppler_and_app(SECRET_KEY='foo')
    response = app.test_client().post('/doppler/foo', data=doppler.signer.sign({'bar': 1}))
    assert response.status_code == 200
    assert response.data == 'spam'


def test_doppler_get_job_returns_none_on_404():
    doppler, app, _ = get_registered_doppler_and_app()
    with mock.patch('doppler.ext.requests.get') as mock_get:
        mock_get.return_value.status_code = 404
        assert doppler.get_job('foo') is None


def test_doppler_get_job():
    doppler, app, _ = get_registered_doppler_and_app()
    with mock.patch('doppler.ext.requests.get') as mock_get:
        mock_get.return_value.json.return_value = {'foo': 'bar'}
        job = doppler.get_job('foo')
    assert job.foo == 'bar'


def test_callback_url():
    doppler, app, callback = get_registered_doppler_and_app(SERVER_NAME='asdf')
    with app.app_context():
        assert callback.url == 'http://asdf/doppler/foo'


def test_seconds_to_epoch_convert_datetime():
    assert seconds_to_epoch(dt.datetime.now() + dt.timedelta(seconds=10)) == int(time.time()) + 10


def test_seconds_to_epoch_convert_timedelta():
    assert seconds_to_epoch(dt.timedelta(seconds=10)) == int(time.time()) + 10


def test_seconds_to_epoch_convert_seconds():
    assert seconds_to_epoch(10) == int(time.time()) + 10
