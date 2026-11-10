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
  prefeito: 'Prefeito', vereador: 'Vereador', governador: 'Governador', senador: 'Senador',
  deputado_federal: 'Deputado Federal', deputado_estadual: 'Deputado Estadual',
};
export const MAJORITARIOS = new Set(['prefeito', 'governador', 'senador']);

// Cargos proporcionais: partido mais votado no local (nominais pelo partido do candidato + legenda).
export function partyByLocal(locais, cands) {
  const out = {};
  for (const l of locais) {
    const soma = {};
    let total = 0;
    for (const [key, v] of Object.entries(l.votos || {})) {
      if (NAO_CANDIDATO.has(key)) continue;
      const sg = key.startsWith('legenda:') ? key.slice(8) : cands[key]?.partido;
      if (!sg) continue;
      soma[sg] = (soma[sg] || 0) + v;
      total += v;
    }
    let best = null;
    for (const [sg, v] of Object.entries(soma)) if (!best || v > best.votos || (v === best.votos && sg < best.sg)) best = { sg, votos: v };
    if (best && total > 0) out[l.id] = { sg: best.sg, votos: best.votos, pct: (best.votos / total) * 100 };
  }
  return out;
}

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

// Indicadores do Censo 2022 (proporcoes por setor somadas; ver docs/fontes.md 6.1).
export const IND_LABEL = {
  alfabetizacao_15: 'Alfabetização 15+', idade_0_14: 'Crianças (0–14)', idade_15_29: 'Jovens (15–29)',
  idade_60: 'Idosos (60+)', pretos_pardos: 'Pretos e pardos', agua_rede: 'Água por rede geral',
  esgoto_rede: 'Esgoto por rede', lixo_coletado: 'Lixo coletado',
};
