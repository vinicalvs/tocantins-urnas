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
