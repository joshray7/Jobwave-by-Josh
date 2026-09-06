from app import app, db

with app.app_context():
    db.session.execute(db.text('ALTER TABLE user ADD COLUMN username VARCHAR(50)'))
    db.session.execute(db.text('CREATE UNIQUE INDEX IF NOT EXISTS ix_user_username ON user(username)'))
    db.session.commit()
    print('Username column added')