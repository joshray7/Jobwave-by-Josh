"""
JobWave — Job Data Quality
----------------------------
Normalization and validation applied to every scraped job before it's
inserted into the database. Pure functions, no DB/Flask dependency,
so they're independently testable.
"""

import re

NIGERIAN_STATES = [
    'Lagos', 'Abuja', 'FCT', 'Kano', 'Rivers', 'Oyo', 'Kaduna', 'Ogun',
    'Enugu', 'Delta', 'Edo', 'Kwara', 'Katsina', 'Imo', 'Plateau',
    'Anambra', 'Osun', 'Ondo', 'Niger', 'Cross River', 'Akwa Ibom',
    'Bayelsa', 'Benue', 'Borno', 'Ebonyi', 'Ekiti', 'Gombe', 'Jigawa',
    'Kebbi', 'Kogi', 'Nasarawa', 'Sokoto', 'Taraba', 'Yobe', 'Zamfara',
    'Bauchi', 'Adamawa',
]

# High-confidence markers that a location string was garbled by
# mistranslation/misattribution upstream (e.g. Google/JSearch indexing bugs).
FOREIGN_LOCATION_GARBAGE_MARKERS = [
    'estado de', 'état de', 'staat', 'provincia di', 'prowincja',
]

BOILERPLATE_SENTENCE_MARKERS = [
    'never miss a job update', 'we have started building our professional',
    'follow us on', 'subscribe to our newsletter', 'share this job',
    'click here to apply now and', 'like our page', 'join our telegram',
    'join our whatsapp group',
]

STRONG_ENTRY_SIGNALS = [
    'entry level', 'entry-level', 'graduate program', 'graduate trainee',
    'internship', 'intern', 'no experience required', 'fresh graduate',
    'nysc', '0-1 year', '0-2 years',
]
STRONG_SENIOR_SIGNALS = [
    'senior', 'lead', 'principal', 'head of', 'director', 'chief',
    '10+ years', '8+ years', 'manager', 'vp ', 'vice president',
]


def normalize_company(company):
    """Mechanical cleanup only — never guess a different company."""
    if not company:
        return 'Unknown'
    company = re.sub(r'\s+', ' ', company).strip()
    company = re.sub(r'\s*[\|\-–]\s*(view all jobs|more jobs|apply now)$', '', company, flags=re.IGNORECASE)
    return company or 'Unknown'


def normalize_location(location):
    """Strip known-garbage foreign-language artifacts. Never touches
    legitimate international locations that don't match these patterns."""
    if not location:
        return location

    cleaned = re.sub(r'\s+', ' ', location).strip()
    low = cleaned.lower()

    has_nigerian_state = any(s.lower() in low for s in NIGERIAN_STATES)
    has_garbage_marker = any(m in low for m in FOREIGN_LOCATION_GARBAGE_MARKERS)

    if has_nigerian_state and has_garbage_marker:
        # Strip everything from the garbage marker onward, keep the
        # legitimate leading part (e.g. "Lagos, Estado de Lagos, US" -> "Lagos")
        parts = re.split(r',\s*', cleaned)
        kept = []
        for part in parts:
            if any(m in part.lower() for m in FOREIGN_LOCATION_GARBAGE_MARKERS):
                break
            kept.append(part)
        cleaned = ', '.join(kept).strip(', ') or cleaned

    return cleaned


def normalize_experience(raw_experience, title, description):
    """Prefer the scraper-provided value; only override to 'unknown' when
    there's a strong, explicit contradiction against the title/description."""
    valid = {'entry', 'mid', 'senior', 'lead'}
    current = raw_experience if raw_experience in valid else 'unknown'

    text = f"{title or ''} {description or ''}".lower()
    has_entry_signal = any(s in text for s in STRONG_ENTRY_SIGNALS)
    has_senior_signal = any(s in text for s in STRONG_SENIOR_SIGNALS)

    if current in ('senior', 'lead') and has_entry_signal and not has_senior_signal:
        return 'unknown', True  # (value, was_contradicted)
    if current == 'entry' and has_senior_signal and not has_entry_signal:
        return 'unknown', True

    return current, False


def clean_description(description):
    """Remove recognized boilerplate/promotional sentences. Never invents
    content — only removes sentences matching known junk patterns."""
    if not description:
        return description

    sentences = re.split(r'(?<=[.!?])\s+', description)
    kept = []
    for s in sentences:
        low = s.lower()
        if any(marker in low for marker in BOILERPLATE_SENTENCE_MARKERS):
            continue
        kept.append(s)

    result = ' '.join(kept).strip()
    return result if result else description  # never return empty if that's all there was


def detect_company_title_mismatch(title, company):
    """Detect when the title names a different company than the company field
    (the APTECH case: two job blocks' metadata got cross-attributed)."""
    if not title or not company:
        return False

    match = re.search(r'\bat\s+([A-Z][\w\s&.,()\-]{2,60})$', title.strip(), re.IGNORECASE)
    if not match:
        return False

    title_company = match.group(1).strip().lower()
    company_low = company.strip().lower()

    if title_company in company_low or company_low in title_company:
        return False
    # Also allow partial word overlap (e.g. "APTECH" appears in both)
    title_words = set(re.findall(r'[a-z]{3,}', title_company))
    company_words = set(re.findall(r'[a-z]{3,}', company_low))
    if title_words & company_words:
        return False

    return True


def validate_scraped_job(job_dict):
    """
    Run after normalization. Returns a list of warning strings.
    Empty list = clean, safe to auto-approve.
    """
    warnings = []

    title = job_dict.get('title') or ''
    company = job_dict.get('company') or ''
    location = job_dict.get('location') or ''
    description = job_dict.get('description') or ''

    if not company or company == 'Unknown':
        warnings.append('missing_company')

    if detect_company_title_mismatch(title, company):
        warnings.append('company_title_mismatch')

    low_loc = location.lower()
    still_has_garbage = any(m in low_loc for m in FOREIGN_LOCATION_GARBAGE_MARKERS)
    if still_has_garbage:
        warnings.append('contradictory_location')

    if not description or len(description.strip()) < 20:
        warnings.append('missing_description')

    if job_dict.get('_experience_contradicted'):
        warnings.append('experience_mismatch')

    return warnings