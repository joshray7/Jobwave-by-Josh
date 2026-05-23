from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.security import generate_password_hash, check_password_hash
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature
from dotenv import load_dotenv
from datetime import datetime, timedelta
import os, json, csv, io, threading, time
from functools import wraps

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'jobwave-secret-2024')

# ─── Database config ────────────────────────────────────────────────────────────
# Render provides DATABASE_URL starting with "postgres://" but SQLAlchemy
# requires "postgresql://" — fix it automatically
database_url = os.environ.get('DATABASE_URL', 'sqlite:///jobwave.db')
if database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = ''

# ─── Rate Limiter ───────────────────────────────────────────────────────────────
limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    default_limits=[],          # no global limit — only apply where we decorate
    storage_uri='memory://',    # in-memory; swap to redis:// in production
)

def on_rate_limit_exceeded(e):
    if request.is_json or request.path.startswith('/api/'):
        return jsonify({'error': 'Too many requests. Please slow down.'}), 429
    flash('Too many attempts. Please wait a moment and try again.', 'error')
    return redirect(request.referrer or url_for('login')), 429

app.register_error_handler(429, on_rate_limit_exceeded)

# ─── Models ────────────────────────────────────────────────────────────────────

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), default='user')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    saved_jobs = db.relationship('SavedJob', backref='user', lazy=True, cascade='all, delete-orphan')
    applications = db.relationship('Application', backref='user', lazy=True, cascade='all, delete-orphan')
    alerts = db.relationship('Alert', backref='user', lazy=True, cascade='all, delete-orphan')
    profile = db.relationship('UserProfile', backref='user', uselist=False, cascade='all, delete-orphan')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def is_authenticated(self): return True

    @property
    def is_anonymous(self): return False

    def get_id(self): return str(self.id)


class UserProfile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, unique=True)
    headline = db.Column(db.String(200))           # e.g. "Full Stack Developer"
    location = db.Column(db.String(200))           # e.g. "Lagos, Nigeria"
    experience_level = db.Column(db.String(50))    # entry | mid | senior | lead
    target_role = db.Column(db.String(200))        # e.g. "Backend Engineer"
    target_salary = db.Column(db.Integer)          # desired salary (yearly)
    preferred_type = db.Column(db.String(50))      # full-time | remote | contract
    skills = db.Column(db.Text)                    # comma-separated: "python,react,aws"
    bio = db.Column(db.Text)
    github = db.Column(db.String(200))
    linkedin = db.Column(db.String(200))
    portfolio = db.Column(db.String(200))
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def skills_list(self):
        if not self.skills:
            return []
        return [s.strip() for s in self.skills.split(',') if s.strip()]


class Job(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    company = db.Column(db.String(200), nullable=False)
    location = db.Column(db.String(200))
    job_type = db.Column(db.String(50))          # full-time | part-time | remote | contract
    experience = db.Column(db.String(50))         # entry | mid | senior
    salary_min = db.Column(db.Integer)
    salary_max = db.Column(db.Integer)
    description = db.Column(db.Text)
    requirements = db.Column(db.Text)
    source = db.Column(db.String(100))
    source_url = db.Column(db.String(500))
    source_id = db.Column(db.String(200), unique=True)  # duplicate detection
    tags = db.Column(db.String(500))
    is_active = db.Column(db.Boolean, default=True)
    scraped_at = db.Column(db.DateTime, default=datetime.utcnow)
    posted_at = db.Column(db.DateTime)
    views = db.Column(db.Integer, default=0)


class SavedJob(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    job_id = db.Column(db.Integer, db.ForeignKey('job.id'), nullable=False)
    saved_at = db.Column(db.DateTime, default=datetime.utcnow)
    job = db.relationship('Job')


class Application(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    job_id = db.Column(db.Integer, db.ForeignKey('job.id'), nullable=False)
    status = db.Column(db.String(50), default='applied')  # applied|interview|offer|rejected|withdrawn
    notes = db.Column(db.Text)
    applied_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    job = db.relationship('Job')


class Alert(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    keyword = db.Column(db.String(200), nullable=False)
    location = db.Column(db.String(200))
    job_type = db.Column(db.String(50))
    frequency = db.Column(db.String(20), default='daily')  # daily | weekly
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_sent = db.Column(db.DateTime)


class ScraperLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    source = db.Column(db.String(100))
    status = db.Column(db.String(20))   # success | failed | running
    jobs_found = db.Column(db.Integer, default=0)
    jobs_added = db.Column(db.Integer, default=0)
    message = db.Column(db.Text)
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    ended_at = db.Column(db.DateTime)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            flash('Admin access required.', 'error')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated


# ─── Auth Routes ───────────────────────────────────────────────────────────────

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    stats = {
        'total_jobs': Job.query.filter_by(is_active=True).count(),
        'companies': db.session.query(Job.company).distinct().count(),
        'sources': db.session.query(Job.source).distinct().count(),
    }
    recent = Job.query.filter_by(is_active=True).order_by(Job.scraped_at.desc()).limit(6).all()
    return render_template('index.html', stats=stats, recent=recent)


@app.route('/register', methods=['GET', 'POST'])
@limiter.limit('5 per hour', methods=['POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        if not name or not email or not password:
            flash('All fields are required.', 'error')
        elif User.query.filter_by(email=email).first():
            flash('Email already registered.', 'error')
        elif len(password) < 6:
            flash('Password must be at least 6 characters.', 'error')
        else:
            user = User(name=name, email=email)
            user.set_password(password)
            # First user becomes admin
            if User.query.count() == 0:
                user.role = 'admin'
            db.session.add(user)
            db.session.commit()
            login_user(user)
            # Send welcome email in background
            try:
                from mailer import send_welcome
                t = threading.Thread(target=send_welcome, args=(user.email, user.name))
                t.daemon = True
                t.start()
            except Exception:
                pass
            flash(f'Welcome aboard, {name}!', 'success')
            return redirect(url_for('dashboard'))
    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
@limiter.limit('10 per minute; 50 per hour', methods=['POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password) and user.is_active:
            login_user(user, remember=request.form.get('remember'))
            next_page = request.args.get('next')
            return redirect(next_page or url_for('dashboard'))
        flash('Invalid email or password.', 'error')
    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))


# ─── Password Reset ─────────────────────────────────────────────────────────────

def get_serializer():
    return URLSafeTimedSerializer(app.config['SECRET_KEY'])


@app.route('/forgot-password', methods=['GET', 'POST'])
@limiter.limit('5 per hour', methods=['POST'])
def forgot_password():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        user = User.query.filter_by(email=email).first()
        # Always show success to prevent email enumeration
        if user:
            try:
                from mailer import send_password_reset
                token = get_serializer().dumps(email, salt='password-reset')
                reset_url = url_for('reset_password', token=token, _external=True)
                t = threading.Thread(target=send_password_reset,
                                     args=(user.email, reset_url, user.name))
                t.daemon = True
                t.start()
            except Exception as e:
                app.logger.error(f"Password reset email failed: {e}")
        flash('If that email is registered, you will receive a reset link shortly.', 'info')
        return redirect(url_for('login'))
    return render_template('forgot_password.html')


@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    try:
        email = get_serializer().loads(token, salt='password-reset', max_age=3600)
    except SignatureExpired:
        flash('This reset link has expired. Please request a new one.', 'error')
        return redirect(url_for('forgot_password'))
    except BadSignature:
        flash('Invalid reset link. Please request a new one.', 'error')
        return redirect(url_for('forgot_password'))

    user = User.query.filter_by(email=email).first()
    if not user:
        flash('User not found.', 'error')
        return redirect(url_for('forgot_password'))

    if request.method == 'POST':
        password = request.form.get('password', '')
        confirm = request.form.get('confirm', '')
        if len(password) < 6:
            flash('Password must be at least 6 characters.', 'error')
        elif password != confirm:
            flash('Passwords do not match.', 'error')
        else:
            user.set_password(password)
            db.session.commit()
            flash('Password reset successfully! You can now sign in.', 'success')
            return redirect(url_for('login'))
    return render_template('reset_password.html', token=token)




@app.route('/dashboard')
@login_required
def dashboard():
    saved_count = SavedJob.query.filter_by(user_id=current_user.id).count()
    app_count = Application.query.filter_by(user_id=current_user.id).count()
    alert_count = Alert.query.filter_by(user_id=current_user.id, is_active=True).count()
    recent_apps = Application.query.filter_by(user_id=current_user.id)\
        .order_by(Application.applied_at.desc()).limit(5).all()
    status_counts = {}
    for status in ['applied', 'interview', 'offer', 'rejected']:
        status_counts[status] = Application.query.filter_by(user_id=current_user.id, status=status).count()
    recent_jobs = Job.query.filter_by(is_active=True).order_by(Job.scraped_at.desc()).limit(8).all()
    return render_template('dashboard.html', saved_count=saved_count, app_count=app_count,
                           alert_count=alert_count, recent_apps=recent_apps,
                           status_counts=status_counts, recent_jobs=recent_jobs)


# ─── Jobs ──────────────────────────────────────────────────────────────────────

@app.route('/jobs')
@login_required
def jobs():
    q = request.args.get('q', '')
    location = request.args.get('location', '')
    job_type = request.args.get('type', '')
    experience = request.args.get('experience', '')
    salary_min = request.args.get('salary_min', type=int)
    source = request.args.get('source', '')
    sort = request.args.get('sort', 'newest')
    page = request.args.get('page', 1, type=int)

    query = Job.query.filter_by(is_active=True)
    if q:
        search = f'%{q}%'
        query = query.filter(
            db.or_(Job.title.ilike(search), Job.company.ilike(search),
                   Job.description.ilike(search), Job.tags.ilike(search))
        )
    if location:
        query = query.filter(Job.location.ilike(f'%{location}%'))
    if job_type:
        query = query.filter(Job.job_type == job_type)
    if experience:
        query = query.filter(Job.experience == experience)
    if salary_min:
        query = query.filter(Job.salary_min >= salary_min)
    if source:
        query = query.filter(Job.source == source)

    if sort == 'salary':
        query = query.order_by(Job.salary_max.desc())
    elif sort == 'oldest':
        query = query.order_by(Job.scraped_at.asc())
    else:
        query = query.order_by(Job.scraped_at.desc())

    pagination = query.paginate(page=page, per_page=12, error_out=False)
    sources = [r[0] for r in db.session.query(Job.source).distinct().all() if r[0]]

    saved_ids = {s.job_id for s in SavedJob.query.filter_by(user_id=current_user.id).all()}
    applied_ids = {a.job_id for a in Application.query.filter_by(user_id=current_user.id).all()}

    return render_template('jobs.html', jobs=pagination.items, pagination=pagination,
                           sources=sources, saved_ids=saved_ids, applied_ids=applied_ids,
                           q=q, location=location, job_type=job_type,
                           experience=experience, salary_min=salary_min,
                           source=source, sort=sort)


@app.route('/jobs/<int:job_id>')
@login_required
def job_detail(job_id):
    job = Job.query.get_or_404(job_id)
    job.views += 1
    db.session.commit()
    is_saved = SavedJob.query.filter_by(user_id=current_user.id, job_id=job_id).first() is not None
    application = Application.query.filter_by(user_id=current_user.id, job_id=job_id).first()
    similar = Job.query.filter(Job.id != job_id, Job.is_active == True,
                               Job.title.ilike(f'%{job.title.split()[0]}%')).limit(4).all()
    return render_template('job_detail.html', job=job, is_saved=is_saved,
                           application=application, similar=similar)


# ─── Saved Jobs ────────────────────────────────────────────────────────────────

@app.route('/saved')
@login_required
def saved_jobs():
    saved = SavedJob.query.filter_by(user_id=current_user.id)\
        .order_by(SavedJob.saved_at.desc()).all()
    return render_template('saved.html', saved=saved)


@app.route('/api/jobs/<int:job_id>/save', methods=['POST'])
@login_required
@limiter.limit('60 per minute')
def toggle_save(job_id):
    job = Job.query.get_or_404(job_id)
    existing = SavedJob.query.filter_by(user_id=current_user.id, job_id=job_id).first()
    if existing:
        db.session.delete(existing)
        db.session.commit()
        return jsonify({'saved': False, 'message': 'Removed from saved'})
    else:
        db.session.add(SavedJob(user_id=current_user.id, job_id=job_id))
        db.session.commit()
        return jsonify({'saved': True, 'message': 'Job saved!'})


# ─── Applications ──────────────────────────────────────────────────────────────

@app.route('/applications')
@login_required
def applications():
    status_filter = request.args.get('status', '')
    query = Application.query.filter_by(user_id=current_user.id)
    if status_filter:
        query = query.filter_by(status=status_filter)
    apps = query.order_by(Application.applied_at.desc()).all()
    status_counts = {}
    for s in ['applied', 'interview', 'offer', 'rejected', 'withdrawn']:
        status_counts[s] = Application.query.filter_by(user_id=current_user.id, status=s).count()
    return render_template('applications.html', applications=apps,
                           status_counts=status_counts, status_filter=status_filter)


@app.route('/api/applications', methods=['POST'])
@login_required
@limiter.limit('30 per minute')
def create_application():
    job_id = request.json.get('job_id')
    job = Job.query.get_or_404(job_id)
    existing = Application.query.filter_by(user_id=current_user.id, job_id=job_id).first()
    if existing:
        return jsonify({'error': 'Already applied'}), 400
    app_obj = Application(user_id=current_user.id, job_id=job_id)
    db.session.add(app_obj)
    db.session.commit()
    return jsonify({'success': True, 'message': 'Application tracked!'})


@app.route('/api/applications/<int:app_id>', methods=['PATCH'])
@login_required
def update_application(app_id):
    app_obj = Application.query.filter_by(id=app_id, user_id=current_user.id).first_or_404()
    data = request.json
    if 'status' in data:
        app_obj.status = data['status']
    if 'notes' in data:
        app_obj.notes = data['notes']
    app_obj.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify({'success': True})


@app.route('/api/applications/<int:app_id>', methods=['DELETE'])
@login_required
def delete_application(app_id):
    app_obj = Application.query.filter_by(id=app_id, user_id=current_user.id).first_or_404()
    db.session.delete(app_obj)
    db.session.commit()
    return jsonify({'success': True})


# ─── Alerts ────────────────────────────────────────────────────────────────────

@app.route('/alerts')
@login_required
def alerts():
    user_alerts = Alert.query.filter_by(user_id=current_user.id).order_by(Alert.created_at.desc()).all()
    return render_template('alerts.html', alerts=user_alerts)


@app.route('/api/alerts', methods=['POST'])
@login_required
@limiter.limit('20 per hour')
def create_alert():
    data = request.json
    alert = Alert(
        user_id=current_user.id,
        keyword=data.get('keyword', ''),
        location=data.get('location', ''),
        job_type=data.get('job_type', ''),
        frequency=data.get('frequency', 'daily')
    )
    db.session.add(alert)
    db.session.commit()
    return jsonify({'success': True, 'id': alert.id})


@app.route('/api/alerts/<int:alert_id>', methods=['DELETE'])
@login_required
def delete_alert(alert_id):
    alert = Alert.query.filter_by(id=alert_id, user_id=current_user.id).first_or_404()
    db.session.delete(alert)
    db.session.commit()
    return jsonify({'success': True})


@app.route('/api/alerts/<int:alert_id>/toggle', methods=['POST'])
@login_required
def toggle_alert(alert_id):
    alert = Alert.query.filter_by(id=alert_id, user_id=current_user.id).first_or_404()
    alert.is_active = not alert.is_active
    db.session.commit()
    return jsonify({'active': alert.is_active})


# ─── Export ────────────────────────────────────────────────────────────────────

@app.route('/export/jobs')
@login_required
def export_jobs():
    fmt = request.args.get('format', 'csv')
    saved_only = request.args.get('saved', '0') == '1'

    if saved_only:
        saved = SavedJob.query.filter_by(user_id=current_user.id).all()
        jobs_list = [s.job for s in saved]
    else:
        jobs_list = Job.query.filter_by(is_active=True).order_by(Job.scraped_at.desc()).limit(500).all()

    if fmt == 'json':
        data = [{'id': j.id, 'title': j.title, 'company': j.company,
                 'location': j.location, 'type': j.job_type, 'source': j.source,
                 'salary_min': j.salary_min, 'salary_max': j.salary_max,
                 'posted_at': str(j.posted_at)} for j in jobs_list]
        return jsonify(data)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Title', 'Company', 'Location', 'Type', 'Experience',
                     'Salary Min', 'Salary Max', 'Source', 'Posted'])
    for j in jobs_list:
        writer.writerow([j.title, j.company, j.location, j.job_type,
                         j.experience, j.salary_min, j.salary_max, j.source, j.posted_at])
    output.seek(0)
    return send_file(io.BytesIO(output.getvalue().encode()),
                     mimetype='text/csv',
                     as_attachment=True,
                     download_name='jobs_export.csv')


# ─── Analytics ─────────────────────────────────────────────────────────────────

@app.route('/analytics')
@login_required
def analytics():
    total_jobs = Job.query.filter_by(is_active=True).count()
    my_apps = Application.query.filter_by(user_id=current_user.id).count()
    my_saved = SavedJob.query.filter_by(user_id=current_user.id).count()
    interview_rate = 0
    if my_apps > 0:
        interviews = Application.query.filter_by(user_id=current_user.id, status='interview').count()
        interview_rate = round((interviews / my_apps) * 100, 1)

    type_dist = db.session.query(Job.job_type, db.func.count(Job.id))\
        .filter(Job.is_active == True).group_by(Job.job_type).all()
    source_dist = db.session.query(Job.source, db.func.count(Job.id))\
        .filter(Job.is_active == True).group_by(Job.source).all()
    status_dist = db.session.query(Application.status, db.func.count(Application.id))\
        .filter(Application.user_id == current_user.id).group_by(Application.status).all()

    return render_template('analytics.html', total_jobs=total_jobs, my_apps=my_apps,
                           my_saved=my_saved, interview_rate=interview_rate,
                           type_dist=type_dist, source_dist=source_dist,
                           status_dist=status_dist)


# ─── Profile ────────────────────────────────────────────────────────────────────

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    prof = current_user.profile
    if not prof:
        prof = UserProfile(user_id=current_user.id)
        db.session.add(prof)
        db.session.commit()

    if request.method == 'POST':
        # Basic info
        current_user.name = request.form.get('name', current_user.name).strip()
        prof.headline = request.form.get('headline', '').strip()
        prof.location = request.form.get('location', '').strip()
        prof.bio = request.form.get('bio', '').strip()
        prof.experience_level = request.form.get('experience_level', '')
        prof.target_role = request.form.get('target_role', '').strip()
        prof.preferred_type = request.form.get('preferred_type', '')
        target_salary = request.form.get('target_salary', '')
        prof.target_salary = int(target_salary) if target_salary.isdigit() else None
        # Skills — clean and deduplicate
        raw_skills = request.form.get('skills', '')
        skills = list(dict.fromkeys(
            [s.strip().lower() for s in raw_skills.replace(';', ',').split(',') if s.strip()]
        ))
        prof.skills = ','.join(skills)
        # Links
        prof.github = request.form.get('github', '').strip()
        prof.linkedin = request.form.get('linkedin', '').strip()
        prof.portfolio = request.form.get('portfolio', '').strip()
        prof.updated_at = datetime.utcnow()
        db.session.commit()
        flash('Profile updated!', 'success')
        return redirect(url_for('profile'))

    return render_template('profile.html', prof=prof)


# ─── AI Match Score ─────────────────────────────────────────────────────────────

@app.route('/api/jobs/<int:job_id>/match', methods=['POST'])
@login_required
@limiter.limit('30 per hour')
def get_match_score(job_id):
    job = Job.query.get_or_404(job_id)
    prof = current_user.profile

    if not prof or not prof.skills:
        return jsonify({'error': 'Complete your profile first to get match scores.'}), 400

    api_key = os.environ.get('ANTHROPIC_API_KEY', '')
    if not api_key:
        return jsonify({'error': 'AI scoring not configured.'}), 503

    def compute_score():
        import requests as req
        profile_summary = f"""
Name: {current_user.name}
Target Role: {prof.target_role or 'Not specified'}
Experience Level: {prof.experience_level or 'Not specified'}
Skills: {prof.skills or 'Not specified'}
Preferred Job Type: {prof.preferred_type or 'Any'}
Location: {prof.location or 'Not specified'}
        """.strip()

        job_summary = f"""
Title: {job.title}
Company: {job.company}
Location: {job.location}
Type: {job.job_type}
Experience Required: {job.experience}
Tags/Skills: {job.tags}
Description (excerpt): {(job.description or '')[:600]}
        """.strip()

        prompt = f"""You are a job matching assistant. Given a candidate profile and a job listing, score how well the candidate matches the job.

CANDIDATE PROFILE:
{profile_summary}

JOB LISTING:
{job_summary}

Respond with ONLY a JSON object in this exact format, nothing else:
{{
  "score": <integer 0-100>,
  "level": "<Poor|Fair|Good|Strong|Excellent>",
  "summary": "<one sentence explaining the match>",
  "matching_skills": ["skill1", "skill2"],
  "missing_skills": ["skill1", "skill2"]
}}"""

        response = req.post(
            'https://api.anthropic.com/v1/messages',
            headers={
                'x-api-key': api_key,
                'anthropic-version': '2023-06-01',
                'content-type': 'application/json',
            },
            json={
                'model': 'claude-haiku-4-5-20251001',
                'max_tokens': 500,
                'messages': [{'role': 'user', 'content': prompt}]
            },
            timeout=15
        )
        if not response.ok:
            app.logger.error(f"Anthropic API error body: {response.text}")
        response.raise_for_status()
        data = response.json()
        text = data['content'][0]['text'].strip()
        # Strip markdown fences if present
        if text.startswith('```'):
            text = text.split('```')[1]
            if text.startswith('json'):
                text = text[4:]
        return json.loads(text.strip())

    try:
        result = compute_score()
        return jsonify({'success': True, **result})
    except Exception as e:
        app.logger.error(f"Match score error: {e}")
        return jsonify({'error': f'Scoring failed: {str(e)}'}), 500




def run_scraper_task(profile_name, app_context):
    with app_context:
        from scrapers.jsearch_scraper import fetch_jsearch_jobs, get_profile
        log = ScraperLog(source=profile_name, status='running')
        db.session.add(log)
        db.session.commit()
        try:
            profile = get_profile(profile_name)
            if not profile:
                raise ValueError(f"Unknown search profile: {profile_name}")
            jobs_data = fetch_jsearch_jobs(
                query=profile.get('query', ''),
                location=profile.get('location', ''),
                num_pages=profile.get('num_pages', 1),
                date_posted=profile.get('date_posted', 'month'),
                remote_only=profile.get('remote_only', False),
            )
            added = 0
            for jd in jobs_data:
                if not Job.query.filter_by(source_id=jd.get('source_id')).first():
                    job = Job(**jd)
                    db.session.add(job)
                    added += 1
            db.session.commit()
            log.status = 'success'
            log.jobs_found = len(jobs_data)
            log.jobs_added = added
            log.ended_at = datetime.utcnow()
        except Exception as e:
            log.status = 'failed'
            log.message = str(e)
            log.ended_at = datetime.utcnow()
        db.session.commit()


@app.route('/api/scraper/run', methods=['POST'])
@login_required
@admin_required
@limiter.limit('10 per hour')
def trigger_scraper():
    source = request.json.get('source', 'demo')
    t = threading.Thread(target=run_scraper_task, args=(source, app.app_context()))
    t.daemon = True
    t.start()
    return jsonify({'success': True, 'message': f'Scraper started for {source}'})


# ─── Admin ─────────────────────────────────────────────────────────────────────

@app.route('/admin')
@login_required
@admin_required
def admin():
    from scrapers.jsearch_scraper import SEARCH_PROFILES
    users = User.query.order_by(User.created_at.desc()).all()
    logs = ScraperLog.query.order_by(ScraperLog.started_at.desc()).limit(20).all()
    total_jobs = Job.query.count()
    active_jobs = Job.query.filter_by(is_active=True).count()
    total_users = User.query.count()
    return render_template('admin.html', users=users, logs=logs,
                           total_jobs=total_jobs, active_jobs=active_jobs,
                           total_users=total_users,
                           scraper_profiles=SEARCH_PROFILES)


@app.route('/admin/clear-fake-jobs', methods=['POST'])
@login_required
@admin_required
def clear_fake_jobs():
    # Delete all jobs not from JSearch (the fake seeded ones)
    deleted = Job.query.filter(Job.source != 'JSearch').delete()
    db.session.commit()
    return jsonify({'success': True, 'deleted': deleted})


@app.route('/admin/users/<int:user_id>/toggle', methods=['POST'])
@login_required
@admin_required
def toggle_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        return jsonify({'error': 'Cannot deactivate yourself'}), 400
    user.is_active = not user.is_active
    db.session.commit()
    return jsonify({'active': user.is_active})


@app.route('/admin/jobs/<int:job_id>/toggle', methods=['POST'])
@login_required
@admin_required
def toggle_job(job_id):
    job = Job.query.get_or_404(job_id)
    job.is_active = not job.is_active
    db.session.commit()
    return jsonify({'active': job.is_active})


# ─── API Endpoints ─────────────────────────────────────────────────────────────

@app.route('/api/jobs')
@login_required
@limiter.limit('100 per minute')
def api_jobs():
    q = request.args.get('q', '')
    limit = min(request.args.get('limit', 20, type=int), 100)
    query = Job.query.filter_by(is_active=True)
    if q:
        query = query.filter(db.or_(Job.title.ilike(f'%{q}%'), Job.company.ilike(f'%{q}%')))
    jobs = query.order_by(Job.scraped_at.desc()).limit(limit).all()
    return jsonify([{
        'id': j.id, 'title': j.title, 'company': j.company,
        'location': j.location, 'type': j.job_type, 'source': j.source,
        'salary_min': j.salary_min, 'salary_max': j.salary_max
    } for j in jobs])


# ─── Init ──────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    from scheduler import init_scheduler
    init_scheduler(app)
    app.run(debug=True)