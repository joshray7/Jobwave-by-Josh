"""
Remotive API Scraper
---------------------
Fetches remote tech jobs from Remotive — completely free, no API key needed.
Docs: https://remotive.com/api/remote-jobs

Categories available:
  software-dev, design, marketing, sales, product, customer-support,
  devops, finance, data, hr, qa, writing, all
"""

import requests
import hashlib
from datetime import datetime
import time

REMOTIVE_BASE = "https://remotive.com/api/remote-jobs"


def make_source_id(job_id) -> str:
    return hashlib.md5(f"remotive::{job_id}".encode()).hexdigest()


def infer_experience(title: str, desc: str) -> str:
    text = (title + ' ' + (desc or '')).lower()
    if any(w in text for w in ['senior', 'sr.', 'lead', 'principal', 'staff', 'head of']):
        return 'senior'
    if any(w in text for w in ['junior', 'entry', 'graduate', 'intern', 'fresher']):
        return 'entry'
    if any(w in text for w in ['manager', 'director', 'vp ', 'vice president']):
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


def parse_remotive_job(item: dict) -> dict:
    title = item.get('title', '')
    company = item.get('company_name', 'Unknown')
    description = item.get('description', '')
    category = item.get('category', '')
    job_type_raw = item.get('job_type', 'full_time')

    job_type_map = {
        'full_time': 'full-time',
        'part_time': 'part-time',
        'contract': 'contract',
        'freelance': 'contract',
        'internship': 'internship',
    }
    job_type = job_type_map.get(job_type_raw, 'remote')

    # Salary — Remotive provides a string like "$80k - $120k"
    salary_str = item.get('salary', '') or ''
    salary_min = None
    salary_max = None
    if salary_str:
        import re
        nums = re.findall(r'\d+(?:,\d+)?(?:k)?', salary_str.lower())
        parsed = []
        for n in nums:
            n = n.replace(',', '')
            if n.endswith('k'):
                parsed.append(int(n[:-1]) * 1000)
            elif len(n) <= 3:
                parsed.append(int(n) * 1000)
            else:
                parsed.append(int(n))
        if len(parsed) >= 2:
            salary_min, salary_max = parsed[0], parsed[1]
        elif len(parsed) == 1:
            salary_min = parsed[0]
            salary_max = int(parsed[0] * 1.3)

    posted_str = item.get('publication_date', '')
    try:
        posted_at = datetime.fromisoformat(posted_str.replace('Z', '+00:00')).replace(tzinfo=None)
    except Exception:
        posted_at = datetime.utcnow()

    job_id = str(item.get('id', ''))
    apply_link = item.get('url', '')
    logo = item.get('company_logo', '')

    return {
        'title': title,
        'company': company,
        'location': 'Remote',
        'job_type': 'remote',
        'experience': infer_experience(title, description),
        'salary_min': salary_min,
        'salary_max': salary_max,
        'description': description[:3000] if description else None,
        'requirements': None,
        'source': 'Remotive',
        'source_url': apply_link,
        'source_id': make_source_id(job_id),
        'tags': extract_tags(title, description),
        'posted_at': posted_at,
        'scraped_at': datetime.utcnow(),
    }


def fetch_remotive_jobs(
    category: str = 'software-dev',
    limit: int = 20,
    search: str = '',
) -> list[dict]:
    """
    Fetch remote jobs from Remotive API (no key needed).

    Args:
        category: Job category (software-dev, design, devops, data, qa, etc.)
        limit:    Max jobs to return
        search:   Optional keyword filter

    Returns:
        List of job dicts ready for insertion into the Job model.
    """
    params = {'limit': limit}
    if category and category != 'all':
        params['category'] = category
    if search:
        params['search'] = search

    time.sleep(1)  # polite delay

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'en-US,en;q=0.9',
        'Referer': 'https://remotive.com/',
        'Origin': 'https://remotive.com',
    }

    try:
        resp = requests.get(REMOTIVE_BASE, params=params, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        jobs = data.get('jobs', [])
        return [parse_remotive_job(j) for j in jobs]
    except requests.exceptions.Timeout:
        raise RuntimeError("Remotive API request timed out.")
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Remotive network error: {e}")


# ─── Search profiles ──────────────────────────────────────────────────────────

REMOTIVE_PROFILES = [
    {
        'name': 'Remote Dev Jobs',
        'category': 'software-dev',
        'limit': 20,
        'search': '',
    },
    {
        'name': 'Remote DevOps & Cloud',
        'category': 'devops',
        'limit': 20,
        'search': '',
    },
    {
        'name': 'Remote Data & AI',
        'category': 'data',
        'limit': 20,
        'search': '',
    },
    {
        'name': 'Remote Design Jobs',
        'category': 'design',
        'limit': 20,
        'search': '',
    },
    {
        'name': 'Remote Marketing Jobs',
        'category': 'marketing',
        'limit': 20,
        'search': '',
    },
    {
        'name': 'Remote Product Jobs',
        'category': 'product',
        'limit': 20,
        'search': '',
    },
    {
        'name': 'Remote QA & Testing',
        'category': 'qa',
        'limit': 20,
        'search': '',
    },  
]


def get_remotive_profile(name: str) -> dict | None:
    return next((p for p in REMOTIVE_PROFILES if p['name'] == name), None)