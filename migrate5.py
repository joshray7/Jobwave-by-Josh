from app import app, db
with app.app_context():
    db.session.execute(db.text('ALTER TABLE job ALTER COLUMN title TYPE VARCHAR(500)'))
    db.session.execute(db.text('ALTER TABLE job ALTER COLUMN company TYPE VARCHAR(300)'))
    db.session.commit()
    print('Columns widened')