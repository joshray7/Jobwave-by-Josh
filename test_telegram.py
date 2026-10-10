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