
/* Nowcast tab: renders nowcast/site data (docs/data/nowcast.json, written by the daily nowcast workflow). */
(async function () {
'use strict';
const box = document.getElementById('panel-nowcast');
if (!box) return;
let D;
try {
  const r = await fetch('data/nowcast.json', { cache: 'no-cache' });
  if (!r.ok) throw new Error('HTTP ' + r.status);
  D = await r.json();
} catch (e) {
  document.getElementById('nc-loading').textContent = 'The nowcast data could not be loaded right now. Please try again later.';
  return;
}
document.getElementById('nc-loading').hidden = true; document.getElementById('nc-body').hidden = false;
const $ = (id) => document.getElementById('nc-' + id);
const NS = 'http://www.w3.org/2000/svg';
const MONTHS = ['January','February','March','April','May','June','July','August','September','October','November','December'];
const MON = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
const monthName = (ym) => { const [y, m] = ym.split('-').map(Number); return MONTHS[m - 1] + ' ' + y; };
const dayLabel = (d) => { const t = new Date(d + 'T00:00:00Z'); return MON[t.getUTCMonth()] + ' ' + t.getUTCDate(); };
const f2 = (v) => v == null ? '–' : v.toFixed(2);
const f1 = (v) => v == null ? '–' : v.toFixed(1);
const css = (n) => getComputedStyle(box).getPropertyValue(n).trim();
function el(tag, attrs, text) { const e = document.createElement(tag); if (attrs) for (const k in attrs) e.setAttribute(k, attrs[k]); if (text != null) e.textContent = text; return e; }
function sv(tag, attrs, text) { const e = document.createElementNS(NS, tag); if (attrs) for (const k in attrs) e.setAttribute(k, attrs[k]); if (text != null) e.textContent = text; return e; }
function clear(n) { while (n.firstChild) n.removeChild(n.firstChild); }
const hasCle = !!D.has_cleveland;

/* ---------- tooltip (labels are data: textContent only) ---------- */
const tip = $('tip');
function showTip(x, y, head, rows) {
  clear(tip);
  if (head) tip.appendChild(el('div', { class: 'th' }, head));
  rows.forEach((r) => {
    const row = el('div', { class: 'tr' });
    if (r.key === 'line') { const k = el('span', { class: 'key-line' }); k.style.borderTopColor = r.color; row.appendChild(k); }
    else if (r.key === 'dot') { const k = el('span', { class: 'key-dot' }); k.style.background = r.color; row.appendChild(k); }
    row.appendChild(el('span', null, r.label));
    row.appendChild(el('b', null, r.value));
    tip.appendChild(row);
  });
  tip.classList.add('on');
  const w = tip.offsetWidth, h = tip.offsetHeight;
  let left = x + 14, top = y - h - 10;
  if (left + w > window.innerWidth - 8) left = x - w - 14;
  if (top < 8) top = y + 16;
  tip.style.left = Math.max(8, left) + 'px'; tip.style.top = top + 'px';
}
function hideTip() { tip.classList.remove('on'); }

/* ---------- header, hero, tiles ---------- */
const F = D.fresh;
const meta = $('meta');
[['Last run', D.run_date], ['CPI/PPI through', F.cpi], ['BEA PCE through', F.pce], hasCle ? ['Cleveland Fed as of', F.cleveland] : null].filter(Boolean).forEach(([k, v]) => {
  const s = el('span'); s.appendChild(document.createTextNode(k + ' ')); s.appendChild(el('b', null, v)); meta.appendChild(s);
});
const tiles = D.tiles;
const heroT = tiles[0];
(function hero() {
  const h = $('hero');
  h.appendChild(el('div', { class: 'nc-eyebrow' }, 'Core PCE inflation, ' + monthName(heroT.month) + ' (month over month, nowcast)'));
  const fig = el('div', { class: 'nc-fig' }, f2(heroT.ours)); fig.appendChild(el('small', null, '%')); h.appendChild(fig);
  const parts = [f1(heroT.ours_ann) + '% annualized'];
  if (hasCle && heroT.cleveland != null) parts.push('Cleveland Fed nowcast ' + f2(heroT.cleveland) + '% (' + dayLabel(heroT.cleveland_date) + ')');
  h.appendChild(el('div', { class: 'nc-herosub' }, parts.join('  ·  ')));
  const ks = D.known_share_core[heroT.month];
  h.appendChild(el('p', { class: 'nc-heronote' }, f1(ks).replace('.0', '') + '% of core PCE spending is already priced from released CPI, PPI and import-price data. BEA has not yet published ' + monthName(heroT.month) + '.'));
})();
(function kpis() {
  const k = $('kpis');
  tiles.slice(1).forEach((t) => {
    const d = el('div', { class: 'nc-tile' });
    d.appendChild(el('div', { class: 'lab' }, t.label + ', ' + monthName(t.month)));
    const v = el('div', { class: 'val' }, f2(t.ours)); v.appendChild(el('small', null, '% m/m')); d.appendChild(v);
    const c = el('div', { class: 'cmp' });
    const ow = el('span', { class: 'nw' }); const ko = el('span', { class: 'key-dot' }); ko.style.background = css('--ours'); ow.appendChild(ko); ow.appendChild(document.createTextNode(' Ours')); c.appendChild(ow);
    if (hasCle && t.cleveland != null) {
      const cw = el('span', { class: 'nw' }); const kc = el('span', { class: 'key-dot' }); kc.style.background = css('--cle'); cw.appendChild(kc);
      cw.appendChild(document.createTextNode(' Cleveland Fed ' + f2(t.cleveland))); c.appendChild(cw);
    }
    d.appendChild(c); k.appendChild(d);
  });
  const tb = el('table'); const th = el('tr');
  ['Measure', 'Month', 'Ours (% m/m)', 'Ours (annualized)'].concat(hasCle ? ['Cleveland Fed (% m/m)', 'Ours minus Cleveland (bp)'] : []).forEach((x, i) => th.appendChild(el('th', i > 1 ? { class: 'n' } : null, x)));
  tb.appendChild(th);
  tiles.forEach((t) => {
    const r = el('tr'); r.appendChild(el('td', null, t.label)); r.appendChild(el('td', null, monthName(t.month)));
    [f2(t.ours), f1(t.ours_ann)].concat(hasCle ? [f2(t.cleveland), t.cleveland == null ? '–' : ((t.ours - t.cleveland) * 100).toFixed(0)] : []).forEach((x) => r.appendChild(el('td', { class: 'n' }, x)));
    tb.appendChild(r);
  });
  $('tiletable-body').appendChild(tb);
})();

/* ---------- generic line chart ---------- */
function niceTicks(lo, hi, n) {
  const span = hi - lo, raw = span / n, p = Math.pow(10, Math.floor(Math.log10(raw))), m = raw / p;
  const step = (m < 1.5 ? 1 : m < 3 ? 2 : m < 7 ? 5 : 10) * p;
  const out = []; for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) out.push(+v.toFixed(10));
  return { ticks: out, step };
}
function drawLines(host, o) {
  /* o: {xs:[numbers], xlabel(x), series:[{name,color,kind:'line'|'dots'|'hollow',pts:[[x,y]],width}], ylabel, endLabels:bool, aria, onHover(xi)->{head,rows}} */
  clear(host);
  const W = Math.max(300, host.clientWidth), narrow = W < 520, H = narrow ? 270 : 340;
  const m = { l: 42, r: o.endLabels ? (narrow ? 8 : 150) : 12, t: 12, b: 28 };
  const all = []; o.series.forEach((s) => s.pts.forEach((p) => all.push(p[1])));
  let lo = Math.min.apply(null, all), hi = Math.max.apply(null, all); const pad = (hi - lo) * 0.12 || 0.05; lo -= pad; hi += pad;
  const nt = niceTicks(lo, hi, 5); lo = Math.min(lo, nt.ticks[0]); hi = Math.max(hi, nt.ticks[nt.ticks.length - 1]);
  const x0 = o.xs[0], x1 = o.xs[o.xs.length - 1];
  const X = (x) => m.l + (W - m.l - m.r) * (x1 === x0 ? 0.5 : (x - x0) / (x1 - x0));
  const Y = (y) => m.t + (H - m.t - m.b) * (1 - (y - lo) / (hi - lo));
  const svg = sv('svg', { viewBox: '0 0 ' + W + ' ' + H, width: W, height: H, 'aria-hidden': 'true' });
  const g = sv('g', { class: 'grid' });
  nt.ticks.forEach((t) => { g.appendChild(sv('line', { x1: m.l, x2: W - m.r, y1: Y(t), y2: Y(t) })); svg.appendChild(sv('text', { x: m.l - 6, y: Y(t) + 4, 'text-anchor': 'end' }, o.ylabel(t))); });
  svg.insertBefore(g, svg.firstChild);
  const ax = sv('g', { class: 'axis' }); ax.appendChild(sv('line', { x1: m.l, x2: W - m.r, y1: H - m.b, y2: H - m.b })); svg.appendChild(ax);
  const nx = narrow ? 3 : 5;
  for (let i = 0; i < nx; i++) { const xv = x0 + (x1 - x0) * (nx === 1 ? 0 : i / (nx - 1)); const xx = o.xs.reduce((a, b) => Math.abs(b - xv) < Math.abs(a - xv) ? b : a); svg.appendChild(sv('text', { x: X(xx), y: H - 8, 'text-anchor': i === 0 ? 'start' : i === nx - 1 ? 'end' : 'middle' }, o.xlabel(xx))); }
  const surface = css('--surface-card');
  const ends = [];
  o.series.forEach((s) => {
    if (s.kind === 'line' && s.pts.length > 1) svg.appendChild(sv('polyline', { points: s.pts.map((p) => X(p[0]) + ',' + Y(p[1])).join(' '), fill: 'none', stroke: s.color, 'stroke-width': 2, 'stroke-linejoin': 'round', 'stroke-linecap': 'round' }));
    if (s.kind === 'dots' && s.pts.length > 1) svg.appendChild(sv('polyline', { points: s.pts.map((p) => X(p[0]) + ',' + Y(p[1])).join(' '), fill: 'none', stroke: s.color, 'stroke-width': 2, 'stroke-linejoin': 'round' }));
    s.pts.forEach((p, i) => {
      const last = i === s.pts.length - 1;
      if (s.kind === 'dots' || s.kind === 'hollow' || (s.kind === 'line' && (last || s.pts.length === 1))) {
        const c = sv('circle', { cx: X(p[0]), cy: Y(p[1]), r: s.kind === 'line' ? 4 : 4.5, fill: s.kind === 'hollow' ? surface : s.color, stroke: s.kind === 'hollow' ? s.color : surface, 'stroke-width': 2 });
        svg.appendChild(c);
      }
    });
    if (o.endLabels && s.endLabel && s.pts.length) { const p = s.pts[s.pts.length - 1]; ends.push({ x: X(p[0]), y: Y(p[1]), text: s.endLabel, color: s.color }); }
  });
  if (o.endLabels && !narrow) {                       /* end labels in a right column with leader lines, spaced so they never overlap */
    ends.sort((a, b) => a.y - b.y); let prev = -1e9;
    ends.forEach((e) => { e.ly = Math.max(e.y, prev + 17); prev = e.ly; });
    const over = ends.length ? ends[ends.length - 1].ly - (H - m.b - 4) : 0; if (over > 0) ends.forEach((e) => { e.ly -= over; });
    ends.forEach((e) => {
      const lx = W - m.r + 22;
      svg.appendChild(sv('polyline', { points: e.x + ',' + e.y + ' ' + (W - m.r + 8) + ',' + e.y + ' ' + (W - m.r + 14) + ',' + e.ly + ' ' + (lx - 4) + ',' + e.ly, fill: 'none', stroke: e.color, 'stroke-width': 1 }));
      svg.appendChild(sv('text', { class: 'endlab', x: lx, y: e.ly + 4 }, e.text));
    });
  }
  const cross = sv('line', { y1: m.t, y2: H - m.b, stroke: css('--ink-muted'), 'stroke-width': 1, opacity: 0 }); svg.appendChild(cross);
  const hit = sv('rect', { x: m.l, y: 0, width: W - m.l - m.r, height: H, fill: 'transparent' }); svg.appendChild(hit);
  host.appendChild(svg);
  host.setAttribute('aria-label', o.aria);
  let idx = o.xs.length - 1;
  function at(i, cx, cy) { idx = Math.max(0, Math.min(o.xs.length - 1, i)); const xx = X(o.xs[idx]); cross.setAttribute('x1', xx); cross.setAttribute('x2', xx); cross.setAttribute('opacity', 1); const r = o.onHover(idx); const b = host.getBoundingClientRect(); showTip(cx == null ? b.left + xx : cx, cy == null ? b.top + 40 : cy, r.head, r.rows); }
  function nearest(clientX) { const b = svg.getBoundingClientRect(); const px = (clientX - b.left) * (W / b.width); let best = 0, bd = 1e18; o.xs.forEach((x, i) => { const d = Math.abs(X(x) - px); if (d < bd) { bd = d; best = i; } }); return best; }
  hit.addEventListener('pointermove', (e) => at(nearest(e.clientX), e.clientX, e.clientY));
  hit.addEventListener('pointerleave', () => { cross.setAttribute('opacity', 0); hideTip(); });
  host.onkeydown = (e) => { if (e.key === 'ArrowLeft') { at(idx - 1); e.preventDefault(); } else if (e.key === 'ArrowRight') { at(idx + 1); e.preventDefault(); } else if (e.key === 'Escape') { cross.setAttribute('opacity', 0); hideTip(); } };
  host.onblur = () => { cross.setAttribute('opacity', 0); hideTip(); };
}
function legendItem(parent, kind, color, text) {
  const s = el('span');
  if (kind === 'line') { const k = el('span', { class: 'key-line' }); k.style.borderTopColor = color; s.appendChild(k); }
  else { const k = el('span', { class: 'key-dot' }); if (kind === 'hollow') { k.style.border = '2px solid ' + color; k.style.background = 'transparent'; k.style.width = '10px'; k.style.height = '10px'; } else k.style.background = color; s.appendChild(k); }
  s.appendChild(document.createTextNode(text)); parent.appendChild(s);
}
function table(host, head, rows) {
  clear(host); const tb = el('table'); const th = el('tr');
  head.forEach((h, i) => th.appendChild(el('th', i ? { class: 'n' } : null, h))); tb.appendChild(th);
  rows.forEach((r) => { const tr = el('tr'); r.forEach((c, i) => tr.appendChild(el('td', i ? { class: 'n' } : null, c))); tb.appendChild(tr); });
  host.appendChild(tb);
}

/* ---------- section: path through the month ---------- */
const MEAS = [['core_pce', 'Core PCE'], ['pce', 'Headline PCE'], ['core_cpi', 'Core CPI'], ['cpi', 'Headline CPI']];
const state = { measure: 'core_pce', month: D.pce_months[0], tmeasure: 'core' };
function monthsFor(meas) { return Object.keys(D.series).filter((k) => k.split('|')[0] === meas).map((k) => k.split('|')[1]).sort(); }
function seg(host, items, current, onPick) {
  clear(host);
  items.forEach(([v, lab]) => { const b = el('button', { type: 'button', 'aria-pressed': String(v === current) }, lab); b.addEventListener('click', () => onPick(v)); host.appendChild(b); });
}
const T = (d) => Date.parse(d + 'T00:00:00Z');
function drawPath() {
  seg($('f-measure'), MEAS, state.measure, (v) => { state.measure = v; const ms = monthsFor(v); state.month = ms.indexOf(state.month) >= 0 ? state.month : ms[ms.length - 1]; drawPath(); });
  const ms = monthsFor(state.measure);
  seg($('f-month'), ms.map((m) => [m, monthName(m)]), state.month, (v) => { state.month = v; drawPath(); });
  const S = D.series[state.measure + '|' + state.month];
  const lg = $('path-legend'); clear(lg);
  const cOurs = css('--ours'), cCle = css('--cle'), cNeu = css('--nc-neutral');
  const series = [];
  if (hasCle && S.cleveland.length) { series.push({ name: 'Cleveland Fed nowcast', color: cCle, kind: 'line', pts: S.cleveland.map((p) => [T(p[0]), p[1]]), endLabel: 'Cleveland ' + f2(S.cleveland[S.cleveland.length - 1][1]) }); legendItem(lg, 'line', cCle, 'Cleveland Fed nowcast (daily)'); }
  if (S.ours.length) { series.push({ name: 'Ours', color: cOurs, kind: 'dots', pts: S.ours.map((p) => [T(p[0]), p[1]]), endLabel: 'Ours ' + f2(S.ours[S.ours.length - 1][1]) }); legendItem(lg, 'dot', cOurs, 'Ours (one dot per daily run)'); }
  if (hasCle && S.actual) { series.push({ name: 'Released', color: cNeu, kind: 'dots', pts: [[T(S.actual[0]), S.actual[1]]], endLabel: 'Released ' + f2(S.actual[1]) }); legendItem(lg, 'dot', cNeu, 'Released figure'); }
  const host = $('path-chart');
  if (!series.length) { clear(host); host.appendChild(el('p', { class: 'nc-cap' }, 'No data for this selection.')); return; }
  const xs = Array.from(new Set([].concat.apply([], series.map((s) => s.pts.map((p) => p[0]))))).sort((a, b) => a - b);
  const lastBefore = (pts, x) => { let v = null; pts.forEach((p) => { if (p[0] <= x) v = p; }); return v; };
  const dstr = (x) => new Date(x).toISOString().slice(0, 10);
  drawLines(host, {
    xs, xlabel: (x) => dayLabel(dstr(x)), ylabel: (t) => t.toFixed(2), endLabels: true,
    aria: state.measure.replace('_', ' ') + ' month-over-month nowcast path for ' + monthName(state.month) + ': ' + series.map((s) => s.name + ' ' + f2(s.pts[s.pts.length - 1][1])).join(', '),
    series,
    onHover: (i) => ({ head: dayLabel(dstr(xs[i])), rows: series.map((s) => { const p = lastBefore(s.pts, xs[i]); return p ? { key: s.kind === 'line' ? 'line' : 'dot', color: s.color, label: s.name, value: f2(p[1]) + '%' } : null; }).filter(Boolean) })
  });
  $('path-cap').textContent = 'Month-over-month percent change, seasonally adjusted. ' + (hasCle ? 'Cleveland Fed nowcast: see credit below.' : '');
  const rows = [];
  S.cleveland.forEach((p) => rows.push([p[0], 'Cleveland Fed', f2(p[1])])); S.ours.forEach((p) => rows.push([p[0], 'Ours', f2(p[1])])); if (S.actual) rows.push([S.actual[0], 'Released', f2(S.actual[1])]);
  rows.sort((a, b) => a[0] < b[0] ? -1 : 1); table($('path-table'), ['Date', 'Series', '% m/m'], rows);
}

/* ---------- section: what changed ---------- */
(function changed() {
  const b = $('changed-body'); const c = D.changed;
  if (!c) { b.appendChild(el('p', { class: 'nc-muted', style: 'margin:0' }, 'Appears from the second daily run (the first run was ' + D.first_run + '). It splits each day\'s move in the nowcast into new data releases, updated forecasts for items not yet released, and revisions to items already released.')); return; }
  b.appendChild(el('p', { class: 'nc-cap', style: 'margin:0 0 8px' }, 'Change since the run of ' + c.prev_run + ', in basis points of the monthly percent change.'));
  const rows = c.rows.map((r) => [monthName(r.month), r.why, ((r.bp_headline || 0)).toFixed(1), ((r.bp_core || 0)).toFixed(1)]);
  const h = el('div', { class: 'scroll' }); b.appendChild(h); table(h, ['Month', 'Source of change', 'Headline PCE (bp)', 'Core PCE (bp)'], rows);
})();

/* ---------- section: components (horizontal bars from a zero baseline) ---------- */
function barRows(host, rows, opt) {
  /* rows: [{label, sub, value, est, tip:[head, rows]}] */
  const vals = rows.map((r) => r.value); let lo = Math.min(0, Math.min.apply(null, vals)), hi = Math.max(0, Math.max.apply(null, vals));
  const pad = (hi - lo) * 0.2 || 1; if (lo < 0) lo -= pad; hi += pad;
  const P = (v) => ((v - lo) / (hi - lo)) * 100;
  rows.forEach((r) => {
    const row = el('div', { class: 'brow', tabindex: '0', role: 'group', 'aria-label': r.label + ' ' + r.value.toFixed(1) + ' basis points' + (r.est ? ', estimated' : '') });
    const lab = el('div', { class: 'bl' }, r.label); if (r.sub) { lab.appendChild(document.createTextNode(' ')); lab.appendChild(el('i', null, r.sub)); }
    const tr = el('div', { class: 'track' });
    tr.appendChild(Object.assign(el('div', { class: 'zero' }), {})).style.left = P(0) + '%';
    const b = el('div', { class: 'bar ' + (r.value >= 0 ? 'pos' : 'neg') + (r.est ? ' est' : '') });
    b.style.left = P(Math.min(0, r.value)) + '%'; b.style.width = Math.max(0.4, Math.abs(P(r.value) - P(0))) + '%'; tr.appendChild(b);
    const v = el('div', { class: 'bval' }, (r.value > 0 ? '+' : '') + r.value.toFixed(1)); if (r.value >= 0) v.style.left = 'calc(' + P(r.value) + '% + 6px)'; else v.style.right = 'calc(' + (100 - P(r.value)) + '% + 6px)'; tr.appendChild(v);
    row.appendChild(lab); row.appendChild(tr);
    const show = (e) => { const bb = row.getBoundingClientRect(); showTip(e && e.clientX ? e.clientX : bb.left + 80, e && e.clientY ? e.clientY : bb.top, r.tip[0], r.tip[1]); };
    row.addEventListener('pointermove', show); row.addEventListener('focus', () => show(null)); row.addEventListener('pointerleave', hideTip); row.addEventListener('blur', hideTip);
    host.appendChild(row);
  });
}
(function comps() {
  const m = D.pce_months[0], C = D.components[m];
  $('comp-lede').textContent = monthName(m) + ' PCE, ' + C.n_released + ' of ' + C.n_leaves + ' components already priced from released data. Bars show contributions in basis points of the monthly percent change.';
  const g = $('comp-groups'); g.appendChild(el('div', { class: 'nc-sub' }, 'Contribution to headline PCE, by group (bp)'));
  barRows(g, C.groups.map((x) => ({ label: x.group, sub: Math.round(x.released_share) + '% released', value: x.bp_headline, est: x.released_share < 50,
    tip: [x.group, [{ label: 'Contribution to headline', value: x.bp_headline.toFixed(1) + ' bp' }, { label: 'Share of PCE spending', value: x.spend_share.toFixed(1) + '%' }, { label: 'Priced from released data', value: Math.round(x.released_share) + '%' }]] })));
  const l = $('comp-leaves'); l.appendChild(el('div', { class: 'nc-sub' }, 'Largest items in core PCE (bp contribution to core)'));
  const lg = el('div', { class: 'nc-legend' }); legendItem(lg, 'dot', css('--ours'), 'priced from released data'); legendItem(lg, 'dot', css('--ours-tint'), 'estimated'); l.appendChild(lg);
  barRows(l, C.leaves.map((x) => ({ label: x.label, sub: x.status === 'released' ? '' : '(estimate)', value: x.bp_core, est: x.status !== 'released',
    tip: [x.label, [{ label: 'Contribution to core', value: x.bp_core.toFixed(1) + ' bp' }, { label: 'Price change', value: x.mom.toFixed(2) + '% m/m' }, { label: 'Share of PCE spending', value: x.spend_share.toFixed(2) + '%' }, { label: 'Status', value: x.status === 'released' ? 'released data' : 'estimate' }]] })));
})();

/* ---------- section: track record ---------- */
function drawTrack() {
  const T0 = D.track; if (!T0) { $('track').style.display = 'none'; return; }
  seg($('t-measure'), [['core', 'Core PCE'], ['all', 'Headline PCE']], state.tmeasure, (v) => { state.tmeasure = v; drawTrack(); });
  const k = state.tmeasure, rows = T0.chart, cNeu = css('--nc-baseline'), cOurs = css('--ours');
  const xs = rows.map((r, i) => i);
  const pts = (key) => rows.map((r, i) => r[key + '_' + k] == null ? null : [i, r[key + '_' + k]]).filter(Boolean);
  $('track-cap').textContent = 'The last ' + rows.length + ' of the ' + T0.n_months + ' backtest months, month-over-month percent change. Ours uses BEA component history at today\'s vintage (see below).';
  const lg = $('track-legend'); clear(lg); legendItem(lg, 'line', cNeu, 'BEA first print'); legendItem(lg, 'line', cOurs, 'Ours, after CPI, PPI and import prices'); legendItem(lg, 'hollow', cOurs, 'Ours, before CPI');
  const [mo0, mo1] = [rows[0].month, rows[rows.length - 1].month];
  drawLines($('track-chart'), {
    xs, xlabel: (i) => { const [y, m] = rows[i].month.split('-'); return MON[+m - 1] + ' ' + y.slice(2); }, ylabel: (t) => t.toFixed(1), endLabels: true,
    aria: 'Monthly ' + (k === 'core' ? 'core' : 'headline') + ' PCE inflation, BEA first print against our nowcasts, ' + mo0 + ' to ' + mo1,
    series: [{ name: 'BEA first print', color: cNeu, kind: 'line', pts: pts('fp'), endLabel: 'First print' }, { name: 'Ours, before CPI', color: cOurs, kind: 'hollow', pts: pts('pre') }, { name: 'Ours, after all releases', color: cOurs, kind: 'line', pts: pts('after'), endLabel: 'Ours, after releases' }],
    onHover: (i) => { const r = rows[i], fp = r['fp_' + k], a = r['after_' + k], p = r['pre_' + k];
      return { head: monthName(r.month), rows: [{ key: 'line', color: cNeu, label: 'BEA first print', value: f2(fp) + '%' }, { key: 'line', color: cOurs, label: 'Ours after releases', value: f2(a) + '%  (' + (a - fp >= 0 ? '+' : '') + ((a - fp) * 100).toFixed(1) + ' bp)' }, { key: 'dot', color: cOurs, label: 'Ours before CPI', value: f2(p) + '%  (' + (p - fp >= 0 ? '+' : '') + ((p - fp) * 100).toFixed(1) + ' bp)' }] }; }
  });
  table($('track-table'), ['Month', 'BEA first print', 'Ours, after releases', 'Ours, before CPI'], rows.map((r) => [monthName(r.month), f2(r['fp_' + k]), f2(r['after_' + k]), f2(r['pre_' + k])]));
}
(function mae() {
  const T0 = D.track; if (!T0) return;
  $('mae-cap').textContent = 'Mean absolute miss of the monthly percent change, in basis points, ' + T0.months + ' (' + T0.n_months + ' months). Lower is better.';
  const tb = $('mae'); const th = el('tr'); ['Model', 'Core PCE', 'Headline PCE', 'Months'].forEach((h, i) => th.appendChild(el('th', i ? { class: 'n' } : null, h))); tb.appendChild(th);
  const best = { core: Math.min.apply(null, T0.table.map((r) => r.core)), headline: Math.min.apply(null, T0.table.map((r) => r.headline)) };
  const colr = { ours: css('--ours'), cleveland: css('--cle'), baseline: css('--nc-baseline') };
  T0.table.forEach((r) => {
    const tr = el('tr'); const first = el('td'); const w = el('span', { class: 'metric' }); const k = el('span', { class: 'key-dot' }); k.style.background = colr[r.who]; w.appendChild(k); w.appendChild(document.createTextNode(r.model)); first.appendChild(w); tr.appendChild(first);
    [['core', r.core], ['headline', r.headline]].forEach(([n, v]) => { const td = el('td', { class: 'n' + (v === best[n] ? ' best' : '') }); const m = el('span', { class: 'metric', style: 'justify-content:flex-end' }); const bar = el('span', { class: 'mbar' }); bar.style.width = (v * 5) + 'px'; bar.style.background = colr[r.who]; m.appendChild(bar); m.appendChild(document.createTextNode(f1(v))); td.appendChild(m); tr.appendChild(td); });
    tr.appendChild(el('td', { class: 'n' }, String(r.n))); tb.appendChild(tr);
  });
  $('mae-notes').textContent = 'Ours and the DMS baseline are a partly real-time backtest (BEA component history at today\'s vintage; backtest run ' + T0.backtest_run + '); the DMS baseline is a simplified Knotek-Zaman model. The Cleveland Fed rows are its real-time nowcasts scored against its own recorded actuals (which appear to be BEA\'s first prints). "Before CPI" is the last nowcast before CPI is released; "last before release" is the last nowcast before PCE is. Differences of a basis point or two are within noise.';
})();

/* ---------- credits ---------- */
(function credits() {
  const c = $('cle-credit');
  if (!hasCle) { c.remove(); return; }
  c.appendChild(document.createTextNode('Federal Reserve Bank of Cleveland, "Inflation Nowcasting," '));
  const a1 = el('a', { href: 'https://doi.org/10.26509/frbc-inflationnowcast' }, 'https://doi.org/10.26509/frbc-inflationnowcast'); c.appendChild(a1);
  c.appendChild(document.createTextNode(', licensed under '));
  c.appendChild(el('a', { href: 'https://creativecommons.org/licenses/by/4.0/' }, 'CC BY 4.0'));
  c.appendChild(document.createTextNode('. Cleveland Fed calculations based on data from BLS, BEA, EIA, Financial Times and Haver Analytics. Shown as published; accuracy statistics on this page are our own. No endorsement by the Cleveland Fed is implied.'));
  })();
$('foot-built').textContent = 'Nowcast data from the run of ' + D.run_date + ' (built ' + D.built + '). Updated on weekdays after the daily data run.';

/* ---------- draw & redraw ---------- */
function drawAll() { drawPath(); drawTrack(); }
drawAll();
const visible = () => box.offsetParent !== null;
document.addEventListener('nowcast:show', () => drawAll());                 /* charts are measured, so redraw when the tab becomes visible */
let rt, lastW = document.body.clientWidth;                                    /* redraw only when the width changes */
new ResizeObserver(() => { const w = document.body.clientWidth; if (w === lastW) return; lastW = w; clearTimeout(rt); rt = setTimeout(() => { if (visible()) drawAll(); }, 120); }).observe(document.body);
const themeRedraw = () => { if (visible()) drawAll(); };                      /* colors are baked into the SVG at draw time */
matchMedia('(prefers-color-scheme: dark)').addEventListener('change', themeRedraw);
new MutationObserver(themeRedraw).observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
})();
