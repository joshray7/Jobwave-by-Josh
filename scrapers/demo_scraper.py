"""
Demo scraper — generates realistic job listings for the platform.
In production, replace these functions with actual BeautifulSoup scrapers
targeting public job boards (always respect robots.txt and ToS).
"""

import random
from datetime import datetime, timedelta
import hashlib

TITLES = [
    'Senior Backend Engineer', 'Frontend Developer', 'Full Stack Engineer',
    'Data Scientist', 'Machine Learning Engineer', 'DevOps Engineer',
    'Product Manager', 'UI/UX Designer', 'Android Developer', 'iOS Developer',
    'Cloud Architect', 'Security Engineer', 'QA Engineer', 'React Developer',
    'Python Developer', 'Node.js Developer', 'Data Analyst', 'AI Engineer',
    'Software Engineer II', 'Engineering Manager', 'Technical Lead',
    'Site Reliability Engineer', 'Database Administrator', 'Systems Analyst',
]

COMPANIES = [
    'Paystack', 'Flutterwave', 'Andela', 'Interswitch', 'PiggyVest',
    'Cowrywise', 'Konga', 'Jumia', 'Terragon Group', 'SystemSpecs',
    'Softcom', 'Eden Life', 'Mono', 'Bankly', 'Carbon', 'FairMoney',
    'Chipper Cash', 'Wave', 'Moniepoint', 'OPay',
    'Google', 'Microsoft', 'Amazon', 'Meta', 'Stripe',
    'Shopify', 'Atlassian', 'Cloudflare', 'Vercel', 'Supabase',
]

LOCATIONS = [
    'Lagos, Nigeria', 'Abuja, Nigeria', 'Port Harcourt, Nigeria',
    'Remote', 'Remote (Africa)', 'Hybrid – Lagos',
    'San Francisco, CA', 'New York, NY', 'London, UK',
    'Nairobi, Kenya', 'Cape Town, South Africa',
]

JOB_TYPES = ['full-time', 'part-time', 'remote', 'contract', 'internship']
EXPERIENCES = ['entry', 'mid', 'senior', 'lead']

DESCRIPTIONS = [
    """We're looking for a talented engineer to join our growing team. You'll work on
    challenging problems that impact millions of users across Africa and beyond.
    Our stack is modern and our team is collaborative. You'll have ownership over
    meaningful features from day one and will be expected to contribute to architecture
    decisions as the product evolves.""",

    """As part of our engineering team, you will design, build, and maintain efficient,
    reusable, and reliable code. You will collaborate with cross-functional teams to
    define, design, and ship new features. You will identify and correct bottlenecks
    and fix bugs, and help maintain code quality, organization, and automatization.""",

    """We are seeking an experienced professional to help scale our infrastructure
    and drive our technical roadmap. You will mentor junior engineers, conduct
    code reviews, and ensure engineering best practices are followed. This role
    offers a unique opportunity to shape the technology foundation of a fast-growing company.""",
]

REQUIREMENTS_LIST = [
    "3+ years of professional experience\nStrong communication skills\nBS/MS in Computer Science or related field\nExperience with agile methodologies\nAbility to work independently",
    "Proficiency in relevant technologies\nExperience with cloud platforms (AWS/GCP/Azure)\nStrong problem-solving skills\nContributions to open source (a plus)\nComfort in a fast-paced startup environment",
    "Solid understanding of data structures and algorithms\nExperience with CI/CD pipelines\nKnowledge of security best practices\nStrong English communication skills\nPassion for building great products",
]

TAGS_POOL = [
    'python', 'javascript', 'react', 'nodejs', 'typescript', 'aws', 'docker',
    'kubernetes', 'postgresql', 'mongodb', 'redis', 'graphql', 'rest api',
    'machine learning', 'data engineering', 'fintech', 'agile', 'devops',
    'flutter', 'android', 'ios', 'vue', 'django', 'fastapi', 'golang',
]


def make_source_id(source, title, company):
    raw = f"{source}::{title}::{company}"
    return hashlib.md5(raw.encode()).hexdigest()


def scrape_demo_jobs(source_name: str, count: int = 12) -> list[dict]:
    """Generate realistic demo job listings for the given source."""
    jobs = []
    random.seed(hash(source_name) % 1000)  # deterministic per source

    for i in range(count):
        title = random.choice(TITLES)
        company = random.choice(COMPANIES)
        location = random.choice(LOCATIONS)
        job_type = random.choice(JOB_TYPES)
        experience = random.choice(EXPERIENCES)

        salary_base = {'entry': 60, 'mid': 100, 'senior': 150, 'lead': 200}[experience]
        salary_min = salary_base * 1000 + random.randint(0, 20) * 1000
        salary_max = salary_min + random.randint(20, 60) * 1000

        tags = random.sample(TAGS_POOL, random.randint(3, 7))

        days_ago = random.randint(0, 30)
        posted = datetime.utcnow() - timedelta(days=days_ago, hours=random.randint(0, 23))

        source_id = make_source_id(source_name, title, company)

        jobs.append({
            'title': title,
            'company': company,
            'location': location,
            'job_type': job_type,
            'experience': experience,
            'salary_min': salary_min,
            'salary_max': salary_max,
            'description': random.choice(DESCRIPTIONS),
            'requirements': random.choice(REQUIREMENTS_LIST),
            'source': source_name,
            'source_url': f'https://example.com/jobs/{source_id[:8]}',
            'source_id': source_id,
            'tags': ','.join(tags),
            'posted_at': posted,
            'scraped_at': datetime.utcnow(),
        })

    return jobs


# ─── Real scraper template (use with caution, respect ToS) ─────────────────────

def scrape_with_requests(url: str, selectors: dict) -> list[dict]:
    """
    Template for a real BeautifulSoup scraper.
    Always check robots.txt before scraping any site.
    
    Example usage:
        jobs = scrape_with_requests(
            'https://example-job-board.com/jobs',
            {
                'job_card': '.job-listing',
                'title': '.job-title',
                'company': '.company-name',
                'location': '.location',
            }
        )
    """
    try:
        import requests
        from bs4 import BeautifulSoup
        import time

        headers = {'User-Agent': 'Mozilla/5.0 (JobWave Aggregator; contact@yoursite.com)'}
        time.sleep(2)  # Polite delay — never hammer a server

        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')
        jobs = []

        for card in soup.select(selectors.get('job_card', '.job')):
            title_el = card.select_one(selectors.get('title', '.title'))
            company_el = card.select_one(selectors.get('company', '.company'))
            location_el = card.select_one(selectors.get('location', '.location'))
            link_el = card.select_one('a')

            if not title_el:
                continue

            title = title_el.get_text(strip=True)
            company = company_el.get_text(strip=True) if company_el else 'Unknown'
            location = location_el.get_text(strip=True) if location_el else ''
            source_url = link_el['href'] if link_el and link_el.get('href') else url

            jobs.append({
                'title': title,
                'company': company,
                'location': location,
                'source_url': source_url,
                'source_id': make_source_id(url, title, company),
                'scraped_at': datetime.utcnow(),
            })

        return jobs

    except Exception as e:
        raise RuntimeError(f'Scraping failed for {url}: {e}')