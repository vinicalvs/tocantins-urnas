// Funcoes puras da tela Conjuntura (testadas com node --test).
const NF1 = new Intl.NumberFormat('pt-BR', { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const NF2 = new Intl.NumberFormat('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

// Por partido do prefeito: prefeituras, quantas tinham candidato da coligacao, quantas entregaram e a taxa
// (entregas / com candidato, %; null sem candidato).
export function rankingPartidos(linhas) {
  const g = new Map();
  for (const l of linhas) {
    const p = l.prefeito?.partido || '–';
    const x = g.get(p) || { partido: p, prefeituras: 0, com_candidato: 0, entregou: 0 };
    x.prefeituras += 1;
    if (l.status !== 'sem_candidato') x.com_candidato += 1;
    if (l.status === 'entregou') x.entregou += 1;
    g.set(p, x);
  }
  return [...g.values()].map((x) => ({ ...x, taxa: x.com_candidato ? (100 * x.entregou) / x.com_candidato : null }))
    .sort((a, b) => b.prefeituras - a.prefeituras || a.partido.localeCompare(b.partido, 'pt-BR'));
}

// 20% das areas com o indicador mais alto x 20% com o mais baixo (por contagem; floor, minimo 1).
// pct = soma dos votos do alvo / soma dos validos do grupo (agregado, nao media de percentuais).
export function quintis(areas, indicador, valorFn) {
  const ok = areas.filter((a) => a.ind?.[indicador] !== null && a.ind?.[indicador] !== undefined && a.validos > 0)
    .sort((a, b) => a.ind[indicador] - b.ind[indicador]);
  const n = Math.max(1, Math.floor(ok.length * 0.2));
  const grupo = (xs) => {
    const val = xs.reduce((s, a) => s + a.validos, 0);
    return { pct: val ? (100 * xs.reduce((s, a) => s + valorFn(a), 0)) / val : null, n: xs.length };
  };
  return { alto: grupo(ok.slice(ok.length - Math.min(n, ok.length))), baixo: grupo(ok.slice(0, n)) };
}

// Pearson ponderado; null com menos de 3 pontos ou variancia zero.
export function correlacaoPonderada(xs, ys, ws) {
  const pts = xs.map((x, i) => [x, ys[i], ws[i]]).filter(([x, y, w]) => Number.isFinite(x) && Number.isFinite(y) && w > 0);
  if (pts.length < 3) return null;
  const W = pts.reduce((s, p) => s + p[2], 0);
  const mx = pts.reduce((s, p) => s + p[0] * p[2], 0) / W;
  const my = pts.reduce((s, p) => s + p[1] * p[2], 0) / W;
  let sxy = 0; let sxx = 0; let syy = 0;
  for (const [x, y, w] of pts) { sxy += w * (x - mx) * (y - my); sxx += w * (x - mx) ** 2; syy += w * (y - my) ** 2; }
  if (sxx <= 1e-12 || syy <= 1e-12) return null;
  return Math.max(-1, Math.min(1, sxy / Math.sqrt(sxx * syy)));
}

function forca(r) {
  const a = Math.abs(r);
  if (a < 0.1) return 'praticamente nula';
  if (a < 0.3) return 'fraca';
  if (a < 0.5) return 'moderada';
  return 'forte';
}

// Frase de leitura: descreve onde o alvo vai melhor, sem afirmar causa.
export function resumoPerfil({ alvo, ind, q, r }) {
  const { alto, baixo } = q;
  if (alto.pct === null || baixo.pct === null) return `Sem áreas suficientes para comparar ${alvo}.`;
  const dif = alto.pct - baixo.pct;
  const onde = Math.abs(dif) < 1 ? `tem desempenho parecido onde ${ind.toLowerCase()} é alto ou baixo`
    : `vai melhor onde ${ind.toLowerCase()} é ${dif > 0 ? 'mais alto' : 'mais baixo'}`;
  const corr = r === null ? '' : ` Correlação ponderada pelo eleitorado: ${NF2.format(r)} (${forca(r)}).`;
  return `${alvo} ${onde}: ${NF1.format(alto.pct)}% dos válidos nos ${alto.n} lugares com o indicador mais alto e `
    + `${NF1.format(baixo.pct)}% nos ${baixo.n} com o mais baixo.${corr}`;
}
