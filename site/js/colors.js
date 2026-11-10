// Paleta de partidos (paleta categorica de referencia do skill dataviz, validada em claro e escuro).
// Cor segue o partido, nunca a posicao: os 8 partidos que mais venceram municipios nas telas
// exportadas tem slot fixo; os demais ficam no cinza "Outros" (identidade nunca so pela cor:
// legenda, tooltip e tabela acompanham o mapa).
export const PALETTE = {
  light: ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#6250d6', '#e34948'],
  dark: ['#3987e5', '#d95926', '#199e70', '#c98500', '#d55181', '#008300', '#9085e9', '#e66767'],
};
export const OUTROS = { light: '#b5b4ad', dark: '#5f5e5a' };
export const PARTY_SLOTS = ['REPUBLICANOS', 'UNIÃO', 'PP', 'PL', 'MDB', 'PSDB', 'PDT', 'PSD'];

export function hasSlot(sg) {
  return PARTY_SLOTS.includes(sg);
}

export function partyColor(sg, mode = 'light') {
  const i = PARTY_SLOTS.indexOf(sg);
  const m = mode === 'dark' ? 'dark' : 'light';
  return i >= 0 ? PALETTE[m][i] : OUTROS[m];
}

function channel(c) {
  const s = c / 255;
  return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
}

function luminance(hex) {
  let h = hex.replace('#', '');
  if (h.length === 3) h = h.split('').map((x) => x + x).join('');
  const [r, g, b] = [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16));
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
}

export function contrastRatio(a, b) {
  const [x, y] = [luminance(a), luminance(b)].sort((p, q) => q - p);
  return (x + 0.05) / (y + 0.05);
}

export function textColorFor(bg) {
  return contrastRatio(bg, '#000') >= contrastRatio(bg, '#fff') ? '#000' : '#fff';
}
