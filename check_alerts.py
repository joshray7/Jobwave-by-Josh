from app import app, db, Alert, Job

with app.app_context():
    alerts = Alert.query.filter_by(is_active=True).all()
    print(f"Active alerts: {len(alerts)}")
    for a in alerts:
        print(f"- Keyword: '{a.keyword}' | Location: '{a.location}' | Last sent: {a.last_sent}")
        matches = Job.query.filter(Job.title.ilike(f'%{a.keyword}%')).count()
        print(f"  Matching jobs in DB: {matches}")