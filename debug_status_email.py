from app import app, db, Job, User
from mailer import send_application_status_email

with app.app_context():
    user = User.query.filter_by(email='raymondehiz07@gmail.com').first()
    job = Job.query.filter_by(title='AI ENGINEER').first()

    print(f"Sending to: {user.email}, job: {job.title}")
    send_application_status_email(to_email=user.email, name=user.name, job=job, status='interview')
    print("✅ Sent successfully")