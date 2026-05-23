"""
JobWave Scheduler — APScheduler
Runs background jobs:
  - Daily scraper (midnight)
  - Job alert emails (every morning at 8am)
"""

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import logging

logger = logging.getLogger(__name__)
scheduler = BackgroundScheduler(timezone='Africa/Lagos')


def run_daily_scraper(app):
    """Fetch fresh jobs from all JSearch profiles."""
    with app.app_context():
        from app import db, Job, ScraperLog
        from scrapers.jsearch_scraper import fetch_jsearch_jobs, SEARCH_PROFILES
        from datetime import datetime

        logger.info("Scheduler: starting daily scrape...")
        for profile in SEARCH_PROFILES:
            log = ScraperLog(source=profile['name'], status='running')
            db.session.add(log)
            db.session.commit()
            try:
                jobs_data = fetch_jsearch_jobs(
                    query=profile.get('query', ''),
                    location=profile.get('location', ''),
                    num_pages=profile.get('num_pages', 1),
                    date_posted=profile.get('date_posted', 'month'),
                    remote_only=profile.get('remote_only', False),
                )
                added = 0
                for jd in jobs_data:
                    if not Job.query.filter_by(source_id=jd.get('source_id')).first():
                        db.session.add(Job(**jd))
                        added += 1
                db.session.commit()
                log.status = 'success'
                log.jobs_found = len(jobs_data)
                log.jobs_added = added
                log.ended_at = datetime.utcnow()
                logger.info(f"Scheduler: {profile['name']} — {added} new jobs added")
            except Exception as e:
                log.status = 'failed'
                log.message = str(e)
                log.ended_at = datetime.utcnow()
                logger.error(f"Scheduler: {profile['name']} failed — {e}")
            db.session.commit()


def run_alert_emails(app):
    """Send job alert emails to users with active alerts."""
    with app.app_context():
        from app import db, Alert, Job, User
        from mailer import send_job_alert
        from datetime import datetime, timedelta

        logger.info("Scheduler: processing job alerts...")
        alerts = Alert.query.filter_by(is_active=True).all()

        for alert in alerts:
            user = User.query.get(alert.user_id)
            if not user or not user.is_active:
                continue

            # Check frequency
            now = datetime.utcnow()
            if alert.last_sent:
                if alert.frequency == 'daily' and (now - alert.last_sent).days < 1:
                    continue
                if alert.frequency == 'weekly' and (now - alert.last_sent).days < 7:
                    continue

            # Find matching jobs since last alert
            since = alert.last_sent or (now - timedelta(days=1))
            query = Job.query.filter(
                Job.is_active == True,
                Job.scraped_at >= since,
            )
            if alert.keyword:
                kw = f'%{alert.keyword}%'
                query = query.filter(
                    db.or_(
                        Job.title.ilike(kw),
                        Job.description.ilike(kw),
                        Job.tags.ilike(kw),
                    )
                )
            if alert.location:
                query = query.filter(Job.location.ilike(f'%{alert.location}%'))
            if alert.job_type:
                query = query.filter(Job.job_type == alert.job_type)

            matching_jobs = query.order_by(Job.scraped_at.desc()).limit(8).all()

            if matching_jobs:
                try:
                    send_job_alert(
                        to_email=user.email,
                        name=user.name,
                        keyword=alert.keyword,
                        jobs=matching_jobs,
                    )
                    alert.last_sent = now
                    db.session.commit()
                    logger.info(f"Alert email sent to {user.email} — {len(matching_jobs)} jobs")
                except Exception as e:
                    logger.error(f"Alert email failed for {user.email}: {e}")


def init_scheduler(app):
    """Start the scheduler. Call once at app startup."""
    if scheduler.running:
        return

    # Daily scrape at midnight Lagos time
    scheduler.add_job(
        func=run_daily_scraper,
        args=[app],
        trigger=CronTrigger(hour=0, minute=0),
        id='daily_scraper',
        name='Daily JSearch Scrape',
        replace_existing=True,
    )

    # Alert emails every morning at 8am Lagos time
    scheduler.add_job(
        func=run_alert_emails,
        args=[app],
        trigger=CronTrigger(hour=8, minute=0),
        id='alert_emails',
        name='Job Alert Emails',
        replace_existing=True,
    )

    scheduler.start()
    logger.info("JobWave scheduler started — daily scrape at midnight, alerts at 8am (Lagos)")