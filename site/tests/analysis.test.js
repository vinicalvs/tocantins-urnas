import { test } from 'node:test';
import assert from 'node:assert/strict';
import { escapeHtml, winnerByLocal } from '../js/analysis.js';

test('escapeHtml neutralizes <, >, &, " and \'', () => {
  const s = escapeHtml(`<img src=x onerror=alert(1)>"O'Neil" & cia`);
  assert.ok(!s.includes('<') && !s.includes('>') && !s.includes('"') && !s.includes("'"));
  assert.equal(escapeHtml(`a&b`), 'a&amp;b');
  assert.equal(escapeHtml(null), '');
  assert.equal(escapeHtml(12), '12');
});

test('winnerByLocal picks highest votes and ignores branco/nulo', () => {
  const w = winnerByLocal([
    { id: '6-1', votos: { '10': 30, '20': 20, branco: 99, nulo: 98, nulo_tecnico: 97 } },
    { id: '7-1', votos: { '10': 5, 'legenda:PT': 40, branco: 1 } },
    { id: '8-1', votos: { branco: 3 } },
  ]);
  assert.deepEqual(w['6-1'], { key: '10', votos: 30, pct: 60 });
  assert.equal(w['7-1'].key, 'legenda:PT');
  assert.equal(w['7-1'].pct, (40 / 45) * 100);
  assert.equal(w['8-1'], undefined);
});

test('winnerByLocal breaks ties deterministically by key', () => {
  const w = winnerByLocal([{ id: 'a', votos: { '20': 5, '10': 5 } }]);
  assert.equal(w.a.key, '10');
});

import { electionOptions, electionLabel, parseElection } from '../js/analysis.js';

test('electionOptions lists only combinations present in the index, in fixed order', () => {
  const index = { municipios: [
    { disponivel: { '2026': { deputado_federal: [1] }, '2024': { vereador: [1], prefeito: [1, 2] } } },
    { disponivel: { '2024': { prefeito: [1] } } },
  ] };
  const o = electionOptions(index);
  assert.deepEqual(o.map(electionLabel), ['2024 · Prefeito', '2024 · Prefeito · 2º turno', '2024 · Vereador',
    '2026 · Deputado Federal']);
  assert.equal(parseElection('2024-vereador-1', o).cargo, 'vereador');
  assert.equal(parseElection('lixo', o), o[0]);
});
