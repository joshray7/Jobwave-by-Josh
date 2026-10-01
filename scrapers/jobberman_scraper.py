"""
Jobberman Scraper
-------------------
Scrapes Nigerian job listings from Jobberman — Nigeria's #1 job site.
No public API, HTML scraping. Includes Naira salary ranges when available.
Site: https://www.jobberman.com
"""

import requests
from bs4 import BeautifulSoup
import hashlib
import re
import time
from datetime import datetime, timedelta

JOBBERMAN_BASE = "https://www.jobberman.com"

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml',
    'Accept-Language': 'en-US,en;q=0.9',
}

JOB_LINK_RE = re.compile(r'/listings/[\w-]+$')

WORK_TYPES = ['Full Time', 'Part Time', 'Contract', 'Internship & Graduate']
CATEGORY_LIST = [
    'Accounting, Auditing & Finance', 'Admin & Office', 'Creative & Design',
    'Building & Architecture', 'Consulting & Strategy', 'Customer Service & Support',
    'Engineering & Technology', 'Farming & Agriculture', 'Food Services & Catering',
    'Hospitality & Leisure', 'Software & Data', 'Legal Services',
    'Marketing & Communications', 'Medical & Pharmaceutical',
    'Product & Project Management', 'Estate Agents & Property Management',
    'Quality Control & Assurance', 'Human Resources', 'Management & Business Development',
    'Community & Social Services', 'Supply Chain & Procurement', 'Sales',
    'Research, Teaching & Training', 'Trades & Services', 'Driver & Transport Services',
    'Health & Safety', 'Insurance & Risk Management', 'Telecoms & Networking', 'Media, Arts & Entertainment',
    'Science & Laboratory', 'Security Services', 'Retail & Consumer Goods',
    'Banking & Investment', 'Manufacturing & Production', 'Real Estate & Property Development',
    'Non-Profit & NGO', 
]


def make_source_id(url: str) -> str:
    return hashlib.md5(f"jobberman::{url}".encode()).hexdigest()


def infer_job_type(work_type_text: str) -> str:
    text = (work_type_text or '').lower()
    if 'part time' in text:
        return 'part-time'
    if 'contract' in text:
        return 'contract'
    if 'internship' in text or 'graduate' in text:
        return 'internship'
    if 'remote' in text:
        return 'remote'
    return 'full-time'


def infer_experience(text: str) -> str:
    text = text.lower()
    if any(w in text for w in ['senior', 'head', 'lead', 'chief', 'manager', 'director', 'executive level']):
        return 'senior'
    if any(w in text for w in ['intern', 'graduate', 'entry', 'junior', 'trainee', 'no experience']):
        return 'entry'
    return 'mid'


def extract_tags(text: str) -> str:
    keywords = [
        'sales', 'marketing', 'accounting', 'finance', 'engineering', 'logistics',
        'customer service', 'hr', 'human resources', 'admin', 'teaching',
        'healthcare', 'medical', 'legal', 'procurement', 'ict', 'software',
        'construction', 'oil and gas', 'ngo', 'hospitality', 'retail', 'security',
        'driving', 'agriculture', 'banking', 'insurance', 'manufacturing', 'telecom', 
        'media', 'entertainment', 'research', 'consulting', 'real estate',
    ]
    text = text.lower()
    found = [k for k in keywords if k in text]
    return ','.join(found[:6])


def parse_posted_date(text: str):
    text = text.strip().lower()
    now = datetime.utcnow()
    if text == 'today':
        return now
    if text == 'yesterday':
        return now - timedelta(days=1)
    match = re.match(r'(\d+)\s+days?\s+ago', text)
    if match:
        return now - timedelta(days=int(match.group(1)))
    match = re.match(r'(\d+)\s+weeks?\s+ago', text)
    if match:
        return now - timedelta(weeks=int(match.group(1)))
    match = re.match(r'(\d+)\s+months?\s+ago', text)
    if match:
        return now - timedelta(days=int(match.group(1)) * 30)
    return now


def find_card_container(title_tag, max_levels=8, max_strings=40):
    """Climb from the title link to the largest ancestor that still holds
    exactly one distinct job link. That ancestor is the full job card."""
    best = None
    node = title_tag.parent
    levels = 0
    while node is not None and node.name not in ('body', 'html', '[document]') and levels < max_levels:
        hrefs = {a.get('href') for a in node.find_all('a', href=JOB_LINK_RE)}
        if len(hrefs) > 1:
            break  # went too far, now containing multiple jobs
        if sum(1 for _ in node.stripped_strings) > max_strings:
            break  # safety cap, e.g. a page with only one job
        best = node
        node = node.parent
        levels += 1
    return best


def parse_job_card(title_tag):
    """Given a job title <a> tag, extract the surrounding job card details."""
    try:
        href = title_tag.get('href', '')
        title = title_tag.get_text(strip=True)
        if not href or not title:
            return None

        container = find_card_container(title_tag)
        if not container:
            return None

        junk = {'FEATURED', 'Popular', 'Easy apply', title}
        strings = [s.strip() for s in container.stripped_strings if s.strip()]
        strings = [s for s in strings if s not in junk and len(s) > 1]

        # Card order: company, "location worktype salary", category, time ago, description
        company = strings[0] if strings else 'Unknown'

        loc_line, work_type_match, location_text = '', '', ''
        for i, s in enumerate(strings[1:], start=1):  # skip index 0: that's the company
            wt = next((w for w in WORK_TYPES if w in s), '')
            if not wt:
                continue
            work_type_match = wt
            if s == wt:
                # work type is its own string -> the city is the string before it
                loc_line = strings[i - 1]
                location_text = loc_line
            else:
                # combined line like "Lagos Full Time" -> keep the old behaviour
                loc_line = s
                location_text = s.split(wt)[0].strip()
            break

        category_match = next((s for s in strings if s in CATEGORY_LIST), '')

        full_text = ' '.join(strings)
        date_match = re.search(
            r'\b(Today|Yesterday|\d+\s+days?\s+ago|\d+\s+weeks?\s+ago|\d+\s+months?\s+ago)\b',
            full_text,
        )
        posted_at = parse_posted_date(date_match.group(1)) if date_match else datetime.utcnow()

        location = location_text if location_text and location_text != company else 'Nigeria'
        if 'remote' in location_text.lower():
            location = 'Remote'

        candidates = [
            s for s in strings
            if s not in (company, loc_line, category_match)
            and not re.fullmatch(r'(Today|Yesterday|\d+\s+\w+\s+ago)', s)
        ]
        description = max(candidates, key=len) if candidates else ''
        if len(description) < 30:
            description = ''

        full_url = href if href.startswith('http') else f"{JOBBERMAN_BASE}{href}"
        combined_text = f"{title} {description} {category_match}"

        return {
            'title': title,
            'company': company,
            'location': location,
            'job_type': infer_job_type(work_type_match),
            'experience': infer_experience(combined_text),
            'salary_min': None,
            'salary_max': None,
            'description': description[:3000] if description else None,
            'requirements': None,
            'source': 'Jobberman',
            'source_url': full_url,
            'source_id': make_source_id(full_url),
            'tags': extract_tags(combined_text) or category_match.lower(),
            'posted_at': posted_at,
            'scraped_at': datetime.utcnow(),
        }
    except Exception:
        return None


def fetch_jobberman_jobs(category_path: str = None, num_pages: int = 1):
    """
    Scrape jobs from Jobberman (no official API — HTML scraping).

    Args:
        category_path: URL path segment e.g. 'sales', 'admin-office',
                        'engineering-technology', 'marketing-communications'.
                        None = all jobs.
        num_pages:      Number of pages to scrape (16 jobs per page)

    Returns:
        List of job dicts ready for insertion into the Job model.
    """
    base_path = f"/jobs/{category_path}" if category_path else "/jobs"
    all_jobs = []

    for page in range(1, num_pages + 1):
        url = base_path if page == 1 else f"{base_path}?page={page}"

        time.sleep(1.5)  # polite delay

        try:
            resp = requests.get(f"{JOBBERMAN_BASE}{url}" if url.startswith('/') else url,
                                 headers=HEADERS, timeout=15)
            resp.raise_for_status()
        except requests.exceptions.Timeout:
            raise RuntimeError("Jobberman request timed out.")
        except requests.exceptions.RequestException as e:
            if page > 1:
                break
            raise RuntimeError(f"Jobberman network error: {e}")

        soup = BeautifulSoup(resp.text, 'html.parser')
        title_links = soup.find_all('a', href=JOB_LINK_RE)
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

JOBBERMAN_PROFILES = [
    {'name': 'Jobberman — Sales', 'category_path': 'sales', 'num_pages': 1},
    {'name': 'Jobberman — Admin & Office', 'category_path': 'admin-office', 'num_pages': 1},
    {'name': 'Jobberman — Engineering', 'category_path': 'engineering', 'num_pages': 1},
    {'name': 'Jobberman — Customer Service', 'category_path': 'customer-service-support', 'num_pages': 1},
    {'name': 'Jobberman — Marketing & Comms', 'category_path': 'marketing-communications', 'num_pages': 1},
    {'name': 'Jobberman — Healthcare & Medical', 'category_path': 'medical-pharmaceutical', 'num_pages': 1},
    {'name': 'Jobberman — Teaching & Education', 'category_path': 'research-teaching-training', 'num_pages': 1},
    {'name': 'Jobberman — Finance & Accounting', 'category_path': 'accounting-auditing-finance', 'num_pages': 1},
    {'name': 'Jobberman — ICT & Software', 'category_path': 'software-data', 'num_pages': 1},
]


def get_jobberman_profile(name: str):
    return next((p for p in JOBBERMAN_PROFILES if p['name'] == name), None)