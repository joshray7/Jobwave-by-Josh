from app import app, db, User
from mailer import send_verification_email

with app.app_context():
    user = User.query.filter_by(email='raymondehiz07@gmail.com').first()
    if not user:
        print("User not found — use your actual test account email")
    else:
        print(f"Sending to: {user.email}")
        send_verification_email(to_email=user.email, name=user.name)
        print("✅ Sent successfully")