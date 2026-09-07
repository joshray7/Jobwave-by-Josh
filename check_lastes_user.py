from app import app, db, User

with app.app_context():
    user = User.query.order_by(User.created_at.desc()).first()
    print(f"Most recent user: {user.email}")