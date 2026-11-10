import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { routeTo, breadcrumb, views } from '../js/app.js';
import { localRow } from '../js/views/municipio.js';

const index = { municipios: [{ cod: '73440', nome: 'PALMAS' }] };

test('malformed hash renders error instead of loading forever', async () => {
  const app = { innerHTML: '' };
  await routeTo(app, '#/municipio/%E0');
  assert.match(app.innerHTML, /class="error"/);
  assert.doesNotMatch(app.innerHTML, /Carregando/);
});

test('breadcrumb keeps election param', () => {
  const cand = { view: 'candidato', args: ['73440', '2024-vereador-1', '10111'], params: {} };
  assert.deepEqual(breadcrumb(cand, index), [
    { label: 'Tocantins', href: '#/estado?e=2024-vereador-1' },
    { label: 'PALMAS', href: '#/municipio/73440?e=2024-vereador-1' },
    { label: 'Candidato 10111', href: null },
  ]);
  const loc = { view: 'municipio', args: ['73440'], params: { e: '2026-governador-2', local: '6-1012' } };
  assert.deepEqual(breadcrumb(loc, index), [
    { label: 'Tocantins', href: '#/estado?e=2026-governador-2' },
    { label: 'PALMAS', href: '#/municipio/73440?e=2026-governador-2' },
    { label: 'Local 6-1012', href: null },
  ]);
  assert.deepEqual(breadcrumb({ view: 'estado', args: [], params: {} }, index), [{ label: 'Tocantins', href: null }]);
});

test('local without coords opens panel from table row', () => {
  const html = localRow({ id: '1-1001', zona: 1, nome: 'ESCOLA', bairro: 'B', lat: null, lon: null,
    aptos: 10, comparecimento: 8 }, null, 'light');
  assert.match(html, /data-local="1-1001"/);
  assert.match(html, /sem coordenadas/);
});

test('menu has no comparativo link', () => {
  const html = readFileSync(new URL('../index.html', import.meta.url), 'utf-8');
  assert.doesNotMatch(html, /comparativo|2024 × 2026/);
  assert.ok(!('comparativo' in views));
});

test('going back to the current screen while another loads still renders it', async () => {
  let rendersA = 0;
  let solta;
  const portao = new Promise((r) => { solta = r; });
  views.ta = async () => ({ render: async (app) => { rendersA += 1; app.innerHTML = 'A'; }, update: () => {} });
  views.tb = async () => ({ render: async (app, r, stale) => { await portao; if (!stale()) app.innerHTML = 'B'; } });
  try {
    const app = { innerHTML: '' };
    await routeTo(app, '#/ta');
    const b = routeTo(app, '#/tb');
    await routeTo(app, '#/ta');
    solta();
    await b;
    assert.equal(app.innerHTML, 'A');
    assert.equal(rendersA, 2);
  } finally {
    delete views.ta; delete views.tb;
  }
});

test('closing the panel goes back when it was opened here, otherwise replaces the entry', async () => {
  const { fecharPainel } = await import('../js/views/municipio.js');
  const calls = [];
  const hist = { back: () => calls.push('back'), replaceState: (_s, _t, url) => calls.push(`replace ${url}`) };
  fecharPainel({ abertoAqui: true, history: hist, hash: '#/municipio/1?e=x&local=2', reabrir: () => calls.push('update') });
  fecharPainel({ abertoAqui: false, history: hist, hash: '#/municipio/1?e=x&local=2', reabrir: () => calls.push('update') });
  assert.deepEqual(calls, ['back', 'replace #/municipio/1?e=x', 'update']);
});
