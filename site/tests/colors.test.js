import { test } from 'node:test';
import assert from 'node:assert/strict';
import { partyColor, contrastRatio, textColorFor, PALETTE, OUTROS } from '../js/colors.js';

test('partyColor returns same color for same party', () => {
  assert.equal(partyColor('REPUBLICANOS'), partyColor('REPUBLICANOS'));
  assert.equal(partyColor('UNIÃO'), partyColor('UNIÃO'));
  assert.notEqual(partyColor('REPUBLICANOS'), partyColor('UNIÃO'));
});

test('unknown party gets the deterministic "Outros" gray, in both modes', () => {
  assert.equal(partyColor('PARTIDO_X'), OUTROS.light);
  assert.equal(partyColor('PARTIDO_X', 'dark'), OUTROS.dark);
  assert.equal(partyColor(null), OUTROS.light);
});

test('dark mode uses the dark step of the same slot', () => {
  assert.equal(partyColor('REPUBLICANOS', 'dark'), PALETTE.dark[0]);
  assert.equal(partyColor('REPUBLICANOS', 'light'), PALETTE.light[0]);
});

test('contrastRatio matches WCAG reference values', () => {
  assert.equal(Math.round(contrastRatio('#000000', '#ffffff') * 10) / 10, 21);
  assert.equal(contrastRatio('#777777', '#777777'), 1);
});

test('every palette color keeps contrast >= 4.5 with textColorFor', () => {
  for (const c of [...PALETTE.light, ...PALETTE.dark, OUTROS.light, OUTROS.dark]) {
    const t = textColorFor(c);
    assert.ok(t === '#000' || t === '#fff');
    assert.ok(contrastRatio(c, t) >= 4.5, `${c} x ${t} = ${contrastRatio(c, t)}`);
  }
});
