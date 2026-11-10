// Tela Municipio: ficha IBGE, prefeito x 2026, resultado por cargo, mapa e tabela dos locais com a ficha do local.
import { loadIndex, loadMunicipio, loadFicha, loadIbge, loadConjuntura, fmtInt, fmtPct, normalizeText } from '../data.js';
import { escapeHtml, winnerByLocal, partyByLocal, availableTurnos, electionLabel, CARGO_LABEL, MAJORITARIOS } from '../analysis.js';
import { partyColor } from '../colors.js';
import { createMap, circleLayer, markersFromLocais, themeMode, cssVar } from '../map.js';
import { openPanel, tooltipLocal } from './local_panel.js';

const swatch = (sg, mode) => `<span class="sw" style="background:${partyColor(sg, mode)}"></span>`;
const NF0 = new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 0 });
const NF1 = new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 1 });

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
  return out.sort((a, b) => b.ano - a.ano || order.indexOf(a.cargo) - order.indexOf(b.cargo));
}

function labelOfKey(key, cands) {
  if (key.startsWith('legenda:')) return `Legenda ${key.slice(8)}`;
  const c = cands[key];
  return c ? `${c.nome} (${c.partido})` : key;
}

// Destaque de cada local: candidato mais votado (majoritarios) ou partido mais votado (proporcionais).
function destaques(json, cands, majoritario) {
  if (majoritario) {
    const w = winnerByLocal(json.locais);
    return Object.fromEntries(Object.entries(w).map(([id, x]) => [id, {
      sg: x.key.startsWith('legenda:') ? x.key.slice(8) : cands[x.key]?.partido, label: labelOfKey(x.key, cands), pct: x.pct }]));
  }
  const p = partyByLocal(json.locais, cands);
  return Object.fromEntries(Object.entries(p).map(([id, x]) => [id, { sg: x.sg, label: x.sg, pct: x.pct }]));
}

export function localRow(l, w, mode) {
  return `<tr class="click" data-local="${escapeHtml(l.id)}" tabindex="0">
    <td>${escapeHtml(l.nome)}<div class="muted">Zona ${escapeHtml(l.zona)} · ${escapeHtml(l.bairro || '')}${
      l.lat === null || l.lon === null ? ' · <strong>sem coordenadas</strong>' : ''}</div></td>
    <td>${w ? `<div class="who">${swatch(w.sg, mode)}<span class="name">${escapeHtml(w.label)}</span></div>` : '–'}</td>
    <td class="num">${w ? fmtPct(w.pct) : '–'}</td>
    <td class="num">${l.aptos ? fmtPct((100 * l.comparecimento) / l.aptos) : '–'}</td></tr>`;
}

function fatos(ibge) {
  if (!ibge) return '';
  const pib = ibge.pib_per_capita === null ? '–' : `R$ ${NF0.format(ibge.pib_per_capita)}`;
  return `<p class="facts">População (Censo 2022) <strong>${fmtInt(ibge.populacao)}</strong> · Área
    <strong>${NF0.format(ibge.area_km2)} km²</strong> · Densidade <strong>${NF1.format(ibge.densidade)} hab/km²</strong>
    · PIB per capita ${escapeHtml(ibge.ano_pib)} <strong>${pib}</strong></p>`;
}

const STATUS = {
  entregou: (s) => `<span class="ok">✓ ${s ? 'entre os 2 mais votados' : 'venceu aqui'}</span>`,
  nao_entregou: () => '<span class="bad">✗ perdeu aqui</span>',
  sem_candidato: () => '<span class="muted">sem candidato da coligação</span>',
};

export function prefeitoCard(conj, cod) {
  if (!conj) return '';
  const linhas = [['governador-1', 'Governador · 1º turno'], ['governador-2', 'Governador · 2º turno'], ['senador-1', 'Senador']]
    .map(([k, label]) => [label, (conj[k] || []).find((r) => r.cod === cod), k === 'senador-1']).filter(([, r]) => r);
  if (!linhas.length) return '';
  const p = linhas[0][1].prefeito;
  const rows = linhas.map(([label, r, sen]) => `<tr><th scope="row">${label}</th>
    <td>${r.cand_nome ? `${escapeHtml(r.cand_nome)} <span class="muted">${escapeHtml(r.cand_partido)}</span>` : '–'}</td>
    <td>${STATUS[r.status](sen)}${r.status === 'nao_entregou' && r.venc_nome
      ? `<div class="muted">mais votado: ${escapeHtml(r.venc_nome)} (${escapeHtml(r.venc_partido)})</div>` : ''}</td>
    <td class="num">${r.margem_pp === null || r.margem_pp === undefined ? '–'
      : `${r.margem_pp > 0 ? '+' : ''}${NF1.format(r.margem_pp)} p.p.`}</td></tr>`).join('');
  return `<section class="card"><h2>O prefeito entregou em 2026?</h2>
    <p class="sub" style="margin-bottom:8px"><strong>${escapeHtml(p.nome)}</strong> (${escapeHtml(p.partido)}), eleito em 2024.
      Candidato da coligação = aquele cuja coligação ou federação inclui o partido do prefeito.</p>
    <div class="table-wrap"><table class="mini"><thead><tr><th scope="col">Cargo</th><th scope="col">Candidato da coligação</th>
      <th scope="col">Resultado no município</th><th scope="col" class="num">Margem</th></tr></thead><tbody>${rows}</tbody></table></div>
    <p class="muted">Margem: votos do candidato menos os do primeiro que ficaria de fora, em pontos percentuais dos válidos.
      <a href="#/conjuntura">Ver todos os municípios</a>.</p></section>`;
}

let state = { cod: null, ficha: null, close: null };

function hashWithout(local) {
  const [path, query = ''] = location.hash.split('?');
  const p = new URLSearchParams(query);
  if (local === null) p.delete('local'); else p.set('local', local);
  const q = p.toString();
  return q ? `${path}?${q}` : path;
}

// Abre/fecha o painel conforme ?local= (chamado tambem quando so o painel muda: ver app.js).
export function update(app, route) {
  const id = route.params.local;
  if (state.close) { const c = state.close; state.close = null; c(true); }
  if (!id || !state.ficha) return;
  const local = state.ficha.find((l) => l.id === id);
  if (!local) return;
  state.close = openPanel(app, local, () => { state.close = null; location.hash = hashWithout(null); });
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
  const opt = (p) => p.catch(() => null);
  const [json, ficha, ibge, conj] = await Promise.all([loadMunicipio(cod, sel.ano, sel.cargo, turno),
    opt(loadFicha(cod)), opt(loadIbge(cod)), opt(loadConjuntura('prefeitos_2026'))]);
  if (stale()) return;
  state = { cod, ficha: ficha?.locais || null, close: null };
  const fichaDe = Object.fromEntries((ficha?.locais || []).map((l) => [l.id, l]));
  const mode = themeMode();
  const t = json.totais;
  const cands = Object.fromEntries(json.candidatos.map((c) => [String(c.nr), c]));
  const majoritario = MAJORITARIOS.has(sel.cargo);
  const dest = destaques(json, cands, majoritario);
  const eKey = `${sel.ano}-${sel.cargo}-${turno}`;
  const eleitos = json.candidatos.filter((c) => c.eleito);
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
    .map((l) => localRow(l, dest[l.id], mode)).join('');
  const eleitoTxt = eleitos.length ? eleitos.map((c) => c.nome).join(' e ') : (turnos.includes(2) && turno === 1 ? '2º turno' : '–');
  const corTxt = majoritario ? 'candidato mais votado' : 'partido mais votado (nominal + legenda)';

  app.innerHTML = `
    <h1>${escapeHtml(mun.nome)}</h1>
    <p class="sub">${fmtInt(mun.eleitorado)} eleitores (cadastro de 2026)</p>
    ${mun.nota ? `<p class="note-box">${escapeHtml(mun.nota)}</p>` : ''}
    ${fatos(ibge)}
    ${prefeitoCard(conj, cod)}
    <h2 style="margin-top:24px">${escapeHtml(electionLabel(sel))}</h2>
    <div class="controls"><label>Eleição<select id="eleicao">${opts}</select></label>${tabs}</div>
    <div class="tiles">
      <div class="tile"><div class="label">Comparecimento</div><div class="value">${t.aptos ? fmtPct((100 * t.comparecimento) / t.aptos) : '–'}</div>
        <div class="note">${fmtInt(t.comparecimento)} de ${fmtInt(t.aptos)} aptos</div></div>
      <div class="tile"><div class="label">Abstenção</div><div class="value">${t.aptos ? fmtPct((100 * t.abstencoes) / t.aptos) : '–'}</div>
        <div class="note">${fmtInt(t.abstencoes)} eleitores</div></div>
      <div class="tile"><div class="label">Votos válidos</div><div class="value">${fmtInt(t.validos)}</div>
        <div class="note">${fmtInt(t.brancos)} brancos · ${fmtInt(t.nulos + t.nulos_tecnicos)} nulos</div></div>
      <div class="tile"><div class="label">${majoritario ? (sel.cargo === 'senador' ? 'Eleitos' : 'Eleito') : 'Eleitos'}</div>
        <div class="value${majoritario ? ' small' : ''}">${majoritario ? escapeHtml(eleitoTxt) : fmtInt(eleitos.length)}</div>
        <div class="note">${majoritario ? escapeHtml(eleitos.map((c) => c.partido).join(' e ')) : (sel.cargo === 'vereador' ? 'vagas na Câmara' : 'eleitos com votos aqui')}</div></div>
    </div>
    <div class="grid2">
      <section class="card"><h2>Locais de votação</h2>
        <div id="mapa" class="map" role="img" aria-label="Mapa dos locais de votação coloridos pelo ${corTxt}; a mesma informação está na tabela de locais."></div>
        <p class="muted">Cor = ${corTxt}. Passe o mouse para o resumo; clique para a ficha completa.
          Ctrl + roda do mouse dá zoom. ${semCoord.length
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
  const abrir = (id) => { location.hash = hashWithout(id); };
  for (const tr of app.querySelectorAll('tr[data-local]')) {
    tr.addEventListener('click', () => abrir(tr.dataset.local));
    tr.addEventListener('keydown', (ev) => { if (ev.key === 'Enter') abrir(tr.dataset.local); });
  }
  const map = createMap(app.querySelector('#mapa'), { tiles: true });
  const markers = markersFromLocais(json.locais, dest);
  circleLayer(map, markers, {
    surface: cssVar('--surface'),
    color: (m) => partyColor(m.winner?.sg ?? null, mode),
    tooltip: (m) => (fichaDe[m.id] ? tooltipLocal(fichaDe[m.id])
      : `<strong>${escapeHtml(m.nome)}</strong><br>${m.winner ? `${escapeHtml(m.winner.label)} · ${fmtPct(m.winner.pct)}` : 'Sem votos válidos'}`),
    onClick: (m) => abrir(m.id),
  });
  if (!markers.length) map.setView([-10.2, -48.3], 7);
  update(app, route);
}
