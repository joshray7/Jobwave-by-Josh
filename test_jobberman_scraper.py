"""
Tests for scrapers/jobberman_scraper.py

No network calls: cards are built from small HTML fragments that mirror the
real Jobberman card layout (each field is its own element), and
requests.get is monkeypatched for the fetch tests.
"""

from datetime import datetime, timedelta
from html import escape

import pytest
import requests
from bs4 import BeautifulSoup

import scrapers.jobberman_scraper as js


# ─── Test-data helpers ────────────────────────────────────────────────────────

DESCRIPTION = (
    "Diamond Throne Limited is seeking a strong, hands-on and results-driven "
    "General Manager to oversee the daily operations and performance of "
    "Diamond Throne Lifestyle. The GM will be responsible for ..."
)

# Mirrors the real card printed by debug_location.py
DEFAULT_STRINGS = [
    'Diamond Throne Limited',
    'Lagos',
    'Full Time',
    'NGN',
    '400,000 - 600,000',
    'Management & Business Development',
    'New',
    'Today',
    DESCRIPTION,
]


def build_card(title='General Manager', slug='general-manager-abc',
               strings=None, href=None, extra_same_link=False):
    """Build one job card. The title link is wrapped in an <h2>, which
    reproduces the old bug where find_parent() returned a title-only wrapper."""
    strings = list(DEFAULT_STRINGS) if strings is None else strings
    href = href or f'/listings/{slug}'
    body = ''.join(f'<p>{escape(s)}</p>' for s in strings)
    extra = f'<a href="{href}">Easy apply</a>' if extra_same_link else ''
    return f'<div class="card"><h2><a href="{href}">{escape(title)}</a></h2>{body}{extra}</div>'


def first_link(html):
    soup = BeautifulSoup(html, 'html.parser')
    return soup.find('a', href=js.JOB_LINK_RE)


def parse(strings=None, **kwargs):
    return js.parse_job_card(first_link(build_card(strings=strings, **kwargs)))


def with_strings(**changes):
    """Copy of DEFAULT_STRINGS with index -> replacement, e.g. with_strings(**{'1': 'Abuja'})."""
    s = list(DEFAULT_STRINGS)
    for idx, value in changes.items():
        s[int(idx)] = value
    return s


class FakeResponse:
    def __init__(self, text='', status=200):
        self.text = text
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(f'{self.status_code}')


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    """The scraper sleeps 1.5s between pages; skip that in tests."""
    monkeypatch.setattr(js.time, 'sleep', lambda s: None)


# ─── Small pure helpers ───────────────────────────────────────────────────────

def test_make_source_id_is_stable_and_url_specific():
    a = js.make_source_id('https://www.jobberman.com/listings/a')
    b = js.make_source_id('https://www.jobberman.com/listings/b')
    assert a == js.make_source_id('https://www.jobberman.com/listings/a')
    assert a != b
    assert len(a) == 32


@pytest.mark.parametrize('text,expected', [
    ('Full Time', 'full-time'),
    ('Part Time', 'part-time'),
    ('Contract', 'contract'),
    ('Internship & Graduate', 'internship'),
    ('Remote', 'remote'),
    ('', 'full-time'),
    (None, 'full-time'),
])
def test_infer_job_type(text, expected):
    assert js.infer_job_type(text) == expected


@pytest.mark.parametrize('text,expected', [
    ('Senior Accountant', 'senior'),
    ('General Manager', 'senior'),
    ('Graduate Trainee', 'entry'),
    ('Junior Developer', 'entry'),
    ('Accountant', 'mid'),
])
def test_infer_experience(text, expected):
    assert js.infer_experience(text) == expected


def test_extract_tags_finds_keywords_in_list_order():
    assert js.extract_tags('sales and marketing manager') == 'sales,marketing'


def test_extract_tags_caps_at_six():
    text = 'sales marketing accounting finance engineering logistics legal medical'
    assert len(js.extract_tags(text).split(',')) == 6


def test_extract_tags_empty_when_nothing_matches():
    assert js.extract_tags('nothing relevant here') == ''


# ─── parse_posted_date ────────────────────────────────────────────────────────

def close_to(actual, expected, seconds=10):
    return abs((actual - expected).total_seconds()) < seconds


def test_parse_posted_date_today_and_yesterday():
    assert close_to(js.parse_posted_date('Today'), datetime.utcnow())
    assert close_to(js.parse_posted_date(' today '), datetime.utcnow())
    assert close_to(js.parse_posted_date('Yesterday'), datetime.utcnow() - timedelta(days=1))


def test_parse_posted_date_relative_units():
    now = datetime.utcnow()
    assert close_to(js.parse_posted_date('3 days ago'), now - timedelta(days=3))
    assert close_to(js.parse_posted_date('1 day ago'), now - timedelta(days=1))
    assert close_to(js.parse_posted_date('2 weeks ago'), now - timedelta(weeks=2))
    assert close_to(js.parse_posted_date('1 month ago'), now - timedelta(days=30))


def test_parse_posted_date_unknown_falls_back_to_now():
    assert close_to(js.parse_posted_date('whenever'), datetime.utcnow())


# ─── find_card_container ──────────────────────────────────────────────────────

def test_container_is_the_full_card_not_the_title_wrapper():
    tag = first_link(build_card())
    container = js.find_card_container(tag)
    text = ' '.join(container.stripped_strings)
    assert 'Diamond Throne Limited' in text
    assert 'Lagos' in text


def test_container_stops_before_merging_two_jobs():
    second = with_strings(**{'0': 'Second Company Ltd'})
    page = (
        '<div id="list">'
        + build_card(slug='job-one')
        + build_card(title='Sales Rep', slug='job-two', strings=second)
        + '</div>'
    )
    container = js.find_card_container(first_link(page))
    text = ' '.join(container.stripped_strings)
    assert 'Diamond Throne Limited' in text
    assert 'Second Company Ltd' not in text


# ─── parse_job_card: the happy path ───────────────────────────────────────────

def test_parse_full_card():
    job = parse()
    assert job['title'] == 'General Manager'
    assert job['company'] == 'Diamond Throne Limited'
    assert job['location'] == 'Lagos'
    assert job['job_type'] == 'full-time'
    assert job['experience'] == 'senior'
    assert job['description'].startswith('Diamond Throne Limited is seeking')
    assert job['source'] == 'Jobberman'
    assert job['salary_min'] is None and job['salary_max'] is None
    assert close_to(job['posted_at'], datetime.utcnow())


def test_source_url_and_id():
    job = parse()
    url = 'https://www.jobberman.com/listings/general-manager-abc'
    assert job['source_url'] == url
    assert job['source_id'] == js.make_source_id(url)


def test_absolute_href_is_kept():
    url = 'https://www.jobberman.com/listings/abs-job'
    job = parse(href=url)
    assert job['source_url'] == url


def test_junk_labels_do_not_become_the_company():
    job = parse(strings=['FEATURED', 'Popular'] + DEFAULT_STRINGS)
    assert job['company'] == 'Diamond Throne Limited'


def test_posted_date_is_read_from_the_card():
    job = parse(strings=with_strings(**{'7': '3 days ago'}))
    assert close_to(job['posted_at'], datetime.utcnow() - timedelta(days=3))


@pytest.mark.parametrize('work_type,expected', [
    ('Part Time', 'part-time'),
    ('Contract', 'contract'),
    ('Internship & Graduate', 'internship'),
])
def test_job_type_comes_from_the_work_type_string(work_type, expected):
    job = parse(strings=with_strings(**{'2': work_type}))
    assert job['job_type'] == expected


# ─── parse_job_card: location (regression for the "Nigeria" bug) ──────────────

def test_location_is_city_when_work_type_is_its_own_string():
    """Real layout: city and work type are separate strings.
    Old code split 'Full Time' on itself, got '', and fell back to 'Nigeria'."""
    job = parse()
    assert job['location'] == 'Lagos'
    assert job['location'] not in js.WORK_TYPES


def test_location_other_city():
    job = parse(strings=with_strings(**{'1': 'Abuja'}))
    assert job['location'] == 'Abuja'


def test_location_when_city_and_work_type_share_one_string():
    strings = [
        'Diamond Throne Limited', 'Lagos Full Time', 'NGN', '400,000 - 600,000',
        'Management & Business Development', 'New', 'Today', DESCRIPTION,
    ]
    assert parse(strings=strings)['location'] == 'Lagos'


def test_location_remote():
    job = parse(strings=with_strings(**{'1': 'Remote'}))
    assert job['location'] == 'Remote'


def test_location_falls_back_to_nigeria_when_card_has_no_location():
    strings = [s for s in DEFAULT_STRINGS if s != 'Lagos']
    job = parse(strings=strings)
    assert job['location'] == 'Nigeria'
    assert job['company'] == 'Diamond Throne Limited'


def test_company_name_containing_a_work_type_word_does_not_break_location():
    """'Contract Masters Ltd' contains 'Contract'; the matcher must skip index 0."""
    job = parse(strings=with_strings(**{'0': 'Contract Masters Ltd'}))
    assert job['company'] == 'Contract Masters Ltd'
    assert job['location'] == 'Lagos'
    assert job['job_type'] == 'full-time'


# ─── parse_job_card: description and bad input ────────────────────────────────

def test_short_description_is_dropped():
    job = parse(strings=with_strings(**{'8': 'Short text'}))
    assert job['description'] is None


def test_link_with_no_title_returns_none():
    tag = first_link('<div><a href="/listings/empty-one"></a><p>Some Co</p></div>')
    assert js.parse_job_card(tag) is None


# ─── fetch_jobberman_jobs (requests mocked) ───────────────────────────────────

def page_with(*cards):
    return '<html><body><div id="list">' + ''.join(cards) + '</div></body></html>'


def test_fetch_parses_multiple_cards(monkeypatch):
    second = with_strings(**{'0': 'Second Company Ltd', '1': 'Abuja'})
    html = page_with(
        build_card(slug='job-one'),
        build_card(title='Sales Rep', slug='job-two', strings=second),
    )
    monkeypatch.setattr(js.requests, 'get', lambda url, headers=None, timeout=None: FakeResponse(html))

    jobs = js.fetch_jobberman_jobs()

    assert len(jobs) == 2
    by_title = {j['title']: j for j in jobs}
    assert by_title['General Manager']['company'] == 'Diamond Throne Limited'
    assert by_title['General Manager']['location'] == 'Lagos'
    assert by_title['Sales Rep']['company'] == 'Second Company Ltd'
    assert by_title['Sales Rep']['location'] == 'Abuja'


def test_fetch_skips_duplicate_links_on_a_page(monkeypatch):
    html = page_with(build_card(extra_same_link=True))
    monkeypatch.setattr(js.requests, 'get', lambda url, headers=None, timeout=None: FakeResponse(html))
    assert len(js.fetch_jobberman_jobs()) == 1


def test_fetch_builds_category_and_page_urls(monkeypatch):
    urls = []

    def fake_get(url, headers=None, timeout=None):
        urls.append(url)
        return FakeResponse(page_with(build_card(slug=f'job-{len(urls)}')))

    monkeypatch.setattr(js.requests, 'get', fake_get)
    jobs = js.fetch_jobberman_jobs(category_path='sales', num_pages=2)

    assert urls == [
        f'{js.JOBBERMAN_BASE}/jobs/sales',
        f'{js.JOBBERMAN_BASE}/jobs/sales?page=2',
    ]
    assert len(jobs) == 2


def test_fetch_keeps_page_one_jobs_if_page_two_fails(monkeypatch):
    calls = {'n': 0}

    def fake_get(url, headers=None, timeout=None):
        calls['n'] += 1
        if calls['n'] == 1:
            return FakeResponse(page_with(build_card()))
        raise requests.exceptions.ConnectionError('boom')

    monkeypatch.setattr(js.requests, 'get', fake_get)
    jobs = js.fetch_jobberman_jobs(num_pages=2)
    assert len(jobs) == 1


def test_fetch_raises_on_page_one_network_error(monkeypatch):
    def fake_get(url, headers=None, timeout=None):
        raise requests.exceptions.ConnectionError('boom')

    monkeypatch.setattr(js.requests, 'get', fake_get)
    with pytest.raises(RuntimeError, match='network error'):
        js.fetch_jobberman_jobs()


def test_fetch_raises_on_timeout(monkeypatch):
    def fake_get(url, headers=None, timeout=None):
        raise requests.exceptions.Timeout()

    monkeypatch.setattr(js.requests, 'get', fake_get)
    with pytest.raises(RuntimeError, match='timed out'):
        js.fetch_jobberman_jobs()


def test_fetch_raises_on_http_error_page_one(monkeypatch):
    monkeypatch.setattr(js.requests, 'get',
                        lambda url, headers=None, timeout=None: FakeResponse('', status=403))
    with pytest.raises(RuntimeError, match='network error'):
        js.fetch_jobberman_jobs()


# ─── Search profiles ──────────────────────────────────────────────────────────

def test_get_jobberman_profile_found_and_missing():
    profile = js.get_jobberman_profile('Jobberman — Sales')
    assert profile['category_path'] == 'sales'
    assert js.get_jobberman_profile('does not exist') is None


def test_every_profile_has_required_keys():
    for p in js.JOBBERMAN_PROFILES:
        assert {'name', 'category_path', 'num_pages'} <= set(p)