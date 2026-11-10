# Como rodar

Tudo em Python 3.12 (`pip install -r requirements.txt`) a partir da raiz do projeto. Rode cada etapa com
`python -I` (modo isolado: nada dos dados baixados é importado como código). A pasta
`../Palmas_Urnas_e_Censo` é só leitura (caso de controle).

| # | Comando | O que faz | Grava |
|---|---|---|---|
| 1 | `python -I scripts/01_baixar.py` | Baixa TSE, IBGE (malha, municípios, setores e agregados do Censo 2022) e SIDRA; extrai os zip, cada um na sua pasta | `dados_brutos/`, `dados_brutos/manifesto.json` (SHA-512) |
| 2 | `python -I scripts/02_normalizar.py` | CSV do TSE → Parquet (BU, locais, munzona, detalhe, votação por seção, candidatos) | `base/*.parquet`, `base/exclusoes.json` |
| 3 | `python -I scripts/02b_censo.py` | Censo por setor, IBGE municipal, coligações, ligação setor → local (numpy e geopandas), credibilidade e áreas de votação (~2–3 min) | `base/censo_setor`, `ibge_municipio`, `coligacoes`, `ligacao_setor_local`, `local_credibilidade`, `area_votacao` (.parquet) |
| 4 | `python -I scripts/excecoes_camada3.py` | Registra as exceções investigadas da camada 3 (nulos técnicos, cobertura) | `validacao/excecoes.json` |
| 5 | `python -I scripts/conferir_oficial.py` | Camada 4: baixa uma vez os JSON oficiais do TSE (cache) e compara com a base | `dados_brutos/oficial/`, `validacao/camada4_oficial.json` |
| 6 | `python -I scripts/03_validar.py` | Camadas 1–5 e controles de Palmas (votos e população); sai com 1 se o selo falhar | `validacao/camada*.json`, `divergencias_*.csv`, `credibilidade_municipios.csv`, `selo.json` |
| 7 | `python -I scripts/04_exportar.py` | Gera os JSON do site; recusa sem selo `ok` ou com selo mais velho que a base | `site_dados/` (troca atômica) |

Mudou a base (etapas 2 ou 3)? Rode de novo 5, 6 e 7: a exportação exige selo mais novo que os Parquet.
Divergência nova na validação reprova o selo até ser corrigida ou registrada em `validacao/excecoes.json`
com causa e data de aprovação.

## Testes

```
python -m pytest -q
node --test site/tests/
```

## Ver o site localmente

```
python -m http.server 8765 --bind 127.0.0.1
```

Abra http://127.0.0.1:8765/site/ (o site lê `../site_dados/`). Rotas: `#/estado`, `#/municipio/<cod TSE>`
(`?e=<ano>-<cargo>-<turno>&local=<zona-local>` abre a ficha do local), `#/candidato/...`,
`#/conjuntura/prefeitos|perfil|comparecimento` e `#/selo`.

## Publicar

O GitHub Pages serve a branch `main` (raiz com `index.html` → `site/`, mais `site_dados/`). Publicar = commit
de `site/` e `site_dados/` e push para `origin/main`.
