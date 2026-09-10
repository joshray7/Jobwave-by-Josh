from app import app, db, User

with app.app_context():
    users = User.query.all()
    print(f"Total users in local DB: {len(users)}")
    for u in users:
        print(f"- {u.email} | username: {u.username} | role: {u.role}")