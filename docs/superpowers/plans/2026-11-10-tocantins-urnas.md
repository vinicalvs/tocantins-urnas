# Tocantins Urnas Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Baixar os boletins de urna do Tocantins (2024 e 2026, turnos 1 e 2), consolidar numa base validada em 4 camadas e publicar um site estático estadual com seletor de município.

**Architecture:** Pacote Python `tocantins/` com etapas separadas (baixar → normalizar para Parquet → validar → exportar JSON por município) e um site estático em JS puro que carrega os JSON sob demanda. DuckDB lê os CSVs grandes sem carregar tudo em RAM; as camadas 2 e 3 têm duas implementações independentes (pandas e SQL) que são comparadas entre si.

**Tech Stack:** Python 3.12, duckdb, pandas, pyarrow, requests, pytest; JS ES modules + Leaflet 1.9.4 (cdnjs); `node --test` para testes de JS.

**Spec:** `docs/superpowers/specs/2026-11-10-tocantins-urnas-design.md`

## Global Constraints

- Projeto em `C:\Users\VINI\Documents\Tocantins_Urnas`. A pasta `C:\Users\VINI\Documents\Palmas_Urnas_e_Censo` não é alterada (só leitura: `B24.pkl`, `B26.pkl`).
- Escopo: Prefeito e Vereador (2024); Deputado Federal e Deputado Estadual (2026); a base guarda também Governador, Senador e Presidente de 2026; 139 municípios; turnos 1 e 2 onde existirem. Sem Censo, sem outros anos.
- Base em granularidade de seção; site em granularidade de local de votação (com lat/lon).
- Download idempotente; SHA-512 do TSE conferido quando publicado; bruto nunca sobrescrito; `manifesto.json` com URL, data, tamanho e hash.
- `#NULO` e `-1` viram nulo; `#NE` e `-3` viram nulo (só em colunas de código/identificação, nunca em `QT_VOTOS`); latin1 decodificado uma única vez; acentos preservados; seções agregadas preservadas; nenhuma linha removida sem registro em `validacao/excecoes.json`. Código TSE do município é texto.
- CSVs grandes lidos por DuckDB ou em blocos; nunca `pd.read_csv` do arquivo inteiro.
- Conferência em 4 camadas; camadas 2 e 3 em duas implementações (pandas e DuckDB SQL) comparadas entre si; falha bloqueia a exportação salvo exceção registrada; divergência nunca corrigida em silêncio.
- Camada 4: Prefeito nos 139 municípios; Vereador, Deputado Federal e Deputado Estadual por totais estaduais e amostra de 10 municípios (5 maiores por eleitorado + 5 sorteados com semente fixa 2026 registrada).
- Palmas (`CD_MUNICIPIO 73440`) reproduz os totais de `B24.pkl` e `B26.pkl` (turno 1).
- Site estático sem servidor, JSON sob demanda, legível no celular, contraste checado (texto sobre cor de partido ≥ 4.5:1), auditoria de acessibilidade ao final.
- Publicar online só depois de o usuário confirmar a hospedagem (Task 14).

## Review Focus

Entradas que a spec não cita e que mais provavelmente quebram o uso real, mais provável primeiro:

1. Urna de seção não apurada, anulada ou não instalada (`CD_TIPO_URNA` ≠ 1): comparecimento ≠ votos. Esperado: não é tratada como erro de dado; é contada e listada à parte. Teste na Task 6.
2. Município sem 2º turno (ou cargo sem turno 2): nenhum arquivo `_t2` nem entrada no índice, e o site não mostra aba vazia nem dá 404. Testes nas Tasks 10 e 12.
3. Local de votação sem coordenadas (`-1`, vazio): aparece na tabela, não no mapa, e é contado no relatório. Testes nas Tasks 10 e 12.
4. Nomes com acento, aspas ou apóstrofo (candidato, local, bairro): sem mojibake na base, JSON em UTF-8 e escape de HTML no site. Testes nas Tasks 3 e 11.
5. Mesmo `NR_LOCAL_VOTACAO` em zonas diferentes, e seções agregadas: o local é identificado por zona + número, e as seções agregadas não somem nem são contadas duas vezes. Testes nas Tasks 4 e 10.

---

## File Structure

```
pyproject.toml, requirements.txt, .gitignore
tocantins/config.py          caminhos, Source, SOURCES
tocantins/download.py        hash, fetch idempotente, manifesto
tocantins/normalize.py       latin1→utf8, BU e fontes auxiliares → Parquet
tocantins/validate/result.py LayerResult, exceções, relatório, compare_impls
tocantins/validate/layer1.py … layer4.py, control.py, runner.py
tocantins/crosswalk.py       código TSE ↔ código IBGE
tocantins/export.py          JSON por município/estado, índice, selo, gate
scripts/01_baixar.py 02_normalizar.py 03_validar.py 04_exportar.py   (CLIs finos)
site/index.html, site/js/{data,colors,analysis,map,app}.js, site/js/views/*.js, site/tests/*.test.js
tests/conftest.py, tests/test_*.py
docs/fontes.md               esquema real de cada fonte (Task 2)
```

---

### Task 1: Scaffold, config e downloader

**Files:**
- Create: `pyproject.toml`, `requirements.txt`, `.gitignore` (ignora `dados_brutos/`, `base/`, `site_dados/`, `__pycache__`), `tocantins/__init__.py`, `tocantins/config.py`, `tocantins/download.py`, `tests/conftest.py`, `tests/test_download.py`

**Interfaces:**
- Produces:
  - `config.ROOT, RAW, BASE, VALID, SITE_DATA: Path`; `config.PALMAS_DIR: Path`
  - `config.Source` (frozen dataclass): `key: str, url: str, sha_url: str | None, filename: str`
  - `config.SOURCES: dict[str, Source]` com as chaves: `bu24_t1, bu24_t2, bu26_t1, bu26_t2, munzona24, munzona26, detalhe24, detalhe26, secao24, secao26, locais24, locais26, cand24, cand26, totaliz24, totaliz26`
  - `download.sha512_file(path: Path) -> str`; `download.parse_sha512_text(text: str) -> str` (primeiro token)
  - `download.HashMismatch(Exception)`
  - `download.fetch(source: Source, raw_dir: Path, manifest_path: Path) -> dict` (entrada do manifesto: `key,url,path,size,sha512,published_sha512,downloaded_at`)

- [ ] **Step 1:** `git init`, instalar dependências (`pip install duckdb pyarrow requests pytest pandas`) e gravar `requirements.txt`.
- [ ] **Step 2: Write the failing tests** em `tests/test_download.py`, usando um `http.server` local numa thread (fixture em `conftest.py`) que serve um zip pequeno e seu `.sha512`:
  - `test_parse_sha512_text_takes_first_token`: `parse_sha512_text("abc123  file.zip\n") == "abc123"`.
  - `test_fetch_downloads_and_verifies_hash`: após `fetch`, arquivo existe, `entry["sha512"] == entry["published_sha512"]`, manifesto tem 1 entrada com `key`.
  - `test_fetch_is_idempotent`: segunda chamada não faz nova requisição (contador do servidor continua em 1) e o arquivo não é reescrito (mtime igual).
  - `test_fetch_raises_on_hash_mismatch_and_keeps_no_partial_file`: servidor devolve `.sha512` errado → `HashMismatch`, e nenhum arquivo final nem `.part` fica em `raw_dir`.
  - `test_fetch_without_sha_url_records_computed_hash`: `sha_url=None` → `published_sha512 is None`, `sha512` calculado.
- [ ] **Step 3: Run** `pytest tests/test_download.py -v` → FAIL (módulo inexistente).
- [ ] **Step 4: Implement** `config.py` e `download.py`. Download em streaming para `<filename>.part`, hash calculado durante a escrita, `os.replace` só após conferir. URLs em `SOURCES` (valores verificados em 2026-11-10):
  - BU: `https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2024/buweb/bweb_1t_TO_091020241636.zip`, `…/bweb_2t_TO_281020241046.zip`, `…/eleicoes2026/buweb/bweb_1t_TO_051020261403.zip`, `…/bweb_2t_TO_261020260742.zip`; `sha_url` = mesma URL + `.sha512`.
  - Base `https://cdn.tse.jus.br/estatistica/sead/odsele/`: `votacao_candidato_munzona/votacao_candidato_munzona_{2024,2026}.zip`, `detalhe_votacao_munzona/detalhe_votacao_munzona_{2024,2026}.zip`, `votacao_secao/votacao_secao_{2024,2026}_TO.zip`, `eleitorado_locais_votacao/eleitorado_local_votacao_{2024,2026}.zip`, `consulta_cand/consulta_cand_{2024,2026}.zip`, `relatorio_resultado_totalizacao/Relatorio_Resultado_Totalizacao_{2024,2026}_TO.zip` (esses sem `sha_url`).
- [ ] **Step 5: Run** `pytest tests/test_download.py -v` → PASS.
- [ ] **Step 6: Commit** `feat: scaffold, config de fontes e downloader idempotente com SHA-512`.

---

### Task 2: Baixar as fontes e perfilar os arquivos reais

**Files:**
- Create: `scripts/01_baixar.py`, `docs/fontes.md`
- Test: `tests/test_sources_smoke.py`

**Interfaces:**
- Consumes: `download.fetch`, `config.SOURCES`
- Produces: `dados_brutos/*.zip`, `dados_brutos/manifesto.json`, `docs/fontes.md` (para cada fonte: arquivos dentro do zip, separador, encoding, **lista exata de colunas**, linhas em TO, intervalo de datas de geração). As Tasks 3 e 4 usam esses nomes de coluna.

- [ ] **Step 1: Write the failing test** `test_manifest_has_all_sources_with_matching_hash`: lê `dados_brutos/manifesto.json`; todas as 16 chaves de `SOURCES` existem; para as 4 de BU, `sha512 == published_sha512`.
- [ ] **Step 2: Run** `pytest tests/test_sources_smoke.py -v` → FAIL (manifesto inexistente).
- [ ] **Step 3: Implement** `01_baixar.py`: percorre `SOURCES`, chama `fetch`, descompacta cada zip em `dados_brutos/<key>/` (pasta própria por zip; arquivos não confiáveis, nunca executar nada de dentro). Para fontes nacionais (`munzona`, `detalhe`, `locais`, `cand`) o filtro `SG_UF == 'TO'` acontece na normalização, não aqui.
- [ ] **Step 4: Run** `python -I scripts/01_baixar.py` e depois `pytest tests/test_sources_smoke.py -v` → PASS. Se o CDN recusar download automatizado, usar o plugin Bright Data como contingência e registrar no manifesto.
- [ ] **Step 5: Perfilar** cada arquivo com a skill `data:explore-data` e escrever `docs/fontes.md`. Responder explicitamente: (a) o `Relatorio_Resultado_Totalizacao_*_TO.zip` é legível por máquina (CSV) ou só PDF? (decide a Task 8); (b) `detalhe_votacao_munzona` tem quais colunas de aptos/comparecimento/abstenções/brancos/nulos; (c) o cadastro de locais de 2026 (versão 2º turno) tem as mesmas seções que o BU 2026 T1?
- [ ] **Step 6: Commit** `feat: coleta das fontes do TSE e perfil de esquemas`.

---

### Task 3: Normalizar o BU para `bu_secao.parquet`

**Files:**
- Create: `tocantins/normalize.py`, `scripts/02_normalizar.py`
- Test: `tests/test_normalize_bu.py`

**Interfaces:**
- Consumes: CSVs de BU em `dados_brutos/bu*_t*/`
- Produces:
  - `normalize.to_utf8(src: Path, dst: Path) -> Path` (decodifica latin1 uma vez, em blocos de 1 MB)
  - `normalize.normalize_bu(csv_files: list[Path], out_parquet: Path) -> int` (linhas gravadas)
  - `base/bu_secao.parquet`, colunas: `ano:int, turno:int, cd_eleicao:int, cd_cargo:int, cargo:str, cd_municipio:str, nm_municipio:str, zona:int, secao:int, local:int, aptos:int, comparecimento:int, abstencoes:int, cd_tipo_urna:int, tipo_votavel:str, nr_votavel:int, nm_votavel:str, nr_partido:int|null, sg_partido:str|null, votos:int, secoes_agregadas:str|null`

- [ ] **Step 1: Write the failing tests**, com um CSV latin1 mínimo gerado em `conftest.py` com o cabeçalho real de 46 colunas do BU (copiar de `docs/fontes.md`):
  - `test_nulo_tokens_become_null`: `"#NULO#"` em `SG_PARTIDO` e `-1` em `NR_PARTIDO` → nulos; `QT_VOTOS` `0` permanece 0.
  - `test_no_mojibake`: candidato `"JOSÉ D'ÁVILA 'ZÉ'"` e município `"GUARAÍ"` saem iguais, e nenhum valor textual contém `Ã` ou `\ufffd`.
  - `test_cd_municipio_is_text_with_leading_digits_kept`: `cd_municipio` é `str` ("73377").
  - `test_secoes_agregadas_preserved`: `"10 / 114"` mantido em `secoes_agregadas`.
  - `test_row_count_matches_input`: linhas de saída = linhas de entrada (nada removido).
- [ ] **Step 2: Run** `pytest tests/test_normalize_bu.py -v` → FAIL.
- [ ] **Step 3: Implement** `to_utf8` e `normalize_bu`: ler o UTF-8 com DuckDB `read_csv(delim=';', quote='"', all_varchar=true)`, aplicar a limpeza em SQL e gravar com `COPY … TO … (FORMAT PARQUET)`. Unir turnos e anos num único Parquet.
- [ ] **Step 4: Run** testes → PASS. Depois `python -I scripts/02_normalizar.py --so-bu` e conferir `SELECT ano, turno, cargo, count(*) FROM 'base/bu_secao.parquet' GROUP BY ALL` (esperado: 2024 T1/T2 Prefeito e Vereador; 2026 T1/T2 com os 5 cargos).
- [ ] **Step 5: Commit** `feat: normalização do BU para Parquet`.

---

### Task 4: Normalizar as fontes auxiliares

**Files:**
- Modify: `tocantins/normalize.py`, `scripts/02_normalizar.py`
- Test: `tests/test_normalize_aux.py`

**Interfaces:**
- Produces (todos filtrados a `SG_UF == 'TO'`; nomes de coluna de origem em `docs/fontes.md`):
  - `normalize_locais(csv: Path, ano: int, out: Path) -> int` → `base/locais.parquet`: `ano, turno, cd_municipio:str, zona, secao, local, nm_local, endereco, bairro, lat:float|null, lon:float|null, eleitores_secao, tipo_secao`. `lat/lon`: vírgula decimal → ponto; `-1`, vazio ou fora de [-14,-5] / [-51,-45] viram nulo.
  - `normalize_munzona(csv, out)` → `base/munzona.parquet`: `ano, turno, cargo, cd_municipio, zona, nr_candidato, nm_candidato, sg_partido, votos_nominais, situacao_turno`
  - `normalize_detalhe(csv, out)` → `base/detalhe_munzona.parquet`: `ano, turno, cargo, cd_municipio, zona, aptos, comparecimento, abstencoes, brancos, nulos`
  - `normalize_votacao_secao(csv, out)` → `base/votacao_secao.parquet`: `ano, turno, cargo, cd_municipio, zona, secao, nr_votavel, votos`
  - `normalize_candidatos(csv, out)` → `base/candidatos.parquet`: `ano, cargo, cd_municipio, nr_candidato, sq_candidato, nm_urna, sg_partido, situacao, situacao_turno`
  - Cada função devolve o nº de linhas gravadas.

- [ ] **Step 1: Write the failing tests** com mini CSVs em `conftest.py`:
  - `test_locais_comma_decimal_and_missing_coords`: `"-10,184"` → `-10.184`; `"-1"` e `""` → nulos (Review Focus 3).
  - `test_locais_same_local_number_in_two_zones_kept_distinct`: duas linhas com `NR_LOCAL_VOTACAO=1012` em zonas 6 e 7 continuam 2 linhas distintas por `(zona, secao)` (Review Focus 5).
  - `test_filters_only_TO`: linha `SG_UF='SP'` descartada.
  - `test_munzona_keeps_situacao_turno`: `"ELEITO POR MÉDIA"` preservado sem mojibake.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** as cinco funções reutilizando `to_utf8` e o mesmo padrão DuckDB da Task 3; `02_normalizar.py` gera todos os Parquet.
- [ ] **Step 4: Run** testes → PASS; depois `python -I scripts/02_normalizar.py` e conferir contagens não vazias de cada Parquet.
- [ ] **Step 5: Commit** `feat: normalização de locais, munzona, detalhe, seção e candidatos`.

---

### Task 5: Framework de validação e Camada 1 (integridade)

**Files:**
- Create: `tocantins/validate/__init__.py`, `tocantins/validate/result.py`, `tocantins/validate/layer1.py`
- Test: `tests/test_validate_framework.py`, `tests/test_layer1.py`

**Interfaces:**
- Produces:
  - `result.LayerResult` (dataclass): `layer: str, check: str, passed: bool, n_checked: int, divergences: pd.DataFrame, unregistered: int`
  - `result.load_exceptions(path: Path) -> list[dict]` (entrada: `{layer, check, key: dict, cause: str, approved_on: str}`; arquivo ausente → `[]`)
  - `result.apply_exceptions(div: pd.DataFrame, layer: str, check: str, exceptions: list[dict]) -> pd.DataFrame` (devolve só as divergências **não** cobertas; uma exceção cobre a linha cujas colunas coincidem com todos os pares de `key`)
  - `result.compare_impls(a: pd.DataFrame, b: pd.DataFrame, key: list[str]) -> pd.DataFrame` (diferença simétrica por chave; vazio = implementações concordam)
  - `result.write_report(results: list[LayerResult], out_dir: Path) -> None` (grava `camada<N>.json` e `divergencias_<check>.csv`)
  - `layer1.run(manifest_path: Path, bu: pd.DataFrame) -> list[LayerResult]` (para dados reais, `bu` é lido do Parquet em blocos por cargo/turno) com checks `hash_manifest, row_counts, municipios_139, no_duplicates, t2_subset_of_t1`

- [ ] **Step 1: Write the failing tests:**
  - `test_apply_exceptions_covers_matching_key_only`: exceção com `key={"zona":6,"secao":13}` cobre só essa linha.
  - `test_compare_impls_flags_asymmetric_rows`.
  - `test_layer1_flags_duplicate_section_rows` e `test_layer1_flags_missing_municipio` (BU sintético com 138 municípios → `municipios_139` falha).
  - `test_layer1_t2_subset`: Prefeito T2 num município onde um candidato teve > 50% dos válidos no T1 → falha em `t2_subset_of_t1`.
  - `test_layer1_hash_manifest_fails_when_published_and_computed_differ`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.** Unicidade em `(ano, turno, cd_municipio, zona, secao, cd_cargo, tipo_votavel, nr_votavel)`.
- [ ] **Step 4: Run** testes → PASS.
- [ ] **Step 5: Commit** `feat: framework de validação e camada 1`.

---

### Task 6: Camada 2 (consistência interna), duas implementações

**Files:**
- Create: `tocantins/validate/layer2.py`
- Test: `tests/test_layer2.py`

**Interfaces:**
- Consumes: `bu_secao`, `locais`, `result.*`
- Produces:
  - `layer2.pandas_impl(bu: pd.DataFrame, locais: pd.DataFrame) -> dict[str, pd.DataFrame]`
  - `layer2.sql_impl(con: duckdb.DuckDBPyConnection) -> dict[str, pd.DataFrame]` (a conexão tem as views `bu` e `locais`)
  - `layer2.run(bu, locais, con, exceptions) -> list[LayerResult]`
  - Checks e chaves das divergências: `votos_eq_comparecimento` [ano, turno, cargo, cd_municipio, zona, secao] + `votos_total, comparecimento`; `comparecimento_mais_abst_eq_aptos` (mesma chave) + `aptos, soma`; `secoes_bu_eq_locais` [ano, turno, cd_municipio, zona, secao] + `lado` (`so_bu` | `so_locais`). Só `cd_tipo_urna == 1` entra nos dois primeiros; o resto vai para o check informativo `urnas_nao_apuradas` (contagem e lista, nunca reprova).

- [ ] **Step 1: Write the failing tests** com BU sintético:
  - `test_votos_ne_comparecimento_is_flagged_in_both_impls` (uma seção com 1 voto a menos).
  - `test_nao_apurada_urn_is_reported_not_failed`: seção `cd_tipo_urna=2` com votos ≠ comparecimento → aparece em `urnas_nao_apuradas`, e `votos_eq_comparecimento` passa (Review Focus 1).
  - `test_aggregated_sections_not_double_counted`: seção com `secoes_agregadas="10 / 114"` conta uma vez.
  - `test_impls_agree_on_clean_and_faulty_data`: `compare_impls` vazio nos dois casos; e **falha** se uma implementação for adulterada de propósito (injetar bug num monkeypatch).
  - `test_secoes_bu_eq_locais_flags_section_missing_in_cadastro`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** as duas versões **sem compartilhar código de lógica** (uma em operações pandas, outra em SQL puro); `run` roda as duas, usa `compare_impls` e, se divergirem, devolve `LayerResult(check="impl_disagreement", passed=False)`.
- [ ] **Step 4: Run** testes → PASS; depois rodar sobre os dados reais e salvar o relatório em `validacao/`.
- [ ] **Step 5: Commit** `feat: camada 2 com duas implementações`.

---

### Task 7: Camada 3 (cruzamento de fontes), duas implementações

**Files:**
- Create: `tocantins/validate/layer3.py`
- Test: `tests/test_layer3.py`

**Interfaces:**
- Produces: `layer3.pandas_impl(...)`, `layer3.sql_impl(con)`, `layer3.run(...)` no mesmo padrão da Task 6. Checks e chaves:
  - `bu_vs_munzona_nominal` [ano, turno, cargo, cd_municipio, zona, nr_votavel] + `votos_bu, votos_ref` (BU só `tipo_votavel='Nominal'`; ref = `munzona.votos_nominais`)
  - `bu_vs_votacao_secao` [ano, turno, cargo, cd_municipio, zona, secao, nr_votavel] + `votos_bu, votos_ref` (todos os tipos de votável, incluindo legenda, branco e nulo)
  - `bu_vs_detalhe` [ano, turno, cargo, cd_municipio, zona] + `aptos/comparecimento/abstencoes` de cada lado

- [ ] **Step 1: Write the failing tests** com fontes sintéticas:
  - `test_vote_difference_flagged_in_each_check` (um teste por check).
  - `test_candidate_only_in_one_source_flagged` (lado ausente aparece como divergência).
  - `test_exception_registered_with_cause_clears_divergence` (usa `apply_exceptions`).
  - `test_impls_agree_and_disagreement_fails` (como na Task 6).
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** duas versões independentes. Divergências reais **não** são resolvidas aqui: o relatório lista, e o humano registra a causa em `validacao/excecoes.json` depois de investigar.
- [ ] **Step 4: Run** testes → PASS; depois rodar sobre os dados reais. Para cada divergência real, investigar a causa (voto anulado e apurado em separado, sub judice, voto em trânsito, contingência) e só então registrar a exceção.
- [ ] **Step 5: Commit** `feat: camada 3 com duas implementações e exceções documentadas`.

---

### Task 8: Camada 4 (verificação externa)

**Files:**
- Create: `tocantins/validate/layer4.py`, `validacao/camada4_visual.json` (preenchido na execução)
- Test: `tests/test_layer4.py`

**Interfaces:**
- Produces:
  - `layer4.prefeito_winners(bu: pd.DataFrame, munzona: pd.DataFrame) -> pd.DataFrame`: `ano, turno, cd_municipio, nr_bu, nr_oficial, ok` (vencedor pelos votos do BU × candidato com `situacao_turno` iniciando em `ELEITO` no TSE)
  - `layer4.sample_municipios(locais: pd.DataFrame, ano: int, seed: int = 2026) -> list[str]` (5 maiores por soma de `eleitores_secao` + 5 sorteados dos demais com `random.Random(seed)`, retorna 10 códigos)
  - `layer4.expected_table(bu, cd_municipio, cargo, turno) -> pd.DataFrame` (candidato, votos, % válidos; o que será comparado com o site oficial)

- [ ] **Step 1: Write the failing tests:**
  - `test_prefeito_winner_mismatch_is_flagged`.
  - `test_prefeito_t2_uses_t2_votes`.
  - `test_sample_is_deterministic_and_has_10_distinct`: duas chamadas iguais; 10 códigos distintos; os 5 primeiros são os maiores.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.** Se na Task 2 o Relatório de Totalização for legível por máquina, adicionar `layer4.compare_totalizacao(...)` comparando totais estaduais por cargo; se for só PDF, a conferência dos totais estaduais vira parte do passo visual.
- [ ] **Step 4: Run** testes → PASS; rodar `prefeito_winners` nos 139 municípios (esperado: `ok` em 100%).
- [ ] **Step 5: Conferência visual.** Para a amostra de 10 municípios (por cargo) e os totais estaduais de Vereador, Deputado Federal e Deputado Estadual, abrir o site oficial de resultados do TSE com a skill `claude-in-chrome` (um agente por cargo, via `superpowers:dispatching-parallel-agents`), copiar os totais e gravar em `validacao/camada4_visual.json` (`cargo, cd_municipio, candidato, votos_site, votos_base, ok, data_consulta`). Qualquer `ok=false` é investigado, não ajustado.
- [ ] **Step 6: Commit** `feat: camada 4 e conferência visual da amostra`.

---

### Task 9: Controle Palmas, runner e gate

**Files:**
- Create: `tocantins/validate/control.py`, `tocantins/validate/runner.py`, `scripts/03_validar.py`
- Test: `tests/test_control_and_runner.py`

**Interfaces:**
- Produces:
  - `control.palmas_control(bu: pd.DataFrame, palmas_dir: Path) -> LayerResult` (lê `B24.pkl`/`B26.pkl` do projeto antigo, só leitura; compara por `(cargo, zona, secao, nr_votavel)` os votos de `73440`, turno 1)
  - `runner.run_all(base: Path, valid_dir: Path, raw_manifest: Path) -> list[LayerResult]`
  - `runner.write_seal(results, path: Path) -> dict` → `validacao/selo.json` com `status: "ok" | "falhou"`, `camadas`, `data`, `hashes` das fontes, e a lista de exceções usadas

- [ ] **Step 1: Write the failing tests:**
  - `test_control_flags_vote_difference_vs_pickle` (pickle sintético numa pasta temporária).
  - `test_seal_status_falhou_if_any_unregistered_divergence`.
  - `test_seal_lists_used_exceptions`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** testes → PASS; depois `python -I scripts/03_validar.py` sobre os dados reais. Esperado: `selo.json` com `status: "ok"`, e Palmas T1 sem diferenças (turno 2 de Palmas, se existir, é reportado como "fora do controle", não como falha).
- [ ] **Step 5: Commit** `feat: controle Palmas, runner e selo de validação`.

---

### Task 10: Crosswalk IBGE e exportação JSON

**Files:**
- Create: `tocantins/crosswalk.py`, `tocantins/export.py`, `scripts/04_exportar.py`, `tocantins/data/crosswalk_overrides.json`
- Test: `tests/test_crosswalk.py`, `tests/test_export.py`

**Interfaces:**
- Consumes: `base/*.parquet`, `validacao/selo.json`
- Produces:
  - `crosswalk.build(tse: pd.DataFrame, ibge: list[dict], overrides: dict[str, str]) -> dict[str, str]` (cd_municipio TSE → id IBGE de 7 dígitos; levanta `ValueError` se não houver 139 correspondências únicas). Normaliza acento, caixa e hífen. IBGE: `https://servicodados.ibge.gov.br/api/v1/localidades/estados/17/municipios`; malha: `https://servicodados.ibge.gov.br/api/v3/malhas/estados/17?intrarregiao=municipio&formato=application/vnd.geo+json&qualidade=minima` (copiada para `site_dados/malha_to.geojson`).
  - `export.GateError(Exception)`; `export.export_all(base: Path, out: Path, valid_dir: Path) -> None` (levanta `GateError` se `selo.json` ausente ou `status != "ok"`)
  - Esquema de `site_dados/<cd_municipio>/<ano>_<cargo>_t<turno>.json` (cargo em minúsculas sem acento, ex. `vereador`): `{municipio:{cod,nome}, ano, cargo, turno, totais:{aptos,comparecimento,abstencoes,brancos,nulos,validos}, candidatos:[{nr,nome,partido,votos,pct_validos,eleito}], partidos:[{sg,legenda,nominais,total}], locais:[{id,zona,nome,endereco,bairro,lat,lon,aptos,comparecimento,votos:{"<nr>":int,"branco":int,"nulo":int,"legenda:<sg>":int}}]}`; `id = f"{zona}-{nr_local}"`; `lat/lon` nulos quando ausentes.
  - `site_dados/index.json`: `{gerado_em, municipios:[{cod, ibge, nome, eleitorado, disponivel:{"<ano>":{"<cargo>":[turnos]}}}]}`
  - `site_dados/estado/<ano>_<cargo>_t<turno>.json`: totais por candidato e partido
  - `site_dados/selo_validacao.json`: cópia de `selo.json`

- [ ] **Step 1: Write the failing tests:**
  - `test_crosswalk_matches_accent_and_case_variants` e `test_crosswalk_raises_when_not_139`.
  - `test_export_refuses_without_ok_seal` (`GateError`).
  - `test_export_omits_missing_turn_files_and_index_lists_only_existing`: município só com T1 → sem arquivo `_t2` e `disponivel` sem `2` (Review Focus 2).
  - `test_local_without_coords_has_null_latlon_and_is_counted` (Review Focus 3).
  - `test_local_id_includes_zone`: mesmo `nr_local` em zonas 6 e 7 → 2 locais com ids `6-1012` e `7-1012`, votos não misturados (Review Focus 5).
  - `test_votes_in_local_sum_to_municipality_totals` (soma de `locais[*].votos` por candidato = `candidatos[*].votos`).
  - `test_json_is_utf8_and_keeps_accents`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.** Eleitos: Prefeito pela `situacao_turno` do TSE; Vereador e Deputados pela `situacao_turno` do TSE (não recalcular quociente). `eleito` é `null` se a fonte não informar.
- [ ] **Step 4: Run** testes → PASS; depois `python -I scripts/04_exportar.py`. Conferir: 139 pastas, `index.json` com 139 entradas, tamanho total de `site_dados/` e maior arquivo individual (reportar; se algum JSON passar de 1,5 MB, discutir antes de seguir).
- [ ] **Step 5: Commit** `feat: crosswalk IBGE e exportação JSON com gate de validação`.

---

### Task 11: Site, parte 1: base, dados, cores e tela Estado

**Files:**
- Create: `site/index.html`, `site/js/data.js`, `site/js/colors.js`, `site/js/analysis.js`, `site/js/map.js`, `site/js/app.js`, `site/js/views/estado.js`, `site/css/app.css`, `site/tests/data.test.js`, `site/tests/colors.test.js`, `site/tests/analysis.test.js`

**Interfaces:**
- Produces (ES modules, funções puras testáveis em Node):
  - `data.js`: `loadIndex(): Promise<Index>`, `loadMunicipio(cod, ano, cargo, turno)`, `loadEstado(ano, cargo, turno)` (cache em memória; `fetch` com caminho relativo `../site_dados/…` configurável por `window.DATA_BASE`); `fmtInt(n): string` (pt-BR), `fmtPct(x): string`
  - `colors.js`: `partyColor(sg: string): string` (hex; partido desconhecido → cor determinística da paleta por hash), `contrastRatio(hexA: string, hexB: string): number`, `textColorFor(bg: string): '#000' | '#fff'`
  - `analysis.js`: `escapeHtml(s: string): string`; `winnerByLocal(locais): Record<string,{key:string,votos:number,pct:number}>` (`key` = `nr` do candidato ou `legenda:<sg>`)

- [ ] **Step 1: Write the failing tests** (`node --test site/tests/`):
  - `partyColor returns same color for same party` e `every palette color keeps contrast >= 4.5 with textColorFor`.
  - `escapeHtml neutralizes <, >, &, " and '` com `escapeHtml(\`<img src=x onerror=alert(1)>"O'Neil"\`)` sem `<` nem aspas cruas (Review Focus 4).
  - `winnerByLocal picks highest votes and ignores branco/nulo`.
  - `fmtInt(1234567) === "1.234.567"`.
- [ ] **Step 2: Run** `node --test site/tests/` → FAIL.
- [ ] **Step 3: Implement** os módulos. `estado.js`: mapa Leaflet (1.9.4, cdnjs) com `malha_to.geojson`, município colorido pelo candidato/partido mais votado do cargo escolhido (seletor de ano+cargo+turno), e ranking estadual. Seletor de cargo mostra só combinações presentes em `index.json`. Navegação por hash (`#/estado`, `#/municipio/<cod>`).
- [ ] **Step 4: Run** testes → PASS. Subir `python -m http.server` na raiz do projeto e abrir `site/index.html` no Chrome (skill `claude-in-chrome`): o mapa mostra 139 municípios coloridos e o ranking carrega, sem erros no console (`read_console_messages`).
- [ ] **Step 5: Commit** `feat: site base, cores, dados e tela Estado`.

---

### Task 12: Site, parte 2: telas Município e Candidato

**Files:**
- Create: `site/js/views/municipio.js`, `site/js/views/candidato.js`
- Modify: `site/js/app.js`, `site/js/map.js`
- Test: `site/tests/map.test.js`, `site/tests/candidato.test.js`

**Interfaces:**
- Consumes: `data.js`, `colors.js`, `analysis.js`
- Produces:
  - `map.markersFromLocais(locais, winners): Marker[]` (omite locais com `lat`/`lon` nulos)
  - `candidato.rowsFor(json, nr): {localId, nome, bairro, votos, pct}[]` ordenável; `candidato.toCsv(rows): string`

- [ ] **Step 1: Write the failing tests:**
  - `markersFromLocais skips locais with null coordinates` (Review Focus 3).
  - `candidato.rowsFor returns only locais where candidato has votes, sorted by votos desc`.
  - `toCsv escapes quotes and semicolons and keeps accents`.
  - `municipio view hides turno 2 option when index.disponivel has only turno 1` (Review Focus 2), testada sobre a função pura `availableTurnos(index, cod, ano, cargo)`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.** Município: busca por nome (sem acento), resultado por cargo, eleitos, comparecimento e abstenção, mapa dos locais com a cor do vencedor, e tabela dos locais sem coordenadas. Candidato: tabela ordenável e botão de CSV. Todo texto de dados passa por `escapeHtml`.
- [ ] **Step 4: Run** testes → PASS. No Chrome: Palmas e um município pequeno de 2 zonas; conferir os totais da tela contra `site_dados/` e que a aba de 2º turno só aparece onde existe.
- [ ] **Step 5: Commit** `feat: telas Município e Candidato`.

---

### Task 13: Site, parte 3: Comparativo, selo e acessibilidade

**Files:**
- Create: `site/js/views/comparativo.js`, `site/js/views/selo.js`
- Modify: `site/js/analysis.js`, `site/js/app.js`
- Test: `site/tests/comparativo.test.js`

**Interfaces:**
- Produces: `analysis.compare2426(locais24, locais26): {id, nome, v24, v26, delta}[]` (só locais presentes nas duas eleições: mesma `zona`, mesmo `nr_local` e nome normalizado igual; `v24`/`v26` = participação do vencedor de cada eleição conforme tela); `selo.render(selo): string`

- [ ] **Step 1: Write the failing tests:**
  - `compare2426 excludes locais that exist in only one election`.
  - `compare2426 does not match same number in different zones`.
  - `compare2426 does not match same number with different normalized name`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.** O comparativo informa na tela quantos locais ficaram de fora e por quê. O selo aparece em cada tela (data, 4 camadas, link para `validacao/`).
- [ ] **Step 4: Run** testes → PASS. Auditoria com `design-skills:accessibility-audit` (WCAG 2.2 AA) e `impeccable` para polimento visual e `dataviz` para os gráficos; corrigir o que for material. Conferir no Chrome em largura de celular (390 px) sem rolagem horizontal.
- [ ] **Step 5: Commit** `feat: comparativo 2024×2026, selo de validação e ajustes de acessibilidade`.

---

### Task 14: Verificação final e publicação

**Files:**
- Create: `validacao/RELATORIO_FINAL.md`

- [ ] **Step 1: Verificação final** (`superpowers:verification-before-completion`): rodar `pytest -v`, `node --test site/tests/`, `python -I scripts/03_validar.py` e `python -I scripts/04_exportar.py`; colar a saída no relatório. Critérios do spec: 139 municípios × 4 cargos × turnos existentes; 4 camadas verdes ou exceções justificadas; Palmas T1 reproduz o projeto antigo; site com as 5 telas.
- [ ] **Step 2: Perguntar ao usuário a hospedagem** (ex.: GitHub Pages) e confirmar antes de publicar. Os dados são públicos do TSE, mas publicar é uma ação externa. Só prosseguir com a confirmação.
- [ ] **Step 3: Publicar** conforme a hospedagem escolhida, abrir a URL no Chrome e conferir Palmas, um município pequeno e o selo.
- [ ] **Step 4: Commit** `docs: relatório final de validação`.
