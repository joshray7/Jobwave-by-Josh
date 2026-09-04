from app import app, db

with app.app_context():
    db.session.execute(db.text('ALTER TABLE application ADD COLUMN cover_note TEXT'))
    db.session.execute(db.text('ALTER TABLE application ADD COLUMN resume_link VARCHAR(500)'))
    db.session.commit()
    print('Columns added')