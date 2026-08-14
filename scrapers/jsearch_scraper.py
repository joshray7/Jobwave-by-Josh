"""
JSearch API Scraper (via RapidAPI)
-----------------------------------
JSearch aggregates real jobs from Indeed, LinkedIn, Glassdoor, and more.

Get your free API key at:
  https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch

Free tier: 200 requests/month
Set your key as environment variable: JSEARCH_API_KEY=your_key_here
"""

import requests
import hashlib
import os
from datetime import datetime

JSEARCH_HOST = "jsearch.p.rapidapi.com"
JSEARCH_BASE = "https://jsearch.p.rapidapi.com"

# ─── Helpers ──────────────────────────────────────────────────────────────────

def make_source_id(job_id: str) -> str:
    return hashlib.md5(f"jsearch::{job_id}".encode()).hexdigest()


def map_employment_type(raw: str) -> str:
    raw = (raw or '').upper()
    mapping = {
        'FULLTIME': 'full-time',
        'FULL_TIME': 'full-time',
        'PARTTIME': 'part-time',
        'PART_TIME': 'part-time',
        'CONTRACTOR': 'contract',
        'CONTRACT': 'contract',
        'INTERN': 'internship',
        'INTERNSHIP': 'internship',
        'TEMPORARY': 'contract',
    }
    return mapping.get(raw, 'full-time')


def infer_experience(title: str, desc: str) -> str:
    text = (title + ' ' + (desc or '')).lower()
    if any(w in text for w in ['senior', 'sr.', 'lead', 'principal', 'staff', 'head of']):
        return 'senior'
    if any(w in text for w in ['junior', 'entry', 'graduate', 'intern', 'fresher', '0-1', '0-2']):
        return 'entry'
    if any(w in text for w in ['manager', 'director', 'vp ', 'vice president']):
        return 'lead'
    return 'mid'


def extract_tags(title: str, desc: str) -> str:
    keywords = [
        'python', 'javascript', 'typescript', 'react', 'node', 'nodejs', 'vue',
        'angular', 'java', 'kotlin', 'swift', 'flutter', 'dart', 'go', 'golang',
        'rust', 'c++', 'c#', '.net', 'php', 'ruby', 'rails', 'django', 'fastapi',
        'flask', 'aws', 'azure', 'gcp', 'docker', 'kubernetes', 'terraform',
        'postgresql', 'mysql', 'mongodb', 'redis', 'elasticsearch', 'graphql',
        'rest', 'api', 'machine learning', 'ai', 'data science', 'sql',
        'devops', 'ci/cd', 'agile', 'scrum', 'figma', 'ux', 'product',
    ]
    text = (title + ' ' + (desc or '')[:1000]).lower()
    found = [k for k in keywords if k in text]
    return ','.join(found[:8])


def parse_job(item: dict) -> dict:
    """Convert a raw JSearch API item into our Job model dict."""
    title = item.get('job_title', '')
    company = item.get('employer_name', 'Unknown')
    city = item.get('job_city', '')
    state = item.get('job_state', '')
    country = item.get('job_country', '')
    location_parts = [p for p in [city, state, country] if p]
    location = ', '.join(location_parts) if location_parts else 'Remote'

    is_remote = item.get('job_is_remote', False)
    if is_remote and 'remote' not in location.lower():
        location = 'Remote' if not city else f'{city} (Remote)'

    description = item.get('job_description', '')
    emp_type = map_employment_type(item.get('job_employment_type', ''))
    experience = infer_experience(title, description)

    # Salary — JSearch provides min/max in yearly
    salary_min = item.get('job_min_salary')
    salary_max = item.get('job_max_salary')
    salary_period = item.get('job_salary_period', '')
    # Normalize hourly → yearly
    if salary_period and 'hour' in salary_period.lower():
        if salary_min: salary_min = int(salary_min * 2080)
        if salary_max: salary_max = int(salary_max * 2080)

    # Posted date
    posted_ts = item.get('job_posted_at_timestamp')
    posted_at = datetime.utcfromtimestamp(posted_ts) if posted_ts else datetime.utcnow()

    job_id = item.get('job_id', '')
    apply_link = item.get('job_apply_link', '')

    return {
        'title': title,
        'company': company,
        'location': location,
        'job_type': emp_type,
        'experience': experience,
        'salary_min': int(salary_min) if salary_min else None,
        'salary_max': int(salary_max) if salary_max else None,
        'description': description[:3000] if description else None,
        'requirements': None,   # JSearch bundles reqs into description
        'source': 'JSearch',
        'source_url': apply_link,
        'source_id': make_source_id(job_id),
        'tags': extract_tags(title, description),
        'posted_at': posted_at,
        'scraped_at': datetime.utcnow(),
    }


# ─── Main fetch function ───────────────────────────────────────────────────────

def fetch_jsearch_jobs(
    query: str = 'software engineer',
    location: str = '',
    num_pages: int = 1,
    date_posted: str = 'week',   # all | today | 3days | week | month
    remote_only: bool = False,
    api_key: str = None,
) -> list[dict]:
    """
    Fetch real jobs from JSearch API.

    Args:
        query:       Search query (e.g. "Python developer Nigeria")
        location:    Location filter (e.g. "Lagos" or "Remote")
        num_pages:   Pages to fetch (10 results per page, max 5 recommended)
        date_posted: Freshness filter
        remote_only: Only return remote jobs
        api_key:     RapidAPI key (falls back to JSEARCH_API_KEY env var)

    Returns:
        List of job dicts ready for insertion into the Job model.

    Raises:
        ValueError: If no API key is configured.
        RuntimeError: On API errors.
    """
    key = api_key or os.environ.get('JSEARCH_API_KEY', '')
    if not key:
        raise ValueError(
            "No JSearch API key found. Set the JSEARCH_API_KEY environment variable "
            "or pass api_key= to this function. "
            "Get a free key at https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch"
        )

    headers = {
        "X-RapidAPI-Key": key,
        "X-RapidAPI-Host": JSEARCH_HOST,
    }

    all_jobs = []

    for page in range(1, num_pages + 1):
        params = {
            "query": f"{query} {location}".strip(),
            "page": str(page),
            "num_pages": "1",
            "date_posted": date_posted,
        }
        if remote_only:
            params["remote_jobs_only"] = "true"

        try:
            resp = requests.get(
                f"{JSEARCH_BASE}/search",
                headers=headers,
                params=params,
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()

            if data.get('status') != 'OK':
                raise RuntimeError(f"JSearch API error: {data.get('message', 'Unknown error')}")

            items = data.get('data', [])
            for item in items:
                try:
                    all_jobs.append(parse_job(item))
                except Exception:
                    continue   # skip malformed entries silently

        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response else 0
            if status == 429:
                raise RuntimeError("JSearch rate limit hit. You've exceeded your monthly quota.")
            elif status == 401 or status == 403:
                raise RuntimeError("Invalid JSearch API key. Check your JSEARCH_API_KEY.")
            else:
                raise RuntimeError(f"JSearch HTTP error {status}: {e}")
        except requests.exceptions.Timeout:
            raise RuntimeError("JSearch API request timed out.")
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"JSearch network error: {e}")

    return all_jobs


# ─── Preset search profiles ────────────────────────────────────────────────────
# These are the searches shown in the Admin panel scraper control.

SEARCH_PROFILES = [
    {
        'name': 'Tech Jobs Nigeria',
        'query': 'software engineer developer Nigeria',
        'location': '',
        'num_pages': 1,
        'date_posted': 'month',
    },
    {
        'name': 'Remote Tech (Africa)',
        'query': 'software developer remote Africa',
        'location': '',
        'remote_only': True,
        'num_pages': 1,
        'date_posted': 'month',
    },
    {
        'name': 'Product & Design',
        'query': 'product manager UI UX designer',
        'location': '',
        'num_pages': 2,
        'date_posted': 'month',
    },
    {
        'name': 'Frontend & Mobile',
        'query': 'frontend developer mobile app react native flutter',
        'location': '',
        'num_pages': 1,
        'date_posted': 'month',
    },
    {
        'name': 'Backend & DevOps',
        'query': 'backend developer devops cloud engineer',
        'location': '',
        'num_pages': 1,
        'date_posted': 'month',
    },
    {
        'name': 'AI & Machine Learning',
        'query': 'Data Scientist Machine learning engineer LLM generative AI',
        'location': '',
        'num_pages': 1,
        'date_posted': 'month',
    },

]


def get_profile(name: str) -> dict | None:
    return next((p for p in SEARCH_PROFILES if p['name'] == name), None)