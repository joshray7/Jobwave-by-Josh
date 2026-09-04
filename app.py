from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_migrate import Migrate
from werkzeug.security import generate_password_hash, check_password_hash
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature
from dotenv import load_dotenv
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import os, json, csv, io, threading, time, re
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
migrate = Migrate(app, db)
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
    posted_to_whatsapp = db.Column(db.Boolean, default=False)
    posted_by_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    approval_status = db.Column(db.String(20), default='approved')  # pending | approved | rejected
    rejection_reason = db.Column(db.String(500))

    @property
    def work_arrangement(self):
        """Infer Remote / Hybrid / Onsite from job_type, location, and description."""
        text = f"{self.job_type or ''} {self.location or ''} {(self.description or '')[:300]}".lower()
        if 'hybrid' in text:
            return 'Hybrid'
        if 'remote' in text or self.job_type == 'remote':
            return 'Remote'
        return 'Onsite'

    @property
    def posted_ago(self):
        """Human-readable freshness label based on scraped_at."""
        if not self.scraped_at:
            return ''
        delta = datetime.utcnow() - self.scraped_at
        days = delta.days
        if days <= 0:
            return 'Today'
        if days == 1:
            return 'Yesterday'
        if days < 7:
            return f'{days} days ago'
        weeks = days // 7
        if weeks < 5:
            return f'{weeks} week{"s" if weeks != 1 else ""} ago'
        months = days // 30
        return f'{months} month{"s" if months != 1 else ""} ago'

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
    cover_note = db.Column(db.Text)
    resume_link = db.Column(db.String(500))
    job = db.relationship('Job')
    applicant = db.relationship('User', foreign_keys=[user_id], overlaps="applications,user")

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


class Collection(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(300))
    color = db.Column(db.String(20), default='indigo')  # indigo | mint | amber | red
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    items = db.relationship('CollectionItem', backref='collection', lazy=True, cascade='all, delete-orphan')


class CollectionItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    collection_id = db.Column(db.Integer, db.ForeignKey('collection.id'), nullable=False)
    job_id = db.Column(db.Integer, db.ForeignKey('job.id'), nullable=False)
    added_at = db.Column(db.DateTime, default=datetime.utcnow)
    job = db.relationship('Job')


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

def employer_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'employer':
            flash('This page is for employer accounts only.', 'error')
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
    salary_max = request.args.get('salary_max', type=int)
    date_posted = request.args.get('date_posted', '')  # 1d | 7d | 30d
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
    if salary_max:
        query = query.filter(db.or_(Job.salary_max <= salary_max, Job.salary_max == None))
    if date_posted:
        days_map = {'1d': 1, '7d': 7, '30d': 30}
        days = days_map.get(date_posted)
        if days:
            cutoff = datetime.utcnow() - timedelta(days=days)
            query = query.filter(Job.scraped_at >= cutoff)
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
    collections = Collection.query.filter_by(user_id=current_user.id).all()

    return render_template('jobs.html', jobs=pagination.items, pagination=pagination,
                           sources=sources, saved_ids=saved_ids, applied_ids=applied_ids,
                           collections=collections,
                           q=q, location=location, job_type=job_type,
                           experience=experience, salary_min=salary_min,
                           salary_max=salary_max, date_posted=date_posted,
                           source=source, sort=sort)


@app.route('/jobs/<int:job_id>')
@login_required
def job_detail(job_id):
    job = Job.query.get_or_404(job_id)

    job.views += 1
    db.session.commit()

    if job.description:
        soup = BeautifulSoup(job.description, "html.parser")

        for tag in soup.find_all(True):
            tag.attrs = {}

        job.description = str(soup)
    else:
        job.description = ""

    is_saved = SavedJob.query.filter_by(
        user_id=current_user.id,
        job_id=job_id
    ).first() is not None

    application = Application.query.filter_by(
        user_id=current_user.id,
        job_id=job_id
    ).first()

    similar = Job.query.filter(
        Job.id != job_id,
        Job.is_active == True,
        Job.title.ilike(f'%{job.title.split()[0]}%')
    ).limit(4).all()

    return render_template(
        'job_detail.html',
        job=job,
        is_saved=is_saved,
        application=application,
        similar=similar
    )

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
    status_counts['applied'] = Application.query.filter_by(user_id=current_user.id).count()
    for s in ['interview', 'offer', 'rejected', 'withdrawn']:
        status_counts[s] = Application.query.filter_by(user_id=current_user.id, status=s).count()
    return render_template('applications.html', applications=apps,
                           status_counts=status_counts, status_filter=status_filter)

def one_line_summary(description, max_len=160):
    """Reduce a job description to a single clean sentence for WhatsApp."""
    if not description:
        return ''
    text = re.sub(r'\s+', ' ', description).strip()
    match = re.search(r'^(.{30,}?[.!?])\s', text + ' ')
    if match:
        sentence = match.group(1).strip()
        if len(sentence) <= max_len:
            return sentence
    if len(text) <= max_len:
        return text
    return text[:max_len].rsplit(' ', 1)[0] + '…'


def extract_requirements(description):
    """Try to pull a short requirements/qualifications bullet list from the description."""
    if not description:
        return []
    match = re.search(r'(requirements?|qualifications?|skills?)\s*:?\s*(.*)', description, re.IGNORECASE | re.DOTALL)
    if not match:
        return []
    tail = match.group(2)
    parts = re.split(r'[•\u2022\-\n;]+', tail)
    parts = [p.strip(' .') for p in parts if p.strip() and len(p.strip()) > 3]
    return [p for p in parts if len(p) < 80][:4]


def build_whatsapp_message(job):
    """Build the standard WhatsApp job announcement format for any job, from any source."""
    job_type_map = {
        'full-time': 'Full-time', 'part-time': 'Part-time',
        'remote': 'Remote', 'contract': 'Contract', 'internship': 'Internship',
    }
    exp_map = {'entry': 'Entry-level', 'mid': 'Mid-level', 'senior': 'Senior-level', 'lead': 'Lead-level'}

    job_type_label = job_type_map.get((job.job_type or '').lower(), (job.job_type or 'Full-time').title())

    lines = [
        "🚨 *NEW JOB — JOBWAVE*",
        f"💼 *{job.title}*",
        f"🏢 {job.company or 'Unknown'}",
    ]
    if job.location:
        lines.append(f"📍 {job.location}")
    lines.append(f"🕐 {job_type_label}")

    exp_label = exp_map.get((job.experience or '').lower())
    if exp_label:
        lines.append(f"📊 {exp_label}")

    summary = one_line_summary(job.description)
    if summary:
        lines.append(f"📝 {summary}")

    reqs = extract_requirements(job.description)
    if reqs:
        lines.append("🎯 Requirements:")
        for r in reqs:
            lines.append(f"• {r}")

    internal_url = url_for('job_detail', job_id=job.id, _external=True)
    lines.append(f"🔗 APPLY: {internal_url}")
    lines.append(f"📌 Source: {job.source}")
    lines.append("🤖 JobWave — Find your next job")

    return "\n".join(lines)

def notify_trackers_of_closed_jobs(job_ids):
    """Email any user tracking these jobs that they're no longer active."""
    if not job_ids:
        return
    from collections import defaultdict
    from mailer import send_job_closed_email

    rows = db.session.query(Application.user_id, Job).join(Job, Application.job_id == Job.id)\
        .filter(Application.job_id.in_(job_ids)).all()

    by_user = defaultdict(list)
    for user_id, job in rows:
        by_user[user_id].append(job)

    for user_id, jobs in by_user.items():
        user = User.query.get(user_id)
        if not user or not user.is_active:
            continue
        try:
            send_job_closed_email(to_email=user.email, name=user.name, jobs=jobs)
        except Exception as e:
            app.logger.error(f"Job closed email failed for {user.email}: {e}")


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
    my_apps = Application.query.filter_by(user_id=current_user.id).count()
    my_saved = SavedJob.query.filter_by(user_id=current_user.id).count()

    interview_rate = 0
    if my_apps > 0:
        interviews = Application.query.filter_by(user_id=current_user.id, status='interview').count()
        interview_rate = round((interviews / my_apps) * 100, 1)

    status_dist = db.session.query(Application.status, db.func.count(Application.id))\
        .filter(Application.user_id == current_user.id).group_by(Application.status).all()

    # Which sources the user has actually applied through
    applied_source_dist = db.session.query(Job.source, db.func.count(Application.id))\
        .join(Application, Application.job_id == Job.id)\
        .filter(Application.user_id == current_user.id)\
        .group_by(Job.source).all()

    # Work arrangement of jobs the user has saved (Remote/Hybrid/Onsite)
    saved_jobs = db.session.query(Job).join(SavedJob, SavedJob.job_id == Job.id)\
        .filter(SavedJob.user_id == current_user.id).all()
    arrangement_counts = {'Remote': 0, 'Hybrid': 0, 'Onsite': 0}
    for j in saved_jobs:
        arrangement_counts[j.work_arrangement] += 1
    arrangement_dist = [(k, v) for k, v in arrangement_counts.items() if v > 0]

    return render_template('analytics.html', my_apps=my_apps,
                           my_saved=my_saved, interview_rate=interview_rate,
                           status_dist=status_dist,
                           applied_source_dist=applied_source_dist,
                           arrangement_dist=arrangement_dist)


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


# ─── Company Pages ──────────────────────────────────────────────────────────────

@app.route('/company/<path:company_name>')
@login_required
def company_page(company_name):
    # Get all jobs from this company
    company_jobs = Job.query.filter(
        Job.company.ilike(company_name),
        Job.is_active == True
    ).order_by(Job.scraped_at.desc()).all()

    if not company_jobs:
        flash(f'No jobs found for {company_name}', 'error')
        return redirect(url_for('jobs'))

    # Stats
    total = len(company_jobs)
    job_types = {}
    locations = {}
    sources = set()
    for j in company_jobs:
        job_types[j.job_type or 'full-time'] = job_types.get(j.job_type or 'full-time', 0) + 1
        if j.location:
            locations[j.location] = locations.get(j.location, 0) + 1
        if j.source:
            sources.add(j.source)

    top_location = max(locations, key=locations.get) if locations else 'Various'
    top_type = max(job_types, key=job_types.get) if job_types else 'full-time'

    saved_ids = {s.job_id for s in SavedJob.query.filter_by(user_id=current_user.id).all()}
    applied_ids = {a.job_id for a in Application.query.filter_by(user_id=current_user.id).all()}

    return render_template('company.html',
        company_name=company_name,
        jobs=company_jobs,
        total=total,
        top_location=top_location,
        top_type=top_type,
        job_types=job_types,
        sources=list(sources),
        saved_ids=saved_ids,
        applied_ids=applied_ids,
    )


@app.route('/companies')
@login_required
def companies():
    # Get all companies with job counts
    results = db.session.query(
        Job.company,
        db.func.count(Job.id).label('job_count'),
        db.func.max(Job.scraped_at).label('latest'),
    ).filter(
        Job.is_active == True
    ).group_by(Job.company).order_by(db.desc('job_count')).all()

    q = request.args.get('q', '')
    if q:
        results = [r for r in results if q.lower() in r.company.lower()]

    return render_template('companies.html', companies=results, q=q)


# ─── AI Match Score ─────────────────────────────────────────────────────────────

@app.route('/api/jobs/<int:job_id>/match', methods=['POST'])
@login_required
def get_match_score(job_id):
    return jsonify({'error': 'AI Match Scoring is coming soon. Stay tuned!'}), 503
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
        log = ScraperLog(source=profile_name, status='running')
        db.session.add(log)
        db.session.commit()
        log_id = log.id

        try:
            jobs_data = []
            profile_found = False

            # ── JSearch ──
            from scrapers.jsearch_scraper import get_profile as get_jsearch_profile, fetch_jsearch_jobs
            jsearch_profile = get_jsearch_profile(profile_name)
            if jsearch_profile:
                profile_found = True
                jobs_data = fetch_jsearch_jobs(
                    query=jsearch_profile.get('query', ''),
                    location=jsearch_profile.get('location', ''),
                    num_pages=jsearch_profile.get('num_pages', 1),
                    date_posted=jsearch_profile.get('date_posted', 'month'),
                    remote_only=jsearch_profile.get('remote_only', False),
                )

            # ── Remotive ──
            if not profile_found:
                from scrapers.remotive_scraper import get_remotive_profile, fetch_remotive_jobs
                remotive_profile = get_remotive_profile(profile_name)
                if remotive_profile:
                    profile_found = True
                    jobs_data = fetch_remotive_jobs(
                        category=remotive_profile.get('category', 'software-dev'),
                        limit=remotive_profile.get('limit', 20),
                        search=remotive_profile.get('search', ''),
                    )

            # ── The Muse ──
            if not profile_found:
                from scrapers.muse_scraper import get_muse_profile, fetch_muse_jobs
                muse_profile = get_muse_profile(profile_name)
                if muse_profile:
                    profile_found = True
                    jobs_data = fetch_muse_jobs(
                        category=muse_profile.get('category', 'Engineering'),
                        num_pages=muse_profile.get('num_pages', 1),
                    )

            # ── Adzuna ──
            if not profile_found:
                from scrapers.adzuna_scraper import get_adzuna_profile, fetch_adzuna_jobs
                adzuna_profile = get_adzuna_profile(profile_name)
                if adzuna_profile:
                    profile_found = True
                    jobs_data = fetch_adzuna_jobs(
                        what=adzuna_profile.get('what', ''),
                        where=adzuna_profile.get('where', ''),
                        country=adzuna_profile.get('country', 'ng'),
                        num_pages=adzuna_profile.get('num_pages', 1),
                        results_per_page=adzuna_profile.get('results_per_page', 20),
                    )

            if not profile_found:
                raise ValueError(f"Unknown profile: {profile_name}")

            added = 0
            for jd in jobs_data:
                if not Job.query.filter_by(source_id=jd.get('source_id')).first():
                    db.session.add(Job(**jd))
                    added += 1
            db.session.commit()

            log = ScraperLog.query.get(log_id)
            log.status = 'success'
            log.jobs_found = len(jobs_data)
            log.jobs_added = added
            log.ended_at = datetime.utcnow()
            db.session.commit()
            app.logger.info(f"Scraper: {profile_name} — {added} new jobs added")

        except Exception as e:
            app.logger.error(f"Scraper error [{profile_name}]: {e}")
            try:
                log = ScraperLog.query.get(log_id)
                if log:
                    log.status = 'failed'
                    log.message = str(e)[:500]
                    log.ended_at = datetime.utcnow()
                    db.session.commit()
            except Exception:
                pass


def run_scraper_task_with_log(profile_name, log_id, app_context):
    """Same as run_scraper_task but uses an existing log entry by ID."""
    with app_context:
        try:
            jobs_data = []
            profile_found = False

            from scrapers.jsearch_scraper import get_profile as get_jsearch_profile, fetch_jsearch_jobs
            jsearch_profile = get_jsearch_profile(profile_name)
            if jsearch_profile:
                profile_found = True
                jobs_data = fetch_jsearch_jobs(
                    query=jsearch_profile.get('query', ''),
                    location=jsearch_profile.get('location', ''),
                    num_pages=jsearch_profile.get('num_pages', 1),
                    date_posted=jsearch_profile.get('date_posted', 'month'),
                    remote_only=jsearch_profile.get('remote_only', False),
                )

            if not profile_found:
                from scrapers.remotive_scraper import get_remotive_profile, fetch_remotive_jobs
                remotive_profile = get_remotive_profile(profile_name)
                if remotive_profile:
                    profile_found = True
                    jobs_data = fetch_remotive_jobs(
                        category=remotive_profile.get('category', 'software-dev'),
                        limit=remotive_profile.get('limit', 20),
                        search=remotive_profile.get('search', ''),
                    )

            if not profile_found:
                from scrapers.muse_scraper import get_muse_profile, fetch_muse_jobs
                muse_profile = get_muse_profile(profile_name)
                if muse_profile:
                    profile_found = True
                    jobs_data = fetch_muse_jobs(
                        category=muse_profile.get('category', 'Engineering'),
                        num_pages=muse_profile.get('num_pages', 1),
                    )

            if not profile_found:
                from scrapers.adzuna_scraper import get_adzuna_profile, fetch_adzuna_jobs
                adzuna_profile = get_adzuna_profile(profile_name)
                if adzuna_profile:
                    profile_found = True
                    jobs_data = fetch_adzuna_jobs(
                        region=adzuna_profile.get('region', 'ng'),
                        keywords=adzuna_profile.get('keywords', 'developer'),
                        page=1,
                    )

            if not profile_found:
                from scrapers.adzuna_scraper import get_adzuna_profile, fetch_adzuna_jobs
                adzuna_profile = get_adzuna_profile(profile_name)
                if adzuna_profile:
                    profile_found = True
                    jobs_data = fetch_adzuna_jobs(
                        region=adzuna_profile.get('region', 'ng'),
                        keywords=adzuna_profile.get('keywords', 'developer'),
                        page=1,
                    )

            if not profile_found:
                from scrapers.myjobmag_scraper import get_myjobmag_profile, fetch_myjobmag_jobs
                myjobmag_profile = get_myjobmag_profile(profile_name)
                if myjobmag_profile:
                    profile_found = True
                    jobs_data = fetch_myjobmag_jobs(
                        category=myjobmag_profile.get('category'),
                        num_pages=myjobmag_profile.get('num_pages', 1),
                    )

            if not profile_found:
                from scrapers.hotnigerianjobs_scraper import get_hotnigerianjobs_profile, fetch_hotnigerianjobs_jobs
                hnj_profile = get_hotnigerianjobs_profile(profile_name)
                if hnj_profile:
                    profile_found = True
                    jobs_data = fetch_hotnigerianjobs_jobs(
                        field_id=hnj_profile.get('field_id'),
                        industry_id=hnj_profile.get('industry_id'),
                        num_pages=hnj_profile.get('num_pages', 1),
                    )

            if not profile_found:
                from scrapers.jobberman_scraper import get_jobberman_profile, fetch_jobberman_jobs
                jobberman_profile = get_jobberman_profile(profile_name)
                if jobberman_profile:
                    profile_found = True
                    jobs_data = fetch_jobberman_jobs(
                        category_path=jobberman_profile.get('category_path'),
                        num_pages=jobberman_profile.get('num_pages', 1),
                    )

           
            if not profile_found:
                raise ValueError(f"Unknown profile: {profile_name}")

            added = 0
            for jd in jobs_data:
                if not Job.query.filter_by(source_id=jd.get('source_id')).first():
                    db.session.add(Job(**jd))
                    added += 1
            db.session.commit()

            log = ScraperLog.query.get(log_id)
            if log:
                log.status = 'success'
                log.jobs_found = len(jobs_data)
                log.jobs_added = added
                log.ended_at = datetime.utcnow()
                db.session.commit()
            app.logger.info(f"Scraper: {profile_name} — {added} new jobs")

        except Exception as e:
            app.logger.error(f"Scraper error [{profile_name}]: {e}")
            try:
                log = ScraperLog.query.get(log_id)
                if log:
                    log.status = 'failed'
                    log.message = str(e)[:500]
                    log.ended_at = datetime.utcnow()
                    db.session.commit()
            except Exception:
                pass



@app.route('/api/scraper/run', methods=['POST'])
@login_required
@admin_required
@limiter.limit('100 per hour')
def trigger_scraper():
    try:
        data = request.get_json(force=True, silent=True) or {}
        source = data.get('source', '')
        if not source:
            return jsonify({'success': False, 'message': 'No source specified'}), 400
        log = ScraperLog(source=source, status='running')
        db.session.add(log)
        db.session.commit()
        log_id = log.id
        t = threading.Thread(target=run_scraper_task_with_log,
                             args=(source, log_id, app.app_context()))
        t.daemon = True
        t.start()
        return jsonify({'success': True, 'message': f'Scraper started for {source}', 'log_id': log_id})
    except Exception as e:
        app.logger.error(f"trigger_scraper error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/admin/logs-partial')
@login_required
@admin_required
def logs_partial():
    logs = ScraperLog.query.order_by(ScraperLog.started_at.desc()).limit(20).all()
    if not logs:
        return '<div class="empty-state" style="padding:30px 0;"><div style="color:var(--text-muted);">No scraper runs yet.</div></div>'
    rows = ''
    for log in logs:
        badge = 'badge-green' if log.status == 'success' else ('badge-red' if log.status == 'failed' else 'badge-amber')
        rows += f'''
        <tr style="cursor:pointer;" onclick="window.location='/admin/log/{log.id}/jobs'">
          <td style="font-weight:600;">{log.source}</td>
          <td><span class="badge {badge}">{log.status}</span></td>
          <td style="color:var(--mint);font-weight:600;">+{log.jobs_added}</td>
          <td style="color:var(--text-muted);font-size:0.8rem;">{log.started_at.strftime('%b %d, %H:%M')}</td>
          <td class="hide-mobile" style="font-size:0.78rem;color:var(--text-muted);max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{log.message or '—'}</td>
          <td><a href="/admin/log/{log.id}/jobs" class="btn btn-ghost btn-sm" onclick="event.stopPropagation()"><i class="fa-solid fa-eye"></i></a></td>
        </tr>'''
    return f'''<div class="table-wrap" style="margin-top:12px;">
      <table><thead><tr><th>Source</th><th>Status</th><th>Added</th><th>Started</th><th class="hide-mobile">Message</th><th>Jobs</th></tr></thead>
      <tbody>{rows}</tbody></table></div>'''


# ─── Admin ─────────────────────────────────────────────────────────────────────

@app.route('/admin')
@login_required
@admin_required
def admin():
    from scrapers.jsearch_scraper import SEARCH_PROFILES as JSEARCH_PROFILES
    from scrapers.remotive_scraper import REMOTIVE_PROFILES
    from scrapers.muse_scraper import MUSE_PROFILES
    from scrapers.adzuna_scraper import ADZUNA_PROFILES
    from scrapers.myjobmag_scraper import MYJOBMAG_PROFILES
    from scrapers.hotnigerianjobs_scraper import HOTNIGERIANJOBS_PROFILES
    from scrapers.jobberman_scraper import JOBBERMAN_PROFILES
    all_profiles = JSEARCH_PROFILES + REMOTIVE_PROFILES + MUSE_PROFILES + ADZUNA_PROFILES + MYJOBMAG_PROFILES + HOTNIGERIANJOBS_PROFILES + JOBBERMAN_PROFILES
    users = User.query.order_by(User.created_at.desc()).all()
    logs = ScraperLog.query.order_by(ScraperLog.started_at.desc()).limit(20).all()
    total_jobs = Job.query.count()
    active_jobs = Job.query.filter_by(is_active=True).count()
    total_users = User.query.count()
    total_applications = Application.query.count()
    total_alerts = Alert.query.count()
    return render_template('admin.html', users=users, logs=logs,
                           total_jobs=total_jobs, active_jobs=active_jobs,
                           total_users=total_users, total_applications=total_applications, total_alerts=total_alerts,
                           scraper_profiles=all_profiles)


@app.route('/admin/clear-fake-jobs', methods=['POST'])
@login_required
@admin_required
def clear_fake_jobs():
    deleted = Job.query.filter(Job.source != 'JSearch').delete()
    db.session.commit()
    return jsonify({'success': True, 'deleted': deleted})


@app.route('/api/scraper/status/<int:log_id>')
@login_required
@admin_required
def scraper_status(log_id):
    log = ScraperLog.query.get_or_404(log_id)
    return jsonify({
        'id': log.id,
        'source': log.source,
        'status': log.status,
        'jobs_found': log.jobs_found,
        'jobs_added': log.jobs_added,
        'message': log.message or '',
        'started_at': log.started_at.strftime('%b %d, %H:%M'),
        'ended_at': log.ended_at.strftime('%b %d, %H:%M') if log.ended_at else None,
    })


@app.route('/admin/log/<int:log_id>/jobs')
@login_required
@admin_required
def scraper_log_jobs(log_id):
    log = ScraperLog.query.get_or_404(log_id)
    jobs = []

    if log.status == 'success' and log.jobs_added and log.jobs_added > 0:
        from datetime import timedelta

        # Map profile name -> actual Job.source value stored in DB
        if 'Adzuna' in log.source:
            base_source = 'Adzuna'
        elif 'Remotive' in log.source or 'Remote' in log.source:
            base_source = 'Remotive'
        elif 'Muse' in log.source:
            base_source = 'The Muse'
        elif 'MyJobMag' in log.source:
            base_source = 'MyJobmag'
        elif 'HotNigerianJobs' in log.source:
            base_source = 'HotNigerianJobs'
        elif 'Jobberman' in log.source:
            base_source = 'Jobberman'
        else:
            base_source = 'JSearch'

        window_start = log.started_at - timedelta(seconds=5)
        window_end = (log.ended_at or log.started_at) + timedelta(seconds=60)

        jobs = Job.query.filter(
            Job.source == base_source,
            Job.scraped_at >= window_start,
            Job.scraped_at <= window_end,
        ).order_by(Job.scraped_at.desc()).all()

        if not jobs:
            jobs = Job.query.filter_by(source=base_source)\
                .order_by(Job.scraped_at.desc())\
                .limit(log.jobs_added)\
                .all()

    return render_template('log_jobs.html', log=log, jobs=jobs)

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

@app.route('/api/jobs/<int:job_id>/mark-posted', methods=['POST'])
@login_required
@admin_required
def mark_job_posted(job_id):
    job = Job.query.get_or_404(job_id)
    job.posted_to_whatsapp = not job.posted_to_whatsapp
    db.session.commit()
    return jsonify({'success': True, 'posted': job.posted_to_whatsapp})

@app.route('/admin/whatsapp-digest')
@login_required
@admin_required
def whatsapp_digest():
    from datetime import timedelta
    hours = request.args.get('hours', 24, type=int)
    show_all = request.args.get('show_all', '0') == '1'
    cutoff = datetime.utcnow() - timedelta(hours=hours)

    NIGERIAN_SOURCES = {'MyJobMag', 'HotNigerianJobs', 'Jobberman'}

    query = Job.query.filter(
        Job.is_active == True,
        Job.scraped_at >= cutoff,
    )
    if not show_all:
        query = query.filter(Job.posted_to_whatsapp == False)

    show_flagged = request.args.get('show_flagged', '0') == '1'

    total_matching = query.count()
    all_jobs = query.order_by(Job.scraped_at.desc()).limit(300).all()

    clean_jobs = [j for j in all_jobs if not is_suspicious_job(j)]
    flagged_jobs = [j for j in all_jobs if is_suspicious_job(j)]

    display_jobs = flagged_jobs if show_flagged else clean_jobs

    job_messages = []
    for j in display_jobs:
        job_messages.append({'job': j, 'message': build_whatsapp_message(j)})

    return render_template('whatsapp_digest.html', job_messages=job_messages, hours=hours,
                           total_matching=total_matching, show_all=show_all,
                           show_flagged=show_flagged, flagged_count=len(flagged_jobs))

SCAM_KEYWORDS = [
    'earn big', 'earn daily', 'earn weekly', 'no experience needed and earn',
    'registration fee', 'training fee', 'processing fee', 'send money',
    'whatsapp only', 'click here to apply', 'guaranteed income',
    'work and earn', 'quick money', 'easy money', 'get rich quick',
    'investment opportunity', 'pyramid scheme',
]


def is_suspicious_job(job):
    """Flag likely scam/spam postings so they're excluded from the WhatsApp digest."""
    if not job.company or job.company.strip().lower() == 'unknown':
        return True

    text = f"{job.title} {job.description or ''}".lower()
    if any(kw in text for kw in SCAM_KEYWORDS):
        return True

    # Excessive exclamation marks — classic spam signal
    if job.title.count('!') >= 2:
        return True

    # Mostly-uppercase title is only suspicious when paired with spammy punctuation
    letters = [c for c in job.title if c.isalpha()]
    if letters and len(letters) > 8:
        upper_ratio = sum(1 for c in letters if c.isupper()) / len(letters)
        if upper_ratio > 0.85 and ('!' in job.title or '$' in job.title):
            return True

    return False

@app.route('/admin/duplicates')
@login_required
@admin_required
def find_duplicates():
    import re
    from collections import defaultdict

    def normalize(text):
        text = text.lower().strip()
        text = re.sub(r'[^a-z0-9\s]', '', text)
        text = re.sub(r'\s+', ' ', text)
        return text

    all_jobs = Job.query.filter_by(is_active=True).order_by(Job.scraped_at.desc()).all()
    groups = defaultdict(list)

    for job in all_jobs:
        key = f"{normalize(job.company)}::{normalize(job.title)}"
        groups[key].append(job)

    duplicate_groups = [jobs for jobs in groups.values() if len(jobs) > 1]
    duplicate_groups.sort(key=lambda g: len(g), reverse=True)

    total_duplicates = sum(len(g) - 1 for g in duplicate_groups)

    return render_template('duplicates.html',
        groups=duplicate_groups,
        total_duplicates=total_duplicates)


@app.route('/admin/duplicates/remove', methods=['POST'])
@login_required
@admin_required
def remove_duplicates():
    data = request.get_json(force=True, silent=True) or {}
    job_ids = data.get('job_ids', [])
    if not job_ids:
        return jsonify({'success': False, 'message': 'No jobs selected'}), 400

    deleted = 0
    skipped = 0
    deactivated_ids = []
    for job_id in job_ids:
        has_saved = SavedJob.query.filter_by(job_id=job_id).first()
        has_applied = Application.query.filter_by(job_id=job_id).first()
        if has_saved or has_applied:
            job = Job.query.get(job_id)
            if job:
                job.is_active = False
            skipped += 1
            if has_applied:
                deactivated_ids.append(job_id)
            continue
        Job.query.filter_by(id=job_id).delete()
        deleted += 1

    db.session.commit()

    if deactivated_ids:
        notify_trackers_of_closed_jobs(deactivated_ids)

    return jsonify({'success': True, 'deleted': deleted, 'skipped': skipped})

@app.route('/admin/duplicates/auto-clean', methods=['POST'])
@login_required
@admin_required
def auto_clean_duplicates():
    import re
    from collections import defaultdict
    from sqlalchemy.exc import IntegrityError

    def normalize(text):
        text = text.lower().strip()
        text = re.sub(r'[^a-z0-9\s]', '', text)
        text = re.sub(r'\s+', ' ', text)
        return text

    all_jobs = db.session.query(Job.id, Job.company, Job.title, Job.scraped_at)\
        .filter_by(is_active=True).all()

    groups = defaultdict(list)
    for job_id, company, title, scraped_at in all_jobs:
        key = f"{normalize(company)}::{normalize(title)}"
        groups[key].append((job_id, scraped_at))

    ids_to_delete = []
    for jobs in groups.values():
        if len(jobs) > 1:
            jobs_sorted = sorted(jobs, key=lambda j: j[1], reverse=True)
            ids_to_delete.extend(job_id for job_id, _ in jobs_sorted[1:])

    deleted_count = 0
    skipped_count = 0
    deactivated_ids = []
    chunk_size = 25

    for i in range(0, len(ids_to_delete), chunk_size):
        chunk = ids_to_delete[i:i + chunk_size]
        try:
            db.session.query(Job).filter(Job.id.in_(chunk)).delete(synchronize_session=False)
            db.session.commit()
            deleted_count += len(chunk)
        except IntegrityError:
            db.session.rollback()
            for job_id in chunk:
                try:
                    db.session.query(Job).filter_by(id=job_id).delete()
                    db.session.commit()
                    deleted_count += 1
                except IntegrityError:
                    db.session.rollback()
                    db.session.query(Job).filter_by(id=job_id).update({'is_active': False})
                    db.session.commit()
                    skipped_count += 1
                    deactivated_ids.append(job_id)

    if deactivated_ids:
        notify_trackers_of_closed_jobs(deactivated_ids)

    return jsonify({'success': True, 'deleted': deleted_count, 'skipped': skipped_count})

@app.route('/admin/employer-jobs')
@login_required
@admin_required
def employer_job_queue():
    pending = Job.query.filter_by(approval_status='pending')\
        .order_by(Job.scraped_at.desc()).all()
    return render_template('employer_job_queue.html', jobs=pending)


@app.route('/admin/employer-jobs/<int:job_id>/approve', methods=['POST'])
@login_required
@admin_required
def approve_employer_job(job_id):
    job = Job.query.get_or_404(job_id)
    job.approval_status = 'approved'
    job.is_active = True
    db.session.commit()
    return jsonify({'success': True})


@app.route('/admin/employer-jobs/<int:job_id>/reject', methods=['POST'])
@login_required
@admin_required
def reject_employer_job(job_id):
    job = Job.query.get_or_404(job_id)
    data = request.get_json(force=True, silent=True) or {}
    job.approval_status = 'rejected'
    job.is_active = False
    job.rejection_reason = data.get('reason', '')[:500]
    db.session.commit()
    return jsonify({'success': True})

# ----- POSTING SECTION -------------------------------------

@app.route('/post-job', methods=['GET', 'POST'])
@login_required
@employer_required
def post_job():
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        company = request.form.get('company', '').strip()
        location = request.form.get('location', '').strip()
        job_type = request.form.get('job_type', 'full-time')
        experience = request.form.get('experience', 'mid')
        salary_min = request.form.get('salary_min', type=int)
        salary_max = request.form.get('salary_max', type=int)
        description = request.form.get('description', '').strip()
        requirements = request.form.get('requirements', '').strip()
        tags = request.form.get('tags', '').strip()

        if not title or not company or not description:
            flash('Title, company, and description are required.', 'error')
            return render_template('post_job.html')

        job = Job(
            title=title, company=company, location=location,
            job_type=job_type, experience=experience,
            salary_min=salary_min, salary_max=salary_max,
            description=description, requirements=requirements, tags=tags,
            source='JobWave Direct', is_active=False, approval_status='pending',
            posted_by_user_id=current_user.id,
            scraped_at=datetime.utcnow(), posted_at=datetime.utcnow(),
        )
        db.session.add(job)
        db.session.commit()

        job.source_url = url_for('job_detail', job_id=job.id, _external=True)
        job.source_id = f'employer-{job.id}'
        db.session.commit()

        flash('Job submitted! It will go live once approved by an admin.', 'success')
        return redirect(url_for('my_postings'))

    return render_template('post_job.html')


@app.route('/my-postings')
@login_required
@employer_required
def my_postings():
    jobs = Job.query.filter_by(posted_by_user_id=current_user.id)\
        .order_by(Job.scraped_at.desc()).all()
    applicant_counts = {j.id: Application.query.filter_by(job_id=j.id).count() for j in jobs}
    return render_template('my_postings.html', jobs=jobs, applicant_counts=applicant_counts)


@app.route('/my-postings/<int:job_id>/edit', methods=['GET', 'POST'])
@login_required
@employer_required
def edit_posting(job_id):
    job = Job.query.filter_by(id=job_id, posted_by_user_id=current_user.id).first_or_404()
    if request.method == 'POST':
        job.title = request.form.get('title', '').strip()
        job.company = request.form.get('company', '').strip()
        job.location = request.form.get('location', '').strip()
        job.job_type = request.form.get('job_type', 'full-time')
        job.experience = request.form.get('experience', 'mid')
        job.salary_min = request.form.get('salary_min', type=int)
        job.salary_max = request.form.get('salary_max', type=int)
        job.description = request.form.get('description', '').strip()
        job.requirements = request.form.get('requirements', '').strip()
        job.tags = request.form.get('tags', '').strip()
        job.approval_status = 'pending'
        job.is_active = False
        db.session.commit()
        flash('Job updated and resubmitted for approval.', 'success')
        return redirect(url_for('my_postings'))
    return render_template('post_job.html', job=job, editing=True)


@app.route('/my-postings/<int:job_id>/close', methods=['POST'])
@login_required
@employer_required
def close_posting(job_id):
    job = Job.query.filter_by(id=job_id, posted_by_user_id=current_user.id).first_or_404()
    job.is_active = False
    db.session.commit()
    notify_trackers_of_closed_jobs([job.id])
    flash('Job closed.', 'success')
    return redirect(url_for('my_postings'))

@app.route('/jobs/<int:job_id>/apply', methods=['GET', 'POST'])
@login_required
def apply_to_job(job_id):
    job = Job.query.get_or_404(job_id)
    if job.source != 'JobWave Direct':
        flash('This job is hosted externally — use the Apply link on the job page.', 'error')
        return redirect(url_for('job_detail', job_id=job.id))

    existing = Application.query.filter_by(user_id=current_user.id, job_id=job.id).first()
    if existing:
        flash('You already applied to this job.', 'info')
        return redirect(url_for('job_detail', job_id=job.id))

    if request.method == 'POST':
        cover_note = request.form.get('cover_note', '').strip()
        resume_link = request.form.get('resume_link', '').strip()

        application = Application(
            user_id=current_user.id,
            job_id=job.id,
            status='applied',
            cover_note=cover_note,
            resume_link=resume_link,
        )
        db.session.add(application)
        db.session.commit()
        flash('Application submitted! The employer will review it soon.', 'success')
        return redirect(url_for('job_detail', job_id=job.id))

    return render_template('apply_job.html', job=job)


@app.route('/my-postings/<int:job_id>/applicants')
@login_required
@employer_required
def job_applicants(job_id):
    job = Job.query.filter_by(id=job_id, posted_by_user_id=current_user.id).first_or_404()
    applications = Application.query.filter_by(job_id=job.id)\
        .order_by(Application.applied_at.desc()).all()
    return render_template('job_applicants.html', job=job, applications=applications)


@app.route('/my-postings/applicants/<int:application_id>/status', methods=['POST'])
@login_required
@employer_required
def update_applicant_status(application_id):
    application = Application.query.get_or_404(application_id)
    if application.job.posted_by_user_id != current_user.id:
        return jsonify({'success': False}), 403
    data = request.get_json(force=True, silent=True) or {}
    new_status = data.get('status')
    if new_status not in ['applied', 'interview', 'offer', 'rejected', 'withdrawn']:
        return jsonify({'success': False, 'message': 'Invalid status'}), 400
    application.status = new_status
    db.session.commit()

    if new_status in ('interview', 'offer', 'rejected'):
        from mailer import send_application_status_email
        try:
            send_application_status_email(
                to_email=application.applicant.email,
                name=application.applicant.name,
                job=application.job,
                status=new_status,
            )
        except Exception as e:
            app.logger.error(f"Status email failed: {e}")

    return jsonify({'success': True})

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
    app.run(debug=True, port=5003)

