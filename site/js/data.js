// Carregamento dos JSON exportados (sob demanda, com cache) e formatacao pt-BR.
const NF_INT = new Intl.NumberFormat('pt-BR');
const NF_PCT = new Intl.NumberFormat('pt-BR', { minimumFractionDigits: 1, maximumFractionDigits: 1 });

export const fmtInt = (n) => NF_INT.format(n);
export const fmtPct = (x) => `${NF_PCT.format(x)}%`;

export function normalizeText(s) {
  return String(s ?? '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().trim();
}

export const municipioPath = (cod, ano, cargo, turno) => `${cod}/${ano}_${cargo}_t${turno}.json`;
export const estadoPath = (ano, cargo, turno) => `estado/${ano}_${cargo}_t${turno}.json`;

export function makeLoader(base, fetchFn) {
  const cache = new Map();
  return (path) => {
    if (!cache.has(path)) {
      const p = fetchFn(`${base}/${path}`).then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status} em ${path}`);
        return r.json();
      });
      p.catch(() => cache.delete(path));
      cache.set(path, p);
    }
    return cache.get(path);
  };
}

const BASE = (globalThis.window && globalThis.window.DATA_BASE) || '../site_dados';
const load = makeLoader(BASE, (u) => fetch(u));

export const dataBase = BASE;
export const loadIndex = () => load('index.json');
export const loadSelo = () => load('selo_validacao.json');
export const loadMalha = () => load('malha_to.geojson');
export const loadMunicipio = (cod, ano, cargo, turno) => load(municipioPath(cod, ano, cargo, turno));
export const loadEstado = (ano, cargo, turno) => load(estadoPath(ano, cargo, turno));
export const loadFicha = (cod) => load(`${cod}/locais_ficha.json`);
export const loadIbge = (cod) => load(`${cod}/ibge.json`);
export const loadConjuntura = (nome) => load(`conjuntura/${nome}.json`);
