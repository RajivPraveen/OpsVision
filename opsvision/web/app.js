const $ = (selector) => document.querySelector(selector);
const esc = (value) => String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
const state = {days:'28',supplier:'',plant:'',geography:'',product:'',material:'',dimension:'supplier'};
let loadedOptions = false;
const COLORS = {data:'#3b6ea8', target:'#b45309', grid:'#ececec', axis:'#d4d4cf', muted:'#8a9099', surface:'#ffffff'};

// [key, plain label, unit, higher is better, one-line explanation]
const groups = [
  ['Delivery to customers', [
    ['otif','Delivered on time & complete (OTIF)','%',true,'order lines on time and in full'],
    ['fill_rate','Units shipped of units ordered','%',true,'fill rate'],
    ['perfect_order_rate','Perfect orders','%',true,'on time, complete, and not returned'],
    ['backorder_rate','Orders shipped short','%',false,'backorder rate'],
    ['order_cycle_time','Order-to-delivery time',' days',false,'average, order placed to delivered']]],
  ['Stock and suppliers', [
    ['stockout_rate','Out of stock','%',false,'product-days with less stock than demand'],
    ['days_inventory_outstanding','Days of stock on hand',' days',false,'how long current stock would last'],
    ['inventory_turnover','Stock turnover','×',true,'times stock was sold through in the period'],
    ['forecast_accuracy','Forecast accuracy','%',true,'how close demand forecasts were'],
    ['supplier_lead_time','Supplier lead time',' days',false,'days from ordering parts to receiving them']]],
  ['Production, quality and cost', [
    ['yield','Good units made of units planned','%',true,'manufacturing yield'],
    ['production_downtime','Production time lost to stoppages','%',false,'downtime ÷ planned time'],
    ['defect_rate','Defective units','%',false,'defects ÷ good units'],
    ['scrap_rate','Units scrapped','%',false,'scrap ÷ planned units'],
    ['cost_per_unit','Cost to make one unit','$',false,'production cost ÷ good units']]],
];

function formatMetric(value, unit) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '—';
  if (unit === '$') return '$' + Number(value).toFixed(2);
  if (unit === '×') return Number(value).toFixed(2) + '×';
  return Number(value).toFixed(1) + (unit === '%' ? '%' : unit);
}

function changeLabel(current, prior, highGood, unit) {
  const delta = current - prior;
  if (Math.abs(delta) < 0.05) return '<span class="change flat">no change</span>';
  const better = (delta > 0) === highGood;
  const size = unit === '%' ? `${Math.abs(delta).toFixed(1)} points` : unit === '$' ? `$${Math.abs(delta).toFixed(2)}`
    : unit === '×' ? Math.abs(delta).toFixed(2) : `${Math.abs(delta).toFixed(1)}${unit}`;
  return `<span class="change ${better ? 'good' : 'bad'}">${delta > 0 ? '▲' : '▼'} ${size} ${better ? 'better' : 'worse'}</span>`;
}

function fillOptions(options) {
  for (const key of ['supplier','plant','geography','product','material']) {
    const select = $('#' + key);
    for (const item of options[key] || []) select.insertAdjacentHTML('beforeend', `<option value="${esc(item.id)}">${esc(item.name)}</option>`);
  }
  loadedOptions = true;
}

function renderAnswer(data) {
  const now = data.kpis.otif, before = data.previous_kpis.otif, delta = data.root_cause.total_change_pp;
  const causes = [...data.root_cause.causes].filter(c => c.change_pp < 0).sort((a, b) => a.change_pp - b.change_pp);
  const days = data.period.days;
  let text = `<b>${now.toFixed(0)}%</b> of order lines arrived on time and complete in the last ${days} days`;
  if (Math.abs(delta) < 0.05) { $('#short-answer').innerHTML = text + ', the same as the period before.'; return; }
  text += `, ${delta < 0 ? 'down' : 'up'} from <b>${before.toFixed(0)}%</b> the period before (target: 95%).`;
  if (delta < 0 && causes.length) {
    const top = causes[0], second = causes[1];
    text += ` The biggest cause is <b>${esc(top.reason.toLowerCase())}</b> (${Math.abs(top.change_pp).toFixed(1)} of the ${Math.abs(delta).toFixed(1)} points)`;
    text += second ? `, then ${esc(second.reason.toLowerCase())} (${Math.abs(second.change_pp).toFixed(1)}).` : '.';
  }
  $('#short-answer').innerHTML = text;
}

function renderKpis(data) {
  $('#kpi-groups').innerHTML = groups.map(([title, items]) => `<div class="kpi-group"><h3>${esc(title)}</h3><div class="kpi-grid">${
    items.map(([key, label, unit, highGood, sub]) => {
      const value = data.kpis[key], prior = data.previous_kpis[key];
      return `<article class="kpi-card" title="Previous period: ${formatMetric(prior, unit)}"><div class="label">${esc(label)}</div>` +
        `<div class="value">${formatMetric(value, unit)}</div>${changeLabel(value, prior, highGood, unit)}<span class="sub">${esc(sub)}</span></article>`;
    }).join('')}</div></div>`).join('');
}

function renderCause(data) {
  const bridge = data.root_cause;
  const before = data.previous_kpis.otif, after = data.kpis.otif, delta = bridge.total_change_pp;
  $('#otif-delta').textContent = `${delta > 0 ? '+' : ''}${delta.toFixed(1)} points`;
  $('#otif-delta').classList.toggle('positive', delta >= 0);
  $('#bridge-summary').innerHTML = `<strong>${before.toFixed(1)}%</strong><span class="arrow">→</span><strong>${after.toFixed(1)}%</strong>` +
    `<span class="caption">late or incomplete lines: ${bridge.causes.reduce((s, c) => s + c.previous_count, 0)} → ${bridge.causes.reduce((s, c) => s + c.current_count, 0)}</span>`;
  const max = Math.max(0.1, ...bridge.causes.map(c => Math.abs(c.change_pp)));
  $('#cause-bars').innerHTML = bridge.causes.map(c => {
    const width = Math.max(1.5, 100 * Math.abs(c.change_pp) / max);
    const cls = Math.abs(c.change_pp) < 0.005 ? 'neutral' : c.change_pp > 0 ? 'up' : '';
    const amountCls = Math.abs(c.change_pp) < 0.005 ? 'flat' : c.change_pp > 0 ? 'positive' : '';
    return `<div class="cause-row" title="${c.previous_count} late or short lines before, ${c.current_count} now"><span class="name">${esc(c.reason)}` +
      `<small>${c.previous_count} → ${c.current_count} orders</small></span><span class="bar-track"><span class="bar ${cls}" style="display:block;width:${width}%"></span></span>` +
      `<span class="amount ${amountCls}">${c.change_pp > 0 ? '+' : c.change_pp < 0 ? '−' : ''}${Math.abs(c.change_pp).toFixed(2)} pts</span></div>`;
  }).join('');
}

function renderTrend(trend) {
  const el = $('#trend-chart');
  if (!trend.length) { el.innerHTML = '<div class="empty-state">No weekly data for these filters.</div>'; $('#trend-current').textContent = ''; return; }
  const width = 600, height = 240, left = 40, right = 16, top = 12, bottom = 28;
  const lo = Math.min(70, Math.floor(Math.min(...trend.map(t => t.otif)) / 5) * 5), hi = 100;
  const x = i => left + (width - left - right) * i / Math.max(1, trend.length - 1);
  const y = v => top + (height - top - bottom) * (hi - v) / (hi - lo);
  const points = trend.map((t, i) => `${x(i).toFixed(1)},${y(t.otif).toFixed(1)}`).join(' ');
  const ticks = [];
  for (let n = lo; n <= hi; n += 10) ticks.push(n);
  const grids = ticks.map(n => `<line x1="${left}" x2="${width - right}" y1="${y(n)}" y2="${y(n)}" stroke="${COLORS.grid}"/>` +
    `<text x="${left - 8}" y="${y(n) + 4}" fill="${COLORS.muted}" font-size="11" text-anchor="end">${n}%</text>`).join('');
  const every = Math.max(1, Math.ceil(trend.length / 5));
  const labels = trend.map((t, i) => (i % every === 0 || i === trend.length - 1)
    ? `<text x="${x(i)}" y="${height - 6}" text-anchor="middle" fill="${COLORS.muted}" font-size="11">${esc(t.week.slice(5))}</text>` : '').join('');
  const dots = trend.map((t, i) => `<circle cx="${x(i)}" cy="${y(t.otif)}" r="4.5" fill="${COLORS.data}" stroke="${COLORS.surface}" stroke-width="2">` +
    `<title>Week of ${esc(t.week)}: ${t.otif}% on time and complete (${t.orders} order lines)</title></circle>`).join('');
  const last = trend[trend.length - 1];
  el.innerHTML = `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Weekly on-time, complete delivery">${grids}` +
    `<line x1="${left}" x2="${width - right}" y1="${y(95)}" y2="${y(95)}" stroke="${COLORS.target}" stroke-width="1.5"/>` +
    `<text x="${width - right}" y="${y(95) - 6}" fill="${COLORS.target}" font-size="11" text-anchor="end">target 95%</text>` +
    `<polyline points="${points}" fill="none" stroke="${COLORS.data}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>${dots}${labels}` +
    `<text x="${x(trend.length - 1) - 8}" y="${y(last.otif) + 18}" fill="#1d2127" font-size="12" font-weight="600" text-anchor="end">${last.otif.toFixed(1)}%</text></svg>`;
  $('#trend-current').textContent = `the latest week was ${last.otif.toFixed(1)}%. Hover a dot for that week's numbers.`;
}

function renderAlerts(alerts) {
  $('#alert-count').textContent = alerts.length;
  $('#anomaly-pill').textContent = `${alerts.length} flagged`;
  const distinct = [];
  for (const alert of alerts) if (!distinct.some(item => item.metric === alert.metric)) distinct.push(alert);
  $('#alert-list').innerHTML = distinct.length ? distinct.slice(0, 6).map(a => {
    const u = a.unit === '%' ? '%' : ' ' + a.unit;
    const who = a.label.includes(' · ') ? a.label.split(' · ').slice(1).join(' · ') : a.label;
    const now = a.basis === 'peak' ? `peaked at ${a.recent}${u}` : `averaging ${a.recent}${u}`;
    const others = alerts.filter(b => b.metric === a.metric).length - 1;
    return `<div class="alert-item"><div><strong>${esc(a.metric)}: ${esc(who)}</strong>` +
      `<p>${esc(now)}, against a usual ${a.baseline}${esc(u)}${others > 0 ? ` · ${others} more like this` : ''}</p></div>` +
      `<em>${Math.abs(a.z_score).toFixed(1)}×<small>usual variation</small></em></div>`;
  }).join('') : '<div class="empty-state">Nothing unusual: every reading is within its normal range.</div>';
}

function renderSegments(segments) {
  $('#segment-rows').innerHTML = segments.length ? segments.slice(0, 8).map(s => `<tr title="Click to show only ${esc(s.name)}" data-id="${esc(s.id)}">` +
    `<td>${esc(s.name)}<small>${s.previous_otif !== undefined ? `was ${s.previous_otif.toFixed(1)}%` : ''}</small></td><td>${s.otif.toFixed(1)}%</td>` +
    `<td class="${s.change_pp < 0 ? 'impact-negative' : 'impact-positive'}">${s.change_pp > 0 ? '+' : s.change_pp < 0 ? '−' : ''}${Math.abs(s.change_pp).toFixed(2)} pts</td></tr>`).join('')
    : '<tr><td colspan="3">Nothing matches these filters</td></tr>';
  $('#segment-rows').querySelectorAll('tr[data-id]').forEach(row => row.addEventListener('click', () => {
    const key = state.dimension;
    state[key] = row.dataset.id;
    const input = $('#' + key);
    if (input) input.value = row.dataset.id;
    load();
  }));
}

function renderInventory(items) {
  $('#inventory-rows').innerHTML = items.length ? items.map(i => `<tr><td>${esc(i.product)}<small>${esc(i.warehouse)}</small></td>` +
    `<td>${(i.on_hand_qty - i.allocated_qty).toLocaleString()}</td><td><span class="risk-badge ${i.days_cover >= 7 ? 'ok' : ''}">${i.days_cover.toFixed(1)} days</span></td></tr>`).join('')
    : '<tr><td colspan="3">No stock records</td></tr>';
}

function renderSuppliers(items) {
  $('#supplier-rows').innerHTML = items.length ? items.map(s => `<tr><td>${esc(s.name)}</td><td>${s.orders.toLocaleString()}</td>` +
    `<td class="score ${s.otif < 90 ? 'low' : ''}">${s.otif.toFixed(1)}%</td></tr>`).join('') : '<tr><td colspan="3">No supplier records</td></tr>';
}

function renderForecast(items) {
  const ranked = [...items].sort((a, b) => Math.abs(b.forecast_bias_pct) - Math.abs(a.forecast_bias_pct)).slice(0, 4);
  $('#forecast-list').innerHTML = ranked.length ? ranked.map(item => `<div class="forecast-item"><strong>${esc(item.product)}</strong>` +
    `<small>warehouse ${esc(item.warehouse_id)}</small><span class="number">${item.next_14_days.toLocaleString()}</span><span class="unit">units expected</span>` +
    `<span class="bias">Forecast off by ${item.forecast_bias_pct > 0 ? '+' : item.forecast_bias_pct < 0 ? '−' : ''}${Math.abs(item.forecast_bias_pct).toFixed(1)}% ` +
    `(${item.forecast_bias_pct > 0 ? 'ran high' : item.forecast_bias_pct < 0 ? 'ran low' : 'on target'})</span></div>`).join('')
    : '<div class="empty-state">No forecast records for these filters.</div>';
}

async function load() {
  const params = new URLSearchParams();
  Object.entries(state).forEach(([key, value]) => { if (value) params.set(key, value); });
  const error = $('#error'); error.hidden = true;
  try {
    const response = await fetch('/api/overview?' + params.toString());
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Unable to load the numbers');
    if (!loadedOptions) fillOptions(data.filters);
    const p = data.period;
    $('#date-range').textContent = `${p.orders.toLocaleString()} order lines · ${p.start} to ${p.end} vs. ${p.previous_start} to ${p.previous_end}`;
    renderAnswer(data); renderKpis(data); renderCause(data); renderTrend(data.trend); renderAlerts(data.anomalies);
    renderSegments(data.root_cause.segments); renderInventory(data.inventory_risks);
    renderSuppliers(data.suppliers); renderForecast(data.forecast);
  } catch (exc) { error.textContent = exc.message; error.hidden = false; }
}

for (const key of ['days','supplier','plant','geography','product','material','dimension']) {
  $('#' + key).addEventListener('change', event => { state[key] = event.target.value; load(); });
}
$('#reset').addEventListener('click', () => {
  for (const key of Object.keys(state)) state[key] = key === 'days' ? '28' : key === 'dimension' ? 'supplier' : '';
  for (const key of Object.keys(state)) $('#' + key).value = state[key];
  load();
});
document.querySelectorAll('.sidebar nav .nav-link').forEach(link => link.addEventListener('click', () => {
  document.querySelectorAll('.sidebar nav .nav-link').forEach(l => l.classList.toggle('active', l === link));
}));
load();
