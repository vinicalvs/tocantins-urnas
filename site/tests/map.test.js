import { test } from 'node:test';
import assert from 'node:assert/strict';
import { markersFromLocais } from '../js/map.js';
import { availableTurnos } from '../js/analysis.js';

test('markersFromLocais skips locais with null coordinates', () => {
  const locais = [
    { id: '6-1012', nome: 'ESCOLA A', lat: -10.1, lon: -48.3, votos: { '10': 3 } },
    { id: '7-1012', nome: 'ESCOLA B', lat: null, lon: null, votos: { '10': 9 } },
    { id: '7-1013', nome: 'ESCOLA C', lat: -10.2, lon: null, votos: {} },
  ];
  const winners = { '6-1012': { key: '10', votos: 3, pct: 100 }, '7-1012': { key: '10', votos: 9, pct: 100 } };
  const m = markersFromLocais(locais, winners);
  assert.deepEqual(m.map((x) => x.id), ['6-1012']);
  assert.deepEqual(m[0], { id: '6-1012', nome: 'ESCOLA A', lat: -10.1, lon: -48.3, winner: winners['6-1012'] });
});

test('municipio view hides turno 2 option when index.disponivel has only turno 1', () => {
  const index = { municipios: [
    { cod: '73440', disponivel: { '2024': { prefeito: [1, 2], vereador: [1] } } },
    { cod: '92410', disponivel: { '2024': { prefeito: [1] } } },
  ] };
  assert.deepEqual(availableTurnos(index, '92410', 2024, 'prefeito'), [1]);
  assert.deepEqual(availableTurnos(index, '73440', 2024, 'prefeito'), [1, 2]);
  assert.deepEqual(availableTurnos(index, '73440', 2026, 'prefeito'), []);
  assert.deepEqual(availableTurnos(index, '00000', 2024, 'prefeito'), []);
});
