"""
MyJobMag Scraper
-----------------
Scrapes Nigerian job listings (all sectors — tech and non-tech) from MyJobMag.
No public API exists, so this parses their HTML pages directly.
Site: https://www.myjobmag.com
"""

import requests
from bs4 import BeautifulSoup
import hashlib
import re
import time
from datetime import datetime
from dateutil import parser as date_parser

MYJOBMAG_BASE = "https://www.myjobmag.com"

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml',
    'Accept-Language': 'en-US,en;q=0.9',
}


def make_source_id(url: str) -> str:
    return hashlib.md5(f"myjobmag::{url}".encode()).hexdigest()


def infer_job_type(text: str) -> str:
    text = text.lower()
    if 'remote' in text:
        return 'remote'
    if 'part time' in text or 'part-time' in text:
        return 'part-time'
    if 'contract' in text:
        return 'contract'
    if 'intern' in text:
        return 'internship'
    return 'full-time'


def infer_experience(text: str) -> str:
    text = text.lower()
    if any(w in text for w in ['senior', 'head', 'lead', 'chief', 'manager', 'director']):
        return 'senior'
    if any(w in text for w in ['intern', 'graduate', 'entry', 'junior', 'trainee']):
        return 'entry'
    return 'mid'


def extract_tags(text: str) -> str:
    keywords = [
        'sales', 'marketing', 'accounting', 'finance', 'engineering', 'logistics',
        'customer service', 'hr', 'human resources', 'admin', 'teaching',
        'healthcare', 'medical', 'legal', 'procurement', 'ict', 'software',
        'construction', 'oil and gas', 'ngo', 'hospitality', 'retail', 'security',
        'driving', 'agriculture', 'banking', 'insurance', 'manufacturing',
    ]
    text = text.lower()
    found = [k for k in keywords if k in text]
    return ','.join(found[:6])


def parse_date(text: str):
    try:
        return date_parser.parse(text, fuzzy=True, default=datetime.utcnow())
    except Exception:
        return datetime.utcnow()


def parse_job_card(title_tag):
    """Given a job title <a> tag, extract the surrounding job card details."""
    try:
        href = title_tag.get('href', '')
        if not href or '/job/' not in href:
            return None
        title_full = title_tag.get_text(strip=True)
        if not title_full:
            return None

        container = title_tag.find_parent('li') or title_tag.find_parent('div') or title_tag.parent

        company = 'Unknown'
        if container:
            company_link = container.find('a', href=re.compile(r'/jobs-at/'))
            if company_link:
                company = company_link.get_text(strip=True) or company

        if company == 'Unknown' and ' at ' in title_full:
            title_part, company_part = title_full.rsplit(' at ', 1)
            title = title_part.strip()
            company = company_part.strip()
        else:
            title = title_full

        description = ''
        if container:
            desc_tag = container.find('p')
            if desc_tag:
                description = desc_tag.get_text(strip=True)

        posted_at = datetime.utcnow()
        if container:
            text_blocks = container.get_text(separator='|', strip=True).split('|')
            for block in reversed(text_blocks):
                if re.match(r'^\d{1,2}\s+[A-Za-z]+$', block.strip()):
                    posted_at = parse_date(block.strip())
                    break

        full_url = href if href.startswith('http') else f"{MYJOBMAG_BASE}{href}"
        combined_text = f"{title} {description}"

        return {
            'title': title,
            'company': company,
            'location': 'Nigeria',
            'job_type': infer_job_type(combined_text),
            'experience': infer_experience(combined_text),
            'salary_min': None,
            'salary_max': None,
            'description': description[:3000] if description else None,
            'requirements': None,
            'source': 'MyJobMag',
            'source_url': full_url,
            'source_id': make_source_id(full_url),
            'tags': extract_tags(combined_text),
            'posted_at': posted_at,
            'scraped_at': datetime.utcnow(),
        }
    except Exception:
        return None


def fetch_myjobmag_jobs(category: str = None, location: str = None, num_pages: int = 1):
    """
    Scrape jobs from MyJobMag (no official API — HTML scraping).

    Args:
        category:   Field slug e.g. 'sales-marketing', 'engineering', 'accounting-audit'
        location:   State slug e.g. 'lagos', 'abuja'
        num_pages:  Number of pages to scrape

    Returns:
        List of job dicts ready for insertion into the Job model.
    """
    if category:
        base_path = f"/jobs-by-field/{category}"
    elif location:
        base_path = f"/jobs-location/{location}"
    else:
        base_path = ""

    all_jobs = []

    for page in range(1, num_pages + 1):
        if page == 1:
            url = f"{MYJOBMAG_BASE}{base_path}" if base_path else MYJOBMAG_BASE
        else:
            url = f"{MYJOBMAG_BASE}{base_path}/page/{page}" if base_path else f"{MYJOBMAG_BASE}/page/{page}"

        time.sleep(1.5)  # polite delay

        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            resp.raise_for_status()
        except requests.exceptions.Timeout:
            raise RuntimeError("MyJobMag request timed out.")
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"MyJobMag network error: {e}")

        soup = BeautifulSoup(resp.text, 'html.parser')
        title_links = soup.find_all('a', href=re.compile(r'^/job/[\w-]'))
        seen_on_page = set()

        for tag in title_links:
            href = tag.get('href', '')
            if href in seen_on_page:
                continue
            seen_on_page.add(href)
            job = parse_job_card(tag)
            if job:
                all_jobs.append(job)

    return all_jobs


# ─── Search profiles ──────────────────────────────────────────────────────────

MYJOBMAG_PROFILES = [
    {'name': 'MyJobMag — Sales & Marketing', 'category': 'sales-marketing', 'num_pages': 1},
    {'name': 'MyJobMag — Admin & Customer Care', 'category': 'administration', 'num_pages': 1},
    {'name': 'MyJobMag — Finance & Accounting', 'category': 'accounting-audit', 'num_pages': 1},
    {'name': 'MyJobMag — Engineering & Technical', 'category': 'engineering', 'num_pages': 1},
    {'name': 'MyJobMag — ICT & Software', 'category': 'ict-software', 'num_pages': 1},
    {'name': 'MyJobMag — Health & Medical', 'category': 'health-medical', 'num_pages': 1},
    {'name': 'MyJobMag — NGO & Development', 'category': 'ngo-development', 'num_pages': 1},
    {'name': 'MyJobMag — Teaching & Education', 'category': 'teaching-education', 'num_pages': 1},
]


def get_myjobmag_profile(name: str):
    return next((p for p in MYJOBMAG_PROFILES if p['name'] == name), None)