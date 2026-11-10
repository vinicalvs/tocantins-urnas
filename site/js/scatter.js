// Dispersao em SVG: um eixo x e um y (sem eixo duplo), area do ponto ~ peso, tooltip ao passar o mouse.
// pontos: [{x, y, r (peso), label (html escapado), cor}]. A view gera a tabela equivalente.
const W = 640;
const H = 380;
const M = { l: 52, r: 16, t: 12, b: 44 };

function ticks(lo, hi, n = 5) {
  const span = hi - lo || 1;
  const step0 = span / n;
  const mag = 10 ** Math.floor(Math.log10(step0));
  const step = [1, 2, 2.5, 5, 10].map((k) => k * mag).find((s) => s >= step0);
  const out = [];
  for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) out.push(Number(v.toFixed(6)));
  return out;
}

function dominio(vs) {
  let lo = Math.min(...vs);
  let hi = Math.max(...vs);
  if (lo === hi) { lo -= 1; hi += 1; }
  const pad = (hi - lo) * 0.05;
  return [Math.max(0, lo - pad), Math.min(100, hi + pad)];
}

const NF = new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 1 });

export function render(el, pontos, { xLabel, yLabel }) {
  const ok = pontos.filter((p) => Number.isFinite(p.x) && Number.isFinite(p.y));
  if (!ok.length) { el.innerHTML = '<p class="muted">Sem pontos para mostrar.</p>'; return; }
  const [x0, x1] = dominio(ok.map((p) => p.x));
  const [y0, y1] = dominio(ok.map((p) => p.y));
  const sx = (v) => M.l + ((v - x0) / (x1 - x0)) * (W - M.l - M.r);
  const sy = (v) => H - M.b - ((v - y0) / (y1 - y0)) * (H - M.t - M.b);
  const rmax = Math.max(...ok.map((p) => p.r || 1));
  const rad = (p) => 3 + 9 * Math.sqrt((p.r || 1) / rmax);
  const xt = ticks(x0, x1);
  const yt = ticks(y0, y1);
  const grid = yt.map((v) => `<line x1="${M.l}" x2="${W - M.r}" y1="${sy(v)}" y2="${sy(v)}" class="sc-grid"/>
      <text x="${M.l - 6}" y="${sy(v) + 4}" text-anchor="end" class="sc-tick">${NF.format(v)}</text>`).join('')
    + xt.map((v) => `<text x="${sx(v)}" y="${H - M.b + 16}" text-anchor="middle" class="sc-tick">${NF.format(v)}</text>`).join('');
  // maiores primeiro: os pequenos ficam por cima e continuam clicaveis
  const ordem = [...ok].sort((a, b) => (b.r || 1) - (a.r || 1));
  const dots = ordem.map((p, i) => `<g class="sc-pt" data-i="${i}">
      <circle cx="${sx(p.x)}" cy="${sy(p.y)}" r="${Math.max(rad(p), 8)}" fill="transparent"/>
      <circle cx="${sx(p.x)}" cy="${sy(p.y)}" r="${rad(p)}" fill="${p.cor}" class="sc-dot"/></g>`).join('');
  el.innerHTML = `<div class="sc-wrap"><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Dispersão: ${xLabel} no eixo horizontal, ${yLabel} no vertical; a mesma informação está na tabela.">
      ${grid}
      <line x1="${M.l}" x2="${W - M.r}" y1="${H - M.b}" y2="${H - M.b}" class="sc-axis"/>
      <text x="${(M.l + W - M.r) / 2}" y="${H - 8}" text-anchor="middle" class="sc-label">${xLabel}</text>
      <text transform="translate(14 ${(M.t + H - M.b) / 2}) rotate(-90)" text-anchor="middle" class="sc-label">${yLabel}</text>
      ${dots}</svg><div class="sc-tip" hidden></div></div>`;
  const tip = el.querySelector('.sc-tip');
  const wrap = el.querySelector('.sc-wrap');
  for (const g of el.querySelectorAll('.sc-pt')) {
    const p = ordem[Number(g.dataset.i)];
    g.addEventListener('mouseenter', () => {
      g.classList.add('on');
      tip.innerHTML = p.label;
      tip.hidden = false;
      const box = wrap.getBoundingClientRect();
      const c = g.lastElementChild.getBoundingClientRect();
      tip.style.left = `${Math.min(c.left - box.left + 12, box.width - 220)}px`;
      tip.style.top = `${Math.max(0, c.top - box.top - 8)}px`;
    });
    g.addEventListener('mouseleave', () => { g.classList.remove('on'); tip.hidden = true; });
  }
}
