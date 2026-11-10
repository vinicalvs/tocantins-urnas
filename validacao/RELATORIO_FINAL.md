# Relatório final de validação — Tocantins nas urnas

Data: 10/11/2026 · branch `feat/conjuntura` (Conjuntura e Censo 2022)

## Situação

| Item | Situação |
|---|---|
| Base (BU 2024 e 2026, 139 municípios) | pronta |
| Validação em 5 camadas + controles de Palmas (votos e população) | **selo ok** (todas as camadas verdes; divergências com causa registrada) |
| Exportação `site_dados/` | 139 municípios, 1.270 arquivos, 14,1 MB |
| Site (Estado, Município com ficha do local, Candidato, Conjuntura em 3 abas, Selo) | renderiza sem erro |
| Aprovação das 206 exceções pelo usuário | aprovadas pelo usuário em 10/11/2026 |
| Publicação | https://vinicalvs.github.io/tocantins-urnas/ (GitHub Pages, repositório vinicalvs/tocantins-urnas) |

## Critérios da spec

1. **139 municípios × 4 cargos × turnos existentes.** `site_dados/index.json`: Prefeito 2024 = 139, Vereador 2024 = 139,
   Deputado Estadual 2026 = 139, Deputado Federal 2026 = 139. 2º turno só onde existiu (Prefeito 2024 em Palmas).
2. **4 camadas verdes ou exceções justificadas.** Todas verdes; 206 exceções usadas, 0 não usadas (abaixo).
3. **Palmas turno 1 reproduz o projeto anterior.** `palmas_turno1`: 171.501 linhas conferidas, 0 diferenças.
4. **Site com as 5 telas.** Estado, Município (Palmas e o menor, Oliveira de Fátima), Candidato
   (por local e no estado), Comparativo 2024 × 2026 e Selo: carregam sem mensagem de erro (Edge headless).

## Saída da validação (`python -I scripts/03_validar.py`)

```
camada 1         hash_manifest                        ok      verificados=26 divergencias=0 sem_registro=0
camada 1         row_counts                           ok      verificados=4 divergencias=0 sem_registro=0
camada 1         municipios_139                       ok      verificados=10 divergencias=0 sem_registro=0
camada 1         no_duplicates                        ok      verificados=733076 divergencias=0 sem_registro=0
camada 1         t2_subset_of_t1                      ok      verificados=139 divergencias=0 sem_registro=0
camada 1         exclusoes_registradas                ok      verificados=7 divergencias=7 sem_registro=0
camada 2         votos_eq_comparecimento              ok      verificados=39659 divergencias=0 sem_registro=0
camada 2         comparecimento_mais_abst_eq_aptos    ok      verificados=39659 divergencias=0 sem_registro=0
camada 2         secoes_bu_eq_locais                  ok      verificados=13945 divergencias=0 sem_registro=0
camada 2         urnas_nao_apuradas                   ok      verificados=39659 divergencias=0 sem_registro=0
camada 2         impl_disagreement                    ok      verificados=4 divergencias=0 sem_registro=0
camada 3         bu_vs_munzona_nominal                ok      verificados=50625 divergencias=197 sem_registro=0
camada 3         bu_vs_votacao_secao                  ok      verificados=686283 divergencias=0 sem_registro=0
camada 3         bu_vs_detalhe                        ok      verificados=1261 divergencias=0 sem_registro=0
camada 3         cobertura_fontes                     ok      verificados=30 divergencias=2 sem_registro=0
camada 3         impl_disagreement                    ok      verificados=4 divergencias=0 sem_registro=0
camada 4         prefeito_winners                     ok      verificados=140 divergencias=0 sem_registro=0
camada 4         visual_amostra                       ok      verificados=12170 divergencias=0 sem_registro=0
camada controle  palmas_turno1                        ok      verificados=171501 divergencias=0 sem_registro=0
camada 5         setores_integridade                  ok      verificados=4117 divergencias=0 sem_registro=0
camada 5         fechamento_municipio                 ok      verificados=139 divergencias=0 sem_registro=0
camada 5         ligacao_impl_disagreement            ok      verificados=8234 divergencias=0 sem_registro=0
camada 5         ligacao_consistencia                 ok      verificados=8234 divergencias=0 sem_registro=0
camada 5         ligacao_credibilidade                ok      verificados=1829 divergencias=0 sem_registro=0
camada 5         coligacoes_prefeitos                 ok      verificados=139 divergencias=0 sem_registro=0
camada controle  palmas_censo                         ok      verificados=1 divergencias=0 sem_registro=0
selo: ok  excecoes usadas=206 nao usadas=0  fora do controle=['2024 turno 2', '2026 turno 2']
```

A camada 4 recalcula, a cada validação, a comparação da base atual com o resultado oficial publicado em
resultados.tse.jus.br (JSON em cache em `dados_brutos/oficial/`): 12.170 linhas, 0 diferenças, agora com
Governador (turnos 1 e 2) e Senador 2026 (arquivo estadual + amostra de 10 municípios).

## Camada 5 — Censo 2022 e ligações

- 4.117 setores (a malha tem 4.119 polígonos: 2 setores partidos em dois) nos 139 municípios, sem código duplicado.
- Fechamento: moradores dos setores = população do Censo 2022 (SIDRA) nos 139 municípios; total 1.511.460; 0 diferenças.
- Ligação setor → local mais próximo do mesmo município, em numpy e geopandas: 8.234 ligações (2024 e 2026), 0 discordâncias.
- Consistência: cada setor em um único local do mesmo município; nenhum local especial (trânsito, prisional, sem eleitores) com setor; soma das áreas = população.
- Ligações críveis (0,4 ≤ eleitores/moradores ≤ 1,6): 63% dos locais em 2024 e 61% em 2026 (por município em `credibilidade_municipios.csv`). Locais não críveis ficam fora do perfil.
- Coligações e prefeitos: os 139 prefeitos eleitos têm partido e estão no `consulta_cand`; toda candidatura votada a Governador/Senador 2026 tem composição.
- Controle `palmas_censo`: 302.692 moradores = total do projeto anterior.


## Saída da exportação (`python -I scripts/04_exportar.py`)

```
municipios=139 arquivos=1270 total=14.1 MB maior=estado/2024_vereador_t1.json (0.74 MB) locais_sem_coordenadas=2
```

## Testes

- `python -m pytest -q`: 200 passed.
- `node --test site/tests/`: 41 passed.

## Exceções (`validacao/excecoes.json`) — aprovadas pelo usuário

| Camada · teste | Casos | Causa |
|---|---|---|
| 1 · exclusoes_registradas | 3 | Linhas de outras UFs no arquivo nacional do TSE (fora do escopo: só Tocantins). |
| 1 · exclusoes_registradas | 4 | Eleição suplementar de Goiatins (CD_ELEICAO 6286, 25/10/2026): não está nos BU e não é eleição ordinária. |
| 3 · bu_vs_munzona_nominal | 197 | Nulos técnicos: voto nominal no BU para candidatura indeferida/cancelada, ausente do munzona; a soma por zona bate exatamente com `QT_VOTOS_NULOS_TECNICOS` do detalhe. |
| 3 · cobertura_fontes | 2 | `votacao_secao` do TSE não traz Presidente; Presidente por seção vem só do BU. |

As entradas foram geradas por script (`scripts/excecoes_camada3.py`) e registradas pelo executor; o usuário
aceitou as causas em 10/11/2026, antes da publicação.

## Publicação conferida

Site no ar em https://vinicalvs.github.io/tocantins-urnas/: página raiz, `site/`, `site_dados/index.json`,
arquivo de Palmas, selo, `site_dados/validacao/excecoes.json` e malha respondem 200; Palmas, Oliveira de Fátima
(menor eleitorado) e o Selo renderizam sem erro.

## Limitações conhecidas

- Votos de legenda contam como válidos; em Vereador 2024 de Pugmil (73571) o total difere do TSE em 2 votos
  (legenda de partido ausente da lista oficial). Os outros 300 arquivos oficiais conferem exatamente.
- 2 locais de votação sem coordenadas: aparecem só nas tabelas.
- Perfil do voto é do lugar, não do eleitor: a ligação usa o local mais próximo, e o eleitor nem sempre vota perto de casa.
- "Candidato da coligação" é o registrado no TSE; não equivale a apoio declarado do prefeito.
- Fora do caso de controle (sem base anterior): 2024 turno 2 e 2026 turno 2.
- Pendências menores da revisão final (não corrigidas): ver as linhas `minor (deferred)` no ledger e a mensagem
  final do executor.
