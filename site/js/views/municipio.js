// Tela Municipio: busca por nome; resultado por cargo, eleitos, comparecimento; mapa dos locais.
import { loadIndex, loadMunicipio, fmtInt, fmtPct, normalizeText } from '../data.js';
import { escapeHtml, winnerByLocal, availableTurnos, electionLabel, CARGO_LABEL, MAJORITARIOS } from '../analysis.js';
import { partyColor } from '../colors.js';
import { createMap, circleLayer, markersFromLocais, themeMode, cssVar } from '../map.js';

const swatch = (sg, mode) => `<span class="sw" style="background:${partyColor(sg, mode)}"></span>`;

function searchView(app, index) {
  const lista = [...index.municipios].sort((a, b) => a.nome.localeCompare(b.nome, 'pt-BR'));
  app.innerHTML = `<h1>Municípios</h1>
    <p class="sub">Busque pelo nome (acentos são opcionais). ${lista.length} municípios.</p>
    <div class="controls"><label style="flex:1;min-width:0">Nome do município
      <input type="search" id="busca" autocomplete="off" placeholder="Ex.: Araguaina"></label></div>
    <p id="contagem" class="muted" aria-live="polite"></p>
    <ul id="lista" class="card" style="list-style:none;margin:0;padding:8px 16px;columns:16rem"></ul>`;
  const ul = app.querySelector('#lista');
  const cnt = app.querySelector('#contagem');
  const draw = (q) => {
    const n = normalizeText(q);
    const hits = lista.filter((m) => normalizeText(m.nome).includes(n));
    cnt.textContent = `${hits.length} município${hits.length === 1 ? '' : 's'}`;
    ul.innerHTML = hits.map((m) => `<li style="padding:6px 0;break-inside:avoid">
      <a href="#/municipio/${escapeHtml(m.cod)}">${escapeHtml(m.nome)}</a>
      <span class="muted"> · ${fmtInt(m.eleitorado)} eleitores</span></li>`).join('');
  };
  const input = app.querySelector('#busca');
  input.addEventListener('input', () => draw(input.value));
  draw('');
}

function electionsFor(m) {
  const out = [];
  const order = Object.keys(CARGO_LABEL);
  for (const [ano, cargos] of Object.entries(m.disponivel)) {
    for (const cargo of Object.keys(cargos)) out.push({ ano: Number(ano), cargo });
  }
  return out.sort((a, b) => a.ano - b.ano || order.indexOf(a.cargo) - order.indexOf(b.cargo));
}

function partyOfKey(key, cands) {
  if (key.startsWith('legenda:')) return key.slice(8);
  return cands[key]?.partido ?? null;
}

function labelOfKey(key, cands) {
  if (key.startsWith('legenda:')) return `Legenda ${key.slice(8)}`;
  const c = cands[key];
  return c ? `${c.nome} (${c.partido})` : key;
}

export async function render(app, route, stale) {
  const index = await loadIndex();
  if (stale()) return;
  const cod = route.args[0];
  const mun = index.municipios.find((m) => m.cod === cod);
  if (!mun) { searchView(app, index); return; }

  const elections = electionsFor(mun);
  const [pa, pc, pt] = String(route.params.e || '').split('-');
  let sel = elections.find((x) => x.ano === Number(pa) && x.cargo === pc) || elections[0];
  const turnos = availableTurnos(index, cod, sel.ano, sel.cargo);
  const turno = turnos.includes(Number(pt)) ? Number(pt) : turnos[0];
  sel = { ...sel, turno };
  const json = await loadMunicipio(cod, sel.ano, sel.cargo, turno);
  if (stale()) return;
  const mode = themeMode();
  const t = json.totais;
  const cands = Object.fromEntries(json.candidatos.map((c) => [String(c.nr), c]));
  const winners = winnerByLocal(json.locais);
  const eKey = `${sel.ano}-${sel.cargo}-${turno}`;
  const eleitos = json.candidatos.filter((c) => c.eleito);
  const majoritario = MAJORITARIOS.has(sel.cargo);
  const semCoord = json.locais.filter((l) => l.lat === null || l.lon === null);

  const opts = elections.map((x) => `<option value="${x.ano}-${x.cargo}"${x.ano === sel.ano && x.cargo === sel.cargo ? ' selected' : ''}>`
    + `${escapeHtml(electionLabel({ ...x, turno: 1 }))}</option>`).join('');
  const tabs = turnos.length > 1 ? `<div class="tabs" role="group" aria-label="Turno">${turnos.map((x) =>
    `<button type="button" data-turno="${x}" aria-pressed="${x === turno}">${x}º turno</button>`).join('')}</div>` : '';
  const maxV = Math.max(...json.candidatos.map((c) => c.votos), 1);
  const candRows = json.candidatos.map((c) => `<tr>
      <td><div class="who">${swatch(c.partido, mode)}<a class="name" href="#/candidato/${escapeHtml(cod)}/${eKey}/${c.nr}">${escapeHtml(c.nome)}</a></div>
        <span class="muted">${escapeHtml(c.partido)} · ${escapeHtml(c.nr)}</span></td>
      <td>${c.eleito ? '<span class="badge">Eleito</span>' : ''}</td>
      <td class="num">${fmtInt(c.votos)}<div class="bar" style="width:${(100 * c.votos) / maxV}%"></div></td>
      <td class="num">${fmtPct(c.pct_validos)}</td></tr>`).join('');
  const locRows = [...json.locais].sort((a, b) => a.zona - b.zona || String(a.nome).localeCompare(String(b.nome), 'pt-BR'))
    .map((l) => {
      const w = winners[l.id];
      return `<tr><td>${escapeHtml(l.nome)}<div class="muted">Zona ${l.zona} · ${escapeHtml(l.bairro || '')}
          ${l.lat === null ? ' · <strong>sem coordenadas</strong>' : ''}</div></td>
        <td>${w ? `<div class="who">${swatch(partyOfKey(w.key, cands), mode)}<span class="name">${escapeHtml(labelOfKey(w.key, cands))}</span></div>` : '–'}</td>
        <td class="num">${w ? fmtPct(w.pct) : '–'}</td>
        <td class="num">${l.aptos ? fmtPct((100 * l.comparecimento) / l.aptos) : '–'}</td></tr>`;
    }).join('');

  app.innerHTML = `
    <p><a href="#/municipio">← Todos os municípios</a></p>
    <h1>${escapeHtml(mun.nome)}</h1>
    <p class="sub">${fmtInt(mun.eleitorado)} eleitores (cadastro de 2026) · ${escapeHtml(electionLabel(sel))}</p>
    <div class="controls"><label>Eleição<select id="eleicao">${opts}</select></label></div>
    ${tabs}
    <div class="tiles">
      <div class="tile"><div class="label">Comparecimento</div><div class="value">${t.aptos ? fmtPct((100 * t.comparecimento) / t.aptos) : '–'}</div>
        <div class="note">${fmtInt(t.comparecimento)} de ${fmtInt(t.aptos)} aptos</div></div>
      <div class="tile"><div class="label">Abstenção</div><div class="value">${t.aptos ? fmtPct((100 * t.abstencoes) / t.aptos) : '–'}</div>
        <div class="note">${fmtInt(t.abstencoes)} eleitores</div></div>
      <div class="tile"><div class="label">Votos válidos</div><div class="value">${fmtInt(t.validos)}</div>
        <div class="note">${fmtInt(t.brancos)} brancos · ${fmtInt(t.nulos + t.nulos_tecnicos)} nulos</div></div>
      <div class="tile"><div class="label">${majoritario ? 'Eleito' : 'Eleitos'}</div>
        <div class="value">${majoritario ? escapeHtml(eleitos[0]?.nome || (turnos.includes(2) && turno === 1 ? '2º turno' : '–')) : fmtInt(eleitos.length)}</div>
        <div class="note">${majoritario ? escapeHtml(eleitos[0]?.partido || '') : (sel.cargo === 'vereador' ? 'vagas na Câmara' : 'eleitos com votos aqui')}</div></div>
    </div>
    <div class="grid2">
      <section class="card"><h2>Locais de votação</h2>
        <div id="mapa" class="map" role="img" aria-label="Mapa dos locais de votação coloridos pelo partido do mais votado em cada local; a mesma informação está na tabela de locais."></div>
        <p class="muted">Cor = partido do mais votado no local. ${semCoord.length
          ? `${semCoord.length} local${semCoord.length > 1 ? 'is' : ''} sem coordenadas: só na tabela.` : ''}</p>
        <details><summary>Tabela dos ${json.locais.length} locais</summary><div class="table-wrap"><table>
          <thead><tr><th scope="col">Local</th><th scope="col">Mais votado</th><th scope="col" class="num">%</th>
          <th scope="col" class="num">Compar.</th></tr></thead><tbody>${locRows}</tbody></table></div></details>
      </section>
      <section class="card"><h2>Resultado — ${escapeHtml(CARGO_LABEL[sel.cargo])}</h2><div class="table-wrap"><table>
        <thead><tr><th scope="col">Candidato</th><th scope="col"><span class="sr">Situação</span></th>
          <th scope="col" class="num">Votos</th><th scope="col" class="num">% válidos</th></tr></thead>
        <tbody>${candRows}</tbody></table></div>
        <p class="muted">% sobre votos em candidatos e legendas. Toque no nome para ver os votos por local.</p></section>
    </div>`;

  app.querySelector('#eleicao').addEventListener('change', (ev) => {
    location.hash = `#/municipio/${cod}?e=${ev.target.value}-1`;
  });
  for (const b of app.querySelectorAll('[data-turno]')) {
    b.addEventListener('click', () => { location.hash = `#/municipio/${cod}?e=${sel.ano}-${sel.cargo}-${b.dataset.turno}`; });
  }
  const map = createMap(app.querySelector('#mapa'), { tiles: true });
  const markers = markersFromLocais(json.locais, winners);
  circleLayer(map, markers, {
    surface: cssVar('--surface'),
    color: (m) => partyColor(m.winner ? partyOfKey(m.winner.key, cands) : null, mode),
    tooltip: (m) => `<strong>${escapeHtml(m.nome)}</strong><br>${m.winner
      ? `${escapeHtml(labelOfKey(m.winner.key, cands))} · ${fmtPct(m.winner.pct)}` : 'Sem votos válidos'}`,
  });
  if (!markers.length) map.setView([-10.2, -48.3], 7);
}
