import uuid
import app as app_module


def _make_job(**overrides):
    fields = dict(
        title='Test Engineer', company='Acme Ltd', location='Lagos',
        job_type='full-time', experience='mid',
        description='A real description that is long enough to read.',
        source='Adzuna', source_url='https://example.com/apply-here',
        source_id=f'test-{uuid.uuid4().hex}',
        is_active=True, approval_status='approved',
    )
    fields.update(overrides)
    job = app_module.Job(**fields)
    app_module.db.session.add(job)
    app_module.db.session.commit()
    return job.id


def test_public_job_page_for_anonymous_visitor():
    with app_module.app.app_context():
        job_id = _make_job()
    client = app_module.app.test_client()
    resp = client.get(f'/jobs/{job_id}')
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert 'Test Engineer' in body
    assert 'Log in to apply' in body
    assert 'https://example.com/apply-here' not in body  # the apply link must not leak


def test_pending_job_is_hidden_from_anonymous_visitors():
    with app_module.app.app_context():
        job_id = _make_job(is_active=False, approval_status='pending')
    client = app_module.app.test_client()
    resp = client.get(f'/jobs/{job_id}')
    assert resp.status_code == 302  # redirected away, page not shown