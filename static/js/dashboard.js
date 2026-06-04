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

/* ─── View Analysis Modal ────────────────────────────────────────────────── */
async function viewAnalysis(id) {
  const modal = document.getElementById('view-modal');
  const body  = document.getElementById('modal-body');
  const title = document.getElementById('modal-title');
  if (!modal || !body) return;

  title.textContent = 'Loading...';
  body.innerHTML = '<div style="padding:2rem;text-align:center;color:var(--muted)">Loading...</div>';
  modal.classList.remove('hidden');
  document.body.style.overflow = 'hidden';

  try {
    const res  = await fetch(`/dashboard/analysis/${id}`);
    if (!res.ok) throw new Error('Failed to load analysis');
    const data = await res.json();

    title.textContent = `${data.asset || 'Analysis'} - Score: ${data.score || '-'}`;

    // Build a container with all the result HTML elements
    body.innerHTML = _buildResultsHTML();
    // Now renderResults into those elements
    if (typeof renderResults === 'function') {
      renderResults(data);
    }
  } catch (err) {
    body.innerHTML = `<div style="padding:2rem;text-align:center;color:var(--down)">${err.message}</div>`;
  }
}

function closeViewModal(event) {
  if (event && event.target !== document.getElementById('view-modal')) return;
  _closeViewModal();
}

function _closeViewModal() {
  const modal = document.getElementById('view-modal');
  if (modal) modal.classList.add('hidden');
  document.body.style.overflow = '';
}

/* ─── Compare Modal ──────────────────────────────────────────────────────── */
async function compareSelected() {
  const ids = Array.from(_selectedIds);
  if (ids.length !== 2) {
    showToast('Select exactly 2 analyses to compare.', 'error');
    return;
  }
  const modal = document.getElementById('compare-modal');
  if (!modal) return;
  modal.classList.remove('hidden');
  document.body.style.overflow = 'hidden';

  const leftBody  = document.getElementById('compare-left-body');
  const rightBody = document.getElementById('compare-right-body');
  const leftTitle  = document.getElementById('compare-left-title');
  const rightTitle = document.getElementById('compare-right-title');

  leftBody.innerHTML  = '<div style="padding:1rem;color:var(--muted)">Loading...</div>';
  rightBody.innerHTML = '<div style="padding:1rem;color:var(--muted)">Loading...</div>';

  try {
    const [dataA, dataB] = await Promise.all(ids.map(id =>
      fetch(`/dashboard/analysis/${id}`).then(r => r.json())
    ));

    leftTitle.textContent  = `${dataA.asset || 'A'} - Score ${dataA.score || '-'}`;
    rightTitle.textContent = `${dataB.asset || 'B'} - Score ${dataB.score || '-'}`;

    leftBody.innerHTML  = _buildResultsHTML('left_');
    rightBody.innerHTML = _buildResultsHTML('right_');

    _renderInContainer(dataA, leftBody, 'left_');
    _renderInContainer(dataB, rightBody, 'right_');
  } catch (err) {
    leftBody.innerHTML  = `<div style="color:var(--down)">${err.message}</div>`;
    rightBody.innerHTML = '';
  }
}

function closeCompareModal(event) {
  if (event && event.target !== document.getElementById('compare-modal')) return;
  const modal = document.getElementById('compare-modal');
  if (modal) modal.classList.add('hidden');
  document.body.style.overflow = '';
}

/* ─── Delete ─────────────────────────────────────────────────────────────── */
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

/* ─── Build results HTML template for modal rendering ────────────────────── */
function _buildResultsHTML(prefix) {
  // Build a minimal results container with the same element IDs app.js expects
  // When used in compare mode, IDs are prefixed to avoid collisions
  const p = prefix || '';
  /* We use a simplified subset that covers the main visible cards */
  return `
    <div id="${p}results" class="results" style="display:flex;flex-direction:column;gap:1.25rem;">
      <!-- Row 1 -->
      <div class="results-top">
        <div class="card header-card">
          <div class="asset-name" id="${p}r-asset">-</div>
          <div class="asset-price" id="${p}r-price">-</div>
          <div id="${p}r-bias-badge" class="bias-badge">-</div>
          <div class="asset-meta" id="${p}r-meta">-</div>
        </div>
        <div class="card gauge-card" id="${p}gauge-card">
          <svg viewBox="0 0 200 120" class="gauge-svg">
            <defs>
              <linearGradient id="${p}gaugeGrad" x1="0%" y1="0%" x2="100%" y2="0%">
                <stop offset="0%" style="stop-color:#ef4444" />
                <stop offset="45%" style="stop-color:#f59e0b" />
                <stop offset="100%" style="stop-color:#10b981" />
              </linearGradient>
            </defs>
            <path d="M 15 105 A 85 85 0 0 1 185 105" fill="none" stroke="#1f2937" stroke-width="18" stroke-linecap="round" />
            <path id="${p}gauge-arc" d="M 15 105 A 85 85 0 0 1 185 105"
                  fill="none" stroke="url(#${p}gaugeGrad)" stroke-width="18" stroke-linecap="round"
                  stroke-dasharray="267" stroke-dashoffset="267"
                  style="transition:stroke-dashoffset 1s ease" />
            <text id="${p}gauge-num" x="100" y="88" text-anchor="middle"
                  font-size="34" fill="#f9fafb" font-weight="700" font-family="Inter">-</text>
            <text x="100" y="108" text-anchor="middle" font-size="10" fill="#6b7280" font-family="Inter">ALIGNMENT SCORE / 100</text>
          </svg>
          <div id="${p}conflict-badges" class="conflict-badges"></div>
        </div>
        <div class="card quick-stats-card">
          <div class="qs-title">Key Indicators</div>
          <table class="qs-table">
            <tr><td class="qs-label">Daily RSI</td><td class="qs-val" id="${p}qs-drsi">-</td></tr>
            <tr><td class="qs-label">Hourly RSI</td><td class="qs-val" id="${p}qs-hrsi">-</td></tr>
            <tr><td class="qs-label">Daily Trend</td><td class="qs-val" id="${p}qs-dtrend">-</td></tr>
            <tr><td class="qs-label">Daily MACD</td><td class="qs-val" id="${p}qs-dmacd">-</td></tr>
            <tr><td class="qs-label">Volatility ATR%</td><td class="qs-val" id="${p}qs-atr">-</td></tr>
            <tr><td class="qs-label">Sentiment</td><td class="qs-val" id="${p}qs-sent">-</td></tr>
          </table>
        </div>
      </div>

      <!-- Key Signal -->
      <div class="card key-signal-card" id="${p}key-signal-card">
        <div class="ks-inner">
          <div class="ks-half" id="${p}ks-signal-half">
            <span class="ks-icon">+</span>
            <div class="ks-content">
              <div class="ks-label">Key Signal</div>
              <div id="${p}ks-text" class="ks-text">-</div>
            </div>
          </div>
          <div class="ks-divider"></div>
          <div class="ks-half" id="${p}ks-risk-half">
            <span class="ks-icon">!</span>
            <div class="ks-content">
              <div class="ks-label">Main Risk</div>
              <div id="${p}ks-risk" class="ks-risk">-</div>
            </div>
          </div>
        </div>
      </div>

      <!-- AI Summary -->
      <div class="card ai-card">
        <div class="card-header">
          <span class="card-title">AI Market Summary</span>
          <span class="ai-provider-badge" id="${p}ai-provider-badge">-</span>
        </div>
        <div class="ai-text" id="${p}ai-summary-text">-</div>
      </div>

      <!-- Technical Tables -->
      <div class="two-col">
        <div class="card">
          <div class="card-header">
            <span class="card-title">Daily Technical</span>
            <span id="${p}daily-dir-badge" class="dir-badge">-</span>
          </div>
          <table class="data-table">
            <thead><tr><th>Indicator</th><th>Value</th><th>Signal</th></tr></thead>
            <tbody id="${p}daily-table"></tbody>
          </table>
          <div class="levels-row">
            <div class="level-box"><span class="level-label">Support</span><span class="level-val down" id="${p}d-support">-</span></div>
            <div class="level-box"><span class="level-label">Resistance</span><span class="level-val up" id="${p}d-resistance">-</span></div>
          </div>
        </div>
        <div class="card">
          <div class="card-header">
            <span class="card-title">Hourly Technical</span>
            <span id="${p}hourly-dir-badge" class="dir-badge">-</span>
          </div>
          <table class="data-table">
            <thead><tr><th>Indicator</th><th>Value</th><th>Signal</th></tr></thead>
            <tbody id="${p}hourly-table"></tbody>
          </table>
          <div class="levels-row">
            <div class="level-box"><span class="level-label">Support</span><span class="level-val down" id="${p}h-support">-</span></div>
            <div class="level-box"><span class="level-label">Resistance</span><span class="level-val up" id="${p}h-resistance">-</span></div>
          </div>
        </div>
      </div>

      <!-- Score Breakdown -->
      <div class="card">
        <div class="card-header"><span class="card-title">Score Breakdown</span></div>
        <div class="breakdown-grid" id="${p}breakdown-grid"></div>
      </div>

      <!-- Trade Guidance -->
      <div class="card tg-card">
        <div class="card-header">
          <span class="card-title">Trade Guidance</span>
          <span id="${p}tg-signal-badge" class="tg-signal-badge">-</span>
        </div>
        <div class="tg-body">
          <div class="tg-left">
            <div class="tg-section-label">Signal Probability</div>
            <div class="tg-prob-track"><div id="${p}tg-fill-up" class="tg-fill-up" style="width:50%"></div><div id="${p}tg-fill-down" class="tg-fill-down" style="width:50%"></div></div>
            <div class="tg-prob-labels"><span id="${p}tg-lbl-up" class="tg-lbl-up">-</span><span id="${p}tg-lbl-down" class="tg-lbl-down">-</span></div>
            <div class="tg-section-label" style="margin-top:1rem">Trade Levels</div>
            <div id="${p}tg-levels"></div>
          </div>
          <div class="tg-right">
            <div class="tg-conf-box">
              <div class="tg-conf-label">Confidence</div>
              <div id="${p}tg-conf-value" class="tg-conf-value">-</div>
              <div id="${p}tg-conf-score" class="tg-conf-score">- / 100</div>
              <div id="${p}tg-conf-advice" class="tg-conf-advice">-</div>
            </div>
          </div>
        </div>
      </div>

      <!-- Sentiment + Intermarket -->
      <div class="two-col" id="${p}inter-sent-row">
        <div class="card" id="${p}intermarket-card">
          <div class="card-title">Intermarket (USD Strength)</div>
          <div class="inter-dollar" id="${p}inter-dollar">-</div>
          <table class="data-table" style="margin-top:0.75rem">
            <tbody>
              <tr><td>EUR/USD Trend</td><td class="qs-val" id="${p}inter-eurusd">-</td></tr>
              <tr><td>USD/JPY Trend</td><td class="qs-val" id="${p}inter-usdjpy">-</td></tr>
            </tbody>
          </table>
          <div id="${p}yield-diff-section" class="yield-diff-section" style="display:none">
            <div class="yd-header">Yield Differential</div>
            <table class="data-table" style="margin-top:0.5rem">
              <tbody>
                <tr><td>US 10Y</td><td class="qs-val" id="${p}yd-us10y">-</td></tr>
                <tr><td>DE 10Y</td><td class="qs-val" id="${p}yd-de10y">-</td></tr>
                <tr><td>Spread</td><td class="qs-val" id="${p}yd-diff">-</td></tr>
              </tbody>
            </table>
            <div id="${p}yd-label" class="yd-dir-label">-</div>
          </div>
        </div>
        <div class="card">
          <div class="card-title">News Sentiment</div>
          <div class="sent-score" id="${p}sent-label">-</div>
          <table class="data-table" style="margin-top:0.75rem">
            <tbody>
              <tr><td>Score</td><td class="qs-val" id="${p}sent-score">-</td></tr>
              <tr><td>Articles Scanned</td><td class="qs-val" id="${p}sent-articles">-</td></tr>
            </tbody>
          </table>
          <div id="${p}sent-headlines" class="sent-headlines" style="display:none">
            <div class="sh-header">Top Headlines</div>
            <div id="${p}sent-headlines-list"></div>
          </div>
        </div>
      </div>

      <!-- COT + Regime -->
      <div class="two-col" id="${p}cot-regime-row">
        <div class="card" id="${p}cot-card" style="display:none">
          <div class="card-header"><span class="card-title">Institutional Positioning (COT)</span><span id="${p}cot-dir-badge" class="dir-badge">-</span></div>
          <div class="cot-net" id="${p}cot-net">-</div>
          <table class="data-table" style="margin-top:0.75rem">
            <tbody>
              <tr><td>Net Position</td><td class="qs-val" id="${p}cot-net-val">-</td></tr>
              <tr><td>Weekly Trend</td><td class="qs-val" id="${p}cot-trend">-</td></tr>
              <tr><td>Currency</td><td class="qs-val" id="${p}cot-currency">-</td></tr>
            </tbody>
          </table>
        </div>
        <div class="card" id="${p}regime-card">
          <div class="card-header"><span class="card-title">Volatility Regime</span><span id="${p}regime-badge" class="regime-badge">-</span></div>
          <div class="regime-label" id="${p}regime-label">-</div>
          <table class="data-table" style="margin-top:0.75rem">
            <tbody>
              <tr><td>ADX (14)</td><td class="qs-val" id="${p}regime-adx">-</td></tr>
              <tr><td>BB Width</td><td class="qs-val" id="${p}regime-bb">-</td></tr>
              <tr><td>BB Expanding</td><td class="qs-val" id="${p}regime-expanding">-</td></tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- Events -->
      <div class="card" id="${p}events-section">
        <div class="card-header"><span class="card-title">Upcoming Economic Events</span><span class="card-sub" id="${p}events-count"></span></div>
        <div id="${p}events-container">
          <table class="data-table events-table">
            <thead><tr><th>Event</th><th>Country</th><th>Impact</th><th>Time (UTC)</th><th>Estimate</th><th>Actual</th></tr></thead>
            <tbody id="${p}events-table"></tbody>
          </table>
        </div>
      </div>

      <!-- Provider footer -->
      <div class="card provider-footer">
        <span class="pf-label">Data:</span>
        <span id="${p}pf-data">-</span>
        <span class="pf-sep">|</span>
        <span class="pf-label">AI:</span>
        <span id="${p}pf-ai">-</span>
        <span class="pf-sep">|</span>
        <span class="pf-label">Generated:</span>
        <span id="${p}pf-time">-</span>
      </div>

      <!-- Hidden stock-only placeholders so renderResults doesn't error -->
      <div class="hidden">
        <div id="${p}earnings-warning-banner"></div>
        <div id="${p}stock-fund-hist-row">
          <div id="${p}fundamentals-card">
            <span id="${p}fund-sector-badge"></span>
            <div id="${p}fund-company-desc" class="hidden"></div>
            <div id="${p}fund-metrics-grid"></div>
            <div id="${p}week52-bar-section" class="hidden"></div>
            <div id="${p}pe-vs-sector-section" class="hidden"></div>
          </div>
          <div id="${p}history-card">
            <span id="${p}hist-dir-badge"></span>
            <div id="${p}hist-label"></div>
            <tbody id="${p}hist-table-body"></tbody>
          </div>
        </div>
        <div id="${p}stock-earn-analyst-row">
          <div id="${p}earnings-card">
            <span id="${p}earnings-record-badge"></span>
            <div id="${p}earnings-next-date"></div>
            <tbody id="${p}earnings-table-body"></tbody>
          </div>
          <div id="${p}analyst-card">
            <span id="${p}analyst-consensus-badge"></span>
            <div id="${p}analyst-target"></div>
            <div id="${p}analyst-bar-wrap"><div id="${p}analyst-bar-fill"></div></div>
            <div id="${p}analyst-bar-legend"></div>
            <tbody id="${p}analyst-ratings-body"></tbody>
          </div>
        </div>
        <div id="${p}insider-card">
          <span id="${p}insider-summary-badge"></span>
          <div id="${p}insider-summary"></div>
          <tbody id="${p}insider-table-body"></tbody>
        </div>
        <div id="${p}stock-short-inst-row">
          <div id="${p}short-interest-card">
            <span id="${p}si-badge"></span>
            <div id="${p}si-main-stat"></div>
            <td id="${p}si-pct"></td><td id="${p}si-dtc"></td><td id="${p}si-squeeze"></td>
          </div>
          <div id="${p}institutional-card">
            <span id="${p}inst-badge"></span>
            <div id="${p}inst-summary"></div>
            <tbody id="${p}inst-table-body"></tbody>
          </div>
        </div>
        <div id="${p}options-sent-card">
          <span id="${p}opt-badge"></span>
          <div id="${p}opt-main"></div>
          <td id="${p}opt-call-oi"></td><td id="${p}opt-put-oi"></td><td id="${p}opt-ratio"></td>
        </div>
      </div>
    </div>
  `;
}

/* ─── Render into a specific container using patched element ID lookup ────── */
function _renderInContainer(data, container, prefix) {
  // Temporarily override document.getElementById to resolve prefixed IDs from container
  const origGetById = document.getElementById.bind(document);
  const patchedGetById = (id) => {
    const el = container.querySelector('#' + prefix + id);
    if (el) return el;
    return origGetById(id);
  };

  // Swap in the patched function, render, then restore
  const backup = document.getElementById.bind(document);
  try {
    document.getElementById = patchedGetById;
    if (typeof renderResults === 'function') {
      renderResults(data);
    }
    // scrollIntoView inside renderResults targets the results div — suppress it in modals
  } finally {
    document.getElementById = backup;
  }
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
