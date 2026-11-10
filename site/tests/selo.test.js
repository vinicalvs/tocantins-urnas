import { test } from 'node:test';
import assert from 'node:assert/strict';
import { render as renderSelo } from '../js/views/selo.js';

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

test('selo.render links each published report file, not a bare directory', () => {
  const html = renderSelo({ status: 'ok', data: '2026-11-10T12:00:00+00:00', camadas: {}, checks: [] },
    ['camada1.json', 'excecoes.json']);
  assert.ok(!html.includes('href="../validacao/"'));
  assert.match(html, /href="[^"]*\/validacao\/camada1\.json"/);
  assert.match(html, /href="[^"]*\/validacao\/excecoes\.json"/);
});

test('selo.render shows camada 5 label and credible-link percentage', () => {
  const html = renderSelo({
    status: 'ok', data: '2026-11-10T12:00:00+00:00', camadas: { '5': true }, checks: [],
    credibilidade: { '2024': { locais: 893, criveis: 563, pct: 63.0 }, '2026': { locais: 928, criveis: 566, pct: 61.0 } },
  });
  assert.match(html, /Camada 5: Censo 2022 e ligações setor → local/);
  assert.match(html, /Ligações críveis: 63,0% dos locais em 2024 · 61,0% em 2026/);
});
