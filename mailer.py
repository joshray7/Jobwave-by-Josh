"""
JobWave Mailer — powered by Resend
Handles all outgoing emails: alerts, password reset, welcome.
"""

import resend
import os
from datetime import datetime

def get_client():
    api_key = os.environ.get('RESEND_API_KEY', '')
    if not api_key:
        raise ValueError("RESEND_API_KEY environment variable not set.")
    resend.api_key = api_key
    return resend

FROM_EMAIL = os.environ.get('FROM_EMAIL', 'onboarding@resend.dev')
APP_NAME   = 'JobWave'
APP_URL    = os.environ.get('APP_URL', 'https://jobwave-by-josh.onrender.com')

# ── Email base template ────────────────────────────────────────────────────────
def base_html(title: str, body: str) -> str:
    return f"""
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <style>
    * {{ margin:0; padding:0; box-sizing:border-box; }}
    body {{ background:#050510; font-family:'Segoe UI',Arial,sans-serif; color:#e8e8ff; }}
    .wrapper {{ max-width:580px; margin:0 auto; padding:32px 16px; }}
    .card {{ background:#0d0d24; border:1px solid rgba(59,0,255,0.2); border-radius:16px; padding:32px; }}
    .logo {{ display:flex; align-items:center; gap:10px; margin-bottom:28px; }}
    .logo-mark {{ width:34px; height:34px; background:linear-gradient(135deg,#3b00ff,#00f5aa); border-radius:9px; display:flex; align-items:center; justify-content:center; font-weight:800; font-size:13px; color:#fff; }}
    .logo-text {{ font-weight:700; font-size:1.1rem; color:#e8e8ff; }}
    .logo-text span {{ color:#00f5aa; }}
    h1 {{ font-size:1.4rem; font-weight:800; margin-bottom:8px; color:#fff; }}
    p {{ color:#7878aa; line-height:1.7; margin-bottom:14px; font-size:0.9rem; }}
    .btn {{ display:inline-block; padding:12px 24px; background:#3b00ff; color:#fff !important; border-radius:8px; text-decoration:none; font-weight:700; font-size:0.9rem; margin:8px 0 16px; }}
    .btn-mint {{ background:#00f5aa; color:#05050f !important; }}
    .job-card {{ background:#12122e; border:1px solid rgba(59,0,255,0.15); border-radius:10px; padding:14px 16px; margin-bottom:10px; }}
    .job-title {{ font-weight:700; color:#fff; font-size:0.95rem; margin-bottom:4px; }}
    .job-meta {{ font-size:0.78rem; color:#7878aa; }}
    .job-salary {{ color:#00f5aa; font-weight:700; font-size:0.82rem; margin-top:4px; }}
    .divider {{ height:1px; background:rgba(59,0,255,0.15); margin:20px 0; }}
    .footer {{ text-align:center; margin-top:24px; font-size:0.75rem; color:#4a4a6a; }}
    .badge {{ display:inline-block; padding:2px 8px; border-radius:20px; font-size:0.72rem; font-weight:600; background:rgba(59,0,255,0.15); color:#8888ff; margin-left:6px; }}
    .badge-mint {{ background:rgba(0,245,170,0.12); color:#00f5aa; }}
  </style>
</head>
<body>
  <div class="wrapper">
    <div class="card">
      <div class="logo">
        <div class="logo-mark">JW</div>
        <div class="logo-text">Job<span>Wave</span></div>
      </div>
      {body}
    </div>
    <div class="footer">
      © {datetime.utcnow().year} JobWave · <a href="{APP_URL}" style="color:#4a4a6a;">Visit Platform</a>
    </div>
  </div>
</body>
</html>
"""

def send_job_closed_email(to_email: str, name: str, jobs: list):
    """Notify a user that job(s) they were tracking have closed or expired."""
    count = len(jobs)
    jobs_html = ""
    for job in jobs[:8]:
        jobs_html += f"""
        <div class="job-card">
          <div class="job-title">{job.title}</div>
          <div class="job-meta">{job.company} · {job.location or 'N/A'}</div>
        </div>
        """
    body = f"""
      <h1>Job{"s" if count != 1 else ""} no longer available</h1>
      <p>Hi {name}, {"these jobs you were tracking are" if count != 1 else "a job you were tracking is"} no longer active — it may have closed or expired.</p>
      {jobs_html}
      <a href="{APP_URL}/applications" class="btn">View My Applications →</a>
      <div class="divider"></div>
      <p style="font-size:0.78rem;">You're receiving this because you tracked this application on JobWave.</p>
    """
    client = get_client()
    client.Emails.send({
        "from": f"{APP_NAME} <{FROM_EMAIL}>",
        "to": [to_email],
        "subject": f"[JobWave] {count} tracked job{'s' if count != 1 else ''} no longer available",
        "html": base_html("Job Update", body),
    })


def send_application_status_email(to_email: str, name: str, job, status: str):
    """Notify an applicant that their JobWave Direct application status changed."""
    status_copy = {
        'interview': ('You\'ve been invited to interview',
                       f'{job.company} would like to interview you for the {job.title} role.'),
        'offer': ('You\'ve received a job offer',
                  f'{job.company} has extended you an offer for {job.title}.'),
        'rejected': ('Update on your application',
                     f'{job.company} has decided not to move forward with your application for {job.title} at this time.'),
    }
    if status not in status_copy:
        return
    heading, message = status_copy[status]
    body = f"""
      <h1>{heading}</h1>
      <p>Hi {name}, {message}</p>
      <div class="job-card">
        <div class="job-title">{job.title}</div>
        <div class="job-meta">{job.company} · {job.location or 'N/A'}</div>
      </div>
      <a href="{APP_URL}/applications" class="btn">View My Applications →</a>
      <div class="divider"></div>
      <p style="font-size:0.78rem;">You're receiving this because you applied to this job on JobWave.</p>
    """
    client = get_client()
    client.Emails.send({
        "from": f"{APP_NAME} <{FROM_EMAIL}>",
        "to": [to_email],
        "subject": f"[JobWave] {heading}",
        "html": base_html("Application Update", body),
    })

# ── Password Reset Email ───────────────────────────────────────────────────────
def send_password_reset(to_email: str, reset_url: str, name: str):
    body = f"""
      <h1>Reset Your Password</h1>
      <p>Hi {name}, we received a request to reset your JobWave password. Click the button below to choose a new one.</p>
      <a href="{reset_url}" class="btn btn-mint">Reset Password →</a>
      <p style="font-size:0.8rem;">This link expires in <strong style="color:#fff;">1 hour</strong>. If you didn't request this, you can safely ignore this email.</p>
      <div class="divider"></div>
      <p style="font-size:0.78rem;">Or copy this link into your browser:<br>
      <span style="color:#8888ff;word-break:break-all;">{reset_url}</span></p>
    """
    client = get_client()
    client.Emails.send({{
        "from": f"{APP_NAME} <{FROM_EMAIL}>",
        "to": [to_email],
        "subject": "Reset your JobWave password",
        "html": base_html("Reset Password", body),
    }})


# ── Job Alert Email ────────────────────────────────────────────────────────────
def send_job_alert(to_email: str, name: str, keyword: str, jobs: list):
    count = len(jobs)
    jobs_html = ""
    for job in jobs[:8]:   # max 8 jobs per email
        salary = ""
        if job.salary_min:
            salary = f'<div class="job-salary">${job.salary_min//1000:,}k - ${job.salary_max//1000:,}k</div>'
        jobs_html += f"""
        <div class="job-card">
          <div class="job-title">{job.title} <span class="badge badge-mint">{job.job_type or 'full-time'}</span></div>
          <div class="job-meta">{job.company} · {job.location or 'N/A'}</div>
          {salary}
        </div>
        """
    body = f"""
      <h1>{count} new job{"s" if count != 1 else ""} for "{keyword}"</h1>
      <p>Hi {name}, we found <strong style="color:#fff;">{count} new listing{"s" if count != 1 else ""}</strong> matching your alert.</p>
      {jobs_html}
      <a href="{APP_URL}/jobs?q={keyword}" class="btn">View All Results →</a>
      <div class="divider"></div>
      <p style="font-size:0.78rem;">You're receiving this because you set up a job alert on JobWave.
      <a href="{APP_URL}/alerts" style="color:#8888ff;">Manage your alerts →</a></p>
    """
    client = get_client()
    client.Emails.send({
        "from": f"{APP_NAME} <{FROM_EMAIL}>",
        "to": [to_email],
        "subject": f"[JobWave] {count} new job{'s' if count != 1 else ''} for \"{keyword}\"",
        "html": base_html("Job Alert", body),
    })


# ── Welcome Email ──────────────────────────────────────────────────────────────
def send_welcome(to_email: str, name: str):
    body = f"""
      <h1>Welcome to JobWave, {name}! 🎉</h1>
      <p>Your account is ready. Here's what you can do on the platform:</p>
      <div class="job-card">
        <div class="job-title">🔍 Browse & Search Jobs</div>
        <div class="job-meta">Filter by keyword, location, salary, experience and more.</div>
      </div>
      <div class="job-card">
        <div class="job-title">📋 Track Applications</div>
        <div class="job-meta">Log every application and track your pipeline from applied to offer.</div>
      </div>
      <div class="job-card">
        <div class="job-title">🔔 Set Job Alerts</div>
        <div class="job-meta">Get email notifications when new matching jobs are posted.</div>
      </div>
      <a href="{APP_URL}/jobs" class="btn btn-mint">Start Browsing Jobs →</a>
    """
    client = get_client()
    client.Emails.send({{
        "from": f"{APP_NAME} <{FROM_EMAIL}>",
        "to": [to_email],
        "subject": f"Welcome to JobWave, {name}!",
        "html": base_html("Welcome", body),
    }})