<p align="center">
  <img style="max-width:50%;" src="https://s3-eu-west-1.amazonaws.com/app-static.takumi.com/Doppler.svg">
</p>

# Doppler [![Deploy](https://www.herokucdn.com/deploy/button.svg)](https://heroku.com/deploy) [![Build Status](https://travis-ci.org/TakumiHQ/doppler.svg?branch=master)](https://travis-ci.org/TakumiHQ/doppler)

# Intro

Doppler helps you schedule HTTP callbacks with retries. Callbacks are HTTP POST
and a Flask helper takes care of signing and unsigning payloads.

There are three components to Doppler

1. Flask helper to define webhook endpoitns and and schedule callbacks
2. Queue worker to trigger callback requests at the right time
3. REST service to accept delay requests, cancellations and job introspection

## One Liner

Let’s say we have an internal endpoint in Flask that sends users reminders. This
is how you would trigger it in 3 hours:

```python
remind_user.delay(60 * 60 * 3, user_id='foo', message='Don’t forget to buy milk')
```

## Accuracy

The Doppler server uses rpqueue and redis to trigger callbacks. I’m not sure
what the resolution is, but I wrote this with "minute resolution" as a goal. If
you need second or microsecond accuracy look elsewhere.

## Use Cases

+ Send users notification reminders at a predictable moment in time
+ Trigger charges only an hour after a purchase to avoid payback on cancellations
+ You get the point...

## Example

```python
from flask import Flask, abort
from doppler.ext import Doppler

app = Flask(__name__)
app.config.update(
    SERVER_NAME='localhost:5001',
    SECRET_KEY='foo',
)
doppler = Doppler('http://localhost:5000/')


@doppler.listen('/expire', max_retries=5, retry_delay=10)
def expire(id):
    try:
        Contract.query.get(id).expire()
    except NotSignedError:
        abort(400)  # Will retry 5x with 10 second delays

doppler.register(app)

if __name__ == "__main__":
    app.run(port=5001)
```

The above Flask app now has an endpoint on `/_callbacks/expire`.

To schedule a delayed and secure request to this endpoint:

```python
job = expire.delay(10, id='foo')
```

### Canceling Jobs

```python
job = expire.delay(10, id='foo')
job.cancel()
```

... and querying the state

```python
job = expire.delay(10, id='foo')
job.state == 'early'
time.sleep(10)
job.refresh()  # or doppler.get_job(job.request_id)
job.state == 'done'
```

Here are the attributes available on jobs

```json
{
  "request_id": "9cbb9962-585a-4240-82a5-ab2537a0fb1b",
  "status": "early",
  "run_at": 1486412420,
  "scheduled_at": 1486412420,
  "last_retry": null,
  "retries_left": 3
}
```

## Security

Note that the endpoint kwargs are **not** based on URL matching. The
`doppler.listen` decorator takes care of sending and storing callback arguments
(using the Werkzeug session cookie implementation). This means the doppler
service is treated like a browser and uses your Flask app secret to make sure
information originating from your internal server is not shared unencrypted with
the doppler server. A public Doppler instance will of course allow anyone to
cancel your jobs if they own the job request id’s (does this mean it’s secure if
you use HTTPS? I don’t know, I’m not a security expert).
