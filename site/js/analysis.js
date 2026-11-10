// Funcoes puras de analise (testadas com node --test).
const ESC = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };

export function escapeHtml(s) {
  if (s === null || s === undefined) return '';
  return String(s).replace(/[&<>"']/g, (c) => ESC[c]);
}

const NAO_CANDIDATO = new Set(['branco', 'nulo', 'nulo_tecnico']);

// Vencedor por local entre candidatos e legendas; pct sobre os votos de candidatos + legendas do local.
export function winnerByLocal(locais) {
  const out = {};
  for (const l of locais) {
    let best = null;
    let total = 0;
    for (const [key, v] of Object.entries(l.votos || {})) {
      if (NAO_CANDIDATO.has(key)) continue;
      total += v;
      if (!best || v > best.votos || (v === best.votos && key < best.key)) best = { key, votos: v };
    }
    if (best && total > 0) out[l.id] = { key: best.key, votos: best.votos, pct: (best.votos / total) * 100 };
  }
  return out;
}

export const CARGO_LABEL = {
  prefeito: 'Prefeito', vereador: 'Vereador',
  deputado_federal: 'Deputado Federal', deputado_estadual: 'Deputado Estadual',
};
export const MAJORITARIOS = new Set(['prefeito']);

export const electionKey = (o) => `${o.ano}-${o.cargo}-${o.turno}`;

export function electionLabel(o) {
  const t = o.turno === 2 ? ' · 2º turno' : '';
  return `${o.ano} · ${CARGO_LABEL[o.cargo] || o.cargo}${t}`;
}

// Combinacoes (ano, cargo, turno) presentes no indice, em ordem fixa.
export function electionOptions(index) {
  const seen = new Map();
  for (const m of index.municipios) {
    for (const [ano, cargos] of Object.entries(m.disponivel)) {
      for (const [cargo, turnos] of Object.entries(cargos)) {
        for (const turno of turnos) {
          const o = { ano: Number(ano), cargo, turno };
          seen.set(electionKey(o), o);
        }
      }
    }
  }
  const order = Object.keys(CARGO_LABEL);
  return [...seen.values()].sort((a, b) => a.ano - b.ano || order.indexOf(a.cargo) - order.indexOf(b.cargo)
    || a.turno - b.turno);
}

export function parseElection(key, options) {
  return options.find((o) => electionKey(o) === key) || options[0];
}

// Turnos que existem para (municipio, ano, cargo): a tela so oferece estes.
export function availableTurnos(index, cod, ano, cargo) {
  const m = index.municipios.find((x) => x.cod === cod);
  return [...(m?.disponivel?.[String(ano)]?.[cargo] || [])].sort((a, b) => a - b);
}

export function normalizeName(s) {
  return String(s ?? '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase()
    .replace(/[^a-z0-9]+/g, ' ').trim();
}

function classify(locais24, locais26) {
  const a = new Map(locais24.map((l) => [l.id, l]));
  const b = new Map(locais26.map((l) => [l.id, l]));
  const pares = [];
  let nomeDiferente = 0;
  for (const [id, l] of a) {
    const m = b.get(id);
    if (!m) continue;
    if (normalizeName(l.nome) === normalizeName(m.nome)) pares.push([l, m]);
    else nomeDiferente += 1;
  }
  return {
    pares, nomeDiferente,
    so2024: [...a.keys()].filter((id) => !b.has(id)).length,
    so2026: [...b.keys()].filter((id) => !a.has(id)).length,
  };
}

// So locais presentes nas duas eleicoes: mesmo id (zona-nr_local) e mesmo nome normalizado.
// v24/v26 = comparecimento / aptos (%); venc = vencedor do local no cargo escolhido em cada eleicao.
export function compare2426(locais24, locais26) {
  const { pares } = classify(locais24, locais26);
  const w24 = winnerByLocal(pares.map((p) => p[0]));
  const w26 = winnerByLocal(pares.map((p) => p[1]));
  const part = (l) => (l.aptos ? (100 * l.comparecimento) / l.aptos : null);
  const venc = (w) => (w ? { key: w.key, pct: w.pct } : null);
  return pares.map(([l, m]) => {
    const v24 = part(l);
    const v26 = part(m);
    return { id: l.id, nome: m.nome, v24, v26, delta: v24 === null || v26 === null ? null : v26 - v24,
      venc24: venc(w24[l.id]), venc26: venc(w26[m.id]) };
  });
}

export function compareReport(locais24, locais26) {
  const c = classify(locais24, locais26);
  return { comparados: c.pares.length, so2024: c.so2024, so2026: c.so2026, nome_diferente: c.nomeDiferente };
}
