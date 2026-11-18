import uuid
import app as app_module


def test_robots_txt_blocks_private_areas_and_points_to_sitemap():
    resp = app_module.app.test_client().get('/robots.txt')
    body = resp.get_data(as_text=True)
    assert resp.status_code == 200
    assert 'Disallow: /admin' in body
    assert body.strip().endswith('/sitemap.xml')


def test_sitemap_lists_only_live_approved_jobs():
    tag = uuid.uuid4().hex
    with app_module.app.app_context():
        live = app_module.Job(title='Live job', company='Acme', source='Adzuna',
                              source_id=f'live-{tag}', is_active=True, approval_status='approved')
        hidden = app_module.Job(title='Hidden job', company='Acme', source='Adzuna',
                                source_id=f'hid-{tag}', is_active=False, approval_status='pending')
        app_module.db.session.add_all([live, hidden])
        app_module.db.session.commit()
        live_id, hidden_id = live.id, hidden.id
    resp = app_module.app.test_client().get('/sitemap.xml')
    body = resp.get_data(as_text=True)
    assert resp.status_code == 200
    assert resp.mimetype == 'application/xml'
    assert f'/jobs/{live_id}<' in body
    assert f'/jobs/{hidden_id}<' not in body


def test_public_job_page_has_canonical_and_title():
    with app_module.app.app_context():
        job = app_module.Job(title='Test Engineer', company='Acme Ltd', source='Adzuna',
                             source_id=f'seo-{uuid.uuid4().hex}', is_active=True,
                             approval_status='approved', description='A real description for testing purposes.')
        app_module.db.session.add(job)
        app_module.db.session.commit()
        job_id = job.id
    body = app_module.app.test_client().get(f'/jobs/{job_id}').get_data(as_text=True)
    assert 'rel="canonical"' in body
    assert f'/jobs/{job_id}"' in body
    assert 'Test Engineer at Acme Ltd' in body