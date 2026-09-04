from app import app, db, Application, Job, User

with app.app_context():
    latest_app = Application.query.order_by(Application.applied_at.desc()).first()
    if latest_app:
        user = User.query.get(latest_app.user_id)
        job = Job.query.get(latest_app.job_id)
        print(f"Job: {job.title} | Tracked by: {user.email} | is_active: {job.is_active}")