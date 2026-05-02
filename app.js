async function loadData() {
  const res = await fetch(`./data.json?ts=${Date.now()}`, { cache: 'no-store' });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

function esc(s) {
  return String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

function monthName(year, month) {
  return new Date(year, month - 1, 1).toLocaleString(undefined, { month: 'long', year: 'numeric' });
}

function normalizeDetailItems(rawItems) {
  if (!Array.isArray(rawItems)) return [];
  return rawItems.map(item => {
    if (item && typeof item === 'object' && !Array.isArray(item)) return item;
    const text = String(item);
    const idx = text.indexOf(': ');
    if (idx === -1) return { person: '', kind: 'trip', text };
    return {
      person: text.slice(0, idx),
      kind: text.includes('✈') ? 'flight' : (text.includes('Staying in:') ? 'stay' : 'trip'),
      text: text.slice(idx + 2),
    };
  });
}

function cleanTooltipText(text) {
  return String(text).replace(/\s*•\s*[A-Z0-9]{2}\s+\d+\s*$/u, '').trim();
}

function renderTooltipItems(items) {
  const groups = new Map();
  for (const rawItem of items) {
    const item = (rawItem && typeof rawItem === 'object' && !Array.isArray(rawItem))
      ? rawItem
      : { person: '', kind: 'trip', text: String(rawItem) };
    const person = item.person || 'Other';
    if (!groups.has(person)) groups.set(person, []);
    groups.get(person).push({
      kind: item.kind || 'trip',
      text: cleanTooltipText(item.text || ''),
    });
  }
  return [...groups.entries()].map(([person, personItems]) => `
    <div class="day-tooltip-group">
      <div class="day-tooltip-group-title">${esc(person)}</div>
      ${personItems.map(item => `
        <div class="day-tooltip-line kind-${esc(item.kind)}">
          <span class="day-tooltip-text">${esc(item.text)}</span>
        </div>
      `).join('')}
    </div>
  `).join('');
}

function buildMonth(month, today) {
  const first = new Date(month.year, month.month - 1, 1);
  const startWeekday = (first.getDay() + 6) % 7;
  const daysInMonth = new Date(month.year, month.month, 0).getDate();
  const cells = [];

  for (let i = 0; i < startWeekday; i++) {
    cells.push('<div class="day empty"></div>');
  }

  for (let day = 1; day <= daysInMonth; day++) {
    const key = String(day);
    const status = month.days[key] || 'none';
    const classes = ['day', status];
    const detailItems = normalizeDetailItems(month.details?.[key] || []);
    if (today && today.getFullYear() === month.year && today.getMonth() === month.month - 1 && today.getDate() === day) {
      classes.push('today');
    }
    const attrs = detailItems.length ? ` data-day-key="${month.year}-${String(month.month).padStart(2, '0')}-${String(day).padStart(2, '0')}"` : '';
    cells.push(`<div class="${classes.join(' ')}"${attrs}><span>${day}</span></div>`);
  }

  return `
    <section class="month-card">
      <div class="month-header">${monthName(month.year, month.month)}</div>
      <div class="weekdays">
        <div>Mon</div><div>Tue</div><div>Wed</div><div>Thu</div><div>Fri</div><div>Sat</div><div>Sun</div>
      </div>
      <div class="days-grid">${cells.join('')}</div>
    </section>
  `;
}

function buildTooltipMap(payload) {
  const map = new Map();
  for (const month of (payload.months || [])) {
    const details = month.details || {};
    for (const [day, rawItems] of Object.entries(details)) {
      const key = `${month.year}-${String(month.month).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
      map.set(key, renderTooltipItems(normalizeDetailItems(rawItems)));
    }
  }
  return map;
}

function renderLegend(legend) {
  const order = ['none', 'ishir', 'duyen', 'family', 'both'];
  const labels = {
    none: legend.none || 'Home',
    ishir: legend.ishir || 'Ishir away',
    duyen: legend.duyen || 'Duyen away',
    family: legend.family || 'Family away',
    both: legend.both || 'Multiple away',
  };
  return order.map(key => `
    <div class="legend-item">
      <span class="swatch ${key}"></span>
      <span>${labels[key]}</span>
    </div>
  `).join('');
}

async function pollRefreshUntilDone() {
  for (let i = 0; i < 60; i++) {
    const res = await fetch(`./__refresh_status__?ts=${Date.now()}`, { cache: 'no-store' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const state = await res.json();
    if (!state.running) return state;
    await new Promise(r => setTimeout(r, 2000));
  }
  throw new Error('Refresh timed out');
}

function positionTooltip(target, tooltip) {
  const rect = target.getBoundingClientRect();
  const tipRect = tooltip.getBoundingClientRect();
  let left = window.scrollX + rect.left + rect.width / 2 - tipRect.width / 2;
  let top = window.scrollY + rect.top - tipRect.height - 10;
  const minLeft = window.scrollX + 8;
  const maxLeft = window.scrollX + window.innerWidth - tipRect.width - 8;
  left = Math.max(minLeft, Math.min(left, maxLeft));
  if (top < window.scrollY + 8) {
    top = window.scrollY + rect.bottom + 10;
  }
  tooltip.style.left = `${left}px`;
  tooltip.style.top = `${top}px`;
}

function setupTooltips(tooltipMap) {
  const tooltip = document.getElementById('day-tooltip');
  if (!tooltip) return;

  let activeDay = null;

  const showForDay = (day) => {
    const html = tooltipMap.get(day.dataset.dayKey || '');
    if (!html) return;
    tooltip.innerHTML = html;
    tooltip.hidden = false;
    positionTooltip(day, tooltip);
    activeDay = day;
  };

  const hide = () => {
    tooltip.hidden = true;
    activeDay = null;
  };

  document.querySelectorAll('.day[data-day-key]').forEach(day => {
    const show = () => showForDay(day);
    day.addEventListener('mouseenter', show);
    day.addEventListener('mouseleave', () => {
      if (activeDay !== day) tooltip.hidden = true;
    });
    day.addEventListener('focus', show);
    day.addEventListener('blur', () => {
      if (activeDay !== day) tooltip.hidden = true;
    });
    day.addEventListener('click', (event) => {
      event.stopPropagation();
      if (activeDay === day && !tooltip.hidden) {
        hide();
      } else {
        showForDay(day);
      }
    });
  });

  document.addEventListener('click', (event) => {
    if (tooltip.hidden) return;
    if (activeDay && activeDay.contains(event.target)) return;
    hide();
  });

  window.addEventListener('scroll', () => {
    if (activeDay && !tooltip.hidden) positionTooltip(activeDay, tooltip);
  }, { passive: true });

  window.addEventListener('resize', () => {
    if (activeDay && !tooltip.hidden) positionTooltip(activeDay, tooltip);
  });
}

function render(payload) {
  const today = new Date();
  const tooltipMap = buildTooltipMap(payload);
  document.getElementById('updated-at').textContent = `Snapshot generated ${new Date(payload.generated_at).toLocaleString()}`;
  const legendEl = document.querySelector('.legend');
  if (legendEl) legendEl.innerHTML = renderLegend(payload.legend || {});
  const monthsEl = document.getElementById('months-grid');
  if (monthsEl) monthsEl.innerHTML = (payload.months || []).map(m => buildMonth(m, today)).join('');
  setupTooltips(tooltipMap);
}

async function refreshData() {
  const updated = document.getElementById('updated-at');
  updated.textContent = 'Refreshing calendar data…';
  const start = await fetch('./__refresh__', { cache: 'no-store' });
  if (!start.ok) throw new Error(`HTTP ${start.status}`);
  const state = await pollRefreshUntilDone();
  if (state.last_returncode !== 0) {
    throw new Error(state.last_stderr || 'Refresh failed');
  }
  const payload = await loadData();
  render(payload);
}

async function init() {
  const payload = await loadData();
  render(payload);
  document.getElementById('refresh-link')?.addEventListener('click', async (event) => {
    event.preventDefault();
    try {
      await refreshData();
    } catch (err) {
      document.getElementById('updated-at').textContent = `Refresh failed: ${String(err.message || err)}`;
    }
  });
}

init().catch((err) => {
  document.getElementById('updated-at').textContent = `Load failed: ${String(err.message || err)}`;
});
