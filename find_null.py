from app import app, Job

with app.app_context():
    pending = Job.query.filter_by(approval_status='pending').all()
    for j in pending:
        if not j.description:
            print(f"Job #{j.id}: '{j.title}' at '{j.company}' has no description — source: {j.source}")