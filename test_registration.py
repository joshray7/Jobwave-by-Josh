import uuid
import app as app_module


def _register(client, name, username, email):
    return client.post('/register', data={
        'name': name, 'username': username, 'email': email, 'password': 'secret123',
    })


def test_duplicate_email_and_username_do_not_crash():
    app_module.limiter.enabled = False  # register is limited to 5 POSTs/hour
    client = app_module.app.test_client()
    tag = uuid.uuid4().hex[:8]
    username, email = f'user_{tag}', f'{tag}@example.com'

    assert _register(client, 'First', username, email).status_code == 302  # created
    client.get('/logout')

    # same email, different username: form shown again, not a 500
    assert _register(client, 'Second', f'other_{tag}', email).status_code == 200
    # same username, different email: same
    assert _register(client, 'Third', username, f'x_{tag}@example.com').status_code == 200

    with app_module.app.app_context():
        assert app_module.User.query.filter_by(email=email).count() == 1
        assert app_module.User.query.filter_by(username=username).count() == 1