import duckdb
import pandas as pd
import pytest

from tocantins.validate import layer2


def secao(secao, zona=1, mun="73440", ano=2024, turno=1, cd_cargo=11, cargo="Prefeito",
          aptos=100, comparecimento=80, votos=(50, 20, 10), cd_tipo_urna=1, agregadas=None):
    """Linhas do BU de uma secao: votos para 2 candidatos e brancos."""
    tipos = [("Nominal", 10), ("Nominal", 20), ("Branco", 95)]
    return [{
        "ano": ano, "turno": turno, "cd_cargo": cd_cargo, "cargo": cargo, "cd_municipio": mun,
        "zona": zona, "secao": secao, "aptos": aptos, "comparecimento": comparecimento,
        "abstencoes": aptos - comparecimento, "cd_tipo_urna": cd_tipo_urna,
        "tipo_votavel": t, "nr_votavel": nr, "votos": v, "secoes_agregadas": agregadas,
    } for (t, nr), v in zip(tipos, votos)]


def locais_de(bu, extra=()):
    s = bu[["ano", "turno", "cd_municipio", "zona", "secao"]].drop_duplicates()
    extra = pd.DataFrame(list(extra), columns=s.columns)
    return pd.concat([s, extra], ignore_index=True)


def con_for(bu, locais):
    con = duckdb.connect()
    con.register("bu", bu)
    con.register("locais", locais)
    return con


def results(bu, locais, exceptions=()):
    return {r.check: r for r in layer2.run(bu, locais, con_for(bu, locais), list(exceptions))}


@pytest.fixture
def clean():
    bu = pd.DataFrame(secao(1) + secao(2) + secao(1, zona=2))
    return bu, locais_de(bu)


def test_clean_data_passes(clean):
    res = results(*clean)
    assert {"votos_eq_comparecimento", "comparecimento_mais_abst_eq_aptos", "secoes_bu_eq_locais",
            "urnas_nao_apuradas", "impl_disagreement"} <= set(res)
    assert all(r.passed for r in res.values())


def test_votos_ne_comparecimento_is_flagged_in_both_impls(clean):
    bu, locais = clean
    bu.loc[(bu["secao"] == 2) & (bu["nr_votavel"] == 10), "votos"] -= 1
    con = con_for(bu, locais)
    for impl in (layer2.pandas_impl(bu, locais), layer2.sql_impl(con)):
        d = impl["votos_eq_comparecimento"]
        assert d[["secao", "votos_total", "comparecimento"]].values.tolist() == [[2, 79, 80]]
    r = results(bu, locais)
    assert not r["votos_eq_comparecimento"].passed and r["impl_disagreement"].passed


def test_comparecimento_mais_abstencao_ne_aptos_flagged(clean):
    bu, locais = clean
    bu.loc[bu["secao"] == 2, "abstencoes"] = 25
    r = results(bu, locais)["comparecimento_mais_abst_eq_aptos"]
    assert not r.passed
    assert r.divergences[["secao", "aptos", "soma"]].values.tolist() == [[2, 100, 105]]


def test_senador_2026_two_votes_per_voter():
    bu = pd.DataFrame(secao(1, ano=2026, cd_cargo=5, cargo="Senador", comparecimento=40, aptos=50))
    res = results(bu, locais_de(bu))
    assert res["votos_eq_comparecimento"].passed
    bu1 = pd.DataFrame(secao(1, ano=2026, cd_cargo=3, cargo="Governador", comparecimento=40, aptos=50))
    assert not results(bu1, locais_de(bu1))["votos_eq_comparecimento"].passed


def test_nao_apurada_urn_is_reported_not_failed(clean):
    bu, _ = clean
    bu = pd.concat([bu, pd.DataFrame(secao(3, cd_tipo_urna=2, votos=(1, 0, 0)))], ignore_index=True)
    res = results(bu, locais_de(bu))
    assert res["votos_eq_comparecimento"].passed
    assert res["comparecimento_mais_abst_eq_aptos"].passed
    nao = res["urnas_nao_apuradas"]
    assert nao.passed and nao.divergences["secao"].tolist() == [3]


def test_aggregated_sections_not_double_counted():
    bu = pd.DataFrame(secao(1, agregadas="10 / 114") + secao(2))
    locais = locais_de(bu, extra=[(2024, 1, "73440", 1, 10), (2024, 1, "73440", 1, 114)])
    res = results(bu, locais)
    assert res["secoes_bu_eq_locais"].passed, res["secoes_bu_eq_locais"].divergences
    assert res["votos_eq_comparecimento"].passed
    # sem a agregacao, 10 e 114 aparecem so no cadastro
    bu2 = pd.DataFrame(secao(1) + secao(2))
    d = results(bu2, locais)["secoes_bu_eq_locais"].divergences
    assert sorted(zip(d["secao"], d["lado"])) == [(10, "so_locais"), (114, "so_locais")]


def test_aggregated_section_also_reported_as_own_section_is_flagged():
    bu = pd.DataFrame(secao(1, agregadas="2") + secao(2))
    d = results(bu, locais_de(bu))["secoes_bu_eq_locais"].divergences
    assert d[["secao", "lado"]].values.tolist() == [[2, "agregada_repetida"]]


def test_secoes_bu_eq_locais_flags_section_missing_in_cadastro(clean):
    bu, locais = clean
    locais = locais[locais["secao"] != 2]
    r = results(bu, locais)["secoes_bu_eq_locais"]
    assert not r.passed
    assert r.divergences[["secao", "lado"]].values.tolist() == [[2, "so_bu"]]


def test_impls_agree_on_clean_and_faulty_data(clean):
    bu, locais = clean
    faulty = bu.copy()
    faulty.loc[faulty["secao"] == 1, "votos"] += 3
    faulty.loc[faulty["secao"] == 2, "abstencoes"] = 0
    faulty = pd.concat([faulty, pd.DataFrame(secao(7, cd_tipo_urna=3))], ignore_index=True)
    for b in (bu, faulty):
        a = layer2.pandas_impl(b, locais)
        s = layer2.sql_impl(con_for(b, locais))
        assert set(a) == set(s)
        for check in layer2.KEYS:
            assert layer2.conform(check, a[check]).equals(layer2.conform(check, s[check])), check


def test_impl_disagreement_detected_when_one_impl_is_broken(clean, monkeypatch):
    bu, locais = clean
    real = layer2.sql_impl

    def broken(con):
        out = real(con)
        out["votos_eq_comparecimento"] = pd.DataFrame([{
            "ano": 2024, "turno": 1, "cargo": "Prefeito", "cd_municipio": "73440", "zona": 1,
            "secao": 1, "votos_total": 1, "comparecimento": 80}])
        return out

    monkeypatch.setattr(layer2, "sql_impl", broken)
    r = results(bu, locais)["impl_disagreement"]
    assert not r.passed
    assert r.divergences["check_origem"].tolist() == ["votos_eq_comparecimento"]
