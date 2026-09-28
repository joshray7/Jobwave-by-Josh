from app import app, db
with app.app_context():
    db.session.execute(db.text('ALTER TABLE user ADD COLUMN profile_picture_data TEXT'))
    db.session.execute(db.text('ALTER TABLE job ADD COLUMN company_logo_data TEXT'))
    db.session.commit()
    print('Columns added')