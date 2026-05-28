"""
The Muse API Scraper
---------------------
Fetches tech & startup jobs from The Muse — free, no API key needed.
Docs: https://www.themuse.com/developers/api/v2

Categories: Engineering, Data Science, Design, Product, Marketing, etc.
"""

import requests
import hashlib
from datetime import datetime
import time
import re

MUSE_BASE = "https://www.themuse.com/api/public/jobs"


def make_source_id(job_id) -> str:
    return hashlib.md5(f"muse::{job_id}".encode()).hexdigest()


def infer_experience(levels: list) -> str:
    if not levels:
        return 'mid'
    level_str = ' '.join(levels).lower()
    if any(w in level_str for w in ['senior', 'lead', 'principal', 'director']):
        return 'senior'
    if any(w in level_str for w in ['entry', 'internship', 'junior']):
        return 'entry'
    if any(w in level_str for w in ['manager', 'vp', 'executive']):
        return 'lead'
    return 'mid'


def extract_tags(title: str, desc: str) -> str:
    keywords = [
        'python', 'javascript', 'typescript', 'react', 'node', 'nodejs', 'vue',
        'angular', 'java', 'kotlin', 'swift', 'flutter', 'go', 'golang', 'rust',
        'c#', '.net', 'php', 'ruby', 'rails', 'django', 'fastapi', 'flask',
        'aws', 'azure', 'gcp', 'docker', 'kubernetes', 'terraform', 'postgresql',
        'mysql', 'mongodb', 'redis', 'graphql', 'rest', 'api', 'sql',
        'machine learning', 'ai', 'data science', 'devops', 'ci/cd',
        'figma', 'ux', 'product', 'agile', 'scrum',
    ]
    text = (title + ' ' + (desc or '')[:1000]).lower()
    found = [k for k in keywords if k in text]
    return ','.join(found[:8])


def clean_html(raw: str) -> str:
    """Strip HTML tags from description."""
    if not raw:
        return ''
    clean = re.sub(r'<[^>]+>', ' ', raw)
    clean = re.sub(r'\s+', ' ', clean).strip()
    return clean[:3000]


def parse_muse_job(item: dict) -> dict:
    title = item.get('name', '')
    company = item.get('company', {}).get('name', 'Unknown')

    # Location
    locations = item.get('locations', [])
    location_str = locations[0].get('name', 'Remote') if locations else 'Remote'
    if 'Flexible' in location_str or 'Remote' in location_str:
        location_str = 'Remote'

    # Job type
    job_type_raw = (item.get('type') or '').lower()
    job_type_map = {
        'permanent': 'full-time',
        'contract': 'contract',
        'internship': 'internship',
        'temporary': 'contract',
    }
    job_type = job_type_map.get(job_type_raw, 'full-time')
    if 'remote' in location_str.lower():
        job_type = 'remote'

    # Experience from levels
    levels = [l.get('short_name', '') for l in item.get('levels', [])]
    experience = infer_experience(levels)

    # Description
    contents = item.get('contents', '')
    description = clean_html(contents)

    # Posted date
    pub_date = item.get('publication_date', '')
    try:
        posted_at = datetime.fromisoformat(pub_date.replace('Z', '+00:00')).replace(tzinfo=None)
    except Exception:
        posted_at = datetime.utcnow()

    job_id = str(item.get('id', ''))
    apply_link = item.get('refs', {}).get('landing_page', '')

    return {
        'title': title,
        'company': company,
        'location': location_str,
        'job_type': job_type,
        'experience': experience,
        'salary_min': None,  # Muse doesn't provide salary data
        'salary_max': None,
        'description': description,
        'requirements': None,
        'source': 'The Muse',
        'source_url': apply_link,
        'source_id': make_source_id(job_id),
        'tags': extract_tags(title, description),
        'posted_at': posted_at,
        'scraped_at': datetime.utcnow(),
    }


def fetch_muse_jobs(
    category: str = 'Engineering',
    page: int = 1,
    num_pages: int = 2,
) -> list[dict]:
    """
    Fetch jobs from The Muse API (no key needed).

    Args:
        category:  Job category (Engineering, Data Science, Design, Product, etc.)
        page:      Starting page number
        num_pages: Number of pages to fetch (20 jobs per page)

    Returns:
        List of job dicts ready for insertion into the Job model.
    """
    all_jobs = []

    for p in range(page, page + num_pages):
        params = {
            'category': category,
            'page': p,
            'descending': 'true',
        }

        time.sleep(1)  # polite delay

        try:
            resp = requests.get(MUSE_BASE, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            results = data.get('results', [])
            if not results:
                break
            for item in results:
                try:
                    all_jobs.append(parse_muse_job(item))
                except Exception:
                    continue
        except requests.exceptions.Timeout:
            raise RuntimeError("The Muse API request timed out.")
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"The Muse network error: {e}")

    return all_jobs


# ─── Search profiles ──────────────────────────────────────────────────────────

MUSE_PROFILES = [
    {
        'name': 'Muse Engineering',
        'category': 'Engineering',
        'num_pages': 2,
    },
    {
        'name': 'Muse Data Science',
        'category': 'Data Science',
        'num_pages': 1,
    },
    {
        'name': 'Muse Design',
        'category': 'Design',
        'num_pages': 1,
    },
    {
        'name': 'Muse Product',
        'category': 'Product',
        'num_pages': 1,
    },
]


def get_muse_profile(name: str) -> dict | None:
    return next((p for p in MUSE_PROFILES if p['name'] == name), None)