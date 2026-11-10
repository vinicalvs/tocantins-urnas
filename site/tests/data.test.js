import { test } from 'node:test';
import assert from 'node:assert/strict';
import { fmtInt, fmtPct, municipioPath, estadoPath, makeLoader, normalizeText } from '../js/data.js';

test('fmtInt(1234567) === "1.234.567"', () => {
  assert.equal(fmtInt(1234567), '1.234.567');
  assert.equal(fmtInt(0), '0');
});

test('fmtPct uses comma decimal and one place', () => {
  assert.equal(fmtPct(39.224), '39,2%');
  assert.equal(fmtPct(100), '100,0%');
});

test('paths follow the export layout', () => {
  assert.equal(municipioPath('73440', 2024, 'prefeito', 2), '73440/2024_prefeito_t2.json');
  assert.equal(estadoPath(2026, 'deputado_federal', 1), 'estado/2026_deputado_federal_t1.json');
});

test('loader caches by path and uses the configured base', async () => {
  const calls = [];
  const fakeFetch = async (url) => { calls.push(url); return { ok: true, json: async () => ({ url }) }; };
  const load = makeLoader('../site_dados', fakeFetch);
  const a = await load('index.json');
  const b = await load('index.json');
  assert.equal(a, b);
  assert.deepEqual(calls, ['../site_dados/index.json']);
});

test('loader rejects on HTTP error', async () => {
  const load = makeLoader('x', async () => ({ ok: false, status: 404 }));
  await assert.rejects(load('nao.json'), /404/);
});

test('normalizeText strips accents and case', () => {
  assert.equal(normalizeText('Araguaína'), 'araguaina');
  assert.equal(normalizeText("PAU D'ARCO"), "pau d'arco");
});
