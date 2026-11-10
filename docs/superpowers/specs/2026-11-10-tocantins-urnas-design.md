# Tocantins Urnas: base validada e site estadual (design)

Data: 2026-11-10
Status: aguardando revisão do usuário

## 1. Objetivo e contexto

Replicar para os 139 municípios do Tocantins o trabalho feito para Palmas em `C:\Users\VINI\Documents\Palmas_Urnas_e_Censo` (cruzamento de boletins de urna com mapa por local de votação, em um HTML). Desta vez, de forma mais completa: coleta de todos os boletins de urna (BU) do estado, base consolidada com conferência dupla e um site estadual publicado.

O Palmas filtrava o BU estadual por `CD_MUNICIPIO == '73440'`. Os CSVs estaduais de 2024 e 2026 (turno 1) já existem lá. Esta spec parte de um download novo e verificado, em pasta separada. A pasta do Palmas não é alterada.

### Pedido do usuário (o que foi dito)
- Baixar todos os BU do estado de 2026 e também os dos municípios.
- Cargos: Prefeito, Deputado Federal, Deputado Estadual e Vereador.
- Usar skills e plugins disponíveis para captar os dados e fazer "double check".

### Decisões tomadas na conversa
- Produto final: base validada + site estático único com seletor de município, publicado online.
- Censo fica para a etapa 2, fora desta spec.
- Abordagem: pipeline em camadas (Parquet + JSON por município + site estático).

### Premissas (a confirmar na revisão desta spec)
- "2026" cobre os cargos de eleição geral (Deputado Federal e Estadual). Prefeito e Vereador só são votados em 2024; o pedido de "municípios" é lido como a eleição municipal de 2024.
- "Double check" significa validar cada número por mais de uma fonte independente e por duas implementações de código.
- Os dois turnos entram (2024 e 2026). O TSE publica `bweb_2t_TO_…` para ambos os anos.

## 2. Escopo

**Dentro:**
- Eleições: municipal 2024 (Prefeito, Vereador) e geral 2026 (Deputado Federal, Deputado Estadual).
- A base também guarda Governador, Senador e Presidente de 2026, porque vêm no mesmo arquivo. O site destaca apenas os quatro cargos pedidos.
- 139 municípios, turnos 1 e 2 onde existirem.
- Granularidade da base: seção eleitoral. Granularidade do site: local de votação (com lat/lon).

**Fora (YAGNI):** Censo, outros anos eleitorais, login, banco em servidor, edição de dados, previsão ou modelagem.

## 3. Estrutura do projeto

```
Tocantins_Urnas/
  dados_brutos/   zips originais + .sha512 + manifesto.json (url, data, tamanho, hash)
  base/           Parquet: bu_secao, locais, candidatos, munzona, detalhe_munzona
  validacao/      relatório por camada (pass/fail + linhas divergentes) + excecoes.json
  site_dados/     index.json, estado/, <cod_municipio>/<eleicao>_<cargo>_t<turno>.json, selo_validacao.json
  site/           HTML/JS estático
  scripts/        01_baixar, 02_normalizar, 03_validar, 04_exportar
  docs/superpowers/specs/
```

## 4. Fontes (TSE, dados abertos)

| Fonte | Uso |
|---|---|
| BU 2024 T1 (`bweb_1t_TO_091020241636`) e T2 (`bweb_2t_TO_281020241046`) | dado principal, por seção |
| BU 2026 T1 (`bweb_1t_TO_051020261403`) e T2 (`bweb_2t_TO_261020260742`) | dado principal, por seção |
| `votacao_candidato_munzona` 2024 e 2026 | 2ª fonte para conferência |
| `detalhe_votacao_munzona` 2024 e 2026 | aptos, comparecimento e abstenção por zona |
| `eleitorado_local_votacao` 2024 e 2026 | local de votação, endereço, lat/lon |
| `consulta_cand` 2024 e 2026 | partido, situação, eleito |

URLs verificadas em 2026-11-10 no pacote `resultados-2026-boletim-de-urna` e `resultados-2024-boletim-de-urna` do portal de dados abertos do TSE. As URLs das demais fontes são levantadas no plano, a partir dos mesmos pacotes.

**Regras de coleta:**
- Download idempotente: não rebaixa arquivo que já existe com hash correto.
- O SHA-512 publicado pelo TSE é conferido para cada zip que o TSE publica com hash.
- Bruto nunca é sobrescrito.
- O manifesto grava URL, data de download, tamanho e hash, para reproduzir o dado ou detectar mudança no TSE.
- Se o CDN do TSE bloquear download automatizado, o plugin Bright Data é a contingência.

## 5. Base normalizada

`bu_secao`: uma linha por seção × votável. Campos: ano, turno, cargo, código TSE do município (texto), zona, seção, local de votação, aptos, comparecimento, abstenções, tipo de votável (nominal, legenda, branco, nulo), número, nome, votos.

Limpeza:
- `#NULO` e `-1` viram nulo; `#NE` e `-3` viram nulo.
- Decodificação latin1 feita uma única vez, acentos preservados.
- Seções agregadas são preservadas (`DS_SECOES_AGREGADAS`), não descartadas.
- Nenhuma linha é removida sem registro em `excecoes.json`.

CSVs grandes (BU 2026 T1: 197 MB) são lidos em blocos ou por DuckDB direto sobre o arquivo, sem carregar tudo em RAM.

## 6. Conferência dupla (4 camadas)

Cada camada é independente. Falha em qualquer camada bloqueia a etapa de exportação, salvo exceção registrada e justificada.

| Camada | Conferência | Critério |
|---|---|---|
| 1. Integridade | SHA-512 dos zips; contagem de linhas; os 139 municípios presentes; nenhuma seção duplicada por cargo e turno; 2º turno de Prefeito só em município que o exigia no 1º turno | exato |
| 2. Consistência interna | por seção e cargo: soma dos votos = comparecimento; comparecimento + abstenção = aptos; conjunto de seções do BU = conjunto de seções do cadastro de locais | exato |
| 3. Cruzamento de fontes | BU somado por candidato × município × zona = `votacao_candidato_munzona`; aptos e comparecimento somados = `detalhe_votacao_munzona` | exato, exceto casos catalogados (voto anulado e apurado em separado, sub judice), cada um com a causa |
| 4. Verificação externa | eleito por município contra o resultado oficial divulgado pelo TSE; conferência visual no site oficial | ver abaixo |

**Camada 4, amostra definida:**
- Prefeito: todos os 139 municípios (e os dois turnos onde houver).
- Vereador, Deputado Federal e Deputado Estadual: totais estaduais por cargo e uma amostra de 10 municípios (os 5 maiores por eleitorado e 5 sorteados com semente fixa registrada).
- O meio de acesso ao resultado oficial (API de divulgação ou página) é verificado no início do plano. Se não houver acesso programático, a conferência passa a ser visual via Chrome, com a mesma amostra.

**Dupla implementação:** as camadas 2 e 3 são implementadas duas vezes, de forma independente (pandas e SQL em DuckDB). Discordância entre as duas implementações é um achado a investigar, mesmo que ambas concordem com o TSE.

**Divergências:** nunca corrigidas em silêncio. Cada uma é registrada em `validacao/` com linhas e causa provável (seção anulada, urna de contingência, seção agregada etc.) e só então resolvida por regra documentada ou exclusão justificada.

**Caso de controle:** Palmas (`CD_MUNICIPIO 73440`). O pipeline novo precisa reproduzir os totais de `B24.pkl` e `B26.pkl` do projeto anterior para o turno 1. Diferenças são investigadas, em qualquer direção.

## 7. Exportação (etapa 04)

Lê apenas a base com validação aprovada e escreve em `site_dados/`:
- `index.json`: 139 municípios com nome, código TSE, eleitorado e eleições/cargos/turnos disponíveis.
- `<cod_municipio>/<eleicao>_<cargo>_t<turno>.json`: votos por candidato e partido por local de votação, com lat/lon, aptos, comparecimento e eleitos.
- `estado/<eleicao>_<cargo>.json`: totais estaduais por partido e candidato.
- `selo_validacao.json`: resultado das 4 camadas, data e hashes das fontes.

## 8. Site

Estático, publicado online, sem servidor. Cada arquivo é carregado sob demanda, para abrir rápido no celular.

1. **Estado:** mapa dos 139 municípios coloridos pelo partido ou candidato mais votado; ranking estadual por cargo.
2. **Município:** busca por nome; resultado por cargo, eleitos, comparecimento, abstenção; mapa dos locais de votação com a cor do vencedor por local.
3. **Candidato:** onde teve votos, tabela ordenável e exportação CSV.
4. **Comparativo 2024 × 2026** por local de votação, apenas onde o local existe nas duas eleições, deixando isso explícito na tela.
5. **Selo de validação** visível em cada tela, com link para o relatório.

Requisitos: legível e utilizável no celular; contraste de cores checado; paleta consistente de partidos; auditoria de acessibilidade ao final. Local sem lat/lon aparece na tabela, não no mapa, e é contado no relatório.

## 9. Ferramentas

| Etapa | Ferramenta |
|---|---|
| Coleta e hash | scripts Python; Bright Data só como contingência |
| Perfilamento dos arquivos | `data:explore-data` |
| Conferência (camadas 2 e 3) | `data:validate-data` + duas implementações |
| Conferência (camada 4) | Chrome (claude-in-chrome) |
| Paralelismo | `superpowers:dispatching-parallel-agents`: um agente por camada de validação e por cargo |
| Site | `impeccable`, `dataviz`, `design-skills:accessibility-audit` |
| Encerramento | `superpowers:verification-before-completion` |

## 10. Riscos

1. Volume e memória (BU 2026: 197 MB): leitura em blocos ou DuckDB.
2. Locais de votação mudam entre 2024 e 2026: o comparativo só vale onde o local existe nas duas eleições.
3. Coordenadas ausentes ou erradas em locais rurais: tratadas como na seção 8.
4. Voto anulado, sub judice, seções agregadas e urnas de contingência geram divergência legítima entre fontes: cada exceção é registrada com causa.
5. 2º turno de Prefeito só em município que o exigia: conferido na camada 1.
6. Arquivos do TSE podem ser atualizados: o manifesto detecta mudança de hash.
7. Verificação externa pode não ter acesso programático: plano B visual definido na seção 6.

## 11. Critério de pronto

- Os 139 municípios nos quatro cargos, com os dois turnos onde existirem.
- As 4 camadas verdes, ou exceções registradas e justificadas em `excecoes.json`.
- Palmas reproduz os totais do projeto anterior (turno 1).
- Site publicado, com selo de validação e as telas da seção 8.
- Cada afirmação de "pronto" acompanhada da saída dos comandos de validação executados.

## 12. Próximos passos

1. Revisão desta spec pelo usuário.
2. Plano de implementação (`superpowers:writing-plans`), com método de execução a escolher.
3. Só então: coleta, base, validação, exportação e site.
