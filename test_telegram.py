from types import SimpleNamespace
import app as app_module


def test_telegram_message_escapes_html():
    job = SimpleNamespace(
        id=1, title='Dev <Remote> & Co', company='A&B', location='Lagos',
        job_type='full-time', experience='mid',
        description='Needs <b>skills</b> and drive for this role.', source='Adzuna',
    )
    text = app_module.build_telegram_message(job)
    assert '<Remote>' not in text
    assert '&lt;Remote&gt;' in text
    assert '<b>skills</b>' not in text
    assert '&lt;b&gt;skills&lt;/b&gt;' in text


def test_keyboard_has_only_view_and_apply():
    kb = app_module.build_telegram_keyboard('https://jobwave.com.ng/jobs/1')
    buttons = [b for row in kb['inline_keyboard'] for b in row]
    assert len(buttons) == 1
    assert buttons[0]['url'] == 'https://jobwave.com.ng/jobs/1'
    assert 'Apply' in buttons[0]['text']


def test_keyboard_is_none_without_a_valid_link():
    assert app_module.build_telegram_keyboard(None) is None
    assert app_module.build_telegram_keyboard('not-a-url') is None