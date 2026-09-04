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
    """Fetch fresh jobs from all profiles — JSearch, Remotive, Muse, Adzuna."""
    with app.app_context():
        from app import db, Job, ScraperLog
        from scrapers.jsearch_scraper import fetch_jsearch_jobs, SEARCH_PROFILES
        from scrapers.remotive_scraper import fetch_remotive_jobs, REMOTIVE_PROFILES
        from scrapers.muse_scraper import fetch_muse_jobs, MUSE_PROFILES
        from scrapers.adzuna_scraper import fetch_adzuna_jobs, ADZUNA_PROFILES
        from scrapers.myjobmag_scraper import fetch_myjobmag_jobs, MYJOBMAG_PROFILES
        from scrapers.hotnigerianjobs_scraper import fetch_hotnigerianjobs_jobs, HOTNIGERIANJOBS_PROFILES
        from scrapers.jobberman_scraper import fetch_jobberman_jobs, JOBBERMAN_PROFILES
        from datetime import datetime

        logger.info("Scheduler: starting daily scrape...")

        def run_profile(profile_name, fetch_fn, kwargs):
            log = ScraperLog(source=profile_name, status='running')
            db.session.add(log)
            db.session.commit()
            try:
                jobs_data = fetch_fn(**kwargs)
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
                logger.info(f"{profile_name} — {added} new jobs")
            except Exception as e:
                log.status = 'failed'
                log.message = str(e)
                log.ended_at = datetime.utcnow()
                logger.error(f"{profile_name} failed: {e}")
            db.session.commit()

        # JSearch profiles
        for p in SEARCH_PROFILES:
            run_profile(p['name'], fetch_jsearch_jobs, {
                'query': p.get('query', ''),
                'location': p.get('location', ''),
                'num_pages': p.get('num_pages', 1),
                'date_posted': p.get('date_posted', 'month'),
                'remote_only': p.get('remote_only', False),
            })

        # Remotive profiles
        for p in REMOTIVE_PROFILES:
            run_profile(p['name'], fetch_remotive_jobs, {
                'category': p.get('category', 'software-dev'),
                'limit': p.get('limit', 20),
                'search': p.get('search', ''),
            })

        # Muse profiles
        for p in MUSE_PROFILES:
            run_profile(p['name'], fetch_muse_jobs, {
                'category': p.get('category', 'Engineering'),
                'num_pages': p.get('num_pages', 1),
            })

        # Adzuna profiles
        for p in ADZUNA_PROFILES:
            run_profile(p['name'], fetch_adzuna_jobs, {
                'region': p.get('region', 'ng'),
                'keywords': p.get('keywords', 'developer'),
                'page': 1,
            })

        # MyJobMag profiles
        for p in MYJOBMAG_PROFILES:
            run_profile(p['name'], fetch_myjobmag_jobs, {
                'category': p.get('category'),
                'num_pages': p.get('num_pages', 1),
            })

        # HotNigerianJobs profiles
        for p in HOTNIGERIANJOBS_PROFILES:
            run_profile(p['name'], fetch_hotnigerianjobs_jobs, {
                'field_id': p.get('field_id'),
                'industry_id': p.get('industry_id'),
                'num_pages': p.get('num_pages', 1),
            })

        # Jobberman profiles
        for p in JOBBERMAN_PROFILES:
            run_profile(p['name'], fetch_jobberman_jobs, {
                'category_path': p.get('category_path'),
                'num_pages': p.get('num_pages', 1),
            })

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

def run_job_expiry(app):
    """Mark jobs older than 30 days as inactive — runs daily."""
    with app.app_context():
        from app import db, Job, notify_trackers_of_closed_jobs
        from datetime import datetime, timedelta

        cutoff = datetime.utcnow() - timedelta(days=30)
        chunk_size = 25

        old_job_ids = [r[0] for r in db.session.query(Job.id)
                       .filter(Job.is_active == True, Job.scraped_at < cutoff).all()]

        expired_count = 0
        for i in range(0, len(old_job_ids), chunk_size):
            chunk = old_job_ids[i:i + chunk_size]
            db.session.query(Job).filter(Job.id.in_(chunk))\
                .update({Job.is_active: False}, synchronize_session=False)
            db.session.commit()
            expired_count += len(chunk)

        if old_job_ids:
            notify_trackers_of_closed_jobs(old_job_ids)

        logger.info(f"Job expiry: {expired_count} jobs marked inactive (older than 30 days)")

def init_scheduler(app):
    """Start the scheduler. Call once at app startup."""
    if scheduler.running:
        return

        # Scrape twice daily — midnight and noon, Lagos time
    scheduler.add_job(
        func=run_daily_scraper,
        args=[app],
        trigger=CronTrigger(hour='0,12', minute=0),
        id='daily_scraper',
        name='Twice-Daily Scrape',
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

    # Job expiry — mark jobs older than 30 days inactive, runs at 1am Lagos time
    scheduler.add_job(
        func=run_job_expiry,
        args=[app],
        trigger=CronTrigger(hour=1, minute=0),
        id='job_expiry',
        name='Job Auto-Expiry',
        replace_existing=True,
    )

    scheduler.start()
    logger.info("JobWave scheduler started — scrape at midnight & noon, expiry at 1am, alerts at 8am (Lagos)")