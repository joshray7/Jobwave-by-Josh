"""
HotNigerianJobs Scraper
-------------------------
Scrapes Nigerian job listings (all sectors) from HotNigerianJobs.com — a second
Nigerian jobs source alongside MyJobMag for wider coverage.
Site: https://www.hotnigerianjobs.com
"""

import requests
from bs4 import BeautifulSoup
import hashlib
import re
import time
from datetime import datetime
from dateutil import parser as date_parser

HNJ_BASE = "https://www.hotnigerianjobs.com"

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml',
    'Accept-Language': 'en-US,en;q=0.9',
}

JOB_LINK_RE = re.compile(r'/hotjobs/\d+/[\w-]+\.html$')


def make_source_id(url: str) -> str:
    return hashlib.md5(f"hotnigerianjobs::{url}".encode()).hexdigest()


def infer_job_type(text: str) -> str:
    text = text.lower()
    if 'remote' in text:
        return 'remote'
    if 'part time' in text or 'part-time' in text:
        return 'part-time'
    if 'contract' in text:
        return 'contract'
    if 'intern' in text or 'nysc' in text or 'siwes' in text:
        return 'internship'
    return 'full-time'


def infer_experience(text: str) -> str:
    text = text.lower()
    if any(w in text for w in ['senior', 'head', 'lead', 'chief', 'manager', 'director']):
        return 'senior'
    if any(w in text for w in ['intern', 'graduate', 'entry', 'junior', 'trainee', 'nysc']):
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


def extract_location(text: str) -> str:
    match = re.search(r'located in\s+([^.]+?)\.', text, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    if 'remote' in text.lower():
        return 'Remote'
    return 'Nigeria'


def parse_date(text: str):
    try:
        cleaned = re.sub(r'^\w{3}\s+', '', text.strip())
        cleaned = re.sub(r'(\d+)(st|nd|rd|th)', r'\1', cleaned)
        return date_parser.parse(cleaned, fuzzy=True, default=datetime.utcnow())
    except Exception:
        return datetime.utcnow()


def parse_job_card(title_tag):
    """Given a job title <a> tag, extract the surrounding job card details."""
    try:
        href = title_tag.get('href', '')
        title = title_tag.get_text(strip=True)
        if not href or not title or title.lower() == 'apply now':
            return None

        container = title_tag.find_parent(['div', 'article']) or title_tag.parent

        description = ''
        posted_at = datetime.utcnow()

        if container:
            full_text = container.get_text(separator=' ', strip=True)
            date_match = re.search(
                r'Posted on\s+([A-Za-z]{3}\s+\d{1,2}\w{0,2}\s+[A-Za-z]+,?\s+\d{4})', full_text
            )
            if date_match:
                posted_at = parse_date(date_match.group(1))

            p_tag = container.find('p')
            description = p_tag.get_text(strip=True) if p_tag else full_text[:600]

        full_url = href if href.startswith('http') else f"{HNJ_BASE}{href}"
        combined_text = f"{title} {description}"

        company = 'Unknown'
        if ' is recruiting' in description:
            company = description.split(' is recruiting')[0].strip()

        return {
            'title': title,
            'company': company,
            'location': extract_location(description),
            'job_type': infer_job_type(combined_text),
            'experience': infer_experience(combined_text),
            'salary_min': None,
            'salary_max': None,
            'description': description[:3000] if description else None,
            'requirements': None,
            'source': 'HotNigerianJobs',
            'source_url': full_url,
            'source_id': make_source_id(full_url),
            'tags': extract_tags(combined_text),
            'posted_at': posted_at,
            'scraped_at': datetime.utcnow(),
        }
    except Exception:
        return None


def fetch_hotnigerianjobs_jobs(field_id: str = None, industry_id: str = None, num_pages: int = 1):
    """
    Scrape jobs from HotNigerianJobs (no official API — HTML scraping).

    Args:
        field_id:    Field category ID e.g. '243' (Marketing and Sales)
        industry_id: Industry category ID e.g. '127' (NGO)
        num_pages:   Number of pages to scrape

    Returns:
        List of job dicts ready for insertion into the Job model.
    """
    if field_id:
        base_path = f"/field/{field_id}/"
    elif industry_id:
        base_path = f"/industry/{industry_id}/"
    else:
        base_path = "/alljobs/0/"

    all_jobs = []

    for page in range(0, num_pages):
        url = f"{HNJ_BASE}{base_path}" if page == 0 else f"{HNJ_BASE}{base_path}{page}/"

        time.sleep(1.5)  # polite delay

        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            resp.raise_for_status()
        except requests.exceptions.Timeout:
            raise RuntimeError("HotNigerianJobs request timed out.")
        except requests.exceptions.RequestException as e:
            if page > 0:
                break  # later pages may not exist — stop quietly
            raise RuntimeError(f"HotNigerianJobs network error: {e}")

        soup = BeautifulSoup(resp.text, 'html.parser')
        title_links = soup.find_all('a', href=JOB_LINK_RE)
        seen_on_page = set()

        for tag in title_links:
            href = tag.get('href', '')
            text = tag.get_text(strip=True)
            if href in seen_on_page or text.lower() == 'apply now':
                continue
            seen_on_page.add(href)
            job = parse_job_card(tag)
            if job:
                all_jobs.append(job)

    return all_jobs


# ─── Search profiles ──────────────────────────────────────────────────────────

HOTNIGERIANJOBS_PROFILES = [
    {'name': 'HotNigerianJobs — Sales & Marketing', 'field_id': '243', 'num_pages': 1},
    {'name': 'HotNigerianJobs — Admin & Customer Service', 'field_id': '201', 'num_pages': 1},
    {'name': 'HotNigerianJobs — Finance', 'field_id': '229', 'num_pages': 1},
    {'name': 'HotNigerianJobs — Engineering', 'field_id': '274', 'num_pages': 1},
    {'name': 'HotNigerianJobs — NGO Sector', 'industry_id': '127', 'num_pages': 1},
]


def get_hotnigerianjobs_profile(name: str):
    return next((p for p in HOTNIGERIANJOBS_PROFILES if p['name'] == name), None)