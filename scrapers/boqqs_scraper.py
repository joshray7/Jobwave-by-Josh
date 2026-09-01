"""
BOQQS Jobs API integration.

Official API:
https://boqqs.com/developers

The API supports country filtering and does not require an API key.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any

import requests


BOQQS_API_URL = "https://boqqs.com/api/v1/jobs"


def make_source_id(job: dict) -> str:
    """Create a stable JobWave ID for a BOQQS listing."""

    raw = (
        job.get("id")
        or job.get("url")
        or job.get("applyUrl")
        or job.get("title")
        or ""
    )

    return hashlib.md5(
        f"boqqs::{raw}".encode("utf-8")
    ).hexdigest()


def parse_datetime(value: Any) -> datetime:
    """Convert BOQQS timestamps into Python datetime objects."""

    if not value:
        return datetime.utcnow()

    if isinstance(value, datetime):
        return value.replace(tzinfo=None)

    try:
        return datetime.fromisoformat(
            str(value).replace("Z", "+00:00")
        ).replace(tzinfo=None)

    except (ValueError, TypeError):
        return datetime.utcnow()


def parse_boqs_job(job: dict) -> dict:
    """Convert a BOQQS job into JobWave's standard format."""

    employer = job.get("employer") or {}

    if isinstance(employer, dict):
        company = (
            employer.get("name")
            or employer.get("companyName")
            or "Unknown"
        )
    else:
        company = str(employer or "Unknown")

    location = job.get("location") or "Nigeria"

    if isinstance(location, dict):
        location = (
            location.get("city")
            or location.get("name")
            or location.get("state")
            or "Nigeria"
        )

    salary = job.get("salary") or {}

    salary_min = None
    salary_max = None

    if isinstance(salary, dict):
        salary_min = (
            salary.get("min")
            or salary.get("minimum")
        )

        salary_max = (
            salary.get("max")
            or salary.get("maximum")
        )

    return {
        "title": str(
            job.get("title")
            or "Untitled Job"
        ),

        "company": str(company),

        "location": str(location),

        "job_type": str(
            job.get("employmentType")
            or job.get("employment_type")
            or "full-time"
        ),

        "experience": "mid",

        "salary_min": salary_min,

        "salary_max": salary_max,

        "description": (
            str(job.get("description"))
            if job.get("description")
            else None
        ),

        "requirements": None,

        "source": "BOQQS",

        "source_url": str(
            job.get("url")
            or ""
        ),

        "source_id": make_source_id(job),

        "tags": "",

        "posted_at": parse_datetime(
            job.get("postedAt")
            or job.get("posted_at")
        ),

        "scraped_at": datetime.utcnow(),
    }


def fetch_boqs_jobs(
    page: int = 1,
    per_page: int = 100,
) -> list[dict]:
    """
    Fetch Nigerian jobs from BOQQS.
    """

    params = {
        "country": "NG",
        "page": page,
        "per_page": min(per_page, 100),
    }

    try:

        response = requests.get(
            BOQQS_API_URL,
            params=params,
            headers={
                "User-Agent": "JobWave/1.0"
            },
            timeout=20,
        )

        response.raise_for_status()

    except requests.exceptions.Timeout as exc:

        raise RuntimeError(
            "BOQQS API request timed out."
        ) from exc

    except requests.exceptions.RequestException as exc:

        raise RuntimeError(
            f"BOQQS API request failed: {exc}"
        ) from exc

    data = response.json()

    jobs = data.get("jobs", [])

    if not isinstance(jobs, list):
        raise RuntimeError(
            "BOQQS returned an unexpected jobs format."
        )

    return [
        parse_boqs_job(job)
        for job in jobs
        if isinstance(job, dict)
    ]