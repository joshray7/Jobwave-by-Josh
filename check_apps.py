from app import app, db, Application

with app.app_context():
    apps = Application.query.order_by(Application.updated_at.desc()).limit(3).all()
    for a in apps:
        print(f"App #{a.id} — status: {a.status} — job: {a.job.title}")