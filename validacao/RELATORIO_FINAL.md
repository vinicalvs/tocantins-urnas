# Relatório final de validação — Tocantins nas urnas

Data: 10/11/2026 · branch `feat/tocantins-urnas` · commit da verificação: 9f0ec8c

## Situação

| Item | Situação |
|---|---|
| Base (BU 2024 e 2026, 139 municípios) | pronta |
| Validação em 4 camadas + controle Palmas | **selo ok** (todas as camadas verdes; divergências com causa registrada) |
| Exportação `site_dados/` | 139 municípios, 564 arquivos, 6,6 MB |
| Site (5 telas) | renderiza sem erro |
| Aprovação das 206 exceções pelo usuário | **pendente** |
| Publicação | **pendente** (aguarda escolha de hospedagem e confirmação do usuário) |

## Critérios da spec

1. **139 municípios × 4 cargos × turnos existentes.** `site_dados/index.json`: Prefeito 2024 = 139, Vereador 2024 = 139,
   Deputado Estadual 2026 = 139, Deputado Federal 2026 = 139. 2º turno só onde existiu (Prefeito 2024 em Palmas).
2. **4 camadas verdes ou exceções justificadas.** Todas verdes; 206 exceções usadas, 0 não usadas (abaixo).
3. **Palmas turno 1 reproduz o projeto anterior.** `palmas_turno1`: 171.501 linhas conferidas, 0 diferenças.
4. **Site com as 5 telas.** Estado, Município (Palmas e o menor, Oliveira de Fátima), Candidato
   (por local e no estado), Comparativo 2024 × 2026 e Selo: carregam sem mensagem de erro (Edge headless).

## Saída da validação (`python -I scripts/03_validar.py`)

```
camada 1         hash_manifest                        ok      verificados=18 divergencias=0 sem_registro=0
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
camada 4         visual_amostra                       ok      verificados=11840 divergencias=0 sem_registro=0
camada controle  palmas_turno1                        ok      verificados=171501 divergencias=0 sem_registro=0
selo: ok  excecoes usadas=206 nao usadas=0  fora do controle=['2024 turno 2', '2026 turno 2']
```

A camada 4 recalcula, a cada validação, a comparação da base atual com o resultado oficial publicado em
resultados.tse.jus.br (JSON em cache em `dados_brutos/oficial/`): 11.840 linhas, 0 diferenças.

## Saída da exportação (`python -I scripts/04_exportar.py`)

```
municipios=139 arquivos=564 total=6.6 MB maior=estado/2024_vereador_t1.json (0.74 MB) locais_sem_coordenadas=2
```

## Testes

- `python -m pytest -v`: 140 passed.
- `node --test site/tests/*.test.js`: 30 passed.

## Exceções (`validacao/excecoes.json`) — aguardam aprovação do usuário

| Camada · teste | Casos | Causa |
|---|---|---|
| 1 · exclusoes_registradas | 3 | Linhas de outras UFs no arquivo nacional do TSE (fora do escopo: só Tocantins). |
| 1 · exclusoes_registradas | 4 | Eleição suplementar de Goiatins (CD_ELEICAO 6286, 25/10/2026): não está nos BU e não é eleição ordinária. |
| 3 · bu_vs_munzona_nominal | 197 | Nulos técnicos: voto nominal no BU para candidatura indeferida/cancelada, ausente do munzona; a soma por zona bate exatamente com `QT_VOTOS_NULOS_TECNICOS` do detalhe. |
| 3 · cobertura_fontes | 2 | `votacao_secao` do TSE não traz Presidente; Presidente por seção vem só do BU. |

As entradas foram geradas por script (`scripts/excecoes_camada3.py`) e registradas pelo executor. A publicação só
acontece depois que o usuário revisar e aceitar essas causas.

## Limitações conhecidas

- Votos de legenda contam como válidos; em Vereador 2024 de Pugmil (73571) o total difere do TSE em 2 votos
  (legenda de partido ausente da lista oficial). Os outros 300 arquivos oficiais conferem exatamente.
- 2 locais de votação sem coordenadas: aparecem só nas tabelas.
- Fora do caso de controle (sem base anterior): 2024 turno 2 e 2026 turno 2.
- Pendências menores da revisão final (não corrigidas): ver as linhas `minor (deferred)` no ledger e a mensagem
  final do executor.
