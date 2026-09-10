"""
Integration tests: scraped jobs land as pending when flagged, approved when
clean, and admin approval actually flips them live.
"""
import pytest


def test_clean_job_auto_approves(flask_app):
    from app import process_scraped_job
    jd = {
        'title': 'Frontend Developer at Paystack', 'company': 'Paystack',
        'location': 'Lagos', 'job_type': 'full-time', 'experience': 'mid',
        'salary_min': None, 'salary_max': None,
        'description': 'We are hiring a frontend developer with React experience for our Lagos team.',
        'requirements': None, 'source': 'JSearch', 'source_url': 'https://example.com/1',
        'source_id': 'test-clean-1', 'tags': 'react', 'posted_at': None,
        'scraped_at': None,
    }
    result = process_scraped_job(jd)
    assert result['approval_status'] == 'approved'
    assert result['is_active'] is True
    assert result['validation_warnings'] is None


def test_aptech_style_job_is_flagged_pending(flask_app):
    from app import process_scraped_job
    jd = {
        'title': 'Software Engineer Instructor At APTECH Computer Education',
        'company': 'Totally Different Recruiting Agency LLC',
        'location': 'Lagos, Estado de Lagos, US',
        'job_type': 'full-time', 'experience': 'senior',
        'salary_min': None, 'salary_max': None,
        'description': 'Never Miss a Job Update Again. We have started building our professional LinkedIn page. Entry level, fresh graduates welcome, no experience required.',
        'requirements': None, 'source': 'JSearch', 'source_url': 'https://example.com/2',
        'source_id': 'test-aptech-1', 'tags': '', 'posted_at': None,
        'scraped_at': None,
    }
    result = process_scraped_job(jd)
    assert result['approval_status'] == 'pending'
    assert result['is_active'] is False
    assert 'company_title_mismatch' in result['validation_warnings']
    assert 'experience_mismatch' in result['validation_warnings']
    assert 'Estado de Lagos' not in result['location']


def test_missing_company_job_is_flagged_pending(flask_app):
    from app import process_scraped_job
    jd = {
        'title': 'Sales Rep', 'company': None, 'location': 'Abuja',
        'job_type': 'full-time', 'experience': 'mid',
        'salary_min': None, 'salary_max': None,
        'description': 'A genuine sales role description with enough real content in it.',
        'requirements': None, 'source': 'Jobberman', 'source_url': 'https://example.com/3',
        'source_id': 'test-missing-1', 'tags': '', 'posted_at': None,
        'scraped_at': None,
    }
    result = process_scraped_job(jd)
    assert result['approval_status'] == 'pending'
    assert 'missing_company' in result['validation_warnings']


def test_admin_can_approve_pending_job(flask_app, client, db_session):
    from app import Job, User
    from datetime import datetime

    with flask_app.app_context():
        admin = User.query.filter_by(role='admin').first()
        if not admin:
            admin = User(name='Test Admin', email='testadmin@example.com',
                        username='testadmin', role='admin', is_verified=True)
            admin.set_password('testpass123')
            db_session.session.add(admin)
            db_session.session.commit()
        admin_id = admin.id  # capture the plain value before the session closes

        import uuid
        job = Job(
            title='Ambiguous Role', company='Some Company', location='Lagos',
            job_type='full-time', experience='unknown', source='JSearch',
            source_url='https://example.com/4', source_id=f'test-approve-flow-{uuid.uuid4()}',
            approval_status='pending', is_active=False,
            validation_warnings='missing_description',
            scraped_at=datetime.utcnow(),
        )
        db_session.session.add(job)
        db_session.session.commit()
        job_id = job.id

    with client.session_transaction() as sess:
        sess['_user_id'] = str(admin_id)
        sess['_fresh'] = True

    response = client.post(f'/admin/employer-jobs/{job_id}/approve')
    assert response.status_code == 200

    with flask_app.app_context():
        updated = Job.query.get(job_id)
        assert updated.approval_status == 'approved'
        assert updated.is_active is True