"""
Tests for job_quality.py — normalization and validation, including the
exact APTECH bug pattern and related edge cases.
"""
from job_quality import (
    normalize_company, normalize_location, normalize_experience,
    clean_description, detect_company_title_mismatch, validate_scraped_job,
)


def test_aptech_location_is_corrected():
    fixed = normalize_location("Lagos, Estado de Lagos, US")
    assert fixed == "Lagos"
    assert "estado" not in fixed.lower()
    assert "US" not in fixed


def test_legitimate_international_location_preserved():
    assert normalize_location("Paris, France") == "Paris, France"
    assert normalize_location("Singapore") == "Singapore"
    assert normalize_location("Remote") == "Remote"


def test_company_title_mismatch_detected():
    mismatch = detect_company_title_mismatch(
        "Software Engineer Instructor At APTECH Computer Education",
        "Aptech Computer Training (Dubai & Sharjah)",
    )
    # APTECH appears in both, so this specific pair should NOT be flagged
    # (word overlap protects genuine partial matches)
    assert mismatch is False


def test_company_title_mismatch_detects_real_conflict():
    mismatch = detect_company_title_mismatch(
        "Accountant At Zenith Bank",
        "Totally Unrelated Logistics Company Ltd",
    )
    assert mismatch is True


def test_boilerplate_description_is_cleaned():
    raw = "Never Miss a Job Update Again. We have started building our professional LinkedIn page. This role requires strong Python skills and 2 years experience."
    cleaned = clean_description(raw)
    assert "Never Miss a Job Update" not in cleaned
    assert "LinkedIn page" not in cleaned
    assert "Python skills" in cleaned


def test_description_never_returns_empty_if_only_boilerplate():
    raw = "Never Miss a Job Update Again."
    cleaned = clean_description(raw)
    assert cleaned  # falls back to original rather than returning blank


def test_experience_contradiction_downgrades_to_unknown():
    exp, contradicted = normalize_experience(
        'senior', 'Graduate Trainee - Entry Level Position', 'No experience required, fresh graduates welcome'
    )
    assert exp == 'unknown'
    assert contradicted is True


def test_experience_kept_when_consistent():
    exp, contradicted = normalize_experience(
        'senior', 'Senior Backend Engineer', '10+ years experience leading engineering teams'
    )
    assert exp == 'senior'
    assert contradicted is False


def test_missing_company_flagged():
    warnings = validate_scraped_job({
        'title': 'Sales Officer', 'company': '', 'location': 'Lagos',
        'description': 'A full valid description of the sales role here.',
    })
    assert 'missing_company' in warnings


def test_clean_job_has_no_warnings():
    warnings = validate_scraped_job({
        'title': 'Backend Developer at Flutterwave', 'company': 'Flutterwave',
        'location': 'Lagos', 'description': 'We are looking for a backend developer with 3 years experience in Python and Django.',
    })
    assert warnings == []


def test_normalize_company_handles_empty():
    assert normalize_company(None) == 'Unknown'
    assert normalize_company('') == 'Unknown'
    assert normalize_company('  Flutterwave  ') == 'Flutterwave'