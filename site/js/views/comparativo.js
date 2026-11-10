// Comparativo 2024 x 2026 por local de votacao (so locais presentes nas duas eleicoes).
import { loadIndex, loadMunicipio, fmtInt, fmtPct } from '../data.js';
import { escapeHtml, compare2426, compareReport, CARGO_LABEL } from '../analysis.js';
import { partyColor } from '../colors.js';
import { themeMode } from '../map.js';

const C24 = ['vereador', 'prefeito'];
const C26 = ['deputado_estadual', 'deputado_federal'];

function partyOf(key, json) {
  if (!key) return null;
  if (key.startsWith('legenda:')) return key.slice(8);
  return json.candidatos.find((c) => String(c.nr) === key)?.partido ?? null;
}

const fmtDelta = (d) => (d === null ? '–' : `${d > 0 ? '+' : d < 0 ? '−' : ''}${fmtPct(Math.abs(d)).replace('%', '')} p.p.`);

export async function render(app, route, stale) {
  const index = await loadIndex();
  const lista = [...index.municipios].sort((a, b) => a.nome.localeCompare(b.nome, 'pt-BR'));
  const cod = route.args[0] && lista.some((m) => m.cod === route.args[0]) ? route.args[0] : '73440';
  const c24 = C24.includes(route.params.a) ? route.params.a : 'vereador';
  const c26 = C26.includes(route.params.b) ? route.params.b : 'deputado_estadual';
  const [j24, j26] = await Promise.all([loadMunicipio(cod, 2024, c24, 1), loadMunicipio(cod, 2026, c26, 1)]);
  if (stale()) return;
  const mode = themeMode();
  const rows = compare2426(j24.locais, j26.locais).sort((a, b) => (a.delta ?? 0) - (b.delta ?? 0));
  const rep = compareReport(j24.locais, j26.locais);
  const mun = lista.find((m) => m.cod === cod);
  const media = (k) => {
    const v = rows.map((r) => r[k]).filter((x) => x !== null);
    return v.length ? v.reduce((s, x) => s + x, 0) / v.length : null;
  };
  const venc = (v, json) => {
    if (!v) return '–';
    const p = partyOf(v.key, json);
    return `<div class="who"><span class="sw" style="background:${partyColor(p, mode)}"></span>`
      + `<span class="name">${escapeHtml(p || '–')} · ${fmtPct(v.pct)}</span></div>`;
  };
  const sel = (id, label, opts, cur) => `<label>${label}<select id="${id}">${opts.map((o) =>
    `<option value="${escapeHtml(o.v)}"${o.v === cur ? ' selected' : ''}>${escapeHtml(o.t)}</option>`).join('')}</select></label>`;
  const body = rows.map((r) => `<tr><td>${escapeHtml(r.nome)}<div class="muted">${escapeHtml(r.id)}</div></td>
      <td class="num">${r.v24 === null ? '–' : fmtPct(r.v24)}</td><td class="num">${r.v26 === null ? '–' : fmtPct(r.v26)}</td>
      <td class="num">${fmtDelta(r.delta)}</td><td>${venc(r.venc24, j24)}</td><td>${venc(r.venc26, j26)}</td></tr>`).join('');
  const fora = rep.so2024 + rep.so2026 + rep.nome_diferente;

  app.innerHTML = `<h1>2024 × 2026 — ${escapeHtml(mun.nome)}</h1>
    <p class="sub">Comparecimento e partido mais votado em cada local de votação, nas duas eleições.</p>
    <div class="controls">
      ${sel('mun', 'Município', lista.map((m) => ({ v: m.cod, t: m.nome })), cod)}
      ${sel('c24', 'Cargo em 2024', C24.map((c) => ({ v: c, t: CARGO_LABEL[c] })), c24)}
      ${sel('c26', 'Cargo em 2026', C26.map((c) => ({ v: c, t: CARGO_LABEL[c] })), c26)}
    </div>
    <p class="note-box">Só entram locais que existem nas duas eleições: mesma zona, mesmo número de local e mesmo nome.
      ${fmtInt(rep.comparados)} locais comparados; ${fmtInt(fora)} ficaram de fora
      (${fmtInt(rep.so2024)} só em 2024, ${fmtInt(rep.so2026)} só em 2026, ${fmtInt(rep.nome_diferente)} com o mesmo número mas outro nome).</p>
    <div class="tiles" style="margin-top:16px">
      <div class="tile"><div class="label">Comparecimento médio 2024</div><div class="value">${media('v24') === null ? '–' : fmtPct(media('v24'))}</div></div>
      <div class="tile"><div class="label">Comparecimento médio 2026</div><div class="value">${media('v26') === null ? '–' : fmtPct(media('v26'))}</div></div>
      <div class="tile"><div class="label">Variação média</div><div class="value">${fmtDelta(media('delta'))}</div>
        <div class="note">média simples entre locais</div></div>
    </div>
    <section class="card"><h2>Locais comparados</h2><div class="table-wrap"><table>
      <caption class="muted" style="text-align:left;caption-side:bottom;padding-top:8px">Ordenado da maior queda para a maior alta
        de comparecimento. p.p. = pontos percentuais.</caption>
      <thead><tr><th scope="col">Local</th><th scope="col" class="num">Compar. 2024</th><th scope="col" class="num">Compar. 2026</th>
        <th scope="col" class="num">Variação</th><th scope="col">Mais votado 2024 (${escapeHtml(CARGO_LABEL[c24])})</th>
        <th scope="col">Mais votado 2026 (${escapeHtml(CARGO_LABEL[c26])})</th></tr></thead>
      <tbody>${body}</tbody></table></div></section>`;

  const go = () => {
    const m = app.querySelector('#mun').value;
    location.hash = `#/comparativo/${m}?a=${app.querySelector('#c24').value}&b=${app.querySelector('#c26').value}`;
  };
  for (const id of ['mun', 'c24', 'c26']) app.querySelector(`#${id}`).addEventListener('change', go);
}
