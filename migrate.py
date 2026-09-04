from app import app, db, User

with app.app_context():
    u = User.query.filter_by(email='raymondehiz07@gmail.com').first()
    u.role = 'admin'
    db.session.commit()
    print('Role updated to admin')