from app import app
from scheduler import run_alert_emails

with app.app_context():
    run_alert_emails(app)
    print("Alert check complete — check your terminal logs above and your email inbox.")