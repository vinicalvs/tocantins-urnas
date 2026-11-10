import duckdb
import pandas as pd
import pytest

from tocantins.validate import layer3

BASE = {"ano": 2024, "turno": 1, "cargo": "Vereador", "cd_municipio": "73440"}


def bu_secao(zona, secao, votos, aptos=100, comparecimento=None, cargo="Vereador"):
    """votos: {(tipo, nr): qtd}"""
    comp = comparecimento if comparecimento is not None else sum(votos.values())
    return [{**BASE, "cargo": cargo, "zona": zona, "secao": secao, "aptos": aptos,
             "comparecimento": comp, "abstencoes": aptos - comp, "tipo_votavel": t,
             "nr_votavel": nr, "votos": v} for (t, nr), v in votos.items()]


@pytest.fixture
def fontes():
    bu = pd.DataFrame(
        bu_secao(1, 1, {("Nominal", 10111): 30, ("Nominal", 20222): 20, ("Legenda", 10): 5, ("Branco", 95): 3})
        + bu_secao(1, 2, {("Nominal", 10111): 10, ("Nulo", 96): 2})
        + bu_secao(2, 7, {("Nominal", 20222): 40})
    )
    munzona = pd.DataFrame([
        {**BASE, "zona": 1, "nr_candidato": 10111, "votos_nominais": 40},
        {**BASE, "zona": 1, "nr_candidato": 20222, "votos_nominais": 20},
        {**BASE, "zona": 1, "nr_candidato": 30333, "votos_nominais": 0},   # 0 voto: ausente no BU, ok
        {**BASE, "zona": 2, "nr_candidato": 20222, "votos_nominais": 40},
    ])
    secao = (bu.groupby(["ano", "turno", "cargo", "cd_municipio", "zona", "secao", "nr_votavel"], as_index=False)
             ["votos"].sum())
    detalhe = pd.DataFrame([
        {**BASE, "zona": 1, "aptos": 200, "comparecimento": 70, "abstencoes": 130},
        {**BASE, "zona": 2, "aptos": 100, "comparecimento": 40, "abstencoes": 60},
    ])
    return {"bu": bu, "munzona": munzona, "votacao_secao": secao, "detalhe": detalhe}


def con_for(f):
    con = duckdb.connect()
    for name, df in f.items():
        con.register(name, df)
    return con


def results(f, exceptions=()):
    return {r.check: r for r in layer3.run(f["bu"], f["munzona"], f["votacao_secao"], f["detalhe"],
                                           con_for(f), list(exceptions))}


def test_clean_sources_pass(fontes):
    res = results(fontes)
    assert {"bu_vs_munzona_nominal", "bu_vs_votacao_secao", "bu_vs_detalhe", "cobertura_fontes",
            "impl_disagreement"} <= set(res)
    assert all(r.passed for r in res.values()), {k: r.divergences for k, r in res.items() if not r.passed}


def test_vote_difference_flagged_in_munzona(fontes):
    fontes["munzona"].loc[3, "votos_nominais"] = 41
    d = results(fontes)["bu_vs_munzona_nominal"].divergences
    assert d[["zona", "nr_votavel", "votos_bu", "votos_ref"]].values.tolist() == [[2, 20222, 40, 41]]


def test_vote_difference_flagged_in_votacao_secao(fontes):
    s = fontes["votacao_secao"]
    s.loc[(s["secao"] == 1) & (s["nr_votavel"] == 95), "votos"] = 4
    d = results(fontes)["bu_vs_votacao_secao"].divergences
    assert d[["secao", "nr_votavel", "votos_bu", "votos_ref"]].values.tolist() == [[1, 95, 3, 4]]


def test_difference_flagged_in_detalhe(fontes):
    fontes["detalhe"].loc[0, "comparecimento"] = 71
    r = results(fontes)["bu_vs_detalhe"]
    assert not r.passed
    row = r.divergences.iloc[0]
    assert (row["zona"], row["comparecimento_bu"], row["comparecimento_ref"]) == (1, 70, 71)
    assert (row["aptos_bu"], row["aptos_ref"]) == (200, 200)


def test_candidate_only_in_one_source_flagged(fontes):
    m = fontes["munzona"]
    fontes["munzona"] = pd.concat([m, pd.DataFrame([{**BASE, "zona": 2, "nr_candidato": 99999,
                                                     "votos_nominais": 7}])], ignore_index=True)
    fontes["munzona"] = fontes["munzona"][fontes["munzona"]["nr_candidato"] != 10111]
    d = results(fontes)["bu_vs_munzona_nominal"].divergences
    assert sorted(map(tuple, d[["nr_votavel", "votos_bu", "votos_ref"]].values.tolist())) == [
        (10111, 40, 0), (99999, 0, 7)]


def test_cargo_missing_in_reference_is_flagged_not_silent(fontes):
    extra = pd.DataFrame(bu_secao(1, 1, {("Nominal", 55): 50}, cargo="Prefeito"))
    fontes["bu"] = pd.concat([fontes["bu"], extra], ignore_index=True)
    res = results(fontes)
    cob = res["cobertura_fontes"]
    assert not cob.passed
    assert sorted(cob.divergences["fonte"]) == ["detalhe", "munzona", "votacao_secao"]
    assert set(cob.divergences["cargo"]) == {"Prefeito"}
    # a falta da fonte nao vira milhares de divergencias nos checks por candidato
    assert res["bu_vs_munzona_nominal"].passed and res["bu_vs_votacao_secao"].passed


def test_exception_registered_with_cause_clears_divergence(fontes):
    fontes["munzona"].loc[3, "votos_nominais"] = 41
    exc = [{"layer": "3", "check": "bu_vs_munzona_nominal",
            "key": {"cd_municipio": "73440", "zona": 2, "nr_votavel": 20222},
            "cause": "voto anulado e apurado em separado", "approved_on": "2026-11-10"}]
    r = results(fontes, exc)["bu_vs_munzona_nominal"]
    assert r.passed and r.unregistered == 0 and len(r.divergences) == 1


def test_impls_agree_and_disagreement_fails(fontes, monkeypatch):
    faulty = {k: v.copy() for k, v in fontes.items()}
    faulty["munzona"].loc[0, "votos_nominais"] = 1
    faulty["detalhe"].loc[1, "aptos"] = 1
    faulty["votacao_secao"] = faulty["votacao_secao"].iloc[1:]
    for f in (fontes, faulty):
        a = layer3.pandas_impl(f["bu"], f["munzona"], f["votacao_secao"], f["detalhe"])
        s = layer3.sql_impl(con_for(f))
        assert set(a) == set(s) == set(layer3.KEYS)
        for check in layer3.KEYS:
            assert layer3.conform(check, a[check]).equals(layer3.conform(check, s[check])), check

    real = layer3.sql_impl

    def broken(con):
        out = real(con)
        out["bu_vs_detalhe"] = out["bu_vs_detalhe"].iloc[0:0]
        return out

    monkeypatch.setattr(layer3, "sql_impl", broken)
    r = results(faulty)["impl_disagreement"]
    assert not r.passed and set(r.divergences["check_origem"]) == {"bu_vs_detalhe"}
