"""Pytest fixtures — isolates tests from your real dev/production database."""
import os
import tempfile
import pytest

os.environ['SKIP_SCHEDULER'] = '1'

db_fd, db_path = tempfile.mkstemp(suffix='.db')
os.environ['DATABASE_URL'] = f'sqlite:///{db_path}'

assert 'jobwave.db' not in db_path, "Refusing to run tests against the real dev database!"

@pytest.fixture(scope='session')
def flask_app():
    import app as app_module
    app_module.app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
    app_module.app.config['TESTING'] = True
    with app_module.app.app_context():
        app_module.db.create_all()
    yield app_module.app


@pytest.fixture()
def client(flask_app):
    return flask_app.test_client()


@pytest.fixture()
def db_session(flask_app):
    import app as app_module
    with flask_app.app_context():
        yield app_module.db
        app_module.db.session.rollback()
        # Clean up any rows committed during this test, so the next test
        # starts from a known-empty state instead of accumulating data.
        for table in reversed(app_module.db.metadata.sorted_tables):
            app_module.db.session.execute(table.delete())
        app_module.db.session.commit()