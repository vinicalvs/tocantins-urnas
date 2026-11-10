// Tela Candidato: onde o candidato teve votos, tabela ordenavel e CSV.
import { loadIndex, loadMunicipio, fmtInt, fmtPct } from '../data.js';
import { escapeHtml, electionLabel, CARGO_LABEL } from '../analysis.js';
import { partyColor } from '../colors.js';
import { createMap, circleLayer, themeMode, cssVar } from '../map.js';

const NAO_VALIDO = new Set(['branco', 'nulo', 'nulo_tecnico']);

function validosLocal(votos) {
  return Object.entries(votos).reduce((s, [k, v]) => (NAO_VALIDO.has(k) ? s : s + v), 0);
}

export function rowsFor(json, nr) {
  const key = String(nr);
  return json.locais
    .filter((l) => (l.votos[key] || 0) > 0)
    .map((l) => {
      const v = l.votos[key];
      const tot = validosLocal(l.votos);
      return { localId: l.id, nome: l.nome, bairro: l.bairro, votos: v, pct: tot ? (100 * v) / tot : 0 };
    })
    .sort((a, b) => b.votos - a.votos || a.localId.localeCompare(b.localId));
}

export function sortRows(rows, col, dir) {
  const s = dir === 'asc' ? 1 : -1;
  return [...rows].sort((a, b) => {
    const x = a[col];
    const y = b[col];
    const c = typeof x === 'number' ? x - y : String(x ?? '').localeCompare(String(y ?? ''), 'pt-BR');
    return s * c || a.localId.localeCompare(b.localId);
  });
}

const csvCell = (v) => {
  const s = String(v ?? '');
  return /[;"\r\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
};

export function toCsv(rows) {
  const head = ['local', 'nome', 'bairro', 'votos', 'pct_validos_local'];
  const body = rows.map((r) => [r.localId, r.nome, r.bairro, r.votos, r.pct.toFixed(2).replace('.', ',')]
    .map(csvCell).join(';'));
  return [head.join(';'), ...body].join('\r\n') + '\r\n';
}

const COLS = [['nome', 'Local'], ['bairro', 'Bairro'], ['votos', 'Votos'], ['pct', '% no local']];

function tableHtml(rows, sort) {
  const head = COLS.map(([c, label]) => {
    const on = sort.col === c;
    const aria = on ? ` aria-sort="${sort.dir === 'asc' ? 'ascending' : 'descending'}"` : '';
    const num = c === 'votos' || c === 'pct' ? ' class="num"' : '';
    return `<th scope="col"${num}${aria}><button type="button" data-col="${c}">${label}${on ? (sort.dir === 'asc' ? ' ▲' : ' ▼') : ''}</button></th>`;
  }).join('');
  const body = rows.map((r) => `<tr><td>${escapeHtml(r.nome)}<div class="muted">${escapeHtml(r.localId)}</div></td>
    <td>${escapeHtml(r.bairro)}</td><td class="num">${fmtInt(r.votos)}</td><td class="num">${fmtPct(r.pct)}</td></tr>`).join('');
  return `<table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
}

export async function render(app, route, stale) {
  const [cod, eKey, nrStr] = route.args;
  const [ano, cargo, turno] = String(eKey || '').split('-');
  const nr = Number(nrStr);
  const [index, json] = await Promise.all([loadIndex(), loadMunicipio(cod, ano, cargo, turno)]);
  if (stale()) return;
  const mun = index.municipios.find((m) => m.cod === cod);
  const cand = json.candidatos.find((c) => c.nr === nr);
  if (!cand) {
    app.innerHTML = `<p class="error">Candidato ${escapeHtml(nrStr)} não encontrado nesta eleição.</p>`;
    return;
  }
  const mode = themeMode();
  const rows = rowsFor(json, nr);
  const sort = { col: 'votos', dir: 'desc' };
  const elec = { ano: Number(ano), cargo, turno: Number(turno) };
  app.innerHTML = `
    <p><a href="#/municipio/${escapeHtml(cod)}?e=${escapeHtml(eKey)}">← ${escapeHtml(mun?.nome)}</a></p>
    <h1><span class="sw" style="background:${partyColor(cand.partido, mode)};width:16px;height:16px"></span>
      ${escapeHtml(cand.nome)}</h1>
    <p class="sub">${escapeHtml(cand.partido)} · ${escapeHtml(cand.nr)} · ${escapeHtml(CARGO_LABEL[cargo])} em
      ${escapeHtml(mun?.nome)} · ${escapeHtml(electionLabel(elec))}
      ${cand.eleito ? ' · <span class="badge">Eleito</span>' : ''}</p>
    <div class="tiles">
      <div class="tile"><div class="label">Votos no município</div><div class="value">${fmtInt(cand.votos)}</div></div>
      <div class="tile"><div class="label">% dos válidos</div><div class="value">${fmtPct(cand.pct_validos)}</div></div>
      <div class="tile"><div class="label">Locais com voto</div><div class="value">${fmtInt(rows.length)}</div>
        <div class="note">de ${fmtInt(json.locais.length)} locais</div></div>
    </div>
    <div class="grid2">
      <section class="card"><h2>Onde teve votos</h2>
        <div id="mapa" class="map" role="img" aria-label="Locais de votação com votos do candidato; tamanho do círculo proporcional aos votos. Os mesmos dados estão na tabela."></div>
        <p class="muted">Círculo maior = mais votos. Locais sem coordenadas aparecem só na tabela.</p></section>
      <section class="card"><div class="controls" style="justify-content:space-between">
          <h2 style="margin:0">Votos por local</h2>
          <button type="button" class="primary" id="csv">Baixar CSV</button></div>
        <div class="table-wrap" id="tabela">${tableHtml(rows, sort)}</div></section>
    </div>`;

  const tabela = app.querySelector('#tabela');
  tabela.addEventListener('click', (ev) => {
    const b = ev.target.closest('button[data-col]');
    if (!b) return;
    const col = b.dataset.col;
    sort.dir = sort.col === col && sort.dir === 'desc' ? 'asc' : (col === 'nome' || col === 'bairro') && sort.col !== col ? 'asc' : 'desc';
    sort.col = col;
    tabela.innerHTML = tableHtml(sortRows(rows, sort.col, sort.dir), sort);
    tabela.querySelector(`button[data-col="${col}"]`).focus();
  });
  app.querySelector('#csv').addEventListener('click', () => {
    const blob = new Blob(['﻿' + toCsv(sortRows(rows, sort.col, sort.dir))], { type: 'text/csv;charset=utf-8' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `${cod}_${eKey}_${nr}.csv`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  });

  const byId = Object.fromEntries(json.locais.map((l) => [l.id, l]));
  const max = Math.max(...rows.map((r) => r.votos), 1);
  const markers = rows.map((r) => byId[r.localId]).filter((l) => typeof l.lat === 'number' && typeof l.lon === 'number')
    .map((l) => ({ id: l.id, nome: l.nome, lat: l.lat, lon: l.lon, votos: l.votos[String(nr)] }));
  const map = createMap(app.querySelector('#mapa'), { tiles: true });
  circleLayer(map, markers, {
    surface: cssVar('--surface'),
    color: () => partyColor(cand.partido, mode),
    radius: (m) => 4 + 14 * Math.sqrt(m.votos / max),
    tooltip: (m) => `<strong>${escapeHtml(m.nome)}</strong><br>${fmtInt(m.votos)} votos`,
  });
  if (!markers.length) map.setView([-10.2, -48.3], 7);
}
