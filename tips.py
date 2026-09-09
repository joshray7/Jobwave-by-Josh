"""
JobWave — Job Search Tips
---------------------------
Central place for dashboard job search tips. Add a new tip by appending
a dict to JOB_SEARCH_TIPS below — no other files need to change.

Fields:
  title         - short headline shown on the rotating card
  summary       - one-line description shown on the rotating card
  icon          - Font Awesome icon class (without the "fa-solid" prefix)
  guide_html    - full HTML shown inside the modal when clicked
  link_endpoint - Flask route name to link to at the bottom of the guide (or None)
  link_text     - button text for that link (or None)
"""

JOB_SEARCH_TIPS = [
    {
        'title': 'Set alerts for your target role',
        'summary': 'Get notified when new matching jobs are posted.',
        'icon': 'fa-bell',
        'guide_html': '''
            <p>Job alerts run automatically twice a day, so you never have to manually check for new listings.</p>
            <ol style="padding-left:20px;margin-top:10px;display:flex;flex-direction:column;gap:8px;">
                <li>Go to <strong>Alerts</strong> in the sidebar.</li>
                <li>Click <strong>Create Alert</strong> and enter a keyword (e.g. "Frontend Developer") and optionally a location or job type.</li>
                <li>Choose how often you want to be emailed: daily or weekly.</li>
                <li>Save it. JobWave will email you whenever a new job matches.</li>
            </ol>
        ''',
        'link_endpoint': 'alerts',
        'link_text': 'Go to Alerts →',
    },
    {
        'title': 'Track every application',
        'summary': "Don't lose track. Log every job you apply to.",
        'icon': 'fa-clipboard-list',
        'guide_html': '''
            <p>JobWave gives you two ways to track applications depending on where the job came from.</p>
            <ol style="padding-left:20px;margin-top:10px;display:flex;flex-direction:column;gap:8px;">
                <li>For jobs posted directly on JobWave, click <strong>Apply Now</strong>. Your application goes straight to the employer.</li>
                <li>For jobs from other sites, apply on the original site first, then come back and click <strong>Track Application</strong> to log it.</li>
                <li>Update the status yourself as things progress: Interview, Offer, or Rejected.</li>
                <li>See your full pipeline anytime on the <strong>Applications</strong> page.</li>
            </ol>
        ''',
        'link_endpoint': 'applications',
        'link_text': 'Go to Applications →',
    },
    {
        'title': 'Aim for 10+ apps a week',
        'summary': 'Volume and quality together lead to more interviews.',
        'icon': 'fa-bolt',
        'guide_html': '''
            <p>A steady volume of applications keeps your pipeline full while you wait to hear back from earlier ones.</p>
            <ol style="padding-left:20px;margin-top:10px;display:flex;flex-direction:column;gap:8px;">
                <li>Use <strong>Browse Jobs</strong> with filters (salary, location, experience level) to find close matches quickly.</li>
                <li>Save promising roles first, then apply in a batch rather than one at a time.</li>
                <li>Use <strong>Collections</strong> to group jobs by priority, so you always know what to apply to next.</li>
            </ol>
        ''',
        'link_endpoint': 'jobs',
        'link_text': 'Browse Jobs →',
    },
    {
        'title': 'Follow up after interviews',
        'summary': 'A quick thank-you note stands out.',
        'icon': 'fa-comment-dots',
        'guide_html': '''
            <p>A short, genuine follow-up message after an interview keeps you top of mind and shows professionalism.</p>
            <ol style="padding-left:20px;margin-top:10px;display:flex;flex-direction:column;gap:8px;">
                <li>Send it within 24 hours of the interview.</li>
                <li>Thank the interviewer for their time, and mention one specific thing you discussed.</li>
                <li>Keep it short: three to four sentences is enough.</li>
                <li>Update the job's status to <strong>Interview</strong> on your Applications page so you remember where things stand.</li>
            </ol>
        ''',
        'link_endpoint': None,
        'link_text': None,
    },
]


def get_dashboard_tips(url_for_func):
    """Resolve each tip's endpoint into a real URL, ready for the template."""
    resolved = []
    for tip in JOB_SEARCH_TIPS:
        resolved.append({
            'title': tip['title'],
            'summary': tip['summary'],
            'icon': tip['icon'],
            'guide_html': tip['guide_html'],
            'link': url_for_func(tip['link_endpoint']) if tip['link_endpoint'] else None,
            'link_text': tip['link_text'],
        })
    return resolved