from app import app
from mailer import send_job_alert
from app import db, Job, User

with app.app_context():
    user = User.query.filter_by(email='raymondehiz07@gmail.com').first()
    jobs = Job.query.filter(Job.title.ilike('%AI engineer%')).limit(3).all()
    print(f"Testing with {len(jobs)} jobs, sending to {user.email}")

    try:
        send_job_alert(
            to_email=user.email,
            name=user.name,
            keyword='AI engineer',
            jobs=jobs,
        )
        print("✅ Email sent successfully")
    except Exception as e:
        print(f"❌ Email failed: {e}")