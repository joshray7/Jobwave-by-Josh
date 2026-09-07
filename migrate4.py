from app import app, db
with app.app_context():
    db.session.execute(db.text('ALTER TABLE user ADD COLUMN is_verified BOOLEAN DEFAULT 0'))
    db.session.commit()
    print('Column added')