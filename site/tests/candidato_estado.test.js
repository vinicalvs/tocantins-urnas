import { test } from 'node:test';
import assert from 'node:assert/strict';
import { rowsForEstado, toCsv, candidatoHref } from '../js/views/candidato.js';

const est = {
  candidatos: [{ nr: 1010, nome: 'A', partido: 'AA', votos: 11, municipios: { '73440': 7, '92410': 4 } }],
  municipios: [{ cod: '73440', validos: 70 }, { cod: '92410', validos: 8 }, { cod: '99999', validos: 5 }],
};
const nomes = { '73440': 'PALMAS', '92410': 'ARAGUAÍNA', '99999': 'X' };

test('rowsForEstado lists municipalities with votes, % of municipal valid votes, sorted by votes', () => {
  const r = rowsForEstado(est, 1010, nomes);
  assert.deepEqual(r.map((x) => [x.localId, x.nome, x.votos, x.pct]), [['73440', 'PALMAS', 7, 10], ['92410', 'ARAGUAÍNA', 4, 50]]);
});

test('toCsv for municipalities uses municipality headers', () => {
  const csv = toCsv(rowsForEstado(est, 1010, nomes), 'municipio');
  assert.equal(csv.split('\r\n')[0], 'cod_municipio;municipio;votos;pct_validos_municipio');
  assert.equal(csv.split('\r\n')[2], '92410;ARAGUAÍNA;4;50,00');
});

test('candidatoHref links statewide cargos to the state view and municipal ones to the municipality', () => {
  assert.equal(candidatoHref('2026-deputado_federal-1', { nr: 1010 }), '#/candidato/estado/2026-deputado_federal-1/1010');
  assert.equal(candidatoHref('2024-prefeito-1', { nr: 10, cod: '73440' }), '#/candidato/73440/2024-prefeito-1/10');
});
