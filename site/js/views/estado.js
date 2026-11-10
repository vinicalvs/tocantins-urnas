// Tela Estado: mapa dos 139 municipios pelo vencedor (ou partido mais votado) e ranking estadual.
import { loadIndex, loadEstado, loadMalha, fmtInt, fmtPct } from '../data.js';
import { escapeHtml, electionOptions, electionKey, electionLabel, parseElection, MAJORITARIOS, CARGO_LABEL } from '../analysis.js';
import { partyColor, hasSlot, OUTROS } from '../colors.js';
import { createMap, choropleth, themeMode, cssVar } from '../map.js';

const swatch = (sg, mode) => `<span class="sw" style="background:${partyColor(sg, mode)}"></span>`;

export function mapParty(m, cargo) {
  if (MAJORITARIOS.has(cargo)) return m.vencedor ? m.vencedor.partido : null;
  return m.partido_mais_votado ? m.partido_mais_votado.sg : null;
}

function tiles(t) {
  const pct = (x) => (t.aptos ? fmtPct((100 * x) / t.aptos) : '–');
  const pc = (x) => (t.comparecimento ? fmtPct((100 * x) / t.comparecimento) : '–');
  return `<div class="tiles">
    <div class="tile"><div class="label">Eleitores aptos</div><div class="value">${fmtInt(t.aptos)}</div></div>
    <div class="tile"><div class="label">Comparecimento</div><div class="value">${pct(t.comparecimento)}</div>
      <div class="note">${fmtInt(t.comparecimento)} eleitores</div></div>
    <div class="tile"><div class="label">Abstenção</div><div class="value">${pct(t.abstencoes)}</div>
      <div class="note">${fmtInt(t.abstencoes)} eleitores</div></div>
    <div class="tile"><div class="label">Brancos e nulos</div><div class="value">${pc(t.brancos + t.nulos + t.nulos_tecnicos)}</div>
      <div class="note">${fmtInt(t.brancos)} brancos · ${fmtInt(t.nulos + t.nulos_tecnicos)} nulos</div></div>
  </div>`;
}

function partyTable(est, cargo, mode) {
  const wins = {};
  for (const m of est.municipios) {
    const p = mapParty(m, cargo);
    if (p) wins[p] = (wins[p] || 0) + 1;
  }
  const eleitos = {};
  for (const c of est.candidatos) if (c.eleito) eleitos[c.partido] = (eleitos[c.partido] || 0) + 1;
  const validos = est.totais.validos || 1;
  const max = Math.max(...est.partidos.map((p) => p.total), 1);
  const winLabel = MAJORITARIOS.has(cargo) ? 'Prefeituras' : 'Mais votado em';
  const rows = est.partidos.slice(0, 25).map((p) => `<tr>
      <td><div class="who">${swatch(p.sg, mode)}<span class="name">${escapeHtml(p.sg)}</span></div></td>
      <td class="num">${fmtInt(wins[p.sg] || 0)}</td>
      <td class="num">${fmtInt(eleitos[p.sg] || 0)}</td>
      <td class="num">${fmtInt(p.total)}<div class="bar" style="width:${(100 * p.total) / max}%"></div></td>
      <td class="num">${fmtPct((100 * p.total) / validos)}</td></tr>`).join('');
  return `<h2>Partidos</h2><div class="table-wrap"><table>
    <caption class="muted" style="text-align:left;caption-side:bottom;padding-top:8px">Votos nominais + legenda.
      ${est.partidos.length > 25 ? `Mostrando 25 de ${est.partidos.length} partidos.` : ''}</caption>
    <thead><tr><th scope="col">Partido</th><th scope="col" class="num">${winLabel}</th>
      <th scope="col" class="num">Eleitos</th><th scope="col" class="num">Votos</th>
      <th scope="col" class="num">% válidos</th></tr></thead><tbody>${rows}</tbody></table></div>`;
}

function candidateTable(est, mode, sel) {
  const top = est.candidatos.slice(0, 30);
  const max = Math.max(...top.map((c) => c.votos), 1);
  const rows = top.map((c, i) => `<tr>
      <td class="num">${i + 1}</td>
      <td><div class="who">${swatch(c.partido, mode)}<span class="name">${escapeHtml(c.nome)}</span></div>
        <span class="muted">${escapeHtml(c.partido)} · ${escapeHtml(c.nr)}</span></td>
      <td>${c.eleito ? '<span class="badge">Eleito</span>' : ''}</td>
      <td class="num">${fmtInt(c.votos)}<div class="bar" style="width:${(100 * c.votos) / max}%"></div></td>
      <td class="num">${fmtPct(c.pct_validos)}</td></tr>`).join('');
  return `<h2>Mais votados no estado — ${escapeHtml(CARGO_LABEL[sel.cargo])}</h2><div class="table-wrap"><table>
    <thead><tr><th scope="col" class="num">#</th><th scope="col">Candidato</th><th scope="col"><span class="sr">Situação</span></th>
      <th scope="col" class="num">Votos</th><th scope="col" class="num">% válidos</th></tr></thead>
    <tbody>${rows}</tbody></table></div>`;
}

function legend(est, cargo, mode) {
  const counts = {};
  let outros = 0;
  for (const m of est.municipios) {
    const p = mapParty(m, cargo);
    if (p && hasSlot(p)) counts[p] = (counts[p] || 0) + 1;
    else if (p) outros += 1;
  }
  const items = Object.entries(counts).sort((a, b) => b[1] - a[1])
    .map(([p, n]) => `<li>${swatch(p, mode)}${escapeHtml(p)} (${n})</li>`);
  if (outros) items.push(`<li><span class="sw" style="background:${OUTROS[mode]}"></span>Outros partidos (${outros})</li>`);
  return `<ul class="legend" aria-label="Legenda do mapa">${items.join('')}</ul>`;
}

function municipalTable(est, index, cargo) {
  const nome = Object.fromEntries(index.municipios.map((m) => [m.cod, m.nome]));
  const rows = [...est.municipios].sort((a, b) => nome[a.cod].localeCompare(nome[b.cod], 'pt-BR')).map((m) => {
    const v = MAJORITARIOS.has(cargo) ? m.vencedor : null;
    const who = v ? `${escapeHtml(v.nome)} (${escapeHtml(v.partido)}) · ${fmtPct(v.pct_validos)}`
      : `${escapeHtml(m.partido_mais_votado?.sg || '–')} · ${fmtInt(m.partido_mais_votado?.total || 0)} votos`;
    return `<tr><td><a href="#/municipio/${escapeHtml(m.cod)}">${escapeHtml(nome[m.cod])}</a></td><td>${who}</td></tr>`;
  }).join('');
  const head = MAJORITARIOS.has(cargo) ? 'Vencedor' : 'Partido mais votado';
  return `<details><summary>Ver como tabela (${est.municipios.length} municípios)</summary><div class="table-wrap"><table>
    <thead><tr><th scope="col">Município</th><th scope="col">${head}</th></tr></thead><tbody>${rows}</tbody></table></div></details>`;
}

export async function render(app, route, stale) {
  const index = await loadIndex();
  const options = electionOptions(index);
  const sel = parseElection(route.params.e, options);
  const [est, malha] = await Promise.all([loadEstado(sel.ano, sel.cargo, sel.turno), loadMalha()]);
  if (stale()) return;
  const mode = themeMode();
  const byIbge = Object.fromEntries(index.municipios.map((m) => [m.ibge, m]));
  const byCod = Object.fromEntries(est.municipios.map((m) => [m.cod, m]));
  const majoritario = MAJORITARIOS.has(sel.cargo);
  const opts = options.map((o) => `<option value="${electionKey(o)}"${electionKey(o) === electionKey(sel) ? ' selected' : ''}>`
    + `${escapeHtml(electionLabel(o))}</option>`).join('');

  app.innerHTML = `
    <h1>Tocantins — ${escapeHtml(electionLabel(sel))}</h1>
    <p class="sub">${majoritario ? 'Cada município pela cor do partido do candidato mais votado.'
      : 'Cada município pela cor do partido mais votado (votos nominais + legenda).'}
      Toque em um município para ver o resultado por local de votação.</p>
    <div class="controls"><label>Eleição<select id="eleicao">${opts}</select></label></div>
    ${tiles(est.totais)}
    <div class="grid2">
      <section class="card" aria-labelledby="t-mapa"><h2 id="t-mapa">Mapa dos municípios</h2>
        <div id="mapa" class="map" role="img" aria-label="Mapa do Tocantins colorido por partido; a mesma informação está na tabela abaixo do mapa."></div>
        ${legend(est, sel.cargo, mode)}
        ${municipalTable(est, index, sel.cargo)}
      </section>
      <section class="card">${majoritario ? '' : candidateTable(est, mode, sel)}
        ${majoritario ? partyTable(est, sel.cargo, mode) : ''}</section>
    </div>
    ${majoritario ? '' : `<section class="card">${partyTable(est, sel.cargo, mode)}</section>`}`;

  app.querySelector('#eleicao').addEventListener('change', (ev) => {
    location.hash = `#/estado?e=${ev.target.value}`;
  });

  const map = createMap(app.querySelector('#mapa'));
  const empty = cssVar('--surface-2');
  choropleth(map, malha, {
    surface: cssVar('--surface'),
    fill: (f) => {
      const m = byIbge[f.properties.codarea];
      const r = m && byCod[m.cod];
      return r ? partyColor(mapParty(r, sel.cargo), mode) : empty;
    },
    tooltip: (f) => {
      const m = byIbge[f.properties.codarea];
      if (!m) return 'Município sem dados';
      const r = byCod[m.cod];
      if (!r) return `<strong>${escapeHtml(m.nome)}</strong><br>Sem ${sel.turno === 2 ? '2º turno' : 'dados'} nesta eleição`;
      const v = r.vencedor;
      const linha = majoritario && v
        ? `${escapeHtml(v.nome)} (${escapeHtml(v.partido)}) · ${fmtPct(v.pct_validos)}`
        : `Partido mais votado: ${escapeHtml(r.partido_mais_votado?.sg || '–')} · ${fmtInt(r.partido_mais_votado?.total || 0)} votos`;
      return `<strong>${escapeHtml(m.nome)}</strong><br>${linha}`;
    },
    onClick: (f) => {
      const m = byIbge[f.properties.codarea];
      if (m) location.hash = `#/municipio/${m.cod}`;
    },
  });
}
