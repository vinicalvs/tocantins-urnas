import { test } from 'node:test';
import assert from 'node:assert/strict';
import { rowsFor, toCsv, sortRows } from '../js/views/candidato.js';

const json = { locais: [
  { id: '6-1', nome: 'ESCOLA A', bairro: 'CENTRO', votos: { '10': 5, '20': 15, branco: 4 } },
  { id: '6-2', nome: 'ESCOLA B', bairro: 'NORTE', votos: { '20': 10 } },
  { id: '7-1', nome: 'COLÉGIO "SÃO JOSÉ"; ANEXO', bairro: 'SUL', votos: { '10': 30, 'legenda:AA': 10 } },
] };

test('candidato.rowsFor returns only locais where candidato has votes, sorted by votos desc', () => {
  const r = rowsFor(json, 10);
  assert.deepEqual(r.map((x) => x.localId), ['7-1', '6-1']);
  assert.deepEqual(r[1], { localId: '6-1', nome: 'ESCOLA A', bairro: 'CENTRO', votos: 5, pct: 25 });
  assert.equal(r[0].pct, 75);
  assert.deepEqual(rowsFor(json, 99), []);
});

test('sortRows sorts by any column in both directions without mutating', () => {
  const r = rowsFor(json, 10);
  assert.deepEqual(sortRows(r, 'nome', 'asc').map((x) => x.localId), ['7-1', '6-1']);
  assert.deepEqual(sortRows(r, 'votos', 'asc').map((x) => x.localId), ['6-1', '7-1']);
  assert.deepEqual(r.map((x) => x.localId), ['7-1', '6-1']);
});

test('toCsv escapes quotes and semicolons and keeps accents', () => {
  const csv = toCsv(rowsFor(json, 10));
  const lines = csv.trim().split('\r\n');
  assert.equal(lines[0], 'local;nome;bairro;votos;pct_validos_local');
  assert.equal(lines[1], '7-1;"COLÉGIO ""SÃO JOSÉ""; ANEXO";SUL;30;75,00');
  assert.equal(lines[2], '6-1;ESCOLA A;CENTRO;5;25,00');
});
