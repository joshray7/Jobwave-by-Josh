from types import SimpleNamespace
import app as app_module
import pathlib

def test_telegram_message_escapes_html():
    job = SimpleNamespace(
        id=1, title='Dev <Remote> & Co', company='A&B', location='Lagos',
        job_type='full-time', experience='mid',
        description='Needs <b>skills</b> and drive for this role.', source='Adzuna',
    )
    text = app_module.build_telegram_message(job)
    assert '<Remote>' not in text
    assert '&lt;Remote&gt;' in text
    assert 'skills' not in text  # the description is intentionally not in the short caption


def test_keyboard_has_only_view_and_apply():
    kb = app_module.build_telegram_keyboard('https://jobwave.com.ng/jobs/1')
    buttons = [b for row in kb['inline_keyboard'] for b in row]
    assert len(buttons) == 1
    assert buttons[0]['url'] == 'https://jobwave.com.ng/jobs/1'
    assert 'Apply' in buttons[0]['text']


def test_keyboard_is_none_without_a_valid_link():
    assert app_module.build_telegram_keyboard(None) is None
    assert app_module.build_telegram_keyboard('not-a-url') is None


def test_telegram_is_only_called_through_the_publish_helper():
    callers = []
    for path in list(pathlib.Path('.').glob('*.py')) + list(pathlib.Path('scrapers').glob('*.py')):
        if path.name.startswith('test_'):
            continue
        for line in path.read_text(encoding='utf-8').splitlines():
            if 'post_to_telegram(' in line and 'def post_to_telegram' not in line:
                callers.append(path.name)
    # exactly one call, inside publish_job_to_telegram in app.py
    assert callers == ['app.py']

def test_banner_is_uploaded_once_then_reused(monkeypatch):
    monkeypatch.setenv('TELEGRAM_BOT_TOKEN', 't')
    monkeypatch.setenv('TELEGRAM_CHANNEL_ID', '1')
    monkeypatch.setattr(app_module, '_banner_file_id', None)
    monkeypatch.setattr(app_module, 'load_banner', lambda: b'fakebytes')
    calls = []

    class Resp:
        ok = True
        status_code = 200
        text = ''
        def json(self):
            return {'result': {'photo': [{'file_id': 'small'}, {'file_id': 'FILE123'}]}}

    def fake_post(url, **kwargs):
        calls.append(kwargs)
        return Resp()

    monkeypatch.setattr(app_module.requests, 'post', fake_post)

    assert app_module.post_to_telegram('hi', job_url='https://example.com/jobs/1')
    assert 'files' in calls[0]               # the first post uploads the image
    assert app_module.post_to_telegram('hi', job_url='https://example.com/jobs/2')
    assert 'files' not in calls[1]           # the second reuses Telegram's id
    assert calls[1]['json']['photo'] == 'FILE123'

def _fake_job(i, source, status='approved'):
    return SimpleNamespace(id=i, source=source, approval_status=status)


def test_pick_jobs_caps_and_reserves_slots_for_nigerian_sources():
    jobs = ([_fake_job(i, 'Jobberman') for i in range(30)]
            + [_fake_job(100 + i, 'Adzuna') for i in range(30)]
            + [_fake_job(999, 'Jobberman', status='pending')])
    picked = app_module.pick_jobs_to_post(jobs, limit=20)
    sources = [j.source for j in picked]
    assert len(picked) == 20
    assert all(j.approval_status == 'approved' for j in picked)
    assert sources.count('Jobberman') == 14
    assert sources.count('Adzuna') == 6


def test_unused_slots_go_to_the_other_group():
    jobs = [_fake_job(i, 'Jobberman') for i in range(30)] + [_fake_job(100 + i, 'Adzuna') for i in range(3)]
    picked = app_module.pick_jobs_to_post(jobs, limit=20)
    sources = [j.source for j in picked]
    assert len(picked) == 20
    assert sources.count('Adzuna') == 3


def test_pick_jobs_rotates_across_sources_in_a_group():
    jobs = [_fake_job(i, 'Jobberman') for i in range(30)] + [_fake_job(100 + i, 'MyJobMag') for i in range(30)]
    picked = app_module.pick_jobs_to_post(jobs, limit=20)
    sources = [j.source for j in picked]
    assert sources.count('Jobberman') == 10 and sources.count('MyJobMag') == 10