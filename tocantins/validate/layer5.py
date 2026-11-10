"""Camada 5: Censo 2022 e ligacoes setor -> local de votacao (spec secao 3).

- setores_integridade: n de setores (4.117 codigos; a malha tem 4.119 poligonos, 2 setores partidos -- Ruling
  da Task 2), 139 municipios, codigo sem duplicata, codigo do setor comeca com o codigo do municipio.
  A presenca de cada setor nos agregados e coberta pelo fechamento (setor sem agregado = 0 morador).
- fechamento_municipio: soma dos moradores dos setores = populacao do Censo (SIDRA) por municipio.
- ligacao_impl_disagreement: numpy x geopandas; NUNCA aceita excecao.
- ligacao_consistencia: cada setor em exatamente um local por ano, do mesmo municipio (crosswalk), nenhum local
  especial com setor, soma dos moradores das areas = populacao.
- ligacao_credibilidade: informativo (sempre passa); o percentual vai para o selo (`resumo`).
- coligacoes_prefeitos: prefeitos eleitos com partido e presentes na consulta_cand; candidaturas a Governador e
  Senador 2026 votadas no BU com composicao preenchida.
"""
import pandas as pd

from tocantins import conjuntura
from tocantins.validate.result import LayerResult, make_result

LAYER = "5"
N_SETORES = 4117
N_MUN = 139
PROB = ["problema"]
MUNZONA_COLUMNS = ["ano", "turno", "cargo", "cd_municipio", "nr_candidato", "nm_candidato", "sg_partido",
                   "situacao_turno"]


def _div(rows: list[dict], cols: list[str]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=PROB + cols)


def integridade(setores: pd.DataFrame, n_setores: int = N_SETORES, n_mun: int = N_MUN,
                exceptions: list[dict] = ()) -> LayerResult:
    rows = []
    cod = setores["cd_setor"].astype(str)
    for c in sorted(cod[cod.duplicated()].unique()):
        rows.append({"problema": "codigo_duplicado", "cd_setor": c})
    u = cod.nunique()
    if u != n_setores:
        rows.append({"problema": "n_setores", "valor": u, "esperado": n_setores})
    m = setores["cd_mun_ibge"].nunique()
    if m != n_mun:
        rows.append({"problema": "n_municipios", "valor": m, "esperado": n_mun})
    bad = setores[cod.str[:7] != setores["cd_mun_ibge"].astype(str)]
    rows += [{"problema": "municipio_do_codigo", "cd_setor": r.cd_setor, "cd_mun_ibge": r.cd_mun_ibge}
             for r in bad.itertuples()]
    div = _div(rows, ["cd_setor", "cd_mun_ibge", "valor", "esperado"])
    return make_result(LAYER, "setores_integridade", len(setores), div, list(exceptions))


def fechamento(setores: pd.DataFrame, municipios: pd.DataFrame, exceptions: list[dict]) -> LayerResult:
    s = setores.groupby("cd_mun_ibge").agg(moradores_setores=("moradores", "sum"), setores_sigilo=("sigilo", "sum"))
    m = municipios.set_index("cd_mun_ibge")[["populacao"]].join(s, how="outer").fillna(0)
    m["diferenca"] = m["moradores_setores"].astype("int64") - m["populacao"].astype("int64")
    div = m[m["diferenca"] != 0].reset_index()[["cd_mun_ibge", "moradores_setores", "populacao", "diferenca",
                                                "setores_sigilo"]]
    div = div.astype({"moradores_setores": "int64", "populacao": "int64", "setores_sigilo": "int64"})
    return make_result(LAYER, "fechamento_municipio", len(m), div, exceptions)


def impl_disagreement(ligacao: pd.DataFrame, exceptions: list[dict] = ()) -> LayerResult:
    """Excecoes sao ignoradas de proposito: implementacoes divergentes sempre reprovam."""
    key = ["ano", "cd_setor"]
    a = ligacao[ligacao["impl"] == "numpy"].set_index(key)[["cd_municipio", "local_id"]]
    b = ligacao[ligacao["impl"] == "geopandas"].set_index(key)[["cd_municipio", "local_id"]]
    m = a.add_suffix("_numpy").join(b.add_suffix("_geopandas"), how="outer")
    diff = (m["local_id_numpy"] != m["local_id_geopandas"]) | (m["cd_municipio_numpy"] != m["cd_municipio_geopandas"])
    return make_result(LAYER, "ligacao_impl_disagreement", len(m), m[diff].reset_index(), [])


def consistencia(setores, ligacao, areas, credibilidade, crosswalk: dict[str, str], municipios,
                 exceptions: list[dict]) -> LayerResult:
    rows = []
    lk = ligacao[ligacao["impl"] == "numpy"]
    mun_setor = setores.set_index("cd_setor")["cd_mun_ibge"]
    for ano, l in lk.groupby("ano", sort=True):
        n = l["cd_setor"].value_counts()
        rows += [{"problema": "setor_sem_ligacao", "ano": ano, "cd_setor": c}
                 for c in sorted(set(setores["cd_setor"]) - set(n.index))]
        rows += [{"problema": "setor_duplicado", "ano": ano, "cd_setor": c} for c in sorted(n[n > 1].index)]
        dif = l[l["cd_municipio"].map(crosswalk) != l["cd_setor"].map(mun_setor)]
        rows += [{"problema": "municipio_diferente", "ano": ano, "cd_setor": r.cd_setor, "cd_municipio": r.cd_municipio,
                  "local_id": r.local_id} for r in dif.itertuples()]
        c = credibilidade[credibilidade["ano"] == ano]
        esp = set(zip(c.loc[c["especial"].astype(bool), "cd_municipio"], c.loc[c["especial"].astype(bool), "local_id"]))
        rows += [{"problema": "local_especial_com_setor", "ano": ano, "cd_setor": r.cd_setor,
                  "cd_municipio": r.cd_municipio, "local_id": r.local_id}
                 for r in l.itertuples() if (r.cd_municipio, r.local_id) in esp]
        a = areas[areas["ano"] == ano].merge(c[["cd_municipio", "local_id", "moradores"]], on=["cd_municipio", "local_id"])
        soma = a.groupby(a["cd_municipio"].map(crosswalk))["moradores"].sum()
        pop = municipios.set_index("cd_mun_ibge")["populacao"]
        for mun in sorted(pop.index):
            if int(soma.get(mun, 0)) != int(pop[mun]):
                rows.append({"problema": "soma_areas", "ano": ano, "cd_mun_ibge": mun, "valor": int(soma.get(mun, 0)),
                             "esperado": int(pop[mun])})
    div = _div(rows, ["ano", "cd_setor", "cd_municipio", "local_id", "cd_mun_ibge", "valor", "esperado"])
    return make_result(LAYER, "ligacao_consistencia", len(lk), div, exceptions)


def credibilidade(cred: pd.DataFrame) -> LayerResult:
    """Informativo: nunca reprova; a tabela por municipio sai em `por_municipio`."""
    return LayerResult(LAYER, "ligacao_credibilidade", True, len(cred), pd.DataFrame(), 0)


def resumo(cred: pd.DataFrame) -> dict:
    out = {}
    for ano, c in cred[~cred["especial"].astype(bool)].groupby("ano", sort=True):
        n, k = len(c), int(c["credivel"].sum())
        out[str(ano)] = {"locais": n, "criveis": k, "pct": round(100 * k / n, 1) if n else 0.0}
    return out


def por_municipio(cred: pd.DataFrame) -> pd.DataFrame:
    c = cred[~cred["especial"].astype(bool)]
    t = c.groupby(["ano", "cd_municipio"]).agg(locais=("local_id", "size"), criveis=("credivel", "sum")).reset_index()
    t["pct_criveis"] = (100 * t["criveis"] / t["locais"]).round(1)
    return t


def coligacoes_prefeitos(munzona, coligacoes, bu, exceptions: list[dict]) -> LayerResult:
    rows = []
    p = conjuntura.prefeitos(None, munzona)
    pref_col = coligacoes[(coligacoes["ano"] == 2024) & (coligacoes["cargo"] == "Prefeito")]
    nrs = set(zip(pref_col["nr_candidato"].astype(int)))
    for r in p.itertuples():
        if pd.isna(r.partido) or not str(r.partido).strip():
            rows.append({"problema": "prefeito_sem_partido", "cd_municipio": r.cd_municipio, "nr": r.nr})
        if (int(r.nr),) not in nrs:
            rows.append({"problema": "prefeito_fora_da_consulta_cand", "cd_municipio": r.cd_municipio, "nr": r.nr})
    for cargo in ("Governador", "Senador"):
        votados = set(bu.loc[(bu["ano"] == 2026) & (bu["cargo"] == cargo) & (bu["tipo_votavel"] == "Nominal"),
                             "nr_votavel"].astype(int))
        col = coligacoes[(coligacoes["ano"] == 2026) & (coligacoes["cargo"] == cargo)]
        comp = {int(n): len(ps) > 0 for n, ps in zip(col["nr_candidato"], col["partidos"])}
        for nr in sorted(votados):
            if not comp.get(nr, False):
                rows.append({"problema": "candidatura_sem_composicao", "cargo": cargo, "nr": nr})
    div = _div(rows, ["cd_municipio", "cargo", "nr"])
    return make_result(LAYER, "coligacoes_prefeitos", len(p), div, exceptions)


def run(inputs: dict, exceptions: list[dict], n_setores: int = N_SETORES, n_mun: int = N_MUN) -> list[LayerResult]:
    d, exc = inputs, list(exceptions)
    return [
        integridade(d["setores"], n_setores, n_mun, exc),
        fechamento(d["setores"], d["municipios"], exc),
        impl_disagreement(d["ligacao"], exc),
        consistencia(d["setores"], d["ligacao"], d["areas"], d["credibilidade"], d["crosswalk"], d["municipios"], exc),
        credibilidade(d["credibilidade"]),
        coligacoes_prefeitos(d["munzona"], d["coligacoes"], d["bu"], exc),
    ]
