"""Camada 3: cruzamento do BU com as outras fontes do TSE, em duas implementacoes (pandas e SQL).

Regras comuns (Rulings R25/R26):
- Os checks por candidato/secao/zona comparam so os (ano, turno, cargo) presentes nas duas
  fontes; a falta de um cargo inteiro numa fonte aparece em `cobertura_fontes`.
- Linha ausente num lado conta como 0 voto: candidato com 0 voto listado so na referencia
  nao e divergencia; com votos, e.
"""
import duckdb
import pandas as pd

from tocantins.validate.result import LayerResult, compare_impls, make_result

LAYER = "3"
C = ["ano", "turno", "cargo"]
K_MZ = C + ["cd_municipio", "zona", "nr_votavel"]
K_VS = C + ["cd_municipio", "zona", "secao", "nr_votavel"]
K_DT = C + ["cd_municipio", "zona"]
DT_VALS = ["aptos", "comparecimento", "abstencoes"]
FONTES = ["munzona", "votacao_secao", "detalhe"]
KEYS = {
    "bu_vs_munzona_nominal": K_MZ,
    "bu_vs_votacao_secao": K_VS,
    "bu_vs_detalhe": K_DT,
    "cobertura_fontes": ["fonte"] + C + ["lado"],
}
VALUES = {
    "bu_vs_munzona_nominal": ["votos_bu", "votos_ref"],
    "bu_vs_votacao_secao": ["votos_bu", "votos_ref"],
    "bu_vs_detalhe": [f"{v}_{s}" for v in DT_VALS for s in ("bu", "ref")],
    "cobertura_fontes": [],
}
_STR_COLS = {"cargo", "cd_municipio", "fonte", "lado"}
BU_COLUMNS = ["ano", "turno", "cargo", "cd_municipio", "zona", "secao", "aptos", "comparecimento",
              "abstencoes", "tipo_votavel", "nr_votavel", "votos"]
MUNZONA_COLUMNS = C + ["cd_municipio", "zona", "nr_candidato", "votos_nominais"]
SECAO_COLUMNS = C + ["cd_municipio", "zona", "secao", "nr_votavel", "votos"]
DETALHE_COLUMNS = C + ["cd_municipio", "zona"] + DT_VALS


def conform(check: str, df: pd.DataFrame) -> pd.DataFrame:
    cols = KEYS[check] + VALUES[check]
    out = df[cols].copy()
    for c in cols:
        out[c] = out[c].astype("str" if c in _STR_COLS else "int64")
    return out.sort_values(KEYS[check]).reset_index(drop=True)


# ----------------------------------------------------------------------------- pandas

def _combos(df: pd.DataFrame) -> pd.DataFrame:
    return df[C].drop_duplicates()


def _restrict(df: pd.DataFrame, combos: pd.DataFrame) -> pd.DataFrame:
    return df.merge(combos, on=C, how="inner")


def _pd_compare(bu_side: pd.DataFrame, ref_side: pd.DataFrame, key: list[str],
                vals: list[str]) -> pd.DataFrame:
    """Outer join por chave, ausente = 0, devolve linhas com algum valor diferente."""
    common = _combos(bu_side).merge(_combos(ref_side), on=C)
    m = _restrict(bu_side, common).merge(_restrict(ref_side, common), on=key, how="outer",
                                          suffixes=("_bu", "_ref"))
    out_cols = [f"{v}_{s}" for v in vals for s in ("bu", "ref")]
    m[out_cols] = m[out_cols].fillna(0).astype("int64")
    diff = pd.Series(False, index=m.index)
    for v in vals:
        diff |= m[f"{v}_bu"] != m[f"{v}_ref"]
    return m.loc[diff, key + out_cols]


def pandas_impl(bu: pd.DataFrame, munzona: pd.DataFrame, votacao_secao: pd.DataFrame,
                detalhe: pd.DataFrame) -> dict[str, pd.DataFrame]:
    nom = (bu[bu["tipo_votavel"] == "Nominal"].groupby(K_MZ, as_index=False)["votos"].sum())
    mz = (munzona.rename(columns={"nr_candidato": "nr_votavel", "votos_nominais": "votos"})
          .groupby(K_MZ, as_index=False)["votos"].sum())
    r_mz = _pd_compare(nom, mz, K_MZ, ["votos"])

    bu_vs = bu.groupby(K_VS, as_index=False)["votos"].sum()
    ref_vs = votacao_secao.groupby(K_VS, as_index=False)["votos"].sum()
    r_vs = _pd_compare(bu_vs, ref_vs, K_VS, ["votos"])

    por_secao = bu.groupby(K_DT + ["secao"], as_index=False)[DT_VALS].max()
    bu_dt = por_secao.groupby(K_DT, as_index=False)[DT_VALS].sum()
    ref_dt = detalhe.groupby(K_DT, as_index=False)[DT_VALS].sum()
    r_dt = _pd_compare(bu_dt, ref_dt, K_DT, DT_VALS)

    cob = []
    b = _combos(bu)
    for fonte, df in zip(FONTES, (munzona, votacao_secao, detalhe)):
        m = b.merge(_combos(df), on=C, how="outer", indicator=True)
        m = m[m["_merge"] != "both"]
        m["lado"] = m["_merge"].map({"left_only": "so_bu", "right_only": "so_fonte"}).astype(str)
        cob.append(m[C + ["lado"]].assign(fonte=fonte))
    r_cob = pd.concat(cob, ignore_index=True)

    return {
        "bu_vs_munzona_nominal": r_mz,
        "bu_vs_votacao_secao": r_vs,
        "bu_vs_detalhe": r_dt,
        "cobertura_fontes": r_cob,
    }


# ----------------------------------------------------------------------------- SQL

def sql_impl(con: duckdb.DuckDBPyConnection) -> dict[str, pd.DataFrame]:
    """`con` precisa das views `bu`, `munzona`, `votacao_secao` e `detalhe`."""

    def compare(bu_sql: str, ref_sql: str, key: list[str], vals: list[str]) -> pd.DataFrame:
        k = ", ".join(key)
        using = ", ".join(key)
        sel_key = ", ".join(f"COALESCE(b.{c}, r.{c}) AS {c}" for c in key)
        sel_vals = ", ".join(f"COALESCE(b.{v}, 0)::BIGINT AS {v}_bu, COALESCE(r.{v}, 0)::BIGINT AS {v}_ref"
                             for v in vals)
        cond = " OR ".join(f"COALESCE(b.{v}, 0) <> COALESCE(r.{v}, 0)" for v in vals)
        return con.sql(f"""
            WITH b0 AS ({bu_sql}), r0 AS ({ref_sql}),
            comuns AS (SELECT DISTINCT ano, turno, cargo FROM b0
                       INTERSECT SELECT DISTINCT ano, turno, cargo FROM r0),
            b AS (SELECT * FROM b0 SEMI JOIN comuns USING (ano, turno, cargo)),
            r AS (SELECT * FROM r0 SEMI JOIN comuns USING (ano, turno, cargo))
            SELECT {sel_key}, {sel_vals}
            FROM b FULL OUTER JOIN r USING ({using})
            WHERE {cond}
            ORDER BY {k}
        """).df()

    mz = compare(
        f"SELECT {', '.join(K_MZ)}, SUM(votos) AS votos FROM bu WHERE tipo_votavel = 'Nominal' GROUP BY ALL",
        f"""SELECT ano, turno, cargo, cd_municipio, zona, nr_candidato AS nr_votavel,
                   SUM(votos_nominais) AS votos FROM munzona GROUP BY ALL""",
        K_MZ, ["votos"])
    vs = compare(
        f"SELECT {', '.join(K_VS)}, SUM(votos) AS votos FROM bu GROUP BY ALL",
        f"SELECT {', '.join(K_VS)}, SUM(votos) AS votos FROM votacao_secao GROUP BY ALL",
        K_VS, ["votos"])
    dt = compare(
        """SELECT ano, turno, cargo, cd_municipio, zona, SUM(aptos) AS aptos,
                  SUM(comparecimento) AS comparecimento, SUM(abstencoes) AS abstencoes
           FROM (SELECT ano, turno, cargo, cd_municipio, zona, secao, MAX(aptos) AS aptos,
                        MAX(comparecimento) AS comparecimento, MAX(abstencoes) AS abstencoes
                 FROM bu GROUP BY ALL)
           GROUP BY ALL""",
        """SELECT ano, turno, cargo, cd_municipio, zona, SUM(aptos) AS aptos,
                  SUM(comparecimento) AS comparecimento, SUM(abstencoes) AS abstencoes
           FROM detalhe GROUP BY ALL""",
        K_DT, DT_VALS)
    cob = con.sql(" UNION ALL ".join(f"""
        SELECT '{f}' AS fonte, *, 'so_bu' AS lado FROM
            (SELECT DISTINCT ano, turno, cargo FROM bu EXCEPT SELECT DISTINCT ano, turno, cargo FROM {f})
        UNION ALL
        SELECT '{f}', *, 'so_fonte' FROM
            (SELECT DISTINCT ano, turno, cargo FROM {f} EXCEPT SELECT DISTINCT ano, turno, cargo FROM bu)
    """ for f in FONTES)).df()
    return {"bu_vs_munzona_nominal": mz, "bu_vs_votacao_secao": vs, "bu_vs_detalhe": dt,
            "cobertura_fontes": cob}


# ----------------------------------------------------------------------------- run

def run(bu: pd.DataFrame, munzona: pd.DataFrame, votacao_secao: pd.DataFrame, detalhe: pd.DataFrame,
        con: duckdb.DuckDBPyConnection, exceptions: list[dict]) -> list[LayerResult]:
    """`con` com as views bu, munzona, votacao_secao, detalhe. Resultado de cada check vem do
    pandas; discordancia entre as implementacoes vira `impl_disagreement` (sem excecao)."""
    a = pandas_impl(bu, munzona, votacao_secao, detalhe)
    s = sql_impl(con)
    n_checked = {
        "bu_vs_munzona_nominal": len(munzona),
        "bu_vs_votacao_secao": len(votacao_secao),
        "bu_vs_detalhe": len(detalhe),
        "cobertura_fontes": len(bu[C].drop_duplicates()) * len(FONTES),
    }
    results, disagreements = [], []
    for check, key in KEYS.items():
        da, ds = conform(check, a[check]), conform(check, s[check])
        ren = {"lado": "lado_check"}
        diff = compare_impls(da.rename(columns=ren), ds.rename(columns=ren), [ren.get(c, c) for c in key])
        if not diff.empty:
            disagreements.append(diff.assign(check_origem=check))
        results.append(make_result(LAYER, check, n_checked[check], da, exceptions))
    dis = pd.concat(disagreements, ignore_index=True) if disagreements else pd.DataFrame(
        columns=["check_origem"])
    results.append(make_result(LAYER, "impl_disagreement", len(KEYS), dis, []))
    return results
