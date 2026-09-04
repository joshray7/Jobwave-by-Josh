from app import app, db, Job, notify_trackers_of_closed_jobs, Application

with app.app_context():
    # Grab the job you just tracked — most recent application
    latest_app = Application.query.order_by(Application.applied_at.desc()).first()
    if not latest_app:
        print("No tracked applications found — track a job first.")
    else:
        job = Job.query.get(latest_app.job_id)
        print(f"Closing: {job.title} at {job.company}")
        job.is_active = False
        db.session.commit()
        notify_trackers_of_closed_jobs([job.id])
        print("Done — check your email.")