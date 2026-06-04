/* ─── Dashboard JS ───────────────────────────────────────────────────────── */
/* Depends on app.js being loaded first (renderResults function) */

'use strict';

/* ─── State ──────────────────────────────────────────────────────────────── */
let _currentTab = 'forex';
let _selectedIds = new Set();

/* ─── Tab Switching ──────────────────────────────────────────────────────── */
function dbSwitchTab(tab) {
  _currentTab = tab;
  document.getElementById('tab-forex').classList.toggle('active', tab === 'forex');
  document.getElementById('tab-stock').classList.toggle('active', tab === 'stock');
  document.getElementById('panel-forex').classList.toggle('hidden', tab !== 'forex');
  document.getElementById('panel-stock').classList.toggle('hidden', tab !== 'stock');
  _selectedIds.clear();
  _updateToolbar();
}

/* ─── Checkbox Selection ─────────────────────────────────────────────────── */
function toggleSelectAll(tab, checked) {
  const tbody = document.getElementById('tbody-' + tab);
  if (!tbody) return;
  tbody.querySelectorAll('.row-check').forEach(cb => {
    cb.checked = checked;
    const row  = cb.closest('tr');
    if (row) {
      const id = row.dataset.id;
      if (checked) _selectedIds.add(id);
      else         _selectedIds.delete(id);
      row.classList.toggle('selected', checked);
    }
  });
  _updateToolbar();
}

function onRowCheck() {
  _selectedIds.clear();
  const activePanel = document.getElementById('panel-' + _currentTab);
  if (activePanel) {
    activePanel.querySelectorAll('tr[data-id]').forEach(row => {
      const cb = row.querySelector('.row-check');
      if (cb && cb.checked) {
        _selectedIds.add(row.dataset.id);
        row.classList.add('selected');
      } else {
        row.classList.remove('selected');
      }
    });
  }
  _updateToolbar();
}

function _updateToolbar() {
  const toolbar   = document.getElementById('db-toolbar');
  const countEl   = document.getElementById('toolbar-count');
  const compareBtn = document.getElementById('btn-compare');
  const n = _selectedIds.size;

  if (toolbar) toolbar.classList.toggle('hidden', false); // always visible for export all
  if (countEl) countEl.textContent = n > 0 ? `${n} selected` : '0 selected';
  if (compareBtn) compareBtn.disabled = (n !== 2);

  // Close any open export dropdowns when selection changes
  document.querySelectorAll('.tb-drop').forEach(d => d.classList.add('hidden'));
}

/* ─── Export Dropdown Toggle ────────────────────────────────────────────── */
function toggleExportDrop(btn) {
  const drop = btn.nextElementSibling;
  if (!drop) return;
  // Close all other dropdowns first
  document.querySelectorAll('.tb-drop').forEach(d => { if (d !== drop) d.classList.add('hidden'); });
  drop.classList.toggle('hidden');
}

document.addEventListener('click', e => {
  if (!e.target.closest('.tb-export-wrap')) {
    document.querySelectorAll('.tb-drop').forEach(d => d.classList.add('hidden'));
  }
});

/* ─── View Analysis Modal (iframe-based) ─────────────────────────────────── */
function viewAnalysis(id, asset, score) {
  const modal  = document.getElementById('view-modal');
  const iframe = document.getElementById('view-iframe');
  const title  = document.getElementById('modal-title');
  if (!modal || !iframe) return;

  if (title) title.textContent = `${asset || 'Analysis'} - Score: ${score != null ? score : '-'}`;
  // Each iframe is a fully isolated document — no element-id collisions possible
  iframe.src = `/dashboard/view/${id}?embed=1`;
  modal.classList.remove('hidden');
  document.body.style.overflow = 'hidden';
}

function closeViewModal(event) {
  if (event && event.target !== document.getElementById('view-modal')) return;
  _closeViewModal();
}

function _closeViewModal() {
  const modal  = document.getElementById('view-modal');
  const iframe = document.getElementById('view-iframe');
  if (modal) modal.classList.add('hidden');
  if (iframe) iframe.src = 'about:blank';   // free the loaded page
  document.body.style.overflow = '';
}

/* ─── Compare Modal (two iframes) ────────────────────────────────────────── */
function compareSelected() {
  const ids = Array.from(_selectedIds);
  if (ids.length !== 2) {
    showToast('Select exactly 2 analyses to compare.', 'error');
    return;
  }
  const modal = document.getElementById('compare-modal');
  if (!modal) return;

  const leftIframe  = document.getElementById('compare-left-iframe');
  const rightIframe = document.getElementById('compare-right-iframe');
  const leftTitle   = document.getElementById('compare-left-title');
  const rightTitle  = document.getElementById('compare-right-title');

  // Pull asset/score labels from the table rows we already have
  const [a, b] = ids.map(_rowMeta);
  if (leftTitle)  leftTitle.textContent  = `${a.asset} - Score ${a.score}`;
  if (rightTitle) rightTitle.textContent = `${b.asset} - Score ${b.score}`;

  leftIframe.src  = `/dashboard/view/${ids[0]}?embed=1`;
  rightIframe.src = `/dashboard/view/${ids[1]}?embed=1`;

  modal.classList.remove('hidden');
  document.body.style.overflow = 'hidden';
}

function _rowMeta(id) {
  const row = document.querySelector(`tr[data-id="${id}"]`);
  if (!row) return { asset: 'Analysis', score: '-' };
  const asset = row.querySelector('.col-asset')?.textContent.trim() || 'Analysis';
  const score = row.querySelector('.col-score')?.textContent.trim() || '-';
  return { asset, score };
}

function closeCompareModal(event) {
  if (event && event.target !== document.getElementById('compare-modal')) return;
  const modal       = document.getElementById('compare-modal');
  const leftIframe  = document.getElementById('compare-left-iframe');
  const rightIframe = document.getElementById('compare-right-iframe');
  if (modal) modal.classList.add('hidden');
  if (leftIframe)  leftIframe.src  = 'about:blank';
  if (rightIframe) rightIframe.src = 'about:blank';
  document.body.style.overflow = '';
}

/* ─── Delete ─────────────────────────────────────────────────────────────── */
function deleteOneAnalysis(id) {
  const msg = 'Delete this analysis? This cannot be undone.';
  document.getElementById('confirm-msg').textContent = msg;
  const yesBtn = document.getElementById('confirm-yes-btn');
  yesBtn.onclick = () => _performDelete([id]);
  document.getElementById('confirm-modal').classList.remove('hidden');
  document.body.style.overflow = 'hidden';
}

function deleteSelected() {
  if (_selectedIds.size === 0) return;
  const ids = Array.from(_selectedIds);
  const msg = `Delete ${ids.length} selected analysis${ids.length > 1 ? 'es' : ''}? This cannot be undone.`;
  document.getElementById('confirm-msg').textContent = msg;
  const yesBtn = document.getElementById('confirm-yes-btn');
  yesBtn.onclick = () => _performDelete(ids);
  document.getElementById('confirm-modal').classList.remove('hidden');
  document.body.style.overflow = 'hidden';
}

async function _performDelete(ids) {
  closeConfirmModal();
  try {
    const res = await fetch('/api/dashboard/analyses', {
      method:  'DELETE',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ ids }),
    });
    if (!res.ok) throw new Error('Delete failed');
    ids.forEach(id => {
      _selectedIds.delete(id);
      const row = document.querySelector(`tr[data-id="${id}"]`);
      if (row) row.remove();
    });
    _updateToolbar();
    showToast(`Deleted ${ids.length} analysis${ids.length > 1 ? 'es' : ''}.`, 'ok');
  } catch (err) {
    showToast('Delete failed: ' + err.message, 'error');
  }
}

function closeConfirmModal(event) {
  if (event && event.target !== document.getElementById('confirm-modal')) return;
  document.getElementById('confirm-modal').classList.add('hidden');
  document.body.style.overflow = '';
}

/* ─── Export ─────────────────────────────────────────────────────────────── */
function exportSelected(format) {
  const ids = Array.from(_selectedIds);
  if (!ids.length) { showToast('No analyses selected.', 'error'); return; }
  const qs = `format=${format}&ids=${ids.join(',')}`;
  window.location.href = `/api/dashboard/export?${qs}`;
}

function exportAll(format) {
  window.location.href = `/api/dashboard/export?format=${format}&asset_type=${_currentTab}`;
}

function exportSelectedPDF() {
  // Inject print-specific inline display of selected rows then print
  window.print();
}

/* ─── Admin Panel ────────────────────────────────────────────────────────── */
function toggleAdminPanel() {
  const panel = document.getElementById('admin-panel');
  if (!panel) return;
  panel.classList.toggle('hidden');
  if (!panel.classList.contains('hidden')) {
    loadAdminUsers();
  }
}

async function loadAdminUsers() {
  const tbody = document.getElementById('admin-users-body');
  if (!tbody) return;
  tbody.innerHTML = '<tr><td colspan="7" class="empty-row">Loading...</td></tr>';
  try {
    const res   = await fetch('/api/admin/users');
    if (!res.ok) throw new Error('Failed to load');
    const users = await res.json();
    if (!users.length) {
      tbody.innerHTML = '<tr><td colspan="7" class="empty-row">No users found.</td></tr>';
      return;
    }
    tbody.innerHTML = users.map(u => `
      <tr>
        <td><strong>${_esc(u.name || '-')}</strong></td>
        <td>${_esc(u.email || '-')}</td>
        <td class="col-date">${(u.created_at || '').slice(0, 10)}</td>
        <td class="col-date">${(u.last_seen || '-').slice(0, 10)}</td>
        <td>${u.analysis_count || 0}</td>
        <td>
          <span class="bias-mini ${u.is_active ? 'up' : 'down'}">
            ${u.is_active ? 'Active' : 'Inactive'}
          </span>
          ${u.is_admin ? '<span class="bias-mini neutral" style="margin-left:0.3rem">Admin</span>' : ''}
        </td>
        <td>
          <a href="/dashboard?user_id=${u.id}" class="tb-btn" style="margin-right:0.35rem;font-size:0.75rem">View</a>
          ${u.is_active
            ? `<button class="tb-btn tb-delete" onclick="adminDeactivate('${u.id}', this)" style="font-size:0.75rem">Deactivate</button>`
            : `<button class="tb-btn" onclick="adminActivate('${u.id}', this)" style="font-size:0.75rem">Activate</button>`
          }
        </td>
      </tr>
    `).join('');
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="7" class="empty-row" style="color:var(--down)">${err.message}</td></tr>`;
  }
}

async function adminDeactivate(uid, btn) {
  btn.disabled = true;
  try {
    await fetch(`/api/admin/users/${uid}/deactivate`, { method: 'POST' });
    showToast('User deactivated.', 'ok');
    loadAdminUsers();
  } catch (err) {
    showToast('Failed: ' + err.message, 'error');
    btn.disabled = false;
  }
}

async function adminActivate(uid, btn) {
  btn.disabled = true;
  try {
    await fetch(`/api/admin/users/${uid}/activate`, { method: 'POST' });
    showToast('User activated.', 'ok');
    loadAdminUsers();
  } catch (err) {
    showToast('Failed: ' + err.message, 'error');
    btn.disabled = false;
  }
}

/* ─── Toast ──────────────────────────────────────────────────────────────── */
let _toastTimer = null;
function showToast(msg, type = 'ok') {
  const toast = document.getElementById('db-toast');
  if (!toast) return;
  toast.textContent = msg;
  toast.className   = `db-toast toast-${type}`;
  toast.classList.remove('hidden');
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => toast.classList.add('hidden'), 3500);
}

/* ─── Helper: escape HTML ────────────────────────────────────────────────── */
function _esc(str) {
  return String(str || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

/* ─── Keyboard: Escape closes modals ────────────────────────────────────── */
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') {
    _closeViewModal();
    closeCompareModal();
    closeConfirmModal();
    document.querySelectorAll('.tb-drop').forEach(d => d.classList.add('hidden'));
  }
});

/* ─── Init ───────────────────────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
  // Always show toolbar (for "Export All" even when 0 selected)
  const toolbar = document.getElementById('db-toolbar');
  if (toolbar) toolbar.classList.remove('hidden');
});
