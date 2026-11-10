// Roteador por hash: #/estado, #/municipio/<cod>, #/candidato/<cod>/<eleicao>/<nr>, #/comparativo, #/selo
import { loadSelo } from './data.js';
import { escapeHtml } from './analysis.js';

const views = {
  estado: () => import('./views/estado.js'),
  municipio: () => import('./views/municipio.js'),
  candidato: () => import('./views/candidato.js'),
  comparativo: () => import('./views/comparativo.js'),
  selo: () => import('./views/selo.js'),
};

export function parseHash(hash) {
  const [path, query = ''] = String(hash || '').replace(/^#\/?/, '').split('?');
  const parts = path.split('/').filter(Boolean).map(decodeURIComponent);
  const params = Object.fromEntries(new URLSearchParams(query));
  return { view: parts[0] || 'estado', args: parts.slice(1), params };
}

let token = 0;

async function route() {
  const app = document.getElementById('app');
  const r = parseHash(location.hash);
  const load = views[r.view] || views.estado;
  for (const a of document.querySelectorAll('[data-nav]')) {
    const nav = r.view === 'candidato' ? (r.args[0] === 'estado' ? 'estado' : 'municipio') : r.view;
    const on = a.dataset.nav === nav;
    if (on) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
  }
  const mine = ++token;
  app.innerHTML = '<p class="loading">Carregando…</p>';
  try {
    const mod = await load();
    if (mine !== token) return;
    await (mod.view || mod.render)(app, r, () => mine !== token);
  } catch (e) {
    if (mine !== token) return;
    console.error(e);
    app.innerHTML = `<p class="error">Não foi possível carregar esta tela: ${escapeHtml(e.message)}</p>`;
  }
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
