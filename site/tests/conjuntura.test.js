import { test } from 'node:test';
import assert from 'node:assert/strict';
import { rankingPartidos, quintis, correlacaoPonderada, resumoPerfil } from '../js/conjuntura.js';

const linha = (partido, status) => ({ cod: 'x', prefeito: { nome: 'P', partido }, status });

test('rankingPartidos counts and rates', () => {
  const r = rankingPartidos([linha('PP', 'entregou'), linha('PP', 'nao_entregou'), linha('PP', 'sem_candidato'),
    linha('MDB', 'entregou'), linha('PL', 'entregou'), linha('PL', 'entregou'), linha('PL', 'nao_entregou')]);
  assert.deepEqual(r.map((x) => x.partido), ['PL', 'PP', 'MDB']);
  assert.deepEqual(r[1], { partido: 'PP', prefeituras: 3, com_candidato: 2, entregou: 1, taxa: 50 });
  assert.equal(r[2].taxa, 100);
});

test('quintis uses pooled percentage and floors group size', () => {
  // 11 areas -> grupos de 2 (floor de 2,2)
  const areas = Array.from({ length: 11 }, (_, i) => ({ ind: { a: i }, validos: 100 + i * 10, v: i }));
  const q = quintis(areas, 'a', (x) => x.v);
  assert.equal(q.baixo.n, 2);
  assert.equal(q.alto.n, 2);
  assert.equal(q.baixo.pct, (100 * (0 + 1)) / (100 + 110));
  assert.equal(q.alto.pct, (100 * (9 + 10)) / (190 + 200));
});

test('quintis with fewer than 5 areas uses 1 per group', () => {
  const areas = [{ ind: { a: 3 }, validos: 10, v: 5 }, { ind: { a: 1 }, validos: 10, v: 1 }, { ind: { a: null }, validos: 10, v: 9 }];
  const q = quintis(areas, 'a', (x) => x.v);
  assert.deepEqual(q, { alto: { pct: 50, n: 1 }, baixo: { pct: 10, n: 1 } });
});

test('correlacaoPonderada known value', () => {
  assert.equal(correlacaoPonderada([1, 2, 3, 4], [2, 4, 6, 8], [1, 5, 1, 2]), 1);
  assert.ok(Math.abs(correlacaoPonderada([1, 2, 3], [3, 2, 1], [1, 1, 1]) + 1) < 1e-12);
});

test('correlacaoPonderada returns null for constant x or < 3 points', () => {
  assert.equal(correlacaoPonderada([2, 2, 2], [1, 2, 3], [1, 1, 1]), null);
  assert.equal(correlacaoPonderada([1, 2], [1, 2], [1, 1]), null);
});

test('perfil text never says porque/causa', () => {
  for (const [alto, baixo] of [[60, 30], [30, 60], [40, 40.2]]) {
    const t = resumoPerfil({ alvo: 'PL', ind: 'Alfabetização 15+', q: { alto: { pct: alto, n: 10 }, baixo: { pct: baixo, n: 10 } }, r: 0.4 });
    assert.doesNotMatch(t, /porque|causa|explica|devido/i);
    assert.match(t, /PL/);
  }
});

test('entrega texts describe the coalition result without crediting the mayor', async () => {
  const { STATUS_TXT, resumoEntrega } = await import('../js/conjuntura.js');
  const { prefeitoCard } = await import('../js/views/municipio.js');
  const linha = { cod: '1', prefeito: { nome: 'P', partido: 'PP' }, status: 'entregou', cand_nome: 'C', cand_partido: 'PP',
    venc_nome: 'C', venc_partido: 'PP', margem_pp: 3 };
  const textos = [...Object.values(STATUS_TXT), resumoEntrega({ entregou: 3, nao_entregou: 1, sem_candidato: 1 }, false),
    resumoEntrega({ entregou: 1, nao_entregou: 0, sem_candidato: 0 }, true),
    prefeitoCard({ 'governador-1': [linha] }, '1')];
  for (const t of textos) assert.doesNotMatch(t, /entreg/i);
  assert.match(resumoEntrega({ entregou: 3, nao_entregou: 1, sem_candidato: 1 }, false), /3 de 4/);
});
