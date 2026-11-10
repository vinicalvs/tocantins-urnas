"""Camada 2: consistencia interna do BU, em duas implementacoes independentes (pandas e SQL).

As duas versoes nao compartilham logica: compartilham so os nomes das colunas de saida
(KEYS/VALUES) e a tabela de fatos VOTOS_POR_ELEITOR.
"""
import duckdb
import pandas as pd

from tocantins.validate.result import LayerResult, compare_impls, make_result

LAYER = "2"
SEC = ["ano", "turno", "cargo", "cd_municipio", "zona", "secao"]
LOC = ["ano", "turno", "cd_municipio", "zona", "secao"]
# Votos por eleitor quando o cargo tem mais de uma vaga na mesma eleicao (Ruling R23):
# Senador em 2026 renova 2/3 do Senado, 2 votos por eleitor.
VOTOS_POR_ELEITOR = {(2026, 5): 2}
KEYS = {
    "votos_eq_comparecimento": SEC,
    "comparecimento_mais_abst_eq_aptos": SEC,
    "secoes_bu_eq_locais": LOC + ["lado"],
    "urnas_nao_apuradas": SEC + ["cd_tipo_urna"],
}
VALUES = {
    "votos_eq_comparecimento": ["votos_total", "comparecimento"],
    "comparecimento_mais_abst_eq_aptos": ["aptos", "soma"],
    "secoes_bu_eq_locais": [],
    "urnas_nao_apuradas": ["votos_total", "comparecimento"],
}
INFORMATIVE = {"urnas_nao_apuradas"}
_STR_COLS = {"cargo", "cd_municipio", "lado"}
BU_COLUMNS = ["ano", "turno", "cd_cargo", "cargo", "cd_municipio", "zona", "secao", "aptos",
              "comparecimento", "abstencoes", "cd_tipo_urna", "votos", "secoes_agregadas"]
LOCAIS_COLUMNS = LOC


def conform(check: str, df: pd.DataFrame) -> pd.DataFrame:
    """Colunas e tipos padronizados de um check, ordenado pela chave."""
    cols = KEYS[check] + VALUES[check]
    out = df[cols].copy()
    for c in cols:
        out[c] = out[c].astype("str" if c in _STR_COLS else "int64")
    return out.sort_values(KEYS[check]).reset_index(drop=True)


# ----------------------------------------------------------------------------- pandas

def pandas_impl(bu: pd.DataFrame, locais: pd.DataFrame) -> dict[str, pd.DataFrame]:
    apur = bu[bu["cd_tipo_urna"] == 1]
    g = apur.groupby(SEC + ["cd_cargo"], as_index=False).agg(
        votos_total=("votos", "sum"), comparecimento=("comparecimento", "max"),
        aptos=("aptos", "max"), abstencoes=("abstencoes", "max"))
    fator = pd.Series([VOTOS_POR_ELEITOR.get((a, c), 1) for a, c in zip(g["ano"], g["cd_cargo"])],
                      index=g.index)
    votos = g[g["votos_total"] != g["comparecimento"] * fator]
    g["soma"] = g["comparecimento"] + g["abstencoes"]
    aptos = g[g["soma"] != g["aptos"]]

    nao = (bu[bu["cd_tipo_urna"] != 1]
           .groupby(SEC + ["cd_tipo_urna"], as_index=False)
           .agg(votos_total=("votos", "sum"), comparecimento=("comparecimento", "max")))

    return {
        "votos_eq_comparecimento": votos[SEC + VALUES["votos_eq_comparecimento"]],
        "comparecimento_mais_abst_eq_aptos": aptos[SEC + VALUES["comparecimento_mais_abst_eq_aptos"]],
        "secoes_bu_eq_locais": _pandas_secoes(bu, locais),
        "urnas_nao_apuradas": nao,
    }


def _pandas_secoes(bu: pd.DataFrame, locais: pd.DataFrame) -> pd.DataFrame:
    own = bu[LOC].drop_duplicates()
    hosts = bu[LOC + ["secoes_agregadas"]].dropna(subset=["secoes_agregadas"]).drop_duplicates()
    ag = hosts.assign(tok=hosts["secoes_agregadas"].str.split("/")).explode("tok")
    ag["sec_ag"] = pd.to_numeric(ag["tok"].str.strip(), errors="coerce")
    ag = ag[ag["sec_ag"].notna() & (ag["sec_ag"] != ag["secao"])]
    ag = ag[LOC[:-1] + ["sec_ag"]].rename(columns={"sec_ag": "secao"})
    ag["secao"] = ag["secao"].astype("int64")

    own_k = own.astype({"secao": "int64"})
    rep_own = ag.merge(own_k, on=LOC)
    rep_multi = ag[ag.duplicated(LOC, keep=False)]
    repetidas = pd.concat([rep_own, rep_multi]).drop_duplicates()

    bu_set = pd.concat([own_k, ag]).drop_duplicates()
    loc = locais[LOC].drop_duplicates().astype({"secao": "int64"})
    m = bu_set.merge(loc, on=LOC, how="outer", indicator=True)
    so_bu = m[m["_merge"] == "left_only"][LOC].assign(lado="so_bu")
    so_loc = m[m["_merge"] == "right_only"][LOC].assign(lado="so_locais")
    return pd.concat([so_bu, so_loc, repetidas.assign(lado="agregada_repetida")], ignore_index=True)


# ----------------------------------------------------------------------------- SQL

def sql_impl(con: duckdb.DuckDBPyConnection) -> dict[str, pd.DataFrame]:
    """`con` precisa das views `bu` e `locais`."""
    fatores = " UNION ALL ".join(f"SELECT {a} AS ano, {c} AS cd_cargo, {f} AS fator"
                                 for (a, c), f in VOTOS_POR_ELEITOR.items())
    por_secao = f"""
        WITH fatores AS ({fatores}),
        s AS (
            SELECT ano, turno, cargo, cd_municipio, zona, secao, cd_cargo,
                   SUM(votos)::BIGINT AS votos_total, MAX(comparecimento) AS comparecimento,
                   MAX(aptos) AS aptos, MAX(abstencoes) AS abstencoes
            FROM bu WHERE cd_tipo_urna = 1
            GROUP BY ano, turno, cargo, cd_municipio, zona, secao, cd_cargo
        )
        SELECT s.*, COALESCE(f.fator, 1) AS fator
        FROM s LEFT JOIN fatores f USING (ano, cd_cargo)
    """
    votos = con.sql(f"""
        SELECT ano, turno, cargo, cd_municipio, zona, secao, votos_total, comparecimento
        FROM ({por_secao}) WHERE votos_total <> comparecimento * fator
    """).df()
    aptos = con.sql(f"""
        SELECT ano, turno, cargo, cd_municipio, zona, secao, aptos,
               comparecimento + abstencoes AS soma
        FROM ({por_secao}) WHERE comparecimento + abstencoes <> aptos
    """).df()
    nao = con.sql("""
        SELECT ano, turno, cargo, cd_municipio, zona, secao, cd_tipo_urna,
               SUM(votos)::BIGINT AS votos_total, MAX(comparecimento) AS comparecimento
        FROM bu WHERE cd_tipo_urna IS DISTINCT FROM 1
        GROUP BY ano, turno, cargo, cd_municipio, zona, secao, cd_tipo_urna
    """).df()
    secoes = con.sql("""
        WITH proprias AS (
            SELECT DISTINCT ano, turno, cd_municipio, zona, secao FROM bu
        ),
        hosts AS (
            SELECT DISTINCT ano, turno, cd_municipio, zona, secao, secoes_agregadas
            FROM bu WHERE secoes_agregadas IS NOT NULL
        ),
        agregadas AS (
            SELECT ano, turno, cd_municipio, zona, sec AS secao FROM (
                SELECT ano, turno, cd_municipio, zona, secao AS host,
                       TRY_CAST(trim(unnest(string_split(secoes_agregadas, '/'))) AS INTEGER) AS sec
                FROM hosts
            ) WHERE sec IS NOT NULL AND sec <> host
        ),
        repetidas AS (
            SELECT ano, turno, cd_municipio, zona, secao FROM agregadas
            GROUP BY ALL HAVING count(*) > 1
            UNION
            SELECT a.ano, a.turno, a.cd_municipio, a.zona, a.secao
            FROM agregadas a JOIN proprias p USING (ano, turno, cd_municipio, zona, secao)
        ),
        bu_set AS (SELECT * FROM proprias UNION SELECT * FROM agregadas),
        cadastro AS (SELECT DISTINCT ano, turno, cd_municipio, zona, secao FROM locais)
        SELECT *, 'so_bu' AS lado FROM (SELECT * FROM bu_set EXCEPT SELECT * FROM cadastro)
        UNION ALL
        SELECT *, 'so_locais' FROM (SELECT * FROM cadastro EXCEPT SELECT * FROM bu_set)
        UNION ALL
        SELECT *, 'agregada_repetida' FROM repetidas
    """).df()
    return {
        "votos_eq_comparecimento": votos,
        "comparecimento_mais_abst_eq_aptos": aptos,
        "secoes_bu_eq_locais": secoes,
        "urnas_nao_apuradas": nao,
    }


# ----------------------------------------------------------------------------- run

def run(bu: pd.DataFrame, locais: pd.DataFrame, con: duckdb.DuckDBPyConnection,
        exceptions: list[dict]) -> list[LayerResult]:
    """Roda as duas implementacoes; o resultado de cada check vem do pandas, e qualquer
    discordancia entre elas vira o check `impl_disagreement` (sem excecao possivel)."""
    a = pandas_impl(bu, locais)
    s = sql_impl(con)
    n_sec = len(bu[SEC].drop_duplicates())
    n_checked = {
        "votos_eq_comparecimento": n_sec,
        "comparecimento_mais_abst_eq_aptos": n_sec,
        "secoes_bu_eq_locais": len(locais[LOC].drop_duplicates()),
        "urnas_nao_apuradas": n_sec,
    }
    results, disagreements = [], []
    for check, key in KEYS.items():
        da, ds = conform(check, a[check]), conform(check, s[check])
        # compare_impls escreve a propria coluna `lado`; renomeia a do check para nao colidir
        ren = {"lado": "lado_check"}
        diff = compare_impls(da.rename(columns=ren), ds.rename(columns=ren),
                             [ren.get(c, c) for c in key])
        if not diff.empty:
            disagreements.append(diff.assign(check_origem=check))
        if check in INFORMATIVE:
            results.append(LayerResult(LAYER, check, True, n_checked[check], da, 0))
        else:
            results.append(make_result(LAYER, check, n_checked[check], da, exceptions))
    dis = pd.concat(disagreements, ignore_index=True) if disagreements else pd.DataFrame(
        columns=["check_origem"])
    results.append(make_result(LAYER, "impl_disagreement", len(KEYS), dis, []))
    return results
