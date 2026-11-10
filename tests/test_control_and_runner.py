import json

import pandas as pd
import pytest

from tocantins.validate import control, runner
from tocantins.validate.result import LayerResult


def bu_rows(ano, votos, turno=1, mun="73440"):
    """votos: {(cargo, secao, tipo, nr): qtd}"""
    return [{"ano": ano, "turno": turno, "cd_municipio": mun, "cargo": c, "zona": 29, "secao": s,
             "tipo_votavel": t, "nr_votavel": nr, "votos": v} for (c, s, t, nr), v in votos.items()]


def pkl_rows(votos):
    return pd.DataFrame([{"NR_TURNO": "1", "CD_MUNICIPIO": "73440", "NR_ZONA": "29", "NR_SECAO": str(s),
                          "DS_CARGO_PERGUNTA": c, "DS_TIPO_VOTAVEL": t, "NR_VOTAVEL": str(nr), "QT_VOTOS": v}
                         for (c, s, t, nr), v in votos.items()])


V24 = {("Prefeito", 1, "Nominal", 22): 10, ("Vereador", 1, "Legenda", 22): 2, ("Vereador", 1, "Branco", 95): 1}
V26 = {("Governador", 1, "Nominal", 45): 7}


@pytest.fixture
def palmas_dir(tmp_path):
    pkl_rows(V24).to_pickle(tmp_path / "B24.pkl")
    pkl_rows(V26).to_pickle(tmp_path / "B26.pkl")
    return tmp_path


def base_bu():
    return pd.DataFrame(bu_rows(2024, V24) + bu_rows(2026, V26)
                        + bu_rows(2024, {("Prefeito", 1, "Nominal", 22): 99}, mun="99999")
                        + bu_rows(2024, {("Prefeito", 1, "Nominal", 22): 50}, turno=2))


def test_control_passes_when_equal(palmas_dir):
    r = control.palmas_control(base_bu(), palmas_dir)
    assert r.passed and r.layer == "controle" and r.check == "palmas_turno1"
    assert r.n_checked == 4


def test_control_flags_vote_difference_vs_pickle(palmas_dir):
    bu = base_bu()
    bu.loc[(bu["ano"] == 2026) & (bu["nr_votavel"] == 45), "votos"] = 8
    bu = pd.concat([bu, pd.DataFrame(bu_rows(2024, {("Vereador", 2, "Nominal", 22123): 3}))], ignore_index=True)
    r = control.palmas_control(bu, palmas_dir)
    assert not r.passed
    d = r.divergences.sort_values("ano")
    assert d[["ano", "cargo", "secao", "nr_votavel", "votos_base", "votos_controle"]].values.tolist() == [
        [2024, "Vereador", 2, 22123, 3, 0], [2026, "Governador", 1, 45, 8, 7]]


def test_control_never_writes_palmas_dir(palmas_dir):
    before = {p.name: p.stat().st_mtime_ns for p in palmas_dir.iterdir()}
    control.palmas_control(base_bu(), palmas_dir)
    assert {p.name: p.stat().st_mtime_ns for p in palmas_dir.iterdir()} == before


def test_fora_do_controle_lists_palmas_turno2():
    assert control.fora_do_controle(base_bu()) == ["2024 turno 2"]


def ok(layer, check):
    return LayerResult(layer, check, True, 1, pd.DataFrame(), 0)


def test_seal_status_ok_when_all_pass(tmp_path):
    seal = runner.write_seal([ok("1", "a"), ok("2", "b")], tmp_path / "selo.json")
    assert seal["status"] == "ok" and seal["camadas"] == {"1": True, "2": True}
    assert json.loads((tmp_path / "selo.json").read_text(encoding="utf-8"))["status"] == "ok"


def test_seal_status_falhou_if_any_unregistered_divergence(tmp_path):
    bad = LayerResult("3", "x", False, 5, pd.DataFrame({"k": [1]}), 1)
    seal = runner.write_seal([ok("1", "a"), bad], tmp_path / "selo.json")
    assert seal["status"] == "falhou" and seal["camadas"]["3"] is False
    assert seal["falhas"] == [{"layer": "3", "check": "x", "unregistered": 1}]


def test_seal_lists_used_exceptions_and_hashes(tmp_path):
    div = pd.DataFrame({"zona": [6, 7]})
    r = LayerResult("2", "soma", True, 2, div, 0)
    used = {"layer": "2", "check": "soma", "key": {"zona": 6}, "cause": "c1", "approved_on": "2026-11-10"}
    used2 = {**used, "key": {"zona": 7}, "cause": "c2"}
    unused = {**used, "key": {"zona": 99}, "cause": "c3"}
    manifest = tmp_path / "manifesto.json"
    manifest.write_text(json.dumps({"bu24_t1": {"sha512": "ab" * 64, "url": "u"}}), encoding="utf-8")
    seal = runner.write_seal([r], tmp_path / "selo.json", manifest_path=manifest,
                             exceptions=[used, used2, unused], extra={"fora_do_controle": ["2024 turno 2"]})
    assert [e["cause"] for e in seal["excecoes_usadas"]] == ["c1", "c2"]
    assert [e["cause"] for e in seal["excecoes_nao_usadas"]] == ["c3"]
    assert seal["hashes"] == {"bu24_t1": "ab" * 64}
    assert seal["fora_do_controle"] == ["2024 turno 2"] and seal["data"]
