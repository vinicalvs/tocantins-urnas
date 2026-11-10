import { test } from 'node:test';
import assert from 'node:assert/strict';
import { compare2426, compareReport } from '../js/analysis.js';
import { render as renderSelo } from '../js/views/selo.js';

const loc = (id, nome, aptos, comp, votos = { '10': 1 }) => ({ id, zona: Number(id.split('-')[0]), nome, aptos, comparecimento: comp, votos });

const l24 = [
  loc('6-1012', 'ESCOLA ESTADUAL SÃO JOSÉ', 100, 80, { '10': 50, '20': 30 }),
  loc('6-1020', 'COLÉGIO A', 100, 70),
  loc('7-1030', 'ESCOLA B', 100, 90),
  loc('6-1040', 'ESCOLA SÓ 2024', 100, 50),
];
const l26 = [
  loc('6-1012', 'Escola Estadual Sao  Jose', 200, 150, { '22': 90, '10': 10 }),
  loc('7-1020', 'COLÉGIO A', 100, 70),                 // mesmo numero, outra zona
  loc('7-1030', 'ESCOLA C', 100, 90),                  // mesmo numero e zona, nome diferente
  loc('6-1050', 'ESCOLA SÓ 2026', 100, 50),
];

test('compare2426 excludes locais that exist in only one election', () => {
  const ids = compare2426(l24, l26).map((r) => r.id);
  assert.ok(!ids.includes('6-1040') && !ids.includes('6-1050'));
});

test('compare2426 does not match same number in different zones', () => {
  const ids = compare2426(l24, l26).map((r) => r.id);
  assert.ok(!ids.includes('6-1020') && !ids.includes('7-1020'));
});

test('compare2426 does not match same number with different normalized name', () => {
  const r = compare2426(l24, l26);
  assert.deepEqual(r.map((x) => x.id), ['6-1012']);
  assert.equal(r[0].v24, 80);
  assert.equal(r[0].v26, 75);
  assert.equal(r[0].delta, -5);
  assert.deepEqual(r[0].venc24, { key: '10', pct: 62.5 });
  assert.deepEqual(r[0].venc26, { key: '22', pct: 90 });
});

test('compareReport counts what was left out and why', () => {
  assert.deepEqual(compareReport(l24, l26), { comparados: 1, so2024: 2, so2026: 2, nome_diferente: 1 });
});

test('selo.render shows status, layers and escapes text', () => {
  const html = renderSelo({
    status: 'ok', data: '2026-11-10T12:00:00+00:00', camadas: { '1': true, '2': true, controle: true },
    checks: [{ layer: '1', check: 'hash_manifest', passed: true, n_checked: 16, n_divergences: 0 }],
    excecoes_usadas: [{ layer: '3', check: 'x', key: {}, cause: '<b>causa</b>', approved_on: '2026-11-10' }],
    fora_do_controle: ['2024 turno 2'],
  });
  assert.match(html, /Validação aprovada/);
  assert.match(html, /hash_manifest/);
  assert.ok(!html.includes('<b>causa</b>') && html.includes('&lt;b&gt;causa&lt;/b&gt;'));
});

test('selo.render groups exceptions by layer and check, causes collapsible', () => {
  const e = (check, cause) => ({ layer: '3', check, key: {}, cause, approved_on: '2026-11-10' });
  const html = renderSelo({
    status: 'ok', data: '2026-11-10T12:00:00+00:00', camadas: {}, checks: [],
    excecoes_usadas: [e('a', 'c1'), e('a', 'c2'), e('a', 'c2'), e('b', 'c3')],
  });
  assert.equal((html.match(/<li class="exc">/g) || []).length, 2);
  assert.match(html, /Camada 3 · a<\/strong> \(3 casos\)/);
  assert.match(html, /<details><summary>2 causas<\/summary>/);
  assert.match(html, /Camada 3 · b<\/strong> \(1 caso\): c3/);
});
