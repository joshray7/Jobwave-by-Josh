"""
Adzuna API Scraper
-------------------
Fetches jobs from Adzuna — covers Nigeria, UK, US, remote, and more.
Free tier: 1000 calls/month
Docs: https://developer.adzuna.com/docs

Requires: ADZUNA_APP_ID and ADZUNA_APP_KEY environment variables
"""

import requests
import hashlib
from datetime import datetime
import time
import os

ADZUNA_BASE = "https://api.adzuna.com/v1/api/jobs"


def make_source_id(job_id) -> str:
    return hashlib.md5(f"adzuna::{job_id}".encode()).hexdigest()


def infer_experience(title: str, desc: str) -> str:
    text = (title + ' ' + (desc or '')).lower()
    if any(w in text for w in ['senior', 'sr.', 'lead', 'principal', 'staff', 'head of']):
        return 'senior'
    if any(w in text for w in ['junior', 'entry', 'graduate', 'intern', 'fresher']):
        return 'entry'
    if any(w in text for w in ['manager', 'director', 'vp ', 'vice president']):
        return 'lead'
    return 'mid'


def extract_tags(title: str, desc: str, category: str = '') -> str:
    keywords = [
        'python', 'javascript', 'typescript', 'react', 'node', 'nodejs', 'vue',
        'angular', 'java', 'kotlin', 'swift', 'flutter', 'go', 'golang', 'rust',
        'c#', '.net', 'php', 'ruby', 'rails', 'django', 'fastapi', 'flask',
        'aws', 'azure', 'gcp', 'docker', 'kubernetes', 'terraform', 'postgresql',
        'mysql', 'mongodb', 'redis', 'graphql', 'rest', 'api', 'sql',
        'machine learning', 'ai', 'data science', 'devops', 'ci/cd',
        'figma', 'ux', 'product', 'agile', 'scrum',
    ]
    text = (title + ' ' + (desc or '')[:1000] + ' ' + category).lower()
    found = [k for k in keywords if k in text]
    return ','.join(found[:8])


def parse_adzuna_job(item: dict, region: str = 'ng') -> dict:
    """Parse a single Adzuna job result."""
    title = item.get('title', '')
    company = item.get('company', {})
    company_name = company.get('display_name', 'Unknown') if isinstance(company, dict) else str(company)

    location = item.get('location', {})
    location_str = ''
    if isinstance(location, dict):
        area = location.get('area', [])
        if area and len(area) > 0:
            location_str = area[0]
        if not location_str:
            location_str = location.get('display_name', '')
    location_str = location_str or 'Remote'

    description = item.get('description', '')
    job_type = 'full-time'  # Adzuna doesn't always specify
    salary_min = None
    salary_max = None

    # Salary from Adzuna
    salary_data = item.get('salary_min') or item.get('salary_max')
    if salary_data:
        try:
            salary_min = int(item.get('salary_min', 0) or 0)
            salary_max = int(item.get('salary_max', 0) or 0)
            if salary_min > 0 and salary_max == 0:
                salary_max = int(salary_min * 1.3)
        except (ValueError, TypeError):
            pass

    posted_str = item.get('created', '')
    try:
        posted_at = datetime.fromisoformat(posted_str.replace('Z', '+00:00')).replace(tzinfo=None)
    except Exception:
        posted_at = datetime.utcnow()

    job_id = str(item.get('id', ''))
    apply_link = item.get('redirect_url', '')
    category = item.get('category', {})
    category_name = category.get('label', '') if isinstance(category, dict) else str(category)

    return {
        'title': title,
        'company': company_name,
        'location': location_str,
        'job_type': job_type,
        'experience': infer_experience(title, description),
        'salary_min': salary_min,
        'salary_max': salary_max,
        'description': description[:3000] if description else None,
        'requirements': None,
        'source': 'Adzuna',
        'source_url': apply_link,
        'source_id': make_source_id(job_id),
        'tags': extract_tags(title, description, category_name),
        'posted_at': posted_at,
        'scraped_at': datetime.utcnow(),
    }


def fetch_adzuna_jobs(
    region: str = 'ng',
    keywords: str = 'developer',
    page: int = 1,
) -> list[dict]:
    """
    Fetch jobs from Adzuna API.

    Args:
        region:   Country code (ng=Nigeria, gb=UK, us=USA, etc)
        keywords: Search keywords
        page:     Page number

    Returns:
        List of job dicts ready for DB insertion.
    """
    app_id = os.environ.get('ADZUNA_APP_ID', '')
    app_key = os.environ.get('ADZUNA_APP_KEY', '')
    if not app_id or not app_key:
        raise ValueError('ADZUNA_APP_ID and ADZUNA_APP_KEY environment variables required')

    params = {
        'app_id': app_id,
        'app_key': app_key,
        'results_per_page': 50,
        'what': keywords,
        'sort_by': 'date',
        'sort_direction': 'decreasing',
    }

    time.sleep(1)  # polite delay

    try:
        url = f"{ADZUNA_BASE}/{region}/search/{page}"
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        results = data.get('results', [])
        return [parse_adzuna_job(j, region) for j in results]
    except requests.exceptions.Timeout:
        raise RuntimeError("Adzuna API request timed out.")
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Adzuna network error: {e}")


# ─── Search profiles ──────────────────────────────────────────────────────────

ADZUNA_PROFILES = [
    {
        'name': 'Adzuna Nigeria — Dev',
        'region': 'ng',
        'keywords': 'software engineer developer',
    },
    {
        'name': 'Adzuna Nigeria — Data',
        'region': 'ng',
        'keywords': 'data scientist machine learning',
    },
    {
        'name': 'Adzuna Remote — Tech',
        'region': 'us',
        'keywords': 'remote developer software engineer',
    },
    {
        'name': 'Adzuna UK — Tech',
        'region': 'gb',
        'keywords': 'developer engineer',
    },
]


def get_adzuna_profile(name: str) -> dict | None:
    return next((p for p in ADZUNA_PROFILES if p['name'] == name), None)