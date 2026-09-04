from app import app, db, Job, User
from mailer import send_job_closed_email

with app.app_context():
    user = User.query.filter_by(email='raymondehiz07@gmail.com').first()
    job = Job.query.filter_by(title='Data Scientist - Machine Learning & Artificial Intelligence').first()

    print(f"Sending to: {user.email}, job: {job.title}")
    send_job_closed_email(to_email=user.email, name=user.name, jobs=[job])
    print("✅ Sent successfully")