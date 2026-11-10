// Roteador por hash: #/estado, #/municipio/<cod>[?e=<eleicao>&local=<id>], #/candidato/..., #/selo
import { loadSelo, loadIndex } from './data.js';
import { escapeHtml } from './analysis.js';

export const views = {
  estado: () => import('./views/estado.js'),
  municipio: () => import('./views/municipio.js'),
  candidato: () => import('./views/candidato.js'),
  conjuntura: () => import('./views/conjuntura.js'),
  selo: () => import('./views/selo.js'),
};

export function parseHash(hash) {
  const [path, query = ''] = String(hash || '').replace(/^#\/?/, '').split('?');
  const parts = path.split('/').filter(Boolean).map(decodeURIComponent);
  const params = Object.fromEntries(new URLSearchParams(query));
  return { view: parts[0] || 'estado', args: parts.slice(1), params };
}

// Trilha: Tocantins › Municipio › Candidato/Local, levando a eleicao escolhida (e=) a cada nivel.
export function breadcrumb(r, index) {
  const e = r.view === 'candidato' ? r.args[1] : r.params.e;
  const q = e ? `?e=${encodeURIComponent(e)}` : '';
  const isState = r.view === 'estado' || (r.view === 'municipio' && !r.args[0]);
  const out = [{ label: 'Tocantins', href: isState && r.view === 'estado' ? null : `#/estado${q}` }];
  if (r.view === 'municipio' && !r.args[0]) out.push({ label: 'Municípios', href: null });
  const cod = r.view === 'municipio' || (r.view === 'candidato' && r.args[0] !== 'estado') ? r.args[0] : null;
  const mun = cod && (index?.municipios || []).find((m) => m.cod === cod);
  if (mun) {
    const last = r.view === 'municipio' && !r.params.local;
    out.push({ label: mun.nome, href: last ? null : `#/municipio/${cod}${q}` });
  }
  if (r.view === 'municipio' && r.params.local) out.push({ label: `Local ${r.params.local}`, href: null });
  if (r.view === 'candidato') out.push({ label: `Candidato ${r.args[2]}`, href: null });
  if (r.view === 'conjuntura') out.push({ label: 'Conjuntura', href: null });
  if (r.view === 'selo') out.push({ label: 'Validação', href: null });
  return out;
}

function trailHtml(items) {
  return items.map((i) => (i.href ? `<a href="${escapeHtml(i.href)}">${escapeHtml(i.label)}</a>`
    : `<span aria-current="page">${escapeHtml(i.label)}</span>`)).join('<span aria-hidden="true"> › </span>');
}

let token = 0;
let current = { key: null, mod: null };

// Chave da tela sem o parametro `local`: so o painel muda quando so ele muda.
const screenKey = (r) => JSON.stringify([r.view, r.args, { ...r.params, local: undefined }]);

export async function routeTo(app, hash, { nav = () => {}, trail = () => {} } = {}) {
  const mine = ++token;
  try {
    const r = parseHash(hash);
    nav(r);
    if (current.mod?.update && current.key === screenKey(r)) {
      current.mod.update(app, r);
      trail(r);
      return;
    }
    app.innerHTML = '<p class="loading">Carregando…</p>';
    const mod = await (views[r.view] || views.estado)();
    if (mine !== token) return;
    await (mod.view || mod.render)(app, r, () => mine !== token);
    if (mine !== token) return;
    current = { key: screenKey(r), mod };
    trail(r);
  } catch (e) {
    if (mine !== token) return;
    current = { key: null, mod: null };
    console.error(e);
    app.innerHTML = `<p class="error">Não foi possível carregar esta tela: ${escapeHtml(e.message)}</p>
      <p><a href="#/estado">Voltar ao Tocantins</a></p>`;
  }
}

function highlightNav(r) {
  const nav = r.view === 'candidato' ? (r.args[0] === 'estado' ? 'estado' : 'municipio') : r.view;
  for (const a of document.querySelectorAll('[data-nav]')) {
    if (a.dataset.nav === nav) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
  }
}

async function drawTrail(r) {
  const el = document.getElementById('trilha');
  if (!el) return;
  const items = breadcrumb(r, await loadIndex().catch(() => null));
  el.innerHTML = items.length > 1 ? trailHtml(items) : '';
}

function route() {
  return routeTo(document.getElementById('app'), location.hash, { nav: highlightNav, trail: drawTrail });
}

async function badge() {
  const el = document.getElementById('selo-badge');
  try {
    const s = await loadSelo();
    const ok = s.status === 'ok';
    const data = new Date(s.data).toLocaleDateString('pt-BR');
    el.innerHTML = `<a href="#/selo"><span class="${ok ? 'ok' : 'bad'}">${ok ? '✓ Validado' : '✗ Validação falhou'}</span>`
      + `<span>${escapeHtml(data)}</span></a>`;
  } catch {
    el.innerHTML = '<a href="#/selo"><span class="bad">Validação indisponível</span></a>';
  }
}

if (globalThis.window && globalThis.document) {
  window.addEventListener('hashchange', route);
  window.addEventListener('DOMContentLoaded', () => { route(); badge(); });
}
