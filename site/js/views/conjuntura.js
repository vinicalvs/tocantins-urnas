// Tela Conjuntura: Prefeitos (entrega em 2026), Perfil do voto (Censo x voto por area) e Comparecimento.
import { loadIndex, loadMalha, loadConjuntura, loadEstado, fmtInt, fmtPct } from '../data.js';
import { escapeHtml, CARGO_LABEL, IND_LABEL } from '../analysis.js';
import { partyColor } from '../colors.js';
import { createMap, choropleth, themeMode, cssVar } from '../map.js';
import { rankingPartidos, quintis, correlacaoPonderada, resumoPerfil } from '../conjuntura.js';
import { render as scatter } from '../scatter.js';

const NF1 = new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 1 });
const NF2 = new Intl.NumberFormat('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
// Entregou / nao entregou: par categorico validado (validate_palette.js, claro e escuro); sem candidato = neutro.
const STATUS_COR = {
  light: { entregou: '#2a78d6', nao_entregou: '#eb6834', sem_candidato: '#b5b4ad' },
  dark: { entregou: '#3987e5', nao_entregou: '#d95926', sem_candidato: '#5f5e5a' },
};
const STATUS_TXT = { entregou: 'Entregou', nao_entregou: 'Não entregou', sem_candidato: 'Sem candidato da coligação' };
// Sequencial azul (um matiz): claro -> escuro no modo claro; no escuro, mais = mais claro.
const SEQ = { light: ['#cde2fb', '#9ec5f4', '#6da7ec', '#3987e5', '#1c5cab'], dark: ['#184f95', '#256abf', '#3987e5', '#6da7ec', '#b7d3f6'] };
const ENTREGA = { 'governador-1': 'Governador · 1º turno', 'governador-2': 'Governador · 2º turno', 'senador-1': 'Senador' };
const AREAS = [['2026', 'governador'], ['2026', 'senador'], ['2026', 'deputado_federal'], ['2026', 'deputado_estadual'],
  ['2024', 'prefeito'], ['2024', 'vereador']];
const ABAS = [['prefeitos', 'Prefeitos'], ['perfil', 'Perfil do voto'], ['comparecimento', 'Comparecimento']];
const AVISO = `<p class="note-box"><strong>Perfil do lugar, não do eleitor.</strong> Cada ponto junta locais de votação
  vizinhos e os setores do Censo 2022 mais próximos deles. Mostra onde um candidato vai melhor, não quem votou nele
  nem por quê.</p>`;

const sel = (id, label, opts, cur) => `<label>${label}<select id="${id}">${opts.map(([v, t]) =>
  `<option value="${escapeHtml(v)}"${v === cur ? ' selected' : ''}>${escapeHtml(t)}</option>`).join('')}</select></label>`;

function go(aba, params) {
  const q = new URLSearchParams(Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== '')).toString();
  location.hash = `#/conjuntura/${aba}${q ? `?${q}` : ''}`;
}

function legenda(itens) {
  return `<ul class="legend" aria-label="Legenda">${itens.map(([cor, txt]) =>
    `<li><span class="sw" style="background:${cor}"></span>${txt}</li>`).join('')}</ul>`;
}

// ---------------------------------------------------------------- Prefeitos
async function prefeitos(el, route, stale, ctx) {
  const c = ENTREGA[route.params.c] ? route.params.c : 'governador-1';
  const [conj, malha] = await Promise.all([loadConjuntura('prefeitos_2026'), loadMalha()]);
  if (stale()) return;
  const linhas = conj[c];
  const { mode, byCod, byIbge } = ctx;
  const cont = { entregou: 0, nao_entregou: 0, sem_candidato: 0 };
  for (const l of linhas) cont[l.status] += 1;
  const comCand = cont.entregou + cont.nao_entregou;
  const rank = rankingPartidos(linhas);
  const porCod = Object.fromEntries(linhas.map((l) => [l.cod, l]));
  const sen = c === 'senador-1';
  const margem = (l) => (l.margem_pp === null || l.margem_pp === undefined ? '–' : `${l.margem_pp > 0 ? '+' : ''}${NF1.format(l.margem_pp)}`);
  const rows = [...linhas].sort((a, b) => byCod[a.cod].nome.localeCompare(byCod[b.cod].nome, 'pt-BR')).map((l) => `<tr>
      <td><a href="#/municipio/${escapeHtml(l.cod)}">${escapeHtml(byCod[l.cod].nome)}</a></td>
      <td>${escapeHtml(l.prefeito.nome)} <span class="muted">${escapeHtml(l.prefeito.partido)}</span></td>
      <td>${l.cand_nome ? `${escapeHtml(l.cand_nome)} <span class="muted">${escapeHtml(l.cand_partido)}</span>` : '–'}</td>
      <td><span class="sw" style="background:${STATUS_COR[mode][l.status]}"></span> ${STATUS_TXT[l.status]}</td>
      <td>${l.venc_nome ? `${escapeHtml(l.venc_nome)} <span class="muted">${escapeHtml(l.venc_partido)}</span>` : '–'}</td>
      <td class="num">${margem(l)}</td></tr>`).join('');
  const rrows = rank.map((r) => `<tr><td><div class="who"><span class="sw" style="background:${partyColor(r.partido, mode)}"></span>${escapeHtml(r.partido)}</div></td>
      <td class="num">${fmtInt(r.prefeituras)}</td><td class="num">${fmtInt(r.com_candidato)}</td>
      <td class="num">${fmtInt(r.entregou)}</td><td class="num">${r.taxa === null ? '–' : fmtPct(r.taxa)}</td></tr>`).join('');

  el.innerHTML = `<div class="controls">${sel('cargo', 'Disputa', Object.entries(ENTREGA), c)}</div>
    <p class="sub">O candidato da coligação do partido do prefeito eleito em 2024 ${sen ? 'ficou entre os 2 mais votados' : 'foi o mais votado'}
      no município? <strong>${fmtInt(cont.entregou)} de ${fmtInt(comCand)}</strong> prefeitos com candidato da coligação
      entregaram (${comCand ? fmtPct((100 * cont.entregou) / comCand) : '–'}); ${fmtInt(cont.sem_candidato)} ${cont.sem_candidato === 1 ? 'não tinha' : 'não tinham'} candidato.</p>
    <div class="grid2">
      <section class="card"><h2>Mapa dos 139 municípios</h2>
        <div id="mapa" class="map" role="img" aria-label="Mapa por resultado da coligação do prefeito; a mesma informação está na tabela."></div>
        ${legenda(['entregou', 'nao_entregou', 'sem_candidato'].map((s) => [STATUS_COR[mode][s], `${STATUS_TXT[s]} (${cont[s]})`]))}
      </section>
      <section class="card"><h2>Por partido do prefeito</h2><div class="table-wrap"><table class="mini">
        <thead><tr><th scope="col">Partido</th><th scope="col" class="num">Prefeituras</th><th scope="col" class="num">Com candidato</th>
          <th scope="col" class="num">Entregaram</th><th scope="col" class="num">Taxa</th></tr></thead><tbody>${rrows}</tbody></table></div>
        <p class="muted">Taxa = entregas ÷ prefeituras com candidato da coligação. Coligação registrada no TSE não é o mesmo que apoio declarado.</p>
      </section>
    </div>
    <section class="card"><details><summary>Tabela por município (${linhas.length})</summary><div class="table-wrap"><table class="mini">
      <thead><tr><th scope="col">Município</th><th scope="col">Prefeito</th><th scope="col">Candidato da coligação</th>
        <th scope="col">Resultado</th><th scope="col">Mais votado no município</th><th scope="col" class="num">Margem (p.p.)</th></tr></thead>
      <tbody>${rows}</tbody></table></div></details></section>`;
  el.querySelector('#cargo').addEventListener('change', (ev) => go('prefeitos', { c: ev.target.value }));
  const map = createMap(el.querySelector('#mapa'));
  choropleth(map, malha, {
    surface: cssVar('--surface'),
    fill: (f) => { const m = byIbge[f.properties.codarea]; const l = m && porCod[m.cod]; return l ? STATUS_COR[mode][l.status] : cssVar('--surface-2'); },
    tooltip: (f) => {
      const m = byIbge[f.properties.codarea]; const l = m && porCod[m.cod];
      if (!l) return 'Sem dados';
      return `<strong>${escapeHtml(m.nome)}</strong><br>Prefeito: ${escapeHtml(l.prefeito.nome)} (${escapeHtml(l.prefeito.partido)})<br>`
        + `${STATUS_TXT[l.status]}${l.cand_nome ? `: ${escapeHtml(l.cand_nome)}` : ''}${l.margem_pp !== null && l.margem_pp !== undefined ? ` · ${margem(l)} p.p.` : ''}`;
    },
    onClick: (f) => { const m = byIbge[f.properties.codarea]; if (m) location.hash = `#/municipio/${m.cod}`; },
  });
}

// ---------------------------------------------------------------- Perfil do voto
function alvos(areas, est, municipal) {
  const part = {};
  for (const a of areas) for (const [sg, v] of Object.entries(a.partidos)) part[sg] = (part[sg] || 0) + v;
  const ps = Object.entries(part).sort((a, b) => b[1] - a[1]).slice(0, 12).map(([sg]) => [`p:${sg}`, `Partido ${sg}`]);
  if (municipal || !est) return ps;
  const cs = est.candidatos.slice(0, 12).map((c) => [`c:${c.nr}`, `${c.nome} (${c.partido})`]);
  return [...cs, ...ps];
}

function pontosMunicipio(areas, munInd) {
  const g = {};
  for (const a of areas) {
    const x = g[a.cod] || (g[a.cod] = { cod: a.cod, validos: 0, eleitores: 0, votos: {}, partidos: {} });
    x.validos += a.validos;
    x.eleitores += a.eleitores;
    for (const [k, v] of Object.entries(a.votos)) x.votos[k] = (x.votos[k] || 0) + v;
    for (const [k, v] of Object.entries(a.partidos)) x.partidos[k] = (x.partidos[k] || 0) + v;
  }
  const ind = Object.fromEntries(munInd.map((m) => [m.cod, m.ind]));
  return Object.values(g).map((x) => ({ ...x, id: x.cod, ind: ind[x.cod] || {} }));
}

async function perfil(el, route, stale, ctx) {
  const [ano, cargo] = AREAS.find(([a, c]) => `${a}-${c}` === route.params.cargo) || AREAS[0];
  const ind = IND_LABEL[route.params.ind] ? route.params.ind : 'alfabetizacao_15';
  const nivel = route.params.nivel === 'municipio' ? 'municipio' : 'area';
  const municipal = cargo === 'prefeito' || cargo === 'vereador';
  const [ar, est, munInd] = await Promise.all([loadConjuntura(`areas_${ano}_${cargo}`),
    municipal ? null : loadEstado(Number(ano), cargo, 1), loadConjuntura('municipios_indicadores')]);
  if (stale()) return;
  const opts = alvos(ar.areas, est, municipal);
  const alvo = opts.some(([v]) => v === route.params.alvo) ? route.params.alvo : opts[0][0];
  const [tipo, chave] = [alvo.slice(0, 1), alvo.slice(2)];
  const alvoTxt = opts.find(([v]) => v === alvo)[1];
  const valor = (a) => (tipo === 'c' ? a.votos[chave] || 0 : a.partidos[chave] || 0);
  const lugares = nivel === 'municipio' ? pontosMunicipio(ar.areas, munInd) : ar.areas;
  const usados = lugares.filter((a) => a.validos > 0 && a.ind[ind] !== null && a.ind[ind] !== undefined);
  const q = quintis(usados, ind, valor);
  const pct = (a) => (100 * valor(a)) / a.validos;
  const r = correlacaoPonderada(usados.map((a) => a.ind[ind]), usados.map(pct), usados.map((a) => a.eleitores));
  const cor = tipo === 'p' ? partyColor(chave, ctx.mode) : partyColor(est?.candidatos.find((c) => String(c.nr) === chave)?.partido, ctx.mode);
  const nome = (a) => `${ctx.byCod[a.cod]?.nome || a.cod}${nivel === 'area' ? ` · área ${a.id}` : ''}`;
  const tabela = [...usados].sort((a, b) => pct(b) - pct(a)).map((a) => `<tr><td>${escapeHtml(nome(a))}</td>
      <td class="num">${fmtPct(a.ind[ind])}</td><td class="num">${fmtPct(pct(a))}</td><td class="num">${fmtInt(a.eleitores)}</td></tr>`).join('');

  el.innerHTML = `<div class="controls">
      ${sel('cargo', 'Cargo', AREAS.map(([a, c]) => [`${a}-${c}`, `${CARGO_LABEL[c]} ${a}`]), `${ano}-${cargo}`)}
      ${sel('alvo', 'Candidato ou partido', opts, alvo)}
      ${sel('ind', 'Indicador do Censo 2022', Object.entries(IND_LABEL), ind)}
      ${sel('nivel', 'Cada ponto é', [['area', 'Área de votação'], ['municipio', 'Município']], nivel)}</div>
    ${AVISO}
    <div class="grid2">
      <section class="card"><h2>${escapeHtml(alvoTxt)} × ${escapeHtml(IND_LABEL[ind])}</h2>
        <div id="sc"></div>
        <p class="muted">${fmtInt(usados.length)} ${nivel === 'area' ? 'áreas de votação críveis' : 'municípios'}; tamanho do ponto = eleitores.
          ${nivel === 'municipio' ? 'Indicador do município inteiro; votos das áreas críveis dele.' : ''}</p></section>
      <section class="card"><h2>Leitura</h2>
        <div class="tiles"><div class="tile"><div class="label">20% com ${escapeHtml(IND_LABEL[ind].toLowerCase())} mais alto</div>
          <div class="value">${q.alto.pct === null ? '–' : fmtPct(q.alto.pct)}</div><div class="note">dos válidos, ${fmtInt(q.alto.n)} lugares</div></div>
        <div class="tile"><div class="label">20% com o mais baixo</div>
          <div class="value">${q.baixo.pct === null ? '–' : fmtPct(q.baixo.pct)}</div><div class="note">dos válidos, ${fmtInt(q.baixo.n)} lugares</div></div></div>
        <p>${escapeHtml(resumoPerfil({ alvo: alvoTxt, ind: IND_LABEL[ind], q, r }))}</p>
        <details><summary>Tabela (${fmtInt(usados.length)})</summary><div class="table-wrap"><table class="mini">
          <thead><tr><th scope="col">Lugar</th><th scope="col" class="num">${escapeHtml(IND_LABEL[ind])}</th>
            <th scope="col" class="num">% válidos</th><th scope="col" class="num">Eleitores</th></tr></thead><tbody>${tabela}</tbody></table></div></details>
      </section></div>`;
  for (const id of ['cargo', 'alvo', 'ind', 'nivel']) {
    el.querySelector(`#${id}`).addEventListener('change', () => {
      const v = (k) => el.querySelector(`#${k}`).value;
      go('perfil', { cargo: v('cargo'), alvo: id === 'cargo' ? '' : v('alvo'), ind: v('ind'), nivel: v('nivel') });
    });
  }
  scatter(el.querySelector('#sc'), usados.map((a) => ({ x: a.ind[ind], y: pct(a), r: a.eleitores, cor,
    label: `<strong>${escapeHtml(nome(a))}</strong><br>${escapeHtml(IND_LABEL[ind])}: ${fmtPct(a.ind[ind])}<br>`
      + `${escapeHtml(alvoTxt)}: ${fmtPct(pct(a))} dos válidos<br>${fmtInt(a.eleitores)} eleitores` })),
  { xLabel: `${IND_LABEL[ind]} (%)`, yLabel: '% dos válidos' });
}

// ---------------------------------------------------------------- Comparecimento
function classes(vals, n = 5) {
  const s = [...vals].sort((a, b) => a - b);
  return Array.from({ length: n - 1 }, (_, i) => s[Math.floor(((i + 1) * s.length) / n)]);
}

async function comparecimento(el, route, stale, ctx) {
  const ano = route.params.ano === '2024' ? '2024' : '2026';
  const ind = IND_LABEL[route.params.ind] ? route.params.ind : 'alfabetizacao_15';
  const [munInd, malha] = await Promise.all([loadConjuntura('municipios_indicadores'), loadMalha()]);
  if (stale()) return;
  const { mode, byCod, byIbge } = ctx;
  const ms = munInd.filter((m) => m.aptos[ano]).map((m) => ({ ...m, abst: (100 * (m.aptos[ano] - m.comparecimento[ano])) / m.aptos[ano] }));
  const cortes = classes(ms.map((m) => m.abst));
  const classe = (v) => cortes.filter((c) => v >= c).length;
  const porCod = Object.fromEntries(ms.map((m) => [m.cod, m]));
  const tot = ms.reduce((s, m) => [s[0] + m.aptos[ano], s[1] + m.comparecimento[ano]], [0, 0]);
  const pts = ms.map((m) => ({ ind: m.ind, validos: m.aptos[ano], v: m.aptos[ano] - m.comparecimento[ano], eleitores: m.aptos[ano] }))
    .filter((m) => m.ind[ind] !== null && m.ind[ind] !== undefined);
  const q = quintis(pts, ind, (m) => m.v);
  const r = correlacaoPonderada(pts.map((m) => m.ind[ind]), pts.map((m) => (100 * m.v) / m.validos), pts.map((m) => m.eleitores));
  const faixas = [Math.min(...ms.map((m) => m.abst)), ...cortes, Math.max(...ms.map((m) => m.abst))];
  const ord = [...ms].sort((a, b) => b.abst - a.abst);
  const linha = (m, i) => `<tr><td class="num muted">${i + 1}</td><td><a href="#/municipio/${escapeHtml(m.cod)}">${escapeHtml(byCod[m.cod].nome)}</a></td>
      <td class="num">${fmtPct(m.abst)}</td><td class="num">${fmtInt(m.aptos[ano])}</td></tr>`;

  el.innerHTML = `<div class="controls">${sel('ano', 'Eleição', [['2026', '2026 · 1º turno'], ['2024', '2024 · 1º turno']], ano)}
      ${sel('ind', 'Indicador do Censo 2022', Object.entries(IND_LABEL), ind)}</div>
    <p class="sub">Abstenção no Tocantins em ${ano}: <strong>${fmtPct((100 * (tot[0] - tot[1])) / tot[0])}</strong>
      (${fmtInt(tot[0] - tot[1])} de ${fmtInt(tot[0])} aptos). Varia de ${fmtPct(faixas[0])} a ${fmtPct(faixas[5])} entre os municípios.</p>
    <div class="grid2">
      <section class="card"><h2>Abstenção por município</h2>
        <div id="mapa" class="map" role="img" aria-label="Mapa da abstenção por município em cinco faixas; a mesma informação está no ranking."></div>
        ${legenda(SEQ[mode].map((c, i) => [c, `${NF1.format(faixas[i])}–${NF1.format(faixas[i + 1])}%`]))}
        <details><summary>Ranking dos ${ms.length} municípios</summary><div class="table-wrap"><table class="mini">
          <thead><tr><th scope="col" class="num">#</th><th scope="col">Município</th><th scope="col" class="num">Abstenção</th>
            <th scope="col" class="num">Aptos</th></tr></thead><tbody>${ord.map(linha).join('')}</tbody></table></div></details>
      </section>
      <section class="card"><h2>Abstenção × ${escapeHtml(IND_LABEL[ind])}</h2><div id="sc"></div>
        <p>Nos ${fmtInt(q.alto.n)} municípios com ${escapeHtml(IND_LABEL[ind].toLowerCase())} mais alto, a abstenção somou
          <strong>${q.alto.pct === null ? '–' : fmtPct(q.alto.pct)}</strong> dos aptos; nos ${fmtInt(q.baixo.n)} com o mais baixo,
          <strong>${q.baixo.pct === null ? '–' : fmtPct(q.baixo.pct)}</strong>.${r === null ? '' : ` Correlação ponderada pelos aptos: ${NF2.format(r)}.`}</p>
        <p class="muted">Um ponto por município; tamanho = aptos. Perfil do lugar, não do eleitor.</p></section>
    </div>`;
  for (const id of ['ano', 'ind']) {
    el.querySelector(`#${id}`).addEventListener('change', () => go('comparecimento', { ano: el.querySelector('#ano').value, ind: el.querySelector('#ind').value }));
  }
  const map = createMap(el.querySelector('#mapa'));
  choropleth(map, malha, {
    surface: cssVar('--surface'),
    fill: (f) => { const m = byIbge[f.properties.codarea]; const x = m && porCod[m.cod]; return x ? SEQ[mode][classe(x.abst)] : cssVar('--surface-2'); },
    tooltip: (f) => { const m = byIbge[f.properties.codarea]; const x = m && porCod[m.cod];
      return x ? `<strong>${escapeHtml(m.nome)}</strong><br>Abstenção ${fmtPct(x.abst)} · ${fmtInt(x.aptos[ano])} aptos` : 'Sem dados'; },
    onClick: (f) => { const m = byIbge[f.properties.codarea]; if (m) location.hash = `#/municipio/${m.cod}`; },
  });
  const corPt = SEQ[mode][3];
  scatter(el.querySelector('#sc'), ms.filter((m) => m.ind[ind] !== null && m.ind[ind] !== undefined).map((m) => ({
    x: m.ind[ind], y: m.abst, r: m.aptos[ano], cor: corPt,
    label: `<strong>${escapeHtml(byCod[m.cod].nome)}</strong><br>${escapeHtml(IND_LABEL[ind])}: ${fmtPct(m.ind[ind])}<br>Abstenção: ${fmtPct(m.abst)}` })),
  { xLabel: `${IND_LABEL[ind]} (%)`, yLabel: 'Abstenção (%)' });
}

export async function render(app, route, stale) {
  const aba = ABAS.some(([k]) => k === route.args[0]) ? route.args[0] : 'prefeitos';
  const index = await loadIndex();
  if (stale()) return;
  const ctx = { mode: themeMode(), byCod: Object.fromEntries(index.municipios.map((m) => [m.cod, m])),
    byIbge: Object.fromEntries(index.municipios.map((m) => [m.ibge, m])) };
  app.innerHTML = `<h1>Conjuntura</h1>
    <p class="sub">Prefeitos eleitos em 2024 diante de 2026, perfil dos lugares onde cada candidato vai melhor e comparecimento.</p>
    <div class="tabs" role="tablist">${ABAS.map(([k, t]) => `<a role="tab" class="tab" href="#/conjuntura/${k}"
      aria-selected="${k === aba}">${t}</a>`).join('')}</div>
    <div id="aba"><p class="loading">Carregando…</p></div>`;
  const fn = { prefeitos, perfil, comparecimento }[aba];
  await fn(app.querySelector('#aba'), route, stale, ctx);
}
