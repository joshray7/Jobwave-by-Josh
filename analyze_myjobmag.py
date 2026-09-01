from collections import Counter

from scrapers.myjobmag_scraper import fetch_myjobmag_jobs


jobs = fetch_myjobmag_jobs()

print("=" * 60)
print("MYJOBMAG ANALYSIS")
print("=" * 60)

print(f"\nTotal jobs: {len(jobs)}")


# ---------------------------------------------------------
# LOCATIONS
# ---------------------------------------------------------

locations = Counter(
    job.get("location") or "Unknown"
    for job in jobs
)

print("\nTOP LOCATIONS")
print("-" * 40)

for location, count in locations.most_common(20):
    print(f"{count:3}  {location}")


# ---------------------------------------------------------
# INDUSTRIES
# ---------------------------------------------------------

industries = Counter(
    job.get("industry") or "Unknown"
    for job in jobs
)

print("\nINDUSTRIES")
print("-" * 40)

for industry, count in industries.most_common(30):
    print(f"{count:3}  {industry}")


# ---------------------------------------------------------
# COMPANIES
# ---------------------------------------------------------

companies = Counter(
    job.get("company") or "Unknown"
    for job in jobs
)

print("\nTOP COMPANIES")
print("-" * 40)

for company, count in companies.most_common(20):
    print(f"{count:3}  {company}")


# ---------------------------------------------------------
# MISSING DATA
# ---------------------------------------------------------

missing_company = sum(
    not job.get("company")
    for job in jobs
)

missing_location = sum(
    not job.get("location")
    for job in jobs
)

missing_description = sum(
    not job.get("description")
    for job in jobs
)

missing_url = sum(
    not job.get("source_url")
    for job in jobs
)

print("\nDATA QUALITY")
print("-" * 40)

print(f"Missing company:     {missing_company}")
print(f"Missing location:    {missing_location}")
print(f"Missing description: {missing_description}")
print(f"Missing URL:         {missing_url}")


# ---------------------------------------------------------
# SAMPLE JOBS
# ---------------------------------------------------------

print("\nSAMPLE JOBS")
print("-" * 40)

for job in jobs[:10]:

    print(
        f"\n{job['title']}"
        f"\nCompany: {job['company']}"
        f"\nLocation: {job['location']}"
        f"\nIndustry: {job.get('industry')}"
        f"\nURL: {job['source_url']}"
    )