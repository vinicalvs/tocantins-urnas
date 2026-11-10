import { test } from 'node:test';
import assert from 'node:assert/strict';
import { renderPanel, tooltipLocal } from '../js/views/local_panel.js';
import { partyByLocal } from '../js/analysis.js';

const cand = (i) => ({ nr: 10000 + i, nome: i === 0 ? '<b>Zé</b>' : `V${i}`, partido: 'AA', votos: 100 - i, pct: 5.5 });
const ficha = {
  id: '6-1012', nome: 'ESCOLA <X>', bairro: 'CENTRO', lat: -10, lon: -48,
  anos: { 2024: { aptos: 100, comparecimento: 80 }, 2026: { aptos: 110, comparecimento: 99 } },
  cargos: {
    '2024-prefeito-1': [{ nr: 10, nome: 'ANA', partido: 'AA', votos: 50, pct: 62.5 }],
    '2024-vereador-1': Array.from({ length: 15 }, (_, i) => cand(i)),
    '2026-governador-1': [{ nr: 45, nome: 'GOV', partido: 'BB', votos: 70, pct: 70.0 }],
  },
  entorno: { credivel: true, ano_ligacao: 2026, area_id: '6-1012', moradores: 2162,
    indicadores: { alfabetizacao_15: 99.6, idade_0_14: 13.2, idade_15_29: 29.6, idade_60: 13.3, pretos_pardos: 51.1,
      agua_rede: 97.1, esgoto_rede: null, lixo_coletado: 100 } },
};

test('renderPanel lists top 15 vereadores and escapes names', () => {
  const html = renderPanel(ficha);
  const ver = html.match(/data-cargo="2024-vereador-1"[\s\S]*?<\/table>/)[0];
  assert.equal((ver.match(/<tr class="c">/g) || []).length, 15);
  assert.ok(!html.includes('<b>Zé</b>') && html.includes('&lt;b&gt;Zé&lt;/b&gt;'));
  assert.ok(html.includes('ESCOLA &lt;X&gt;'));
  assert.match(html, /80,0%/);                       // comparecimento 2024
  assert.match(html, /Alfabetização 15\+/);
  assert.match(html, /não indica como cada pessoa votou/);
});

test('renderPanel shows aviso when entorno is null', () => {
  const html = renderPanel({ ...ficha, entorno: null });
  assert.match(html, /Perfil do entorno indisponível/);
  assert.doesNotMatch(html, /Alfabetização/);
});

test('tooltipLocal is short: name, turnout and top of each cargo', () => {
  const t = tooltipLocal(ficha);
  assert.match(t, /ESCOLA &lt;X&gt;/);
  assert.match(t, /Prefeito 2024: ANA \(AA\) 62,5%/);
  assert.match(t, /Governador 2026: GOV \(BB\) 70,0%/);
  assert.ok((t.match(/<br>/g) || []).length <= 8);
});

test('partyByLocal sums nominal and legenda by party', () => {
  const cands = { 10111: { partido: 'AA' }, 22222: { partido: 'BB' }, 22333: { partido: 'BB' } };
  const r = partyByLocal([{ id: 'x', votos: { 10111: 30, 22222: 20, 22333: 15, 'legenda:AA': 2, branco: 9 } }], cands);
  assert.deepEqual(r.x, { sg: 'BB', votos: 35, pct: (35 / 67) * 100 });
});
