// Selo de validacao: o que foi conferido, quando, e com quais excecoes.
import { loadSelo, fmtInt } from '../data.js';
import { escapeHtml } from '../analysis.js';

const CAMADA = {
  '1': 'Integridade (hashes, contagens, 139 municípios, duplicatas, 2º turno)',
  '2': 'Consistência interna (votos = comparecimento, aptos, seções) em duas implementações',
  '3': 'Cruzamento com outras bases do TSE em duas implementações',
  '4': 'Resultado oficial publicado pelo TSE',
  controle: 'Caso de controle: Palmas reproduz o projeto anterior',
};

export function render(selo) {
  const ok = selo.status === 'ok';
  const data = new Date(selo.data).toLocaleString('pt-BR', { dateStyle: 'long', timeStyle: 'short' });
  const camadas = Object.entries(selo.camadas || {}).map(([k, v]) => `<li>
      <strong class="${v ? 'ok' : 'bad'}">${v ? '✓' : '✗'}</strong>
      ${k === 'controle' ? '' : `Camada ${escapeHtml(k)}: `}${escapeHtml(CAMADA[k] || k)}</li>`).join('');
  const checks = (selo.checks || []).map((c) => `<tr><td>${escapeHtml(c.layer)}</td><td>${escapeHtml(c.check)}</td>
      <td>${c.passed ? '✓ ok' : '✗ falhou'}</td><td class="num">${fmtInt(c.n_checked)}</td>
      <td class="num">${fmtInt(c.n_divergences)}</td></tr>`).join('');
  const grupos = {};
  for (const e of selo.excecoes_usadas || []) {
    const k = `${e.layer}|${e.check}`;
    grupos[k] = grupos[k] || { layer: e.layer, check: e.check, n: 0, causas: new Map() };
    grupos[k].n += 1;
    grupos[k].causas.set(e.cause, (grupos[k].causas.get(e.cause) || 0) + 1);
  }
  const casos = (n) => `${fmtInt(n)} ${n === 1 ? 'caso' : 'casos'}`;
  const exc = Object.values(grupos).map((g) => {
    const head = `<strong>Camada ${escapeHtml(g.layer)} · ${escapeHtml(g.check)}</strong> (${casos(g.n)})`;
    if (g.causas.size === 1) return `<li class="exc">${head}: ${escapeHtml([...g.causas.keys()][0])}</li>`;
    const itens = [...g.causas].map(([c, n]) => `<li>${escapeHtml(c)} — ${casos(n)}</li>`).join('');
    return `<li class="exc">${head}<details><summary>${fmtInt(g.causas.size)} causas</summary><ul>${itens}</ul></details></li>`;
  }).join('');
  return `<h1>${ok ? 'Validação aprovada' : 'Validação reprovada'}</h1>
    <p class="sub">Executada em ${escapeHtml(data)}. Os dados do site só são publicados com todas as camadas aprovadas
      ou com cada divergência explicada e registrada.</p>
    <section class="card"><h2>Camadas</h2><ul class="selo-list">${camadas}</ul></section>
    <section class="card"><h2>Divergências explicadas</h2>
      ${exc ? `<ul>${exc}</ul>` : '<p>Nenhuma.</p>'}
      ${(selo.fora_do_controle || []).length ? `<p class="muted">Fora do caso de controle (sem base anterior):
        ${selo.fora_do_controle.map(escapeHtml).join(', ')}.</p>` : ''}</section>
    <section class="card"><h2>Todos os testes</h2><div class="table-wrap"><table>
      <thead><tr><th scope="col">Camada</th><th scope="col">Teste</th><th scope="col">Resultado</th>
        <th scope="col" class="num">Verificados</th><th scope="col" class="num">Divergências</th></tr></thead>
      <tbody>${checks}</tbody></table></div>
      <p class="muted">Relatórios completos e listas de divergências: <a href="../validacao/">pasta validacao</a>.</p></section>`;
}

export async function view(app, route, stale) {
  const selo = await loadSelo();
  if (stale()) return;
  app.innerHTML = render(selo);
}
