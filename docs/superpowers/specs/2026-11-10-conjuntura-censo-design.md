# Conjuntura e Censo — design

Data: 10/11/2026 · Projeto: Tocantins nas urnas (continuação de `2026-11-10-tocantins-urnas-design.md`)

## 1. Objetivo

Transformar o site de consulta de resultados em ferramenta de **análise política da conjuntura do Tocantins**,
com transparência e gestão pública como usos secundários. O Censo 2022 entra para **explicar o voto**, não como
produto à parte.

Perguntas que o site precisa responder (prioridade do usuário):

1. **Força dos prefeitos:** o candidato a Governador/Senador 2026 da coligação do partido do prefeito eleito em
   2024 venceu no município?
2. **Perfil do voto:** em que tipo de lugar (pelo Censo) cada candidato ou partido vai melhor ou pior?
3. **Comparecimento:** onde se vota menos e qual o perfil desses lugares?

Também corrige a usabilidade apontada pelo usuário: depois de entrar no mapa do município não se consegue voltar;
o comparativo 2024 × 2026 por local não faz sentido agora; o tooltip dos locais deve mostrar prefeito, vereadores
e governador.

### Critérios de sucesso

- As três análises funcionam para os 139 municípios, com os dados passando pelo selo (camada 5).
- Do mapa do município sempre se volta ao estado/município sem usar o botão voltar do navegador; o botão voltar
  também funciona.
- Clicar num local abre a ficha com prefeito, 15 vereadores mais votados, Governador, Senador, 5 mais votados de
  cada cargo de deputado e o perfil do entorno (ou o aviso de ligação não crível).
- Nenhuma frase do site afirma causalidade entre perfil do lugar e voto.

### Fora do escopo

- Lista de apoios formais de prefeitos (não existe ainda; a ligação é por partido/coligação registrados no TSE).
  Pode entrar depois como fonte nova.
- Finanças municipais (DCA/Siconfi) e comparação Censo 2010 × 2022.
- Comparativo 2024 × 2026 por local (sai do menu; código fica no histórico do git).

## 2. Dados

### 2.1 Fontes novas (em `SOURCES`, baixadas para `dados_brutos/`, com hash no manifesto)

| Fonte | Uso |
|---|---|
| Malha de setores censitários 2022 do Tocantins (IBGE) | geometria dos 4.119 setores |
| Agregados por setor 2022: básico, demografia, alfabetização, cor ou raça, características do domicílio 2 (IBGE, arquivos nacionais) | indicadores por setor |
| Agregados por setor 2022: renda do responsável, **se publicado** | indicador de renda; se não existir, fica fora |
| População municipal do Censo 2022, área territorial e PIB per capita (SIDRA / API de agregados do IBGE) | ficha do município e fechamento da camada 5 |

Governador e Senador 2026 já estão no BU. As coligações e federações vêm de `consulta_cand` 2024/2026, já
baixados. Os arquivos nacionais do Censo são lidos em blocos, filtrando setores com código iniciado por `17`.
Nada é copiado de `Palmas_Urnas_e_Censo`, que só é lido no caso de controle.

### 2.2 Processamento (método de Palmas generalizado)

1. **Setor → local:** o centroide de cada setor (SIRGAS 2000 / UTM, métrico) vai para o local de votação mais
   próximo **do mesmo município**, separadamente para 2024 e 2026. Locais especiais (voto em trânsito, unidade
   prisional, sem eleitorado no cadastro) não recebem setores.
2. **Ligação crível:** um local representa o entorno só se tiver de 0,4 a 1,6 eleitor por morador ligado. Fora
   dessa faixa, ele fica marcado (`credivel=false`) e sai das análises de perfil.
3. **Área de votação:** dentro de cada município, locais vizinhos se juntam até que eleitores e moradores fiquem
   na faixa crível. A área é a unidade do gráfico de dispersão. Municípios pequenos podem virar uma área só.
4. **Indicadores** por setor, área e município, sempre como proporção com numerador e denominador guardados:
   alfabetização 15+, faixas etárias (0–14, 15–29, 60+), cor ou raça (pretos + pardos), água por rede,
   esgoto por rede, lixo coletado, densidade, média de moradores e renda (se houver).

Saídas em `base/`: `censo_setor.parquet`, `ligacao_setor_local.parquet`, `area_votacao.parquet`,
`ibge_municipio.parquet`, `coligacoes.parquet`.

Dependência nova: `geopandas`.

### 2.3 Prefeitos × 2026

- Prefeito de cada município = eleito em 2024 (turno 2 em Palmas), já validado na camada 4.
- Candidato da coligação do prefeito, para Governador e Senador 2026: aquele cuja coligação/federação inclui o
  partido do prefeito. Se o próprio partido lançou candidato, é ele. Sem nenhum: "sem candidato da coligação".
- Resultado por município: `entregou` (o candidato da coligação foi o mais votado ali), `nao_entregou` ou
  `sem_candidato`, com a margem em votos e pontos percentuais sobre o vencedor local.
- Senador 2026 tem duas vagas: "entregou" significa que o candidato da coligação ficou entre os dois mais
  votados no município.

## 3. Validação — camada 5 "Censo e ligações"

Mesmas regras do selo atual: divergência sem causa registrada em `validacao/excecoes.json` reprova, e a
exportação recusa selo que não seja ok.

1. **Integridade:** hashes no manifesto; 4.119 setores nos 139 municípios; os mesmos setores nos agregados e na
   malha; nenhum código duplicado.
2. **Fechamento:** a soma da população dos setores por município é igual à população municipal do Censo 2022.
   Diferença causada por sigilo de setor pequeno ("X") vira exceção com causa; qualquer outra reprova.
3. **Ligação em duas implementações:** `geopandas.sjoin_nearest` × distância direta com numpy. Qualquer setor
   ligado a locais diferentes reprova (e não aceita exceção).
4. **Consistência:** todo setor ligado a exatamente um local do mesmo município; a soma de moradores das áreas
   é igual à população do município; nenhum local especial recebe setores. O percentual de ligações críveis
   por município vai para o relatório como informação.
5. **Coligações e prefeitos:** os 140 prefeitos eleitos têm partido e estão em `consulta_cand`; toda candidatura
   a Governador/Senador 2026 tem a composição da coligação preenchida.

Ampliações:

- **Camada 4:** passa a conferir Governador e Senador 2026 com o JSON oficial do TSE (arquivo estadual + a mesma
  amostra de 10 municípios), recalculado contra a base atual como já acontece com os outros cargos.
- **Caso de controle:** a população dos setores de Palmas tem de bater com o total de
  `Palmas_Urnas_e_Censo/census_regioes.json` (somente leitura).
- **Selo:** a camada 5 aparece na tela do Selo com o percentual de ligações críveis e o link para os relatórios.

## 4. Site

### 4.1 Navegação

- Menu: **Estado · Municípios · Conjuntura** + selo. A rota `#/comparativo` sai.
- Mapas: a roda do mouse rola a página; o zoom é pelos botões ou com Ctrl + roda. Há um botão "ver tudo" que
  volta ao enquadramento inicial.
- Trilha no topo: Tocantins › Município › Local/Candidato, mantendo a eleição escolhida em cada nível.
- `parseHash` dentro do `try` do roteador: endereço malformado mostra erro, não "Carregando…" para sempre.

### 4.2 Tela Município

- Ficha IBGE: população 2022, área, densidade e PIB per capita.
- Prefeito eleito em 2024 com o indicador entregou/não entregou para Governador 2026.
- Seletor de eleição inclui Governador e Senador 2026.
- Mapa dos locais:
  - **Ao passar o mouse:** nome, comparecimento e o mais votado de cada cargo.
  - **Ao clicar:** painel lateral (no celular, ocupa a tela por baixo, com botão fechar e tecla Esc) com prefeito,
    15 vereadores mais votados, Governador, Senador, 5 mais votados de Deputado Federal e Estadual, e o perfil do
    entorno pelo Censo, ou "local sem ligação crível com o entorno". O local selecionado entra no endereço
    (`?local=<id>`), para o voltar funcionar.
- Cor dos locais em cargos proporcionais: partido mais votado no local (nominal + legenda), a mesma regra do mapa
  estadual.
- Goiatins (2024): nota sobre a eleição suplementar de 25/10/2026, que não faz parte destes dados.

### 4.3 Tela Conjuntura (`#/conjuntura/<aba>`)

1. **Prefeitos** (`prefeitos`): seletor Governador | Senador; mapa dos 139 com três categorias (entregou, não
   entregou, sem candidato da coligação) e legenda com contagens; tabela por município (prefeito e partido,
   vencedor local, candidato da coligação, margem); ranking de partidos (prefeituras, entregas, taxa).
2. **Perfil do voto** (`perfil`): seletores de cargo, candidato ou partido e indicador; dispersão com um ponto por
   área de votação (ou por município, num seletor), tamanho pelo número de eleitores; resumo dos quintis (% de
   válidos nos 20% de áreas com o indicador mais alto × nos 20% mais baixo) e correlação ponderada pelo eleitorado;
   aviso fixo "perfil do lugar, não do eleitor"; tabela equivalente.
3. **Comparecimento** (`comparecimento`): mapa da abstenção por município (escala sequencial), ranking, e dispersão
   abstenção × indicador no mesmo formato.

Gráficos seguem o skill dataviz: uma escala, cores validadas, legenda sempre, tabela equivalente, tooltip, e
modo escuro.

### 4.4 Arquivos novos em `site_dados/` (carregados sob demanda)

- `conjuntura/prefeitos_2026.json`
- `conjuntura/areas_<ano>_<cargo>.json`: áreas com indicadores e votos por candidato e partido (estimativa: 1–2 MB
  por cargo de deputado)
- `conjuntura/municipios_indicadores.json`
- `<mun>/locais_ficha.json`: os cargos juntos por local (painel)
- `<mun>/ibge.json`
- `estado/2026_governador_t*.json`, `estado/2026_senador_t1.json` e os arquivos municipais desses cargos

## 5. Pendências menores incluídas

- Endereço malformado travando em "Carregando…" (4.1).
- Nota de Goiatins (4.2).
- Cor dos locais em cargos proporcionais (4.2).
- Latitude e longitude de um local vindas de seções diferentes: anular as duas quando uma for inválida e escolher
  uma linha completa por local.
- Guia de execução dos scripts (`docs/como_rodar.md`), incluindo as etapas novas.

Continuam adiadas: SRI do Leaflet, hash em vez de data na trava da exportação, detecção de atualização do TSE,
denominador do check de 2º turno, teste de exportação com seções agregadas, nome do campo `data_consulta`.

## 6. Testes

- Python (pytest), com dados pequenos: leitura em blocos do Censo filtrando o TO; as duas implementações da
  ligação, inclusive empate de distância e local especial; agrupamento em áreas; fechamento por município com
  sigilo; coligação do prefeito (partido próprio, coligação, federação, sem candidato); Senador com duas vagas;
  cada check da camada 5 passando e falhando.
- Node: entrega, quintis, correlação ponderada, montagem do painel do local, trilha de navegação.
- Visual: Edge headless a 1280 px e iframe de 390 px, sem rolagem horizontal; conferência de contraste.

## 7. Riscos

1. **Proximidade ≠ local de votação real:** o eleitor nem sempre vota no local mais perto de casa. Mitigação:
   faixa crível, áreas de votação, texto "perfil do entorno".
2. **Falácia ecológica:** correlação entre lugares não descreve o eleitor. Mitigação: aviso fixo e linguagem
   "vai melhor em".
3. **Memória:** arquivos nacionais grandes. Mitigação: leitura em blocos, só colunas usadas, um arquivo por vez.
4. **Renda por setor pode não estar publicada:** o indicador fica fora sem bloquear o resto.
5. **Coligação ≠ apoio:** prefeito pode apoiar candidato de outra coligação. Mitigação: o site diz "candidato da
   coligação do partido do prefeito", nunca "candidato do prefeito".
