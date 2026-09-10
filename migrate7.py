from app import app, db

with app.app_context():
    db.session.execute(db.text('ALTER TABLE job ADD COLUMN posted_to_telegram BOOLEAN DEFAULT 0'))
    db.session.execute(db.text('ALTER TABLE job ADD COLUMN validation_warnings VARCHAR(500)'))
    db.session.commit()
    print('Columns added')