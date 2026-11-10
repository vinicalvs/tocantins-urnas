# Conjuntura e Censo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Acrescentar ao site do Tocantins a análise de conjuntura (prefeitos × 2026, perfil do voto pelo Censo 2022, comparecimento), a ficha do local de votação e a correção da navegação, com os dados novos validados numa camada 5 do selo.

**Architecture:** Novas etapas no pacote `tocantins/`: `censo.py` (Censo por setor e IBGE municipal), `ligacao.py` (setor → local e áreas de votação, em duas implementações), `conjuntura.py` (entrega dos prefeitos), `validate/layer5.py`. A exportação ganha Governador/Senador 2026 e arquivos sob demanda para a ficha do local e a seção Conjuntura. O site ganha `views/conjuntura.js`, `views/local_panel.js`, `js/conjuntura.js` (funções puras) e `js/scatter.js` (SVG).

**Tech Stack:** Python 3.12, duckdb, pandas, pyarrow, requests, **geopandas** (novo), pytest; JS ES modules + Leaflet 1.9.4, `node --test`.

**Spec:** `docs/superpowers/specs/2026-11-10-conjuntura-censo-design.md` (o projeto base é `docs/superpowers/specs/2026-11-10-tocantins-urnas-design.md`).

## Global Constraints

- `C:\Users\VINI\Documents\Palmas_Urnas_e_Censo` é só leitura. Dele se lê `census_regioes.json` (caso de controle) e, como referência de método, `p3_census.py` e `p8_ligacao.py`; nada é copiado de lá como dado.
- Toda fonte nova entra em `tocantins/config.py:SOURCES`, é baixada para `dados_brutos/` e fica com hash no manifesto; bruto nunca sobrescrito.
- Arquivos nacionais do Censo (centenas de MB) são lidos em blocos, só colunas usadas, filtrando setores com código iniciado por `17`; nunca carregar o arquivo inteiro.
- Locais especiais = nome contém `TRÂNSITO`, `TRANSITO`, `PENAL` ou `PRISIONAL` (sem diferenciar acento/caixa) ou 0 eleitores no cadastro do ano. Não recebem setores.
- Ligação crível: 0,4 ≤ eleitores / moradores ≤ 1,6.
- Ligação setor → local calculada em projeção métrica EPSG:31982 (SIRGAS 2000 / UTM 22S), só dentro do mesmo município, para 2024 e 2026 separadamente.
- Divergência sem causa em `validacao/excecoes.json` reprova; `impl_disagreement` da ligação não aceita exceção; exportação só com selo ok.
- Texto do site: "perfil do entorno", "vai melhor em"; nunca causalidade; "candidato da coligação do partido do prefeito", nunca "candidato do prefeito".
- Gráficos seguem o skill dataviz (uma escala, legenda, tabela equivalente, tooltip, modo escuro, paleta validada).
- Publicar (push para `origin/main`, que alimenta o GitHub Pages) só depois de o usuário confirmar.
- Mensagens ao usuário em português.
- Princípio de interface pedido pelo usuário: **enxuto, com muita informação e claro**. Densidade alta (tabelas compactas, números com contexto: votos + % + margem), nada decorativo, um título e uma frase de leitura por bloco ("o que isto mostra"), sem texto explicativo longo; detalhes em `<details>` ou no painel, não na tela principal.

## Review Focus

1. Partido do prefeito que é membro de federação (ex.: PC do B na federação com PT e PV) e coligação de Governador descrita só pela sigla da federação: o prefeito tem candidato da coligação. Teste na Task 3.
2. Governador 2º turno em que a coligação do prefeito ficou de fora: status `sem_candidato`, sem erro. Teste na Task 5.
3. Município pequeno onde nenhum local tem ligação crível (ou só um local): vira uma área só; a ficha do local mostra o aviso; o perfil usa o município. Testes nas Tasks 4 e 8.
4. Local sem coordenadas: fica fora do mapa e da ligação, mas a ficha abre pela tabela de locais. Testes nas Tasks 4 e 8.
5. Empate de distância entre dois locais e setor com 0 morador: desempate pelo menor `id` do local nas duas implementações; setor vazio é ligado mas não pesa nas proporções. Teste na Task 4.

---

## File Structure

```
tocantins/config.py            + fontes do Censo e do SIDRA
tocantins/censo.py             agregados por setor (em blocos), centroides, IBGE municipal
tocantins/coligacoes.py        partidos de cada candidatura (coligação + federação)
tocantins/ligacao.py           setor → local (geopandas e numpy), credibilidade, áreas de votação
tocantins/conjuntura.py        entrega dos prefeitos
tocantins/validate/layer5.py   camada 5 "Censo e ligações"
tocantins/validate/layer4.py   + Governador e Senador (alvos)
tocantins/validate/control.py  + controle de população de Palmas
tocantins/export.py            + Governador/Senador, ficha do local, ibge.json, conjuntura/*
scripts/02b_censo.py           normaliza Censo, coligações e ligação para base/
docs/fontes.md                 + seção 6 (Censo/SIDRA); docs/como_rodar.md (novo)
site/js/app.js, map.js         navegação, trilha, mapa sem captura da roda
site/js/conjuntura.js          funções puras: entrega, quintis, correlação, ficha
site/js/scatter.js             dispersão em SVG
site/js/views/municipio.js     ficha IBGE, prefeito × 2026, tooltip curto, painel
site/js/views/local_panel.js   painel do local
site/js/views/conjuntura.js    abas Prefeitos, Perfil, Comparecimento
```

---

### Task 1: Fontes do Censo 2022 e do IBGE municipal

**Files:**
- Modify: `tocantins/config.py`, `docs/fontes.md`
- Test: `tests/test_config_censo.py`

**Interfaces:**
- Produces: chaves em `SOURCES`: `censo_malha_to`, `censo_basico`, `censo_demografia`, `censo_alfabetizacao`, `censo_cor_raca`, `censo_domicilio2`, `censo_renda` (só se publicado), `sidra_pop_area`, `sidra_pib`. Arquivos em `dados_brutos/censo/` e `dados_brutos/sidra/`.

- [ ] **Step 1: Descobrir as URLs reais.** Agregados por setor: diretório `https://ftp.ibge.gov.br/Censos/Censo_Demografico_2022/Agregados_por_Setores_Censitarios/` (zips nacionais em CSV). Malha: `geoftp.ibge.gov.br`, setores 2022 da UF TO em GPKG. SIDRA: tabela 4714 (população, área, densidade do Censo 2022) e a tabela de PIB per capita municipal mais recente, via `https://apisidra.ibge.gov.br/values/t/<tabela>/n6/in n3 17/v/<vars>/p/last`. Confirmar cada URL com uma requisição `HEAD` (ou GET da listagem) e registrar URL, tamanho e data em `docs/fontes.md` seção 6, com os códigos das variáveis usadas (conferir no dicionário do IBGE; `p3_census.py` de Palmas serve de referência). Renda por setor: registrar se existe; se não, `censo_renda` não é criado.
- [ ] **Step 2: Write the failing test** `test_censo_sources_registered`: as chaves acima existem (exceto `censo_renda` se ausente), `sha_url is None`, `filename` começa com `censo/` ou `sidra/`, URLs começam com `https://`.
- [ ] **Step 3: Run** `pytest tests/test_config_censo.py -v` → FAIL (chave ausente).
- [ ] **Step 4: Implement** as entradas em `_build()` de `config.py`.
- [ ] **Step 5: Run** → PASS; depois `python -I scripts/01_baixar.py` (baixa só o que falta; zips do Censo são descompactados como os do TSE). Conferir no manifesto as novas chaves com tamanho > 0.
- [ ] **Step 6: Commit** `feat: fontes do Censo 2022 e do SIDRA no manifesto`.

### Task 2: Censo por setor e IBGE municipal

**Files:**
- Create: `tocantins/censo.py`
- Test: `tests/test_censo.py`

**Interfaces:**
- Consumes: arquivos da Task 1.
- Produces:
  - `censo.read_setores(csv: Path, cols: list[str], uf_prefix: str = "17", chunksize: int = 200_000) -> pd.DataFrame` (índice `cd_setor` texto de 15 dígitos; valores numéricos; `X`/vazio → `NaN`, marcado em coluna `sigilo: bool`).
  - `censo.INDICADORES: dict[str, tuple[str, str]]` = nome → (coluna numerador, coluna denominador): `alfabetizacao_15`, `idade_0_14`, `idade_15_29`, `idade_60`, `pretos_pardos`, `agua_rede`, `esgoto_rede`, `lixo_coletado`, `renda_media` (se houver). Mais `moradores`, `domicilios`, `area_km2`, `densidade` diretos.
  - `censo.build_setores(raw: Path) -> pd.DataFrame` → `base/censo_setor.parquet`: `cd_setor, cd_mun_ibge (7 díg.), cx, cy` (centroide em EPSG:31982), `moradores, domicilios, area_km2, sigilo` e um par `<ind>_num, <ind>_den` por indicador.
  - `censo.build_municipios(sidra_dir: Path) -> pd.DataFrame` → `base/ibge_municipio.parquet`: `cd_mun_ibge, populacao, area_km2, densidade, pib_per_capita, ano_pib`.
- [ ] **Step 1: Write the failing tests:**
  - `test_read_setores_filters_uf_in_chunks`: CSV com setores `17…` e `52…`, `chunksize=2` → só os `17…`, em todos os blocos.
  - `test_read_setores_marks_suppressed_X_as_nan_and_sigilo`.
  - `test_read_setores_normalizes_code_with_punctuation`: `"1721000.05.000001P"`-like → 15 dígitos.
  - `test_indicator_pairs_keep_numerator_and_denominator`: setor com 80 alfabetizados de 100 com 15+ → `alfabetizacao_15_num=80`, `_den=100`.
  - `test_centroids_are_metric`: polígono quadrado conhecido em EPSG:4674 → centroide em EPSG:31982 dentro de 1 m do esperado.
  - `test_build_municipios_parses_sidra_json`: resposta SIDRA mínima (cabeçalho na 1ª linha) → `populacao` int, `area_km2` float.
- [ ] **Step 2: Run** `pytest tests/test_censo.py -v` → FAIL.
- [ ] **Step 3: Implement** com `pd.read_csv(..., sep=";", encoding="latin1", dtype=str, usecols=..., chunksize=...)`; geometria com `geopandas.read_file` e `.to_crs(31982).centroid`.
- [ ] **Step 4: Run** → PASS. Adicionar `geopandas` a `requirements.txt`/`pyproject.toml`.
- [ ] **Step 5: Commit** `feat: Censo 2022 por setor e indicadores municipais do IBGE`.

### Task 3: Coligações e federações

**Files:**
- Create: `tocantins/coligacoes.py`
- Modify: `tocantins/normalize.py` (`normalize_candidatos` passa a guardar `SG_FEDERACAO`, `DS_COMPOSICAO_FEDERACAO`, `NM_COLIGACAO`, `DS_COMPOSICAO_COLIGACAO`)
- Test: `tests/test_coligacoes.py`, `tests/test_normalize_aux.py`

**Interfaces:**
- Produces:
  - colunas novas em `base/candidatos.parquet`: `sg_federacao, composicao_federacao, nm_coligacao, composicao_coligacao` (texto, nulo quando `#NULO`).
  - `coligacoes.partidos_da_candidatura(row) -> frozenset[str]`: o próprio partido ∪ partidos da composição da coligação ∪ partidos das federações citadas nela. Siglas normalizadas: caixa alta, sem acento, sem espaços (`PC do B` → `PCDOB`).
  - `coligacoes.build(candidatos: pd.DataFrame) -> pd.DataFrame` → `base/coligacoes.parquet`: `ano, cargo, nr_candidato, sg_partido, partidos (lista ordenada)`, só candidaturas aptas.
  - `coligacoes.norm_sigla(s: str) -> str`.
- [ ] **Step 1: Write the failing tests:**
  - `test_own_party_is_in_set`.
  - `test_coligacao_composition_split_on_slash`: `"PL / PP / REPUBLICANOS"` → {PL, PP, REPUBLICANOS}.
  - `test_federation_in_composition_expands_to_members` (Review Focus 1): composição `"Federação BRASIL DA ESPERANÇA - FE BRASIL(PT/PC do B/PV) / PSB"` → {PT, PCDOB, PV, PSB}.
  - `test_norm_sigla_variants`: `"PC do B"`, `"PCdoB"` → `PCDOB`; `"UNIÃO"` → `UNIAO`.
  - `test_normalize_candidatos_keeps_coalition_columns` (em `test_normalize_aux.py`).
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.** Formato real das composições: conferir 20 linhas reais de `consulta_cand_2026` e registrar em `docs/fontes.md` antes de fixar o parser.
- [ ] **Step 4: Run** → PASS; `python -I scripts/02_normalizar.py` regrava `candidatos.parquet`.
- [ ] **Step 5: Commit** `feat: partidos de cada candidatura por coligação e federação`.

### Task 4: Ligação setor → local e áreas de votação

**Files:**
- Create: `tocantins/ligacao.py`, `scripts/02b_censo.py`
- Test: `tests/test_ligacao.py`

**Interfaces:**
- Consumes: `base/censo_setor.parquet` (Task 2), `base/locais.parquet`, crosswalk TSE↔IBGE (`tocantins/crosswalk.py`).
- Produces:
  - `ligacao.locais_ano(locais: pd.DataFrame, ano: int) -> pd.DataFrame`: um registro por local (`id = f"{zona}-{local}"`, `cd_municipio`, `nome`, `lat`, `lon`, `eleitores` = soma de `eleitores_secao` do turno 1, `especial: bool`, `x`, `y` em EPSG:31982). Locais sem coordenadas ficam com `x,y` nulos e não recebem setores.
  - `ligacao.link_geopandas(setores, locais) -> pd.DataFrame` e `ligacao.link_numpy(setores, locais) -> pd.DataFrame`: `cd_setor, local_id, dist_m`. Só locais do mesmo município (via crosswalk), não especiais, com coordenadas. Empate de distância → menor `local_id` (ordem de texto).
  - `ligacao.credibilidade(link, setores, locais) -> pd.DataFrame`: por local `moradores, eleitores, razao, credivel` (0,4 ≤ razao ≤ 1,6; local sem setor → `credivel=False`).
  - `ligacao.areas(link, setores, locais) -> pd.DataFrame`: `local_id → area_id` (ver algoritmo).
  - `base/ligacao_setor_local.parquet` (`ano, cd_setor, local_id, dist_m`), `base/area_votacao.parquet` (`ano, cd_municipio, area_id, local_id`), `base/local_credibilidade.parquet`.
- Algoritmo de áreas, por município e ano (determinístico):

```
cada local com setores começa como uma área (area_id = menor local_id da área)
enquanto houver mais de 1 área e alguma área com razao fora de [0.4, 1.6]:
    a = área fora da faixa com menor (eleitores + moradores); empate → menor area_id
    b = área mais próxima de a (distância entre centroides ponderados por eleitores); empate → menor area_id
    funde a e b
locais sem setores (especiais, sem coordenadas) não entram em área
```

- [ ] **Step 1: Write the failing tests:**
  - `test_both_impls_link_to_nearest_same_municipality`: setor perto de local de outro município liga ao do próprio.
  - `test_special_local_receives_no_sectors`: local "ESCOLA X - VOTO EM TRÂNSITO" e local com 0 eleitores.
  - `test_tie_breaks_by_smallest_local_id_in_both_impls` (Review Focus 5).
  - `test_local_without_coords_not_linked` (Review Focus 4).
  - `test_zero_population_sector_linked_but_not_weighted` (Review Focus 5).
  - `test_credibilidade_range_inclusive`: razões 0,4 e 1,6 críveis; 0,39 e 1,61 não.
  - `test_areas_merge_until_in_range`: três locais (razões 0,2; 1,0; 3,0) → áreas finais todas na faixa.
  - `test_single_local_municipality_is_one_area` (Review Focus 3).
  - `test_areas_deterministic`: duas execuções → mesmo resultado.
- [ ] **Step 2: Run** `pytest tests/test_ligacao.py -v` → FAIL.
- [ ] **Step 3: Implement.** `link_geopandas` com `gpd.sjoin_nearest(..., distance_col="dist_m")` por município; `link_numpy` com distância euclidiana em matriz por município. `scripts/02b_censo.py` roda Tasks 2–4 e grava os Parquet.
- [ ] **Step 4: Run** testes → PASS; depois `python -I scripts/02b_censo.py`. Reportar: setores ligados, % de locais críveis por ano, nº de áreas, tempo e pico de memória.
- [ ] **Step 5: Commit** `feat: ligação setor-local e áreas de votação`.

### Task 5: Entrega dos prefeitos

**Files:**
- Create: `tocantins/conjuntura.py`
- Test: `tests/test_conjuntura.py`

**Interfaces:**
- Consumes: `base/bu_secao.parquet`, `base/munzona.parquet` (eleitos), `base/coligacoes.parquet` (Task 3).
- Produces:
  - `conjuntura.prefeitos(bu, munzona) -> pd.DataFrame`: `cd_municipio, nr, nome, partido` (eleito de 2024: turno 2 onde houve, senão turno 1).
  - `conjuntura.entrega(bu, prefeitos, coligacoes, cargo: str, turno: int) -> pd.DataFrame`: por município `status ∈ {entregou, nao_entregou, sem_candidato}`, `cand_nr, cand_nome, cand_partido` (nulos se sem candidato), `venc_nr, venc_nome, venc_partido`, `margem_votos`, `margem_pp`.
- Regras: candidato da coligação = candidatura cujo `partidos` contém o partido do prefeito; se houver mais de uma, a do próprio partido do prefeito, senão a mais votada no município. Governador (turno 1 e 2): `entregou` se for o mais votado no município. Senador: `entregou` se ficar entre os 2 mais votados. `margem` = votos do candidato da coligação − votos do mais votado que não é ele (positiva quando entregou); `margem_pp` sobre os válidos do município.
- [ ] **Step 1: Write the failing tests:**
  - `test_prefeito_uses_t2_where_it_happened`.
  - `test_governador_entregou_and_margin`.
  - `test_governador_t2_coalition_out_is_sem_candidato` (Review Focus 2).
  - `test_senador_two_seats_second_place_counts_as_entregou`.
  - `test_federation_member_mayor_finds_candidate` (Review Focus 1, com `coligacoes` da Task 3).
  - `test_own_party_preferred_over_coalition_partner`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat: entrega dos prefeitos para Governador e Senador 2026`.

### Task 6: Camada 5, controle do Censo e Governador/Senador na camada 4

**Files:**
- Create: `tocantins/validate/layer5.py`
- Modify: `tocantins/validate/runner.py`, `tocantins/validate/control.py`, `scripts/conferir_oficial.py`, `site/js/views/selo.js` (texto da camada 5)
- Test: `tests/test_layer5.py`, `tests/test_control_and_runner.py`, `site/tests/comparativo.test.js` (selo)

**Interfaces:**
- Consumes: Parquet das Tasks 2–4, `base/coligacoes.parquet`, `base/ibge_municipio.parquet`.
- Produces: `layer5.run(inputs: dict[str, pd.DataFrame], exceptions) -> list[LayerResult]` com checks `setores_integridade`, `fechamento_municipio`, `ligacao_impl_disagreement`, `ligacao_consistencia`, `ligacao_credibilidade` (informativo, sempre `passed`), `coligacoes_prefeitos`. `control.palmas_censo(setores, palmas_dir) -> LayerResult` (layer `controle`, check `palmas_censo`). `runner.run_all` inclui ambos; `selo.json` passa a ter `camadas["5"]`.
- [ ] **Step 1: Write the failing tests** (um passa/um falha por check):
  - `test_integridade_counts_and_duplicates` (4.119 esperado vira parâmetro `n_setores`).
  - `test_fechamento_flags_difference_and_accepts_sigilo_exception`.
  - `test_impl_disagreement_cannot_be_excepted`.
  - `test_consistencia_every_sector_one_local_same_municipality_and_no_special`.
  - `test_coligacoes_prefeitos_missing_party_fails`.
  - `test_palmas_censo_matches_and_never_writes_palmas_dir`.
  - `test_seal_has_layer5` e, no node, `selo.render shows camada 5 label`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.** Em `conferir_oficial.py`, os alvos ganham Governador turno 1 e 2 e Senador turno 1: arquivo estadual + a mesma amostra de 10 municípios.
- [ ] **Step 4: Run** testes → PASS; depois `python -I scripts/conferir_oficial.py` (baixa os JSON novos para o cache) e `python -I scripts/03_validar.py`. Divergências reais de sigilo: registrar exceções com causa e mostrar a lista ao usuário antes de considerá-las aprovadas. Expected: `selo: ok`.
- [ ] **Step 5: Commit** `feat: camada 5 do selo (Censo e ligações) e Governador/Senador na camada 4`.

### Task 7: Exportação dos dados novos

**Files:**
- Modify: `tocantins/export.py`, `tocantins/normalize.py` (lat/lon)
- Test: `tests/test_export.py`, `tests/test_normalize_aux.py`

**Interfaces:**
- Consumes: Tasks 2–6.
- Produces (todos sob `site_dados/`):
  - `CARGOS[2026]` += `Governador` (turnos 1 e 2), `Senador`; `MAJORITARIOS` (site e export) incluem governador e senador. Arquivos municipais e estaduais como os demais.
  - `<mun>/ibge.json`: `{populacao, area_km2, densidade, pib_per_capita, ano_pib}`.
  - `<mun>/locais_ficha.json`: `{locais:[{id, nome, bairro, lat, lon, anos:{"2024":{aptos,comparecimento},"2026":{...}}, cargos:{"<ano>-<cargo>-<turno>":[{nr,nome,partido,votos,pct}]}, entorno:{credivel, area_id, moradores, indicadores:{<ind>: pct}} | null}]}`. Limites: vereador 15, deputados 5, demais todos. `entorno` usa a ligação de 2026 se o local existir em 2026, senão a de 2024.
  - `conjuntura/prefeitos_2026.json`: `{"governador-1":[...], "governador-2":[...], "senador-1":[...]}`, linhas da Task 5 com `cod` e `prefeito:{nome,partido}`.
  - `conjuntura/areas_<ano>_<cargo>.json` para os 6 cargos exportados (turno 1): `{indicadores:[...], areas:[{id, cod, eleitores, moradores, aptos, comparecimento, validos, ind:{<ind>: pct}, votos:{"<nr>":int}, partidos:{"<sg>":int}}]}`, só áreas críveis.
  - `conjuntura/municipios_indicadores.json`: `[{cod, ind:{...}, aptos:{"2024":..,"2026":..}, comparecimento:{...}}]`.
  - `index.json`: `municipios[].nota` (texto ou `null`); o município de nome `GOIATINS` (identificado pelo nome no `index.json`, não por código fixo) recebe a nota da suplementar de 25/10/2026.
  - normalize: lat e lon anulados juntos quando um for inválido; export escolhe uma linha completa por local (a de menor seção).
- [ ] **Step 1: Write the failing tests:**
  - `test_governador_and_senador_exported_with_t2_where_exists`.
  - `test_locais_ficha_limits_and_keys` (vereador 15, deputado 5).
  - `test_ficha_entorno_null_when_not_credible`.
  - `test_areas_file_only_credible_and_votes_sum_to_area_validos`.
  - `test_prefeitos_file_has_three_keys`.
  - `test_goiatins_note_in_index`.
  - `test_latlon_nulled_together` (normalize) e `test_local_coords_from_one_complete_row` (export).
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** → PASS; `python -I scripts/04_exportar.py`. Reportar tamanho total e maior arquivo; se algum passar de 2 MB, discutir antes de seguir.
- [ ] **Step 5: Commit** `feat: exportação de Governador/Senador, ficha do local, IBGE e conjuntura`.

### Task 8: Navegação, tela Município e painel do local

**Files:**
- Modify: `site/index.html` (menu), `site/js/app.js`, `site/js/map.js`, `site/js/analysis.js` (`CARGO_LABEL`, `MAJORITARIOS`), `site/js/views/municipio.js`, `site/js/views/estado.js`, `site/css/app.css`
- Create: `site/js/views/local_panel.js`, `site/tests/navegacao.test.js`, `site/tests/local_panel.test.js`
- Delete: rota e link de `comparativo` (arquivo `views/comparativo.js` e `compare2426` saem; testes correspondentes também)

**Interfaces:**
- Produces:
  - `app.parseHash` chamado dentro do `try` de `route()`.
  - `app.breadcrumb(route, index) -> [{label, href}]` (Tocantins › Município › Candidato/Local), preservando `e=`.
  - `map.createMap(el, {tiles})`: `scrollWheelZoom: false`; Ctrl + roda dá zoom; controle "Ver tudo" que chama `fitBounds` do enquadramento inicial.
  - `local_panel.renderPanel(ficha_local, cands_label) -> string` (HTML escapado) e `openPanel(app, local, onClose)`; Esc e botão fechar; `?local=<id>` no hash abre o painel.
  - `CARGO_LABEL` += `governador: 'Governador'`, `senador: 'Senador'`.
- [ ] **Step 1: Write the failing tests:**
  - `test malformed hash renders error instead of loading forever` (route com `#/municipio/%E0`).
  - `breadcrumb keeps election param`.
  - `renderPanel lists top 15 vereadores and escapes names`.
  - `renderPanel shows aviso when entorno is null` (Review Focus 3).
  - `local without coords opens panel from table row` (Review Focus 4: a linha da tabela tem `data-local`).
  - `menu has no comparativo link`.
- [ ] **Step 2: Run** `node --test site/tests/` → FAIL.
- [ ] **Step 3: Implement.** Tooltip curto: nome, comparecimento, mais votado de cada cargo da ficha. Ficha IBGE e prefeito × Governador 2026 (lidos de `ibge.json` e `prefeitos_2026.json`) no topo do Município. Cor dos locais em cargos proporcionais = partido mais votado (nominal + legenda).
- [ ] **Step 4: Run** → PASS. Visual no Edge: Palmas e Oliveira de Fátima a 1280 px; iframe 390 px sem rolagem horizontal; painel aberto e fechado por Esc.
- [ ] **Step 5: Commit** `feat: navegação, ficha do local e Governador/Senador na tela Município`.

### Task 9: Tela Conjuntura

**Files:**
- Create: `site/js/conjuntura.js`, `site/js/scatter.js`, `site/js/views/conjuntura.js`, `site/tests/conjuntura.test.js`
- Modify: `site/js/app.js` (rota `conjuntura`), `site/index.html` (menu), `site/css/app.css`

**Interfaces:**
- Consumes: arquivos `conjuntura/*` da Task 7.
- Produces:
  - `conjuntura.rankingPartidos(linhas) -> [{partido, prefeituras, entregou, taxa}]` (ordenado por prefeituras desc, depois sigla).
  - `conjuntura.quintis(areas, indicador, valorFn) -> {alto:{pct, n}, baixo:{pct, n}}`: ordena por indicador; 20% de cima e de baixo por contagem (arredonda para baixo, mínimo 1); `pct` = soma dos votos / soma dos válidos do grupo.
  - `conjuntura.correlacaoPonderada(xs, ys, ws) -> number | null` (Pearson ponderado; `null` com < 3 pontos ou variância zero).
  - `scatter.render(el, pontos:[{x,y,r,label,cor}], {xLabel, yLabel}) -> void` (SVG com eixos, tooltip por ponto e tabela equivalente gerada pela view).
  - Rotas: `#/conjuntura/prefeitos?c=governador-1`, `#/conjuntura/perfil?cargo=..&alvo=..&ind=..&nivel=area|municipio`, `#/conjuntura/comparecimento?ind=..`.
- [ ] **Step 1: Write the failing tests:**
  - `rankingPartidos counts and rates`.
  - `quintis uses pooled percentage and floors group size`.
  - `quintis with fewer than 5 areas uses 1 per group`.
  - `correlacaoPonderada known value` (ex.: pontos alinhados → 1) e `returns null for constant x`.
  - `perfil text never says porque/causa` (renderiza o resumo e procura as palavras).
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.** Mapa da aba Prefeitos em três categorias com paleta validada (`node <skill dataviz>/scripts/validate_palette.js`), legenda com contagens e tabela; abstenção em escala sequencial de um matiz. Aviso fixo "perfil do lugar, não do eleitor". Nível `municipio` usa `municipios_indicadores.json`.
- [ ] **Step 4: Run** → PASS. Visual no Edge (1280 px, 390 px, claro/escuro) das três abas; console sem erros.
- [ ] **Step 5: Commit** `feat: seção Conjuntura (prefeitos, perfil do voto, comparecimento)`.

### Task 10: Guia, verificação final e publicação

**Files:**
- Create: `docs/como_rodar.md`
- Modify: `validacao/RELATORIO_FINAL.md`

- [ ] **Step 1: Escrever `docs/como_rodar.md`:** ordem `01_baixar → 02_normalizar → 02b_censo → excecoes_camada3 → conferir_oficial → 03_validar → 04_exportar`, o que cada um grava, e como servir o site localmente.
- [ ] **Step 2: Verificação final:** `python -m pytest -q`, `node --test site/tests/`, `03_validar` (selo ok, camada 5 verde), `04_exportar`; as seis telas renderizam no Edge sem erro. Atualizar `RELATORIO_FINAL.md` com a saída e a seção da camada 5.
- [ ] **Step 3: Perguntar ao usuário** se pode publicar (push para `origin/main`). Só com o sim: push, esperar o build do Pages e conferir no site no ar Palmas, um município pequeno, a Conjuntura e o Selo.
- [ ] **Step 4: Commit** `docs: guia de execução e relatório da camada 5`.
