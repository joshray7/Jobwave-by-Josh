from app import app, db, Job
from datetime import datetime, timedelta

with app.app_context():
    inactive_total = Job.query.filter_by(is_active=False).count()
    cutoff = datetime.utcnow() - timedelta(days=30)
    inactive_old = Job.query.filter(Job.is_active == False, Job.scraped_at < cutoff).count()
    inactive_unknown = Job.query.filter(Job.is_active == False, Job.company == 'Unknown').count()

    print(f"Total inactive: {inactive_total}")
    print(f"Inactive AND older than 30 days: {inactive_old}")
    print(f"Inactive AND company is Unknown: {inactive_unknown}")