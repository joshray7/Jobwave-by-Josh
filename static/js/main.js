/* JobWave — main.js */

// ── Sidebar toggle ────────────────────────────────────────────────────────────
const sidebarToggle = document.querySelector('.sidebar-toggle');
const sidebar = document.querySelector('.sidebar');
const overlay = document.querySelector('.sidebar-overlay');

if (sidebarToggle) {
  sidebarToggle.addEventListener('click', () => {
    sidebar.classList.toggle('open');
    overlay?.classList.toggle('show');
  });
}
overlay?.addEventListener('click', () => {
  sidebar.classList.remove('open');
  overlay.classList.remove('show');
});

// ── Flash auto-dismiss ────────────────────────────────────────────────────────
document.querySelectorAll('.flash').forEach(el => {
  setTimeout(() => {
    el.style.transition = 'opacity 0.4s, transform 0.4s';
    el.style.opacity = '0';
    el.style.transform = 'translateY(-6px)';
    setTimeout(() => el.remove(), 400);
  }, 3500);
});

// ── Modal helpers ─────────────────────────────────────────────────────────────
function openModal(id) {
  document.getElementById(id)?.classList.add('open');
}
function closeModal(id) {
  document.getElementById(id)?.classList.remove('open');
}

document.querySelectorAll('[data-modal-open]').forEach(btn => {
  btn.addEventListener('click', () => openModal(btn.dataset.modalOpen));
});
document.querySelectorAll('[data-modal-close]').forEach(btn => {
  btn.addEventListener('click', () => closeModal(btn.dataset.modalClose));
});
document.querySelectorAll('.modal-backdrop').forEach(backdrop => {
  backdrop.addEventListener('click', e => {
    if (e.target === backdrop) backdrop.classList.remove('open');
  });
});

// ── Toast notifications ───────────────────────────────────────────────────────
function showToast(message, type = 'info') {
  const container = document.getElementById('toast-container') || (() => {
    const c = document.createElement('div');
    c.id = 'toast-container';
    c.style.cssText = 'position:fixed;bottom:24px;right:24px;z-index:9999;display:flex;flex-direction:column;gap:8px;';
    document.body.appendChild(c);
    return c;
  })();

  const colors = {
    success: { bg: 'rgba(0,200,100,0.08)', border: 'rgba(0,200,100,0.2)', color: '#00c864' },
    error: { bg: 'rgba(255,60,60,0.08)', border: 'rgba(255,60,60,0.2)', color: '#ff5555' },
    info: { bg: 'rgba(59,0,255,0.1)', border: 'rgba(59,0,255,0.2)', color: '#8888ff' },
  };
  const c = colors[type] || colors.info;
  const icons = { success: '✓', error: '✕', info: 'ℹ' };

  const toast = document.createElement('div');
  toast.style.cssText = `
    padding:12px 16px;border-radius:8px;font-size:0.875rem;font-weight:500;
    font-family:'Space Grotesk',sans-serif;
    background:${c.bg};border:1px solid ${c.border};color:${c.color};
    display:flex;align-items:center;gap:8px;min-width:220px;
    animation:fadeIn 0.3s ease;box-shadow:0 4px 20px rgba(0,0,0,0.4);
  `;
  toast.innerHTML = `<span>${icons[type]}</span><span>${message}</span>`;
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.transition = 'opacity 0.3s, transform 0.3s';
    toast.style.opacity = '0';
    toast.style.transform = 'translateX(20px)';
    setTimeout(() => toast.remove(), 300);
  }, 3000);
}

// ── Save/Unsave jobs ──────────────────────────────────────────────────────────
document.addEventListener('click', async e => {
  const btn = e.target.closest('.save-btn');
  if (!btn) return;
  const jobId = btn.dataset.jobId;
  if (!jobId) return;

  btn.disabled = true;
  try {
    const res = await fetch(`/api/jobs/${jobId}/save`, { method: 'POST' });
    const data = await res.json();
    if (data.saved) {
      btn.classList.add('saved');
      btn.textContent = '♥';
      showToast(data.message, 'success');
    } else {
      btn.classList.remove('saved');
      btn.textContent = '♡';
      showToast(data.message, 'info');
    }
  } catch {
    showToast('Something went wrong', 'error');
  } finally {
    btn.disabled = false;
  }
});

// ── Apply tracking ────────────────────────────────────────────────────────────
document.querySelectorAll('.track-apply-btn').forEach(btn => {
  btn.addEventListener('click', async () => {
    const jobId = btn.dataset.jobId;
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span>';
    try {
      const res = await fetch('/api/applications', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ job_id: parseInt(jobId) })
      });
      const data = await res.json();
      if (data.success) {
        btn.textContent = '✓ Tracking';
        btn.classList.remove('btn-primary');
        btn.classList.add('btn-outline');
        showToast('Application tracked!', 'success');
      } else {
        btn.textContent = 'Already tracked';
        showToast(data.error, 'info');
      }
    } catch {
      showToast('Error tracking application', 'error');
      btn.disabled = false;
    }
  });
});

// ── Update application status ─────────────────────────────────────────────────
document.querySelectorAll('.status-select').forEach(sel => {
  sel.addEventListener('change', async () => {
    const appId = sel.dataset.appId;
    try {
      await fetch(`/api/applications/${appId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: sel.value })
      });
      showToast('Status updated', 'success');
      // Update badge color
      const row = sel.closest('tr');
      if (row) {
        const badge = row.querySelector('.status-badge');
        if (badge) {
          badge.className = 'badge status-badge ' + statusBadgeClass(sel.value);
          badge.textContent = sel.value;
        }
      }
    } catch {
      showToast('Update failed', 'error');
    }
  });
});

function statusBadgeClass(status) {
  const map = { applied: 'badge-indigo', interview: 'badge-amber', offer: 'badge-green', rejected: 'badge-red', withdrawn: 'badge-gray' };
  return map[status] || 'badge-gray';
}

// ── Delete application ────────────────────────────────────────────────────────
document.querySelectorAll('.delete-app-btn').forEach(btn => {
  btn.addEventListener('click', async () => {
    if (!confirm('Remove this application from tracking?')) return;
    const appId = btn.dataset.appId;
    try {
      await fetch(`/api/applications/${appId}`, { method: 'DELETE' });
      btn.closest('tr')?.remove();
      showToast('Application removed', 'info');
    } catch {
      showToast('Delete failed', 'error');
    }
  });
});

// ── Alert toggle ──────────────────────────────────────────────────────────────
document.querySelectorAll('.alert-toggle').forEach(btn => {
  btn.addEventListener('click', async () => {
    const alertId = btn.dataset.alertId;
    try {
      const res = await fetch(`/api/alerts/${alertId}/toggle`, { method: 'POST' });
      const data = await res.json();
      btn.textContent = data.active ? '⏸ Pause' : '▶ Resume';
      showToast(data.active ? 'Alert activated' : 'Alert paused', 'info');
    } catch {
      showToast('Toggle failed', 'error');
    }
  });
});

// ── Delete alert ──────────────────────────────────────────────────────────────
document.querySelectorAll('.delete-alert-btn').forEach(btn => {
  btn.addEventListener('click', async () => {
    if (!confirm('Delete this alert?')) return;
    const alertId = btn.dataset.alertId;
    try {
      await fetch(`/api/alerts/${alertId}`, { method: 'DELETE' });
      btn.closest('.alert-row')?.remove();
      showToast('Alert deleted', 'info');
    } catch {
      showToast('Delete failed', 'error');
    }
  });
});

// ── Create alert form ─────────────────────────────────────────────────────────
const alertForm = document.getElementById('alert-form');
if (alertForm) {
  alertForm.addEventListener('submit', async e => {
    e.preventDefault();
    const data = {
      keyword: alertForm.keyword.value,
      location: alertForm.location?.value || '',
      job_type: alertForm.job_type?.value || '',
      frequency: alertForm.frequency?.value || 'daily',
    };
    try {
      const res = await fetch('/api/alerts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
      });
      if ((await res.json()).success) {
        showToast('Alert created!', 'success');
        closeModal('alert-modal');
        setTimeout(() => location.reload(), 800);
      }
    } catch {
      showToast('Failed to create alert', 'error');
    }
  });
}

// ── Admin scraper trigger handled in admin.html ───────────────────────────────

// ── Admin user toggle ─────────────────────────────────────────────────────────
document.querySelectorAll('.toggle-user-btn').forEach(btn => {
  btn.addEventListener('click', async () => {
    const userId = btn.dataset.userId;
    try {
      const res = await fetch(`/admin/users/${userId}/toggle`, { method: 'POST' });
      const data = await res.json();
      if (data.error) { showToast(data.error, 'error'); return; }
      btn.textContent = data.active ? 'Deactivate' : 'Activate';
      showToast(data.active ? 'User activated' : 'User deactivated', data.active ? 'success' : 'info');
    } catch {
      showToast('Action failed', 'error');
    }
  });
});

// ── Progress bar animate on load ─────────────────────────────────────────────
document.querySelectorAll('.progress-fill[data-width]').forEach(el => {
  setTimeout(() => el.style.width = el.dataset.width, 200);
});

// ── Search debounce ───────────────────────────────────────────────────────────
const liveSearch = document.getElementById('live-search');
if (liveSearch) {
  let debounce;
  liveSearch.addEventListener('input', () => {
    clearTimeout(debounce);
    debounce = setTimeout(() => {
      const form = liveSearch.closest('form');
      if (form) form.submit();
    }, 600);
  });
}

// ── Keyboard shortcuts ────────────────────────────────────────────────────────
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') {
    document.querySelectorAll('.modal-backdrop.open').forEach(m => m.classList.remove('open'));
  }
  if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
    e.preventDefault();
    const searchInput = document.querySelector('input[name="q"]');
    searchInput?.focus();
  }
});