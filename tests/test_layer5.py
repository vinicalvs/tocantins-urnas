"""Camada 5: Censo e ligacoes setor -> local; controle do Censo em Palmas."""
import json

import pandas as pd
import pytest

from tocantins.validate import control, layer5, runner

CW = {"73440": "1721000", "92410": "1702109"}


def setores(rows):
    """rows: (cd_setor, cd_mun_ibge, moradores, sigilo)"""
    return pd.DataFrame(rows, columns=["cd_setor", "cd_mun_ibge", "moradores", "sigilo"])


def municipios(pop):
    return pd.DataFrame([{"cd_mun_ibge": m, "populacao": p} for m, p in pop.items()])


def link(rows, ano=2026, impl="numpy"):
    """rows: (cd_setor, cd_municipio, local_id)"""
    return pd.DataFrame([{"ano": ano, "impl": impl, "cd_setor": s, "cd_municipio": m, "local_id": l, "dist_m": 1.0}
                         for s, m, l in rows])


def cred(rows, ano=2026):
    """rows: (cd_municipio, local_id, eleitores, moradores, especial)"""
    return pd.DataFrame([{"ano": ano, "cd_municipio": m, "local_id": l, "eleitores": e, "moradores": mo,
                          "razao": e / mo if mo else None, "credivel": bool(mo) and 0.4 <= e / mo <= 1.6,
                          "especial": esp, "lat": -10.0, "lon": -48.0} for m, l, e, mo, esp in rows])


def areas(rows, ano=2026):
    return pd.DataFrame([{"ano": ano, "cd_municipio": m, "local_id": l, "area_id": a} for m, l, a in rows])


S = setores([("172100005000001", "1721000", 100, False), ("172100005000002", "1721000", 50, False),
             ("170210905000001", "1702109", 30, False)])
L = link([("172100005000001", "73440", "1-1"), ("172100005000002", "73440", "1-1"),
          ("170210905000001", "92410", "1-1")])
C = cred([("73440", "1-1", 120, 150, False), ("92410", "1-1", 25, 30, False)])
A = areas([("73440", "1-1", "1-1"), ("92410", "1-1", "1-1")])


def test_integridade_counts_and_duplicates():
    assert layer5.integridade(S, n_setores=3, n_mun=2).passed
    r = layer5.integridade(pd.concat([S, S.iloc[[0]]]), n_setores=3, n_mun=2)
    assert not r.passed and "codigo_duplicado" in set(r.divergences["problema"])
    r2 = layer5.integridade(S, n_setores=4117, n_mun=2)
    assert not r2.passed and "n_setores" in set(r2.divergences["problema"])
    bad = S.assign(cd_mun_ibge=["1721000", "1702109", "1702109"])          # codigo do setor nao bate com o municipio
    assert "municipio_do_codigo" in set(layer5.integridade(bad, n_setores=3, n_mun=2).divergences["problema"])


def test_fechamento_flags_difference_and_accepts_sigilo_exception():
    assert layer5.fechamento(S, municipios({"1721000": 150, "1702109": 30}), []).passed
    s = S.assign(sigilo=[False, True, False])
    r = layer5.fechamento(s, municipios({"1721000": 155, "1702109": 30}), [])
    assert not r.passed and r.divergences.iloc[0]["diferenca"] == -5 and r.divergences.iloc[0]["setores_sigilo"] == 1
    exc = [{"layer": "5", "check": "fechamento_municipio", "key": {"cd_mun_ibge": "1721000"},
            "cause": "sigilo de setor pequeno", "approved_on": "2026-11-10"}]
    assert layer5.fechamento(s, municipios({"1721000": 155, "1702109": 30}), exc).passed


def test_impl_disagreement_cannot_be_excepted():
    other = L.assign(impl="geopandas")
    assert layer5.impl_disagreement(pd.concat([L, other])).passed
    other.loc[0, "local_id"] = "1-2"
    exc = [{"layer": "5", "check": "ligacao_impl_disagreement", "key": {"cd_setor": "172100005000001"},
            "cause": "x", "approved_on": "2026-11-10"}]
    r = layer5.impl_disagreement(pd.concat([L, other]), exc)
    assert not r.passed and r.unregistered == 1


def test_consistencia_every_sector_one_local_same_municipality_and_no_special():
    pop = municipios({"1721000": 150, "1702109": 30})
    assert layer5.consistencia(S, L, A, C, CW, pop, []).passed
    sem = L.iloc[1:]                                                       # setor sem ligacao
    assert "setor_sem_ligacao" in set(layer5.consistencia(S, sem, A, C, CW, pop, []).divergences["problema"])
    outro = L.copy(); outro.loc[2, "cd_municipio"] = "73440"               # setor de 1702109 num local de Palmas
    assert "municipio_diferente" in set(layer5.consistencia(S, outro, A, C, CW, pop, []).divergences["problema"])
    esp = C.copy(); esp.loc[0, "especial"] = True
    assert "local_especial_com_setor" in set(layer5.consistencia(S, L, A, esp, CW, pop, []).divergences["problema"])
    sem_area = A.iloc[1:]
    assert "soma_areas" in set(layer5.consistencia(S, L, sem_area, C, CW, pop, []).divergences["problema"])


def test_credibilidade_is_informative_and_resumo():
    r = layer5.credibilidade(C.assign(credivel=[True, False]))
    assert r.passed and r.layer == "5"
    res = layer5.resumo(C.assign(credivel=[True, False]))
    assert res["2026"] == {"locais": 2, "criveis": 1, "pct": 50.0}


def test_coligacoes_prefeitos_missing_party_fails():
    mz = pd.DataFrame([{"ano": 2024, "cargo": "Prefeito", "turno": 1, "cd_municipio": "73440", "zona": 1,
                        "nr_candidato": 10, "nm_candidato": "A", "sg_partido": "MDB", "votos_nominais": 1,
                        "situacao_turno": "ELEITO"}])
    col = pd.DataFrame([{"ano": 2024, "cargo": "Prefeito", "nr_candidato": 10, "sg_partido": "MDB", "partidos": ["MDB"]},
                        {"ano": 2026, "cargo": "Governador", "nr_candidato": 15, "sg_partido": "MDB", "partidos": ["MDB"]}])
    bu = pd.DataFrame([{"ano": 2026, "cargo": "Governador", "turno": 1, "tipo_votavel": "Nominal", "nr_votavel": 15}])
    assert layer5.coligacoes_prefeitos(mz, col, bu, []).passed
    r = layer5.coligacoes_prefeitos(mz.assign(sg_partido=[None]), col, bu, [])
    assert not r.passed and "prefeito_sem_partido" in set(r.divergences["problema"])
    r2 = layer5.coligacoes_prefeitos(mz, col.assign(partidos=[["MDB"], []]), bu, [])
    assert "candidatura_sem_composicao" in set(r2.divergences["problema"])
    r3 = layer5.coligacoes_prefeitos(mz, col.iloc[[1]], bu, [])
    assert "prefeito_fora_da_consulta_cand" in set(r3.divergences["problema"])


def test_palmas_censo_matches_and_never_writes_palmas_dir(tmp_path):
    (tmp_path / "census_regioes.json").write_text(json.dumps({"Centro": {"pop": 100}, "Palmas (total)": {"pop": 150}}),
                                                  encoding="utf-8")
    before = {p.name: p.stat().st_mtime_ns for p in tmp_path.iterdir()}
    r = control.palmas_censo(S, tmp_path)
    assert r.passed and r.layer == "controle" and r.check == "palmas_censo"
    assert not control.palmas_censo(S.assign(moradores=[100, 49, 30]), tmp_path).passed
    assert {p.name: p.stat().st_mtime_ns for p in tmp_path.iterdir()} == before


def test_seal_has_layer5(tmp_path):
    inputs = {"setores": S, "municipios": municipios({"1721000": 150, "1702109": 30}),
              "ligacao": pd.concat([L, L.assign(impl="geopandas")]), "areas": A, "credibilidade": C,
              "crosswalk": CW, "coligacoes": pd.DataFrame(columns=["ano", "cargo", "nr_candidato", "sg_partido", "partidos"]),
              "munzona": pd.DataFrame(columns=["ano", "cargo", "turno", "cd_municipio", "nr_candidato", "nm_candidato", "sg_partido",
                                               "situacao_turno"]),
              "bu": pd.DataFrame(columns=["ano", "cargo", "turno", "tipo_votavel", "nr_votavel"])}
    res = layer5.run(inputs, [], n_setores=3, n_mun=2)
    assert {r.check for r in res} == {"setores_integridade", "fechamento_municipio", "ligacao_impl_disagreement",
                                      "ligacao_consistencia", "ligacao_credibilidade", "coligacoes_prefeitos"}
    seal = runner.write_seal(res, tmp_path / "selo.json", extra={"credibilidade": layer5.resumo(C)})
    assert seal["camadas"]["5"] is True and seal["credibilidade"]["2026"]["locais"] == 2


def test_crosswalk_mapa_base_reads_bu_and_ibge(tmp_path):
    from tocantins import crosswalk
    pd.DataFrame([{"cd_municipio": "73440", "nm_municipio": "PALMAS"}]).to_parquet(tmp_path / "bu_secao.parquet")
    (tmp_path / "ibge").mkdir()
    (tmp_path / "ibge" / "municipios_17.json").write_text(json.dumps([{"id": 1721000, "nome": "Palmas"}]),
                                                          encoding="utf-8")
    assert crosswalk.mapa_base(tmp_path, tmp_path, expected=1) == {"73440": "1721000"}
