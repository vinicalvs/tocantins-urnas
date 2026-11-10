// Ficha do local de votacao: painel lateral (clique) e tooltip curto (passar o mouse).
import { fmtInt, fmtPct } from '../data.js';
import { escapeHtml, CARGO_LABEL, MAJORITARIOS, IND_LABEL } from '../analysis.js';

const ORDEM = Object.keys(CARGO_LABEL);

// Chaves "<ano>-<cargo>-<turno>": ano mais recente primeiro, cargos na ordem fixa, 2o turno antes do 1o.
function chaves(cargos) {
  return Object.keys(cargos).map((k) => {
    const [ano, cargo, turno] = k.split('-');
    return { k, ano: Number(ano), cargo, turno: Number(turno) };
  }).sort((a, b) => b.ano - a.ano || ORDEM.indexOf(a.cargo) - ORDEM.indexOf(b.cargo) || b.turno - a.turno);
}

const titulo = (c) => `${CARGO_LABEL[c.cargo] || c.cargo} ${c.ano}${c.turno === 2 ? ' · 2º turno' : ''}`;

function comparecimento(anos) {
  return Object.entries(anos || {}).sort().map(([ano, a]) => `${escapeHtml(ano)} <strong>${a.aptos
    ? fmtPct((100 * a.comparecimento) / a.aptos) : '–'}</strong> <span class="muted">(${fmtInt(a.comparecimento)} de ${fmtInt(a.aptos)})</span>`)
    .join(' · ');
}

function tabela(lista) {
  return `<table class="mini"><tbody>${lista.map((x, i) => `<tr class="c"><td class="num muted">${i + 1}</td>
    <td>${escapeHtml(x.nome)} <span class="muted">${escapeHtml(x.partido)}</span></td>
    <td class="num">${fmtInt(x.votos)}</td><td class="num">${fmtPct(x.pct)}</td></tr>`).join('')}</tbody></table>`;
}

function entorno(e) {
  if (!e) {
    return `<p class="note-box">Perfil do entorno indisponível: este local não tem coordenadas ou a ligação com
      os setores do Censo não é crível (eleitores e moradores ligados muito diferentes).</p>`;
  }
  const rows = Object.entries(IND_LABEL).map(([k, label]) => `<tr><td>${escapeHtml(label)}</td>
    <td class="num">${e.indicadores?.[k] === null || e.indicadores?.[k] === undefined ? '–' : fmtPct(e.indicadores[k])}</td></tr>`).join('');
  return `<h3>Entorno · Censo 2022</h3>
    <p class="muted">${fmtInt(e.moradores)} moradores nos setores mais próximos deste local (ligação de ${escapeHtml(e.ano_ligacao)}).</p>
    <table class="mini"><tbody>${rows}</tbody></table>
    <p class="muted">Descreve o lugar; não indica como cada pessoa votou.</p>`;
}

export function renderPanel(local) {
  const blocos = chaves(local.cargos || {}).map((c) => {
    const lista = local.cargos[c.k] || [];
    if (!lista.length) return '';
    if (MAJORITARIOS.has(c.cargo)) {
      return `<section data-cargo="${escapeHtml(c.k)}"><h3>${escapeHtml(titulo(c))}</h3>${tabela(lista)}</section>`;
    }
    return `<details data-cargo="${escapeHtml(c.k)}"><summary>${escapeHtml(titulo(c))} · ${lista.length} mais votados</summary>
      ${tabela(lista)}</details>`;
  }).join('');
  return `<div class="panel-head"><div><h2 id="painel-titulo">${escapeHtml(local.nome)}</h2>
      <p class="muted">${escapeHtml(local.bairro || '')} · Local ${escapeHtml(local.id)}</p></div>
      <button type="button" class="close" aria-label="Fechar ficha do local">×</button></div>
    <p>Comparecimento: ${comparecimento(local.anos)}</p>
    ${blocos}
    <section class="entorno">${entorno(local.entorno)}</section>`;
}

// Uma linha por cargo (o turno decisivo), mais votado e %: cabe no tooltip do mapa.
export function tooltipLocal(local) {
  const anos = Object.keys(local.anos || {}).sort();
  const ult = anos[anos.length - 1];
  const a = ult && local.anos[ult];
  const visto = new Set();
  const linhas = [];
  for (const c of chaves(local.cargos || {})) {
    const id = `${c.ano}-${c.cargo}`;
    if (visto.has(id)) continue;
    visto.add(id);
    const top = (local.cargos[c.k] || [])[0];
    if (top) {
      linhas.push(`${escapeHtml(CARGO_LABEL[c.cargo] || c.cargo)} ${c.ano}${c.turno === 2 ? ' · 2º t.' : ''}: `
        + `${escapeHtml(top.nome)} (${escapeHtml(top.partido)}) ${fmtPct(top.pct)}`);
    }
  }
  return [`<strong>${escapeHtml(local.nome)}</strong>`,
    a ? `Comparecimento ${escapeHtml(ult)}: ${a.aptos ? fmtPct((100 * a.comparecimento) / a.aptos) : '–'}` : null,
    ...linhas.slice(0, 6)].filter(Boolean).join('<br>');
}

// id -> ficha da eleicao escolhida: o mesmo "zona-local" pode ser outro lugar em outro ano.
export function fichaPorId(locais, ano) {
  const out = {};
  for (const l of locais || []) {
    if (l.anos?.[ano] || Object.keys(l.cargos || {}).some((k) => k.startsWith(`${ano}-`))) out[l.id] = l;
  }
  return out;
}

// Abre o painel dentro de `container`; Esc e o botao fecham. Devolve a funcao que fecha.
export function openPanel(container, local, onClose = () => {}) {
  container.querySelector('.panel')?.remove();
  const el = document.createElement('aside');
  el.className = 'panel';
  el.setAttribute('role', 'dialog');
  el.setAttribute('aria-labelledby', 'painel-titulo');
  el.innerHTML = renderPanel(local);
  container.appendChild(el);
  const prev = document.activeElement;
  const close = (silent = false) => {
    document.removeEventListener('keydown', onKey);
    el.remove();
    if (prev && prev.focus) prev.focus();
    if (!silent) onClose();
  };
  const onKey = (ev) => { if (ev.key === 'Escape') close(); };
  document.addEventListener('keydown', onKey);
  el.querySelector('.close').addEventListener('click', () => close());
  el.querySelector('.close').focus();
  return close;
}
