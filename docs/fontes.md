# Fontes do TSE: perfil dos arquivos reais

Gerado na Task 2 a partir dos arquivos baixados em 2026-11-10 por `python -I scripts/01_baixar.py`
(`dados_brutos/manifesto.json` registra URL, tamanho, SHA-512 e data de cada zip). Os numeros abaixo
foram medidos nos arquivos reais com DuckDB (`read_csv`, tudo `varchar`, `;`, latin-1), sempre
filtrando `SG_UF = 'TO'`. Nada de dentro dos zips foi executado.

Conferencia cruzada: os zips e CSVs de BU de 1o turno (2024 e 2026) tem exatamente o mesmo tamanho em bytes
das copias antigas de `Palmas_Urnas_e_Censo/dados_brutos` (zips de 17.637.974 e 29.667.347 bytes).

## 1. Convencoes comuns a todos os CSV

- Separador `;`, aspas duplas em todos os campos, quebra de linha CRLF, com cabecalho, **sem BOM**.
- Encoding **latin-1** (nao e UTF-8 valido) em todos os 14 CSV de TO / BU perfilados.
- Datas `DD/MM/AAAA` (`DT_GERACAO`, `DT_ELEICAO`) e horas `HH:MM:SS`; nos BU as colunas `DT_PLEITO`,
  `DT_BU_RECEBIDO`, `DT_ABERTURA`, `DT_ENCERRAMENTO`, `DT_EMISSAO_BU`, `DT_CARGA_URNA_EFETIVADA` vem em
  ISO `AAAA-MM-DD HH:MM:SS`.
- Sentinelas de ausente: `#NULO#` e `#NULO` (BU: `DS_SECOES_AGREGADAS`; munzona/cand: `NM_SOCIAL_CANDIDATO`,
  `DS_SIT_TOT_TURNO`), `#NE` (nao informado; `cand26.DS_SITUACAO_CANDIDATURA` em todas as 372 linhas), `-1`
  (`NR_JUNTA_APURADORA` e `NR_TURMA_APURADORA` nos BU, `SQ_CANDIDATO` de branco/nulo em `votacao_secao`,
  latitude de local sem geocodificacao).
- Os codigos de tipo de eleicao diferem entre familias: BU usa `CD_TIPO_ELEICAO=0` (Eleicao Ordinaria);
  munzona/detalhe/secao/cand usam `2` (ordinaria) e `1` (extraordinaria/suplementar). `DS_ELEICAO` e MAIUSCULO em
  munzona, `ELEICAO ORDINARIA` (maiusculo) em `NM_TIPO_ELEICAO` de cand. Normalizar por `CD_ELEICAO` (inteiro), nao por texto.
- Os esquemas (lista de colunas) sao **identicos entre 2024 e 2026** em cada familia, e entre os arquivos `_TO`,
  `_BR` e `_BRASIL` (verificado cabecalho a cabecalho).
- Cada zip de odsele (exceto votacao_secao e locais 2024) traz um CSV por UF (`*_TO.csv`) mais `*_BRASIL.csv` (tudo) e
  `leiame.pdf`; os de 2026 trazem tambem `*_BR.csv` e (locais) `*_ZZ.csv`. Ler o `_TO.csv` direto evita carregar o
  nacional (`votacao_candidato_munzona_2026_BRASIL.csv` tem 3,2 GB). **Excecao importante: ver 2.2 (Presidente 2026
  so existe nos arquivos `_BR`/`_BRASIL`).**
- Cada arquivo tem uma unica data/hora de geracao, com a excecao indicada em `secao24`. Os arquivos de odsele 2024
  (munzona, detalhe, cand) foram **regenerados em 09-10/11/2026**: a data de geracao nao reflete a data da eleicao.

## 2. Achados que afetam as Tasks seguintes (leia primeiro)

1. **Suplementar de Goiatins (`CD_ELEICAO=6286`)**: aparece nos arquivos de odsele 2024 (`ANO_ELEICAO=2024`, mas
   `DT_ELEICAO=25/10/2026`, `CD_TIPO_ELEICAO=1`, turno 1, cargo Prefeito): 132 linhas em `votacao_secao_2024_TO`
   (34 secoes, zona 32, geradas 28/10/2026 10:48:20), 2 em munzona24, 1 em detalhe24, 6 em cand24 (3 prefeito + 3 vice).
   **Nao esta nos BU 2024.** Filtrar `CD_ELEICAO` 619/620 na base de 2024.
2. **Presidente 2026 nao esta nos arquivos `_TO.csv`** de munzona, detalhe e cand (so cargos estaduais, `CD_ELEICAO`
   6259/6260). Os votos de Presidente por municipio/zona de TO estao em `votacao_candidato_munzona_2026_BR.csv`
   (`SG_UF='TO'`: 1.680 linhas no T1 e 280 no T2, `CD_ELEICAO` 6257/6258) e em
   `detalhe_votacao_munzona_2026_BR.csv` (`SG_UF='TO'`: 140 + 140). Os candidatos a presidente estao em
   `consulta_cand_2026_BR.csv` com `SG_UF='BR'` (14 + 14 no T1, 2 + 2 no T2), nunca com `SG_UF='TO'`. `votacao_secao_2026_TO`
   nao tem Presidente (so Governador, Senador, Dep. Federal, Dep. Estadual): presidente por secao so vem do BU.
3. **BU 2026 mistura duas eleicoes** (`CD_ELEICAO`): 6257 = Geral Federal (Presidente) e 6259 = Gerais Estaduais
   (Governador, Senador, Deputados) no T1; 6258 / 6260 no T2. `DS_ELEICAO` difere entre linhas do mesmo arquivo.
4. **O cadastro de locais 2026 e a versao do 2o turno** (gerado 25/10/2026 15:27:44) e traz **uma linha por secao
   por turno** (as linhas T1 e T2 sao copias: mesmos locais e mesmo `QT_ELEITOR_SECAO`; mudam so
   `QT_ELEITOR_ELEICAO_FEDERAL/ESTADUAL`). O de 2024 (gerado 29/10/2024 02:00:30) tambem e por secao por turno, mas o
   turno 2 so tem as secoes de Palmas (632 linhas).
5. **Latitude/longitude**: 2024 usa ponto decimal (`-10.1528383`), 2026 usa **virgula** (`-8,839815`); ausente = `-1`
   (12 secoes em 2024, 8 em 2026). Telefones em formatos mistos.
6. **Linhas com 0 voto nao existem** no BU (nenhuma linha com `QT_VOTOS='0'`; por isso ha menos linhas de Branco/Nulo
   que secoes). `QT_APTOS`/`QT_COMPARECIMENTO`/`QT_ABSTENCOES` se repetem em cada linha da secao.
7. **BU x totalizacao**: no BU o Nominal inclui votos nulos tecnicos (Governador 2026 T1: BU nominal 849.656 =
   detalhe `QT_VOTOS_NOMINAIS_VALIDOS` 848.629 + `QT_VOTOS_NULOS_TECNICOS` 1.027). Em Prefeito 2024 T1 o BU tem 941.208
   nominais contra 941.204 em munzona (`QT_VOTOS_NOMINAIS`) e detalhe (`QT_VOTOS_CONCORRENTES`): diferenca de 4. Branco e Nulo
   do BU batem com detalhe (`QT_VOTOS_BRANCOS`, `QT_VOTOS_NULOS`). A validacao deve tolerar e explicar essas diferencas.
8. `DS_SITUACAO_CANDIDATURA` em `consulta_cand_2026_TO` e `#NE` nas 372 linhas (ainda nao publicada no arquivo gerado
   em 09/11/2026); `DS_SIT_TOT_TURNO` e `#NULO` em 33 linhas.
9. Em `votacao_secao_*` a coluna `NR_LOCAL_VOTACAO` repete numeros entre municipios (so 115 valores distintos em
   2026): a chave do local deve ser (municipio, zona, local), nunca o numero sozinho.

## 3. Perguntas da Task 2

**(a) `Relatorio_Resultado_Totalizacao_*_TO.zip` e legivel por maquina?** **Nao: so PDF.** O zip de 2024 tem 142
PDFs (139 `619_TO_<MUNICIPIO>_2024_T1.pdf`, 1 `620_TO_..._T2.pdf`, 1 `6286_TO_..._T1.pdf` da suplementar de Goiatins e
`_leiame.pdf`); o de 2026 tem 5 PDFs (`6257_..._T1_PRESIDENTE`, `6258_..._T2_PRESIDENTE`, `6259_..._T1`, `6260_..._T2`,
`_leiame.pdf`). Sao relatorios JasperReports (OpenPDF) com camada de texto (ex.: 100 paginas no estadual 2026 T1, 75 no de
Palmas 2024), nao ha CSV, XLSX nem JSON. Para a Task 8, o relatorio so serve de conferencia humana (ou exigiria um parser de
PDF); nao e fonte de dados.

**(b) `detalhe_votacao_munzona`: colunas de totais.** Uma linha por (municipio, zona, cargo, turno):

| Conceito | Coluna |
|---|---|
| aptos | `QT_APTOS` |
| comparecimento | `QT_COMPARECIMENTO` |
| abstencoes | `QT_ABSTENCOES` |
| votos brancos | `QT_VOTOS_BRANCOS` |
| votos nulos | `QT_VOTOS_NULOS` (nulos de urna) e `QT_TOTAL_VOTOS_NULOS` (nulos + `QT_VOTOS_NULOS_TECNICOS`) |
| nulos tecnicos | `QT_VOTOS_NULOS_TECNICOS` |
| total / validos | `QT_VOTOS` (= comparecimento x votos por eleitor: Senador 2026 conta 2), `QT_VOTOS_CONCORRENTES`, `QT_TOTAL_VOTOS_VALIDOS`, `QT_VOTOS_NOMINAIS_VALIDOS`, `QT_TOTAL_VOTOS_LEG_VALIDOS`, `QT_VOTOS_LEG_VALIDOS`, `QT_VOTOS_NOM_CONVR_LEG_VALIDOS` |
| anulados | `QT_TOTAL_VOTOS_ANULADOS`, `QT_VOTOS_NOMINAIS_ANULADOS`, `QT_VOTOS_LEGENDA_ANULADOS`, `QT_TOTAL_VOTOS_ANUL_SUBJUD`, `QT_VOTOS_NOMINAIS_ANUL_SUBJUD`, `QT_VOTOS_LEGENDA_ANUL_SUBJUD`, `QT_VOTOS_ANULADOS_APU_SEP` |
| secoes | `QT_SECOES_PRINCIPAIS`, `QT_SECOES_AGREGADAS`, `QT_SECOES_NAO_INSTALADAS`, `QT_TOTAL_SECOES`, `QT_ELEITORES_SECOES_NAO_INSTALADAS` |
| outros | `ST_VOTO_EM_TRANSITO` (sempre `N` em TO), `HH_ULTIMA_TOTALIZACAO`, `DT_ULTIMA_TOTALIZACAO` |

Totais de TO medidos: 2026 T1 `QT_APTOS` 1.180.433, comparecimento 963.810, abstencoes 216.623 (iguais nos 4 cargos);
2026 T2 Governador aptos 1.180.466, comparecimento 953.385, abstencoes 227.081; 2024 T1 Vereador aptos 1.171.342,
comparecimento 978.712, abstencoes 192.630; 2024 T1 Prefeito soma 1.180.153 porque inclui a suplementar de Goiatins
(8.811 aptos; sem ela e igual a Vereador); 2024 T2 Prefeito (Palmas) aptos 209.524, comparecimento 155.605.

**(c) Cadastro de locais 2026 x secoes do BU 2026 T1.** Contando `(NR_ZONA, NR_SECAO)` distintos de TO:
BU 2026 T1 = **4.384**, locais 2026 = **4.490**. O BU esta contido no cadastro (4.384 em comum, 0 so no BU) e o cadastro
tem **106 secoes a mais, todas `Agregada`** (`CD_TIPO_SECAO_AGREGADA=2`, ATIVO), que nao tem BU proprio (votam junto da
secao principal). O mesmo vale para o T2 (BU T2 = 4.384; locais T2 = 4.490; 106 a mais). Com `CD_MUNICIPIO` na chave o
resultado e o mesmo. Em 2024: BU T1 4.171 x locais T1 4.333 (162 a mais) e BU T2 629 x locais T2 632 (3 a mais), tambem so
agregadas. Em 2026 todas as 4.384 secoes principais estao no BU, inclusive as 277 de locais `BLOQUEADO`.

## 4. Fontes (16)

Chave, zip, arquivos, linhas em TO e datas de geracao. "Linhas TO" = linhas com `SG_UF='TO'`.

### 4.1 BU (Boletim de Urna), 4 fontes: `bu24_t1`, `bu24_t2`, `bu26_t1`, `bu26_t2`

Dentro de cada zip: `_leiame-boletimurnaweb.pdf` e `bweb_<t>t_TO_<ddmmaaaahhmm>.csv`, ja so de TO. Tem hash
`.sha512` publicado e ele confere com o calculado nas 4. Layout real do `.sha512`: `<hash hex minusculo>  <arquivo>.zip\n`
(primeiro token), entao `parse_sha512_text` nao precisou mudar de layout. Colunas (45), identicas nos 4:

```
DT_GERACAO;HH_GERACAO;ANO_ELEICAO;CD_TIPO_ELEICAO;NM_TIPO_ELEICAO;CD_PLEITO;DT_PLEITO;NR_TURNO;
CD_ELEICAO;DS_ELEICAO;SG_UF;CD_MUNICIPIO;NM_MUNICIPIO;NR_ZONA;NR_SECAO;NR_LOCAL_VOTACAO;
CD_CARGO_PERGUNTA;DS_CARGO_PERGUNTA;NR_PARTIDO;SG_PARTIDO;NM_PARTIDO;DT_BU_RECEBIDO;QT_APTOS;
QT_COMPARECIMENTO;QT_ABSTENCOES;CD_TIPO_URNA;DS_TIPO_URNA;CD_TIPO_VOTAVEL;DS_TIPO_VOTAVEL;
NR_VOTAVEL;NM_VOTAVEL;QT_VOTOS;NR_URNA_EFETIVADA;CD_CARGA_1_URNA_EFETIVADA;
CD_CARGA_2_URNA_EFETIVADA;CD_FLASHCARD_URNA_EFETIVADA;DT_CARGA_URNA_EFETIVADA;
DS_CARGO_PERGUNTA_SECAO;DS_SECOES_AGREGADAS;DT_ABERTURA;DT_ENCERRAMENTO;
QT_ELEI_BIOM_SEM_HABILITACAO;DT_EMISSAO_BU;NR_JUNTA_APURADORA;NR_TURMA_APURADORA
```

| chave | zip (bytes) | linhas | secoes distintas (mun, zona, secao) | municipios | geracao |
|---|---|---|---|---|---|
| `bu24_t1` | 17.637.974 | 270.223 | 4.171 | 139 | 09/10/2024 16:36:29 |
| `bu24_t2` | 335.492 | 2.495 | 629 | 1 (Palmas) | 28/10/2024 10:46:41 |
| `bu26_t1` | 29.667.347 | 426.458 | 4.384 | 139 | 05/10/2026 14:03:43 |
| `bu26_t2` | 2.383.586 | 33.900 | 4.384 | 139 | 26/10/2026 07:42:38 |

`CD_ELEICAO`: 2024 T1 = 619, T2 = 620 (`DT_PLEITO` 2024-10-06 / 2024-10-27); 2026 T1 = 6257 e 6259 (2026-10-04),
T2 = 6258 e 6260 (2026-10-25). Chave da secao: `CD_MUNICIPIO`, `NR_ZONA`, `NR_SECAO`.

**`DS_CARGO_PERGUNTA` por ano/turno** (`CD_CARGO_PERGUNTA`, linhas):

| ano/turno | cargos |
|---|---|
| 2024 T1 | 11 Prefeito (18.231), 13 Vereador (251.992) |
| 2024 T2 | 11 Prefeito (2.495) |
| 2026 T1 | 1 Presidente (30.084; `CD_ELEICAO` 6257); 3 Governador (28.547), 5 Senador (54.482), 6 Deputado Federal (121.834), 7 Deputado Estadual (191.511) (estes 6259) |
| 2026 T2 | 1 Presidente (16.709; 6258); 3 Governador (17.191; 6260) |

**`CD_TIPO_VOTAVEL` / `DS_TIPO_VOTAVEL`** (valores distintos, linhas / votos; `NR_VOTAVEL` 95 = Branco, 96 = Nulo, com
`NM_VOTAVEL` `Branco`/`Nulo`; Legenda tem `NR_VOTAVEL` = numero do partido):

| arquivo | 1 Nominal | 2 Branco | 3 Nulo | 4 Legenda |
|---|---|---|---|---|
| `bu24_t1` | 241.829 / 1.867.033 | 6.357 / 18.897 | 8.122 / 45.114 | 13.915 / 26.380 (so Vereador) |
| `bu24_t2` | 1.258 / 148.357 | 608 / 2.746 | 629 / 4.502 | nao ha |
| `bu26_t1` | 339.472 / 5.172.099 | 20.367 / 182.016 | 21.626 / 344.906 | 44.993 / 85.225 (so Dep. Federal e Estadual) |
| `bu26_t2` | 17.529 / 1.782.037 | 7.619 / 28.382 | 8.752 / 97.729 | nao ha |

Cargo x tipo: Legenda so aparece em Vereador (2024) e Deputado Federal/Estadual (2026); Presidente, Governador,
Senador e Prefeito so tem Nominal, Branco e Nulo.

**`CD_TIPO_URNA` / `DS_TIPO_URNA`**: um unico valor em todos os 4 arquivos, `1` = `Apurada`: `bu24_t1` 270.223 linhas
(4.171 secoes), `bu24_t2` 2.495 (629), `bu26_t1` 426.458 (4.384), `bu26_t2` 33.900 (4.384). Nao ha urnas de outro tipo
nestes arquivos. Outros campos: `DS_SECOES_AGREGADAS` e `#NULO#` em quase todas as linhas (preenchido em 9.096 de
426.458 no 2026 T1); `NR_JUNTA_APURADORA` e `NR_TURMA_APURADORA` valem `-1`.

Votos agregados de TO (para a validacao), nominal / branco / nulo: 2024 T1 Prefeito 941.208 / 10.440 / 27.064; Vereador
925.825 (+26.380 legenda) / 8.457 / 18.050. 2026 T1: Presidente 930.475 / 8.344 / 26.377; Governador 849.656 / 27.085 /
87.069; Senador 1.653.665 / 93.579 / 180.376; Dep. Federal 878.708 (+28.164 legenda) / 28.980 / 27.958; Dep. Estadual
859.595 (+57.061 legenda) / 24.028 / 23.126.

### 4.2 `munzona24`, `munzona26`: votacao_candidato_munzona

Zip nacional com um CSV por UF. Arquivo de TO: `votacao_candidato_munzona_<ano>_TO.csv`. Sem `.sha512` publicado.
Colunas (50):

```
DT_GERACAO;HH_GERACAO;ANO_ELEICAO;CD_TIPO_ELEICAO;NM_TIPO_ELEICAO;NR_TURNO;CD_ELEICAO;DS_ELEICAO;
DT_ELEICAO;TP_ABRANGENCIA;SG_UF;SG_UE;NM_UE;CD_MUNICIPIO;NM_MUNICIPIO;NR_ZONA;CD_CARGO;DS_CARGO;
SQ_CANDIDATO;NR_CANDIDATO;NM_CANDIDATO;NM_URNA_CANDIDATO;NM_SOCIAL_CANDIDATO;
CD_SITUACAO_CANDIDATURA;DS_SITUACAO_CANDIDATURA;CD_DETALHE_SITUACAO_CAND;DS_DETALHE_SITUACAO_CAND;
CD_SITUACAO_JULGAMENTO;DS_SITUACAO_JULGAMENTO;CD_SITUACAO_CASSACAO;DS_SITUACAO_CASSACAO;
CD_SITUACAO_DCONST_DIPLOMA;DS_SITUACAO_DCONST_DIPLOMA;TP_AGREMIACAO;NR_PARTIDO;SG_PARTIDO;
NM_PARTIDO;NR_FEDERACAO;NM_FEDERACAO;SG_FEDERACAO;DS_COMPOSICAO_FEDERACAO;SQ_COLIGACAO;NM_COLIGACAO;
DS_COMPOSICAO_COLIGACAO;ST_VOTO_EM_TRANSITO;QT_VOTOS_NOMINAIS;NM_TIPO_DESTINACAO_VOTOS;
QT_VOTOS_NOMINAIS_VALIDOS;CD_SIT_TOT_TURNO;DS_SIT_TOT_TURNO
```

| chave | zip (bytes) | linhas TO | geracao | observacao |
|---|---|---|---|---|
| `munzona24` | 48.071.608 | 6.807 (T1 6.805 = 6.803 de 619 + 2 de 6286; T2 2) | 10/11/2026 02:17:06 | Prefeito 318, Vereador 6.485, suplementar 2 |
| `munzona26` | 395.670.866 | 41.860 (T1 41.580; T2 280) | 09/11/2026 19:32:20 | Governador 840, Senador 1.820, Dep. Fed. 11.760, Dep. Est. 27.160; Governador T2 280 |

Presidente 2026: ver 2.2 (`_BR.csv`, 1.960 linhas para TO). Valores distintos: `NM_TIPO_DESTINACAO_VOTOS` = `Válido`,
`Anulado`, `Anulado sub judice`, `Válido (legenda)`; `DS_SIT_TOT_TURNO` = ELEITO, ELEITO POR QP, ELEITO POR MÉDIA, SUPLENTE,
NÃO ELEITO, 2º TURNO; `TP_AGREMIACAO` = PARTIDO ISOLADO, FEDERAÇÃO, COLIGAÇÃO; `ST_VOTO_EM_TRANSITO` = `N`.
Votos por candidato: `QT_VOTOS_NOMINAIS` (todos) e `QT_VOTOS_NOMINAIS_VALIDOS`. 297 candidatos distintos em 2026.
Soma 2024 T1 (619): Prefeito `QT_VOTOS_NOMINAIS` 941.204 / validos 939.884; Vereador 925.392 / 915.800.

### 4.3 `detalhe24`, `detalhe26`: detalhe_votacao_munzona

Um CSV por UF. Colunas (47):

```
DT_GERACAO;HH_GERACAO;ANO_ELEICAO;CD_TIPO_ELEICAO;NM_TIPO_ELEICAO;NR_TURNO;CD_ELEICAO;DS_ELEICAO;
DT_ELEICAO;TP_ABRANGENCIA;SG_UF;SG_UE;NM_UE;CD_MUNICIPIO;NM_MUNICIPIO;NR_ZONA;CD_CARGO;DS_CARGO;
QT_APTOS;QT_SECOES_PRINCIPAIS;QT_SECOES_AGREGADAS;QT_SECOES_NAO_INSTALADAS;QT_TOTAL_SECOES;
QT_COMPARECIMENTO;QT_ELEITORES_SECOES_NAO_INSTALADAS;QT_ABSTENCOES;ST_VOTO_EM_TRANSITO;QT_VOTOS;
QT_VOTOS_CONCORRENTES;QT_TOTAL_VOTOS_VALIDOS;QT_VOTOS_NOMINAIS_VALIDOS;QT_TOTAL_VOTOS_LEG_VALIDOS;
QT_VOTOS_LEG_VALIDOS;QT_VOTOS_NOM_CONVR_LEG_VALIDOS;QT_TOTAL_VOTOS_ANULADOS;
QT_VOTOS_NOMINAIS_ANULADOS;QT_VOTOS_LEGENDA_ANULADOS;QT_TOTAL_VOTOS_ANUL_SUBJUD;
QT_VOTOS_NOMINAIS_ANUL_SUBJUD;QT_VOTOS_LEGENDA_ANUL_SUBJUD;QT_VOTOS_BRANCOS;QT_TOTAL_VOTOS_NULOS;
QT_VOTOS_NULOS;QT_VOTOS_NULOS_TECNICOS;QT_VOTOS_ANULADOS_APU_SEP;HH_ULTIMA_TOTALIZACAO;
DT_ULTIMA_TOTALIZACAO
```

| chave | zip (bytes) | linhas TO | geracao |
|---|---|---|---|
| `detalhe24` | 1.509.658 | 282 (T1 281 = 140 Prefeito + 140 Vereador + 1 suplementar; T2 1) | 09/11/2026 02:17:09 |
| `detalhe26` | 4.199.314 | 700 (T1 560 = 4 cargos x 140; T2 140 Governador) | 09/11/2026 19:32:47 |

140 pares municipio-zona. Presidente 2026: 280 linhas em `detalhe_votacao_munzona_2026_BR.csv` (`SG_UF='TO'`, 140 no T1 +
140 no T2). `ST_VOTO_EM_TRANSITO` = `N`.

### 4.4 `secao24`, `secao26`: votacao_secao (ja so de TO)

Zip com `votacao_secao_<ano>_TO.csv` e `leiame.pdf`. Colunas (26):

```
DT_GERACAO;HH_GERACAO;ANO_ELEICAO;CD_TIPO_ELEICAO;NM_TIPO_ELEICAO;NR_TURNO;CD_ELEICAO;DS_ELEICAO;
DT_ELEICAO;TP_ABRANGENCIA;SG_UF;SG_UE;NM_UE;CD_MUNICIPIO;NM_MUNICIPIO;NR_ZONA;NR_SECAO;CD_CARGO;
DS_CARGO;NR_VOTAVEL;NM_VOTAVEL;QT_VOTOS;NR_LOCAL_VOTACAO;SQ_CANDIDATO;NM_LOCAL_VOTACAO;
DS_LOCAL_VOTACAO_ENDERECO
```

| chave | zip (bytes) | linhas | geracao | observacao |
|---|---|---|---|---|
| `secao24` | 10.175.412 | 272.850 (T1 270.355 = 270.223 de 619 + 132 de 6286; T2 2.495) | 28/10/2024 11:46:22 (suplementar: 28/10/2026 10:48:20) | Prefeito 18.231, Vereador 251.992 (619 T1); Prefeito 2.495 (T2) |
| `secao26` | 13.707.414 | 413.565 (T1 396.374; T2 17.191) | 26/10/2026 12:07:25 | Governador 28.547, Senador 54.482, Dep. Fed. 121.834, Dep. Est. 191.511 (T1); Governador 17.191 (T2). Sem Presidente |

Uma linha por (secao, votavel). Brancos e nulos como `NR_VOTAVEL` 95/96 e `NM_VOTAVEL` `VOTO BRANCO` / `VOTO NULO` (no BU
e `Branco`/`Nulo`), com `SQ_CANDIDATO=-1`. Soma de `QT_VOTOS` por cargo no T1 2024 (619) = 978.712 (= comparecimento) e em
2026 = 963.810 (Senador 1.927.620, dois votos).

### 4.5 `locais24`, `locais26`: eleitorado_locais_votacao

`locais24`: zip com **um unico CSV nacional** `eleitorado_local_votacao_2024.csv` (245 MB; 599.204 linhas, 4.965 de TO).
`locais26`: um CSV por UF + `BRASIL` + `ZZ` (exterior); usar `eleitorado_local_votacao_2026_TO.csv`. Os campos de endereco
em `locais24` tem quebra de linha entre aspas: no DuckDB e preciso `parallel=false`. Colunas (41):

```
DT_GERACAO;HH_GERACAO;AA_ELEICAO;DT_ELEICAO;DS_ELEICAO;NR_TURNO;SG_UF;CD_MUNICIPIO;NM_MUNICIPIO;
NR_ZONA;NR_SECAO;CD_TIPO_SECAO_AGREGADA;DS_TIPO_SECAO_AGREGADA;NR_SECAO_PRINCIPAL;NR_LOCAL_VOTACAO;
NM_LOCAL_VOTACAO;CD_TIPO_LOCAL;DS_TIPO_LOCAL;DS_ENDERECO;NM_BAIRRO;NR_CEP;NR_TELEFONE_LOCAL;
NR_LATITUDE;NR_LONGITUDE;CD_SITU_LOCAL_VOTACAO;DS_SITU_LOCAL_VOTACAO;CD_SITU_ZONA;DS_SITU_ZONA;
CD_SITU_SECAO;DS_SITU_SECAO;CD_SITU_LOCALIDADE;DS_SITU_LOCALIDADE;CD_SITU_SECAO_ACESSIBILIDADE;
DS_SITU_SECAO_ACESSIBILIDADE;QT_ELEITOR_SECAO;QT_ELEITOR_ELEICAO_FEDERAL;
QT_ELEITOR_ELEICAO_ESTADUAL;QT_ELEITOR_ELEICAO_MUNICIPAL;NR_LOCAL_VOTACAO_ORIGINAL;
NM_LOCAL_VOTACAO_ORIGINAL;DS_ENDERECO_LOCVT_ORIGINAL
```

| chave | zip (bytes) | linhas TO | secoes distintas (zona, secao) | geracao |
|---|---|---|---|---|
| `locais24` | 45.276.803 | 4.965 (T1 4.333; T2 632, so Palmas) | 4.333 (T1), 632 (T2) | 29/10/2024 02:00:30 |
| `locais26` | 167.493.511 | 8.980 (T1 4.490; T2 4.490) | 4.490 em cada turno | 25/10/2026 15:27:44 |

`NR_TURNO`: `1` (`DS_ELEICAO='1º Turno'`, 06/10/2024 ou 04/10/2026) e `2` (27/10/2024 ou 25/10/2026). **Uma linha por secao
por turno**, sem duplicatas dentro do turno; em `locais26` o T2 repete o T1. Locais distintos (municipio, zona,
`NR_LOCAL_VOTACAO`): 897 (2024 T1), 83 (2024 T2), 932 (2026). `DS_TIPO_SECAO_AGREGADA`: Principal / Agregada (2026 T1:
4.384 principais + 106 agregadas; 2024 T1: 4.171 + 162). `DS_SITU_LOCAL_VOTACAO`: ATIVO / BLOQUEADO (2026: 277 principais
+ 8 agregadas em locais bloqueados). `DS_TIPO_LOCAL` 2026 (por turno): Convencional 4.464, Temporario 16, Voto em transito 8,
Preso provisorio 2. `QT_ELEITOR_SECAO` soma 1.171.342 (2024 T1; igual a `QT_APTOS` de Vereador no detalhe), 209.524
(2024 T2; igual ao detalhe) e 1.182.307 (2026 nos dois turnos, contra `QT_APTOS` 1.180.433 no detalhe T1 e 1.180.466 no
T2; `QT_ELEITOR_ELEICAO_FEDERAL` 1.182.023 / 1.182.041 e `QT_ELEITOR_ELEICAO_ESTADUAL` 1.180.433 / 1.180.466 por turno).
Em 2024 as colunas federal/estadual valem 0 e a municipal e preenchida; em 2026 o inverso.

### 4.6 `cand24`, `cand26`: consulta_cand

Um CSV por UF + `BRASIL` (+ `BR` em 2026). Colunas (50):

```
DT_GERACAO;HH_GERACAO;ANO_ELEICAO;CD_TIPO_ELEICAO;NM_TIPO_ELEICAO;NR_TURNO;CD_ELEICAO;DS_ELEICAO;
DT_ELEICAO;TP_ABRANGENCIA;SG_UF;SG_UE;NM_UE;CD_CARGO;DS_CARGO;SQ_CANDIDATO;NR_CANDIDATO;
NM_CANDIDATO;NM_URNA_CANDIDATO;NM_SOCIAL_CANDIDATO;NR_CPF_CANDIDATO;DS_EMAIL;
CD_SITUACAO_CANDIDATURA;DS_SITUACAO_CANDIDATURA;TP_AGREMIACAO;NR_PARTIDO;SG_PARTIDO;NM_PARTIDO;
NR_FEDERACAO;NM_FEDERACAO;SG_FEDERACAO;DS_COMPOSICAO_FEDERACAO;SQ_COLIGACAO;NM_COLIGACAO;
DS_COMPOSICAO_COLIGACAO;SG_UF_NASCIMENTO;DT_NASCIMENTO;NR_TITULO_ELEITORAL_CANDIDATO;CD_GENERO;
DS_GENERO;CD_GRAU_INSTRUCAO;DS_GRAU_INSTRUCAO;CD_ESTADO_CIVIL;DS_ESTADO_CIVIL;CD_COR_RACA;
DS_COR_RACA;CD_OCUPACAO;DS_OCUPACAO;CD_SIT_TOT_TURNO;DS_SIT_TOT_TURNO
```

| chave | zip (bytes) | linhas TO | geracao | observacao |
|---|---|---|---|---|
| `cand24` | 64.782.445 | 7.202 (T1 7.198 = 7.192 de 619 [330 prefeito, 335 vice, 6.527 vereador] + 6 de 6286; T2 4) | 10/11/2026 02:16:46 | |
| `cand26` | 3.288.348 | 372 (T1 368; T2 4) | 09/11/2026 19:31:31 | Dep. Est. 209, Dep. Fed. 98, Senador 13, Governador 8, Vice 8, 1o suplente 17, 2o suplente 15; T2: Governador 2 + Vice 2 |

`SQ_CANDIDATO` se repete nas linhas de turno 2. `DS_SITUACAO_CANDIDATURA` = `#NE` em todas as linhas de 2026.
`NR_CPF_CANDIDATO` e `NR_TITULO_ELEITORAL_CANDIDATO` estao preenchidos (dado pessoal: nao publicar no site); `DS_EMAIL` vem como `NÃO DIVULGÁVEL`.

### 4.7 `totaliz24`, `totaliz26`: Relatorio_Resultado_Totalizacao

So PDF (ver 3.a). `totaliz24`: 85.671.399 bytes, 142 arquivos; `totaliz26`: 601.726 bytes, 5 arquivos. Sem esquema tabular.

## 5. Nota sobre o downloader

`scripts/01_baixar.py` baixa cada fonte via `fetch` e descompacta cada zip em `dados_brutos/<chave>/` (extracao em
pasta temporaria `.<chave>.extraindo`, com checagem de caminhos, renomeada ao fim). Reexecutar nao baixa de novo. Os
`.sha512` existem so para os 4 BU; as outras 12 fontes (odsele) nao tem hash publicado (404) e o manifesto guarda apenas
o hash calculado.
