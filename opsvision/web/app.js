const $ = (selector) => document.querySelector(selector);
const esc = (value) => String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
const state = {days:'28',supplier:'',plant:'',geography:'',product:'',material:'',dimension:'supplier'};
let loadedOptions = false;

const metrics = [
  ['otif','OTIF','%',true],['fill_rate','Fill rate','%',true],['perfect_order_rate','Perfect order rate','%',true],
  ['stockout_rate','Stockout rate','%',false],['backorder_rate','Backorder rate','%',false],
  ['inventory_turnover','Inventory turnover','×',true],['days_inventory_outstanding','Days inventory outstanding',' days',false],
  ['supplier_lead_time','Supplier lead time',' days',false],['forecast_accuracy','Forecast accuracy','%',true],
  ['defect_rate','Defect rate','%',false],['yield','Manufacturing yield','%',true],
  ['scrap_rate','Scrap rate','%',false],['production_downtime','Production downtime','%',false],
  ['order_cycle_time','Order cycle time',' days',false],['cost_per_unit','Cost per unit','$',false]
];

function formatMetric(value, unit) {
  if (unit === '$') return '$' + Number(value).toFixed(2);
  return Number(value).toFixed(unit === '%' ? 1 : 2) + unit;
}

function changeLabel(current, prior, highGood) {
  const delta = current-prior;
  const good = (delta >= 0) === highGood;
  const sign = delta > 0 ? '+' : '';
  return `<span class="change ${good?'':'bad'}">${sign}${delta.toFixed(1)}</span>`;
}

function fillOptions(options) {
  for (const key of ['supplier','plant','geography','product','material']) {
    const select = $('#' + key);
    for (const item of options[key] || []) select.insertAdjacentHTML('beforeend', `<option value="${esc(item.id)}">${esc(item.name)}</option>`);
  }
  loadedOptions = true;
}

function renderKpis(data) {
  $('#kpi-grid').innerHTML = metrics.map(([key,label,unit,highGood]) => {
    const value = data.kpis[key];
    const prior = data.previous_kpis[key];
    const bad = ((value-prior)>0) !== highGood;
    return `<article class="kpi-card ${bad?'warn':''}" title="Prior period: ${formatMetric(prior,unit)}"><div class="label">${label}</div><div class="value">${formatMetric(value,unit)}</div>${changeLabel(value,prior,highGood)}<span class="sub">vs prior period</span></article>`;
  }).join('');
}

function renderCause(data) {
  const bridge = data.root_cause;
  const before = data.previous_kpis.otif, after = data.kpis.otif;
  const delta = bridge.total_change_pp;
  $('#otif-delta').textContent = `${delta>0?'+':''}${delta.toFixed(1)} pp`;
  $('#otif-delta').classList.toggle('positive',delta>=0);
  $('#bridge-summary').innerHTML = `<strong>${before.toFixed(1)}%</strong><span class="arrow">→</span><strong>${after.toFixed(1)}%</strong><span class="caption">${bridge.previous_orders} → ${bridge.current_orders} order lines</span>`;
  const max = Math.max(0.1,...bridge.causes.map(c => Math.abs(c.change_pp)));
  $('#cause-bars').innerHTML = bridge.causes.map(c => {
    const width = Math.max(2, 100*Math.abs(c.change_pp)/max);
    const sign = c.change_pp>0?'+':'';
    return `<div class="cause-row" title="${c.current_count} current misses vs ${c.previous_count} prior misses"><span class="name">${esc(c.reason)}</span><span class="bar-track"><span class="bar ${c.change_pp>=0?'neutral':''}" style="display:block;width:${width}%"></span></span><span class="amount ${c.change_pp>=0?'positive':''}">${sign}${c.change_pp.toFixed(2)}</span></div>`;
  }).join('');
}

function renderTrend(trend) {
  const el = $('#trend-chart');
  if (!trend.length) {el.innerHTML = '<div class="empty-state">No trend data for this scope.</div>';return;}
  const width=600,height=235,left=38,right=16,top=12,bottom=28;
  const min=65,max=100;
  const x=i=>left+(width-left-right)*i/Math.max(1,trend.length-1);
  const y=v=>top+(height-top-bottom)*(max-v)/(max-min);
  const points=trend.map((item,i)=>`${x(i).toFixed(1)},${y(item.otif).toFixed(1)}`).join(' ');
  const area=`${left},${height-bottom} ${points} ${x(trend.length-1)},${height-bottom}`;
  const grids=[70,80,90,100].map(n=>`<line x1="${left}" x2="${width-right}" y1="${y(n)}" y2="${y(n)}" stroke="#e8eff1" stroke-dasharray="3 4"/><text x="5" y="${y(n)+4}" fill="#9cafb7" font-size="10">${n}%</text>`).join('');
  const labels=trend.filter((_,i)=>i%Math.max(1,Math.ceil(trend.length/5))===0 || i===trend.length-1).map(item=>{
    const i=trend.indexOf(item);return `<text x="${x(i)}" y="${height-4}" text-anchor="middle" fill="#9aadb5" font-size="10">${item.week.slice(5)}</text>`;
  }).join('');
  const dots=trend.map((item,i)=>`<circle cx="${x(i)}" cy="${y(item.otif)}" r="3.4" fill="#0a96a1" stroke="white" stroke-width="2"><title>${item.week}: ${item.otif}% OTIF, ${item.orders} orders</title></circle>`).join('');
  el.innerHTML=`<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Weekly OTIF trend"><defs><linearGradient id="shade" x1="0" x2="0" y1="0" y2="1"><stop stop-color="#3dbdc2" stop-opacity=".23"/><stop offset="1" stop-color="#3dbdc2" stop-opacity="0"/></linearGradient></defs>${grids}<line x1="${left}" x2="${width-right}" y1="${y(95)}" y2="${y(95)}" stroke="#dda757" stroke-dasharray="5 5"/><polygon points="${area}" fill="url(#shade)"/><polyline points="${points}" fill="none" stroke="#0b98a1" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>${dots}${labels}</svg>`;
  $('#trend-current').textContent=`Latest ${trend[trend.length-1].otif.toFixed(1)}%`;
}

function renderAlerts(alerts) {
  $('#alert-count').textContent=alerts.length;
  $('#anomaly-pill').textContent=`${alerts.length} signal${alerts.length===1?'':'s'}`;
  const distinct=[];
  for(const alert of alerts)if(!distinct.some(item=>item.metric===alert.metric))distinct.push(alert);
  $('#alert-list').innerHTML=distinct.length?distinct.slice(0,6).map(a=>{const u=a.unit==='%'?'%':' '+a.unit;return `<div class="alert-item"><span class="alert-icon">!</span><div><strong>${esc(a.label)}</strong><p>${esc(a.metric)} · ${a.recent}${esc(u)} ${a.basis==='peak'?'peak':'recent mean'} vs ${a.baseline}${esc(u)} baseline</p></div><em>${Math.abs(a.z_score).toFixed(1)}σ</em></div>`;}).join(''):'<div class="empty-state">No observations exceed the 2.5σ alert threshold.</div>';
}

function renderSegments(segments) {
  $('#segment-rows').innerHTML=segments.length?segments.slice(0,8).map(s=>`<tr title="Click to filter by ${esc(state.dimension)}" data-id="${esc(s.id)}"><td>${esc(s.name)}</td><td>${s.otif.toFixed(1)}%</td><td class="${s.change_pp<0?'impact-negative':'impact-positive'}">${s.change_pp>0?'+':''}${s.change_pp.toFixed(2)} pp</td></tr>`).join(''):'<tr><td colspan="3">No matching segments</td></tr>';
  $('#segment-rows').querySelectorAll('tr[data-id]').forEach(row=>row.addEventListener('click',()=>{
    const key=state.dimension;
    state[key]=row.dataset.id;
    const input=$('#'+key);
    if(input)input.value=row.dataset.id;
    load();
  }));
}

function renderInventory(items) {
  $('#inventory-rows').innerHTML=items.length?items.map(i=>`<tr><td>${esc(i.product)}<br><span style="color:#9aadb4;font-weight:400">${esc(i.warehouse)}</span></td><td>${i.on_hand_qty-i.allocated_qty}</td><td><span class="risk-badge ${i.days_cover>=7?'ok':''}">${i.days_cover.toFixed(1)} d</span></td></tr>`).join(''):'<tr><td colspan="3">No inventory records</td></tr>';
}

function renderSuppliers(items) {
  $('#supplier-rows').innerHTML=items.length?items.map(s=>`<tr><td>${esc(s.name)}<br><span style="color:#9aadb4;font-weight:400">${esc(s.id)}</span></td><td>${s.orders}</td><td class="score ${s.otif<90?'low':''}">${s.otif.toFixed(1)}%</td></tr>`).join(''):'<tr><td colspan="3">No supplier records</td></tr>';
}

function renderForecast(items) {
  const ranked=[...items].sort((a,b)=>Math.abs(b.forecast_bias_pct)-Math.abs(a.forecast_bias_pct)).slice(0,4);
  $('#forecast-list').innerHTML=ranked.length?ranked.map(item=>`<div class="forecast-item"><strong>${esc(item.product)}</strong><small>${esc(item.warehouse_id)} · next 14 days</small><span class="number">${item.next_14_days.toLocaleString()}</span><span class="bias ${item.forecast_bias_pct<0?'positive':''}">${item.forecast_bias_pct>0?'+':''}${item.forecast_bias_pct.toFixed(1)}% bias</span></div>`).join(''):'<div class="empty-state">No forecast records for this scope.</div>';
}

async function load() {
  const params=new URLSearchParams();
  Object.entries(state).forEach(([key,value])=>{if(value)params.set(key,value)});
  const error=$('#error');error.hidden=true;
  try {
    const response=await fetch('/api/overview?'+params.toString());
    const data=await response.json();
    if(!response.ok)throw new Error(data.error||'Unable to load analytics');
    if(!loadedOptions)fillOptions(data.filters);
    const p=data.period;
    $('#hero-period').textContent=`${p.start} — ${p.end}`;
    $('#date-range').textContent=`${p.orders.toLocaleString()} order lines · ${p.start} to ${p.end}`;
    renderKpis(data);renderCause(data);renderTrend(data.trend);renderAlerts(data.anomalies);
    renderSegments(data.root_cause.segments);renderInventory(data.inventory_risks);
    renderSuppliers(data.suppliers);renderForecast(data.forecast);
  } catch(exc) {error.textContent=exc.message;error.hidden=false;}
}

for(const key of ['days','supplier','plant','geography','product','material','dimension']) {
  $('#'+key).addEventListener('change',event=>{state[key]=event.target.value;load();});
}
$('#reset').addEventListener('click',()=>{
  for(const key of Object.keys(state))state[key]=key==='days'?'28':key==='dimension'?'supplier':'';
  for(const key of Object.keys(state))$('#'+key).value=state[key];
  load();
});
load();
