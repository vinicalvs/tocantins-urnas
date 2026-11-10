// Tela Candidato: onde o candidato teve votos, tabela ordenavel e CSV.
// #/candidato/<cod>/<eleicao>/<nr>: por local de votacao no municipio.
// #/candidato/estado/<eleicao>/<nr>: por municipio (cargos estaduais: deputados).
import { loadIndex, loadMunicipio, loadEstado, loadMalha, fmtInt, fmtPct } from '../data.js';
import { escapeHtml, electionLabel, CARGO_LABEL } from '../analysis.js';
import { partyColor } from '../colors.js';
import { createMap, circleLayer, choropleth, themeMode, cssVar } from '../map.js';

const NAO_VALIDO = new Set(['branco', 'nulo', 'nulo_tecnico']);

function validosLocal(votos) {
  return Object.entries(votos).reduce((s, [k, v]) => (NAO_VALIDO.has(k) ? s : s + v), 0);
}

// Link da tela Candidato: cargo estadual (sem `cod`) vai para a visao por municipio.
export function candidatoHref(eKey, c) {
  return c.cod ? `#/candidato/${c.cod}/${eKey}/${c.nr}` : `#/candidato/estado/${eKey}/${c.nr}`;
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

export function rowsForEstado(est, nr, nomes) {
  const cand = est.candidatos.find((c) => c.nr === Number(nr) && !c.cod);
  const validos = Object.fromEntries(est.municipios.map((m) => [m.cod, m.validos]));
  return Object.entries(cand?.municipios || {})
    .filter(([, v]) => v > 0)
    .map(([cod, v]) => ({ localId: cod, nome: nomes[cod] || cod, votos: v, pct: validos[cod] ? (100 * v) / validos[cod] : 0 }))
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

export function toCsv(rows, kind = 'local') {
  const pct = (r) => r.pct.toFixed(2).replace('.', ',');
  const [head, cells] = kind === 'municipio'
    ? [['cod_municipio', 'municipio', 'votos', 'pct_validos_municipio'], (r) => [r.localId, r.nome, r.votos, pct(r)]]
    : [['local', 'nome', 'bairro', 'votos', 'pct_validos_local'], (r) => [r.localId, r.nome, r.bairro, r.votos, pct(r)]];
  const body = rows.map((r) => cells(r).map(csvCell).join(';'));
  return [head.join(';'), ...body].join('\r\n') + '\r\n';
}

const COLS = [['nome', 'Local'], ['bairro', 'Bairro'], ['votos', 'Votos'], ['pct', '% no local']];
const COLS_MUN = [['nome', 'Município'], ['votos', 'Votos'], ['pct', '% no município']];

function tableHtml(rows, sort, cols = COLS) {
  const head = cols.map(([c, label]) => {
    const on = sort.col === c;
    const aria = on ? ` aria-sort="${sort.dir === 'asc' ? 'ascending' : 'descending'}"` : '';
    const num = c === 'votos' || c === 'pct' ? ' class="num"' : '';
    return `<th scope="col"${num}${aria}><button type="button" data-col="${c}">${label}${on ? (sort.dir === 'asc' ? ' ▲' : ' ▼') : ''}</button></th>`;
  }).join('');
  const mun = cols === COLS_MUN;
  const body = rows.map((r) => `<tr><td>${mun
    ? `<a href="#/municipio/${escapeHtml(r.localId)}">${escapeHtml(r.nome)}</a>`
    : `${escapeHtml(r.nome)}<div class="muted">${escapeHtml(r.localId)}</div>`}</td>
    ${mun ? '' : `<td>${escapeHtml(r.bairro)}</td>`}<td class="num">${fmtInt(r.votos)}</td><td class="num">${fmtPct(r.pct)}</td></tr>`).join('');
  return `<table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
}

function wireTable(app, rows, sort, cols, csvName, kind) {
  const tabela = app.querySelector('#tabela');
  tabela.addEventListener('click', (ev) => {
    const b = ev.target.closest('button[data-col]');
    if (!b) return;
    const col = b.dataset.col;
    sort.dir = sort.col === col && sort.dir === 'desc' ? 'asc' : (col === 'nome' || col === 'bairro') && sort.col !== col ? 'asc' : 'desc';
    sort.col = col;
    tabela.innerHTML = tableHtml(sortRows(rows, sort.col, sort.dir), sort, cols);
    tabela.querySelector(`button[data-col="${col}"]`).focus();
  });
  app.querySelector('#csv').addEventListener('click', () => {
    const blob = new Blob(['﻿' + toCsv(sortRows(rows, sort.col, sort.dir), kind)], { type: 'text/csv;charset=utf-8' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = csvName;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  });
}

function mixHex(a, b, t) {
  const rgb = (h) => (/^#[0-9a-f]{6}$/i.test(h) ? [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16)) : null);
  const x = rgb(String(a).trim());
  const y = rgb(String(b).trim());
  if (!x || !y) return b;
  return `#${x.map((v, i) => Math.round(v + (y[i] - v) * t).toString(16).padStart(2, '0')).join('')}`;
}

async function renderEstado(app, eKey, nrStr, stale) {
  const [ano, cargo, turno] = String(eKey || '').split('-');
  const nr = Number(nrStr);
  const [index, est, malha] = await Promise.all([loadIndex(), loadEstado(ano, cargo, turno), loadMalha()]);
  if (stale()) return;
  const cand = est.candidatos.find((c) => c.nr === nr && !c.cod);
  if (!cand) {
    app.innerHTML = `<p class="error">Candidato ${escapeHtml(nrStr)} não encontrado nesta eleição.</p>`;
    return;
  }
  const mode = themeMode();
  const nomes = Object.fromEntries(index.municipios.map((m) => [m.cod, m.nome]));
  const rows = rowsForEstado(est, nr, nomes);
  const sort = { col: 'votos', dir: 'desc' };
  const elec = { ano: Number(ano), cargo, turno: Number(turno) };
  const cor = partyColor(cand.partido, mode);
  app.innerHTML = `
    <p><a href="#/estado?e=${escapeHtml(eKey)}">← Tocantins</a></p>
    <h1><span class="sw" style="background:${cor};width:16px;height:16px"></span> ${escapeHtml(cand.nome)}</h1>
    <p class="sub">${escapeHtml(cand.partido)} · ${escapeHtml(cand.nr)} · ${escapeHtml(electionLabel(elec))}${cand.eleito ? ' · <span class="badge">Eleito</span>' : ''}</p>
    <div class="tiles">
      <div class="tile"><div class="label">Votos no estado</div><div class="value">${fmtInt(cand.votos)}</div></div>
      <div class="tile"><div class="label">% dos válidos</div><div class="value">${fmtPct(cand.pct_validos)}</div></div>
      <div class="tile"><div class="label">Municípios com voto</div><div class="value">${fmtInt(rows.length)}</div>
        <div class="note">de ${fmtInt(est.municipios.length)} municípios</div></div>
    </div>
    <div class="grid2">
      <section class="card"><h2>Onde teve votos</h2>
        <div id="mapa" class="map" role="img" aria-label="Mapa do Tocantins: cor mais forte onde o candidato teve maior parcela dos votos válidos do município. Os mesmos dados estão na tabela."></div>
        <p class="muted">Cor mais forte = maior % dos votos válidos no município. Toque em um município para ver os votos por local.</p></section>
      <section class="card"><div class="controls" style="justify-content:space-between">
          <h2 style="margin:0">Votos por município</h2>
          <button type="button" class="primary" id="csv">Baixar CSV</button></div>
        <div class="table-wrap" id="tabela">${tableHtml(rows, sort, COLS_MUN)}</div></section>
    </div>`;
  wireTable(app, rows, sort, COLS_MUN, `TO_${eKey}_${nr}.csv`, 'municipio');

  const byIbge = Object.fromEntries(index.municipios.map((m) => [m.ibge, m]));
  const byCod = Object.fromEntries(rows.map((r) => [r.localId, r]));
  const maxPct = Math.max(...rows.map((r) => r.pct), 0.01);
  const vazio = cssVar('--surface-2') || cssVar('--surface');
  const map = createMap(app.querySelector('#mapa'));
  choropleth(map, malha, {
    surface: cssVar('--surface'),
    fill: (f) => {
      const r = byCod[byIbge[f.properties.codarea]?.cod];
      return r ? mixHex(vazio, cor, 0.15 + 0.85 * (r.pct / maxPct)) : vazio;
    },
    tooltip: (f) => {
      const m = byIbge[f.properties.codarea];
      if (!m) return 'Município sem dados';
      const r = byCod[m.cod];
      return `<strong>${escapeHtml(m.nome)}</strong><br>${r ? `${fmtInt(r.votos)} votos · ${fmtPct(r.pct)} dos válidos` : 'Sem votos'}`;
    },
    onClick: (f) => {
      const m = byIbge[f.properties.codarea];
      if (m) location.hash = `#/candidato/${m.cod}/${eKey}/${nr}`;
    },
  });
}

export async function render(app, route, stale) {
  if (route.args[0] === 'estado') {
    await renderEstado(app, route.args[1], route.args[2], stale);
    return;
  }
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
  const estadual = cargo === 'deputado_federal' || cargo === 'deputado_estadual';
  app.innerHTML = `
    <p><a href="#/municipio/${escapeHtml(cod)}?e=${escapeHtml(eKey)}">← ${escapeHtml(mun?.nome)}</a>
      ${estadual ? ` · <a href="#/candidato/estado/${escapeHtml(eKey)}/${nr}">Votos em todo o estado</a>` : ''}</p>
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
  wireTable(app, rows, sort, COLS, `${cod}_${eKey}_${nr}.csv`, 'local');

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
