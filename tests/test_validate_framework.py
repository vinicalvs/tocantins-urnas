import json

import pandas as pd
import pytest

from tocantins.validate.result import (
    LayerResult, apply_exceptions, compare_impls, load_bu_columns, load_exceptions, write_report,
)


def exc(layer="2", check="soma", key=None, cause="causa investigada", approved_on="2026-11-10"):
    return {"layer": layer, "check": check, "key": key or {}, "cause": cause, "approved_on": approved_on}


@pytest.fixture
def div():
    return pd.DataFrame({"zona": [6, 6, 7], "secao": [12, 13, 13], "dif": [1, 2, 3]})


def test_apply_exceptions_covers_matching_key_only(div):
    left = apply_exceptions(div, "2", "soma", [exc(key={"zona": 6, "secao": 13})])
    assert left[["zona", "secao"]].values.tolist() == [[6, 12], [7, 13]]


def test_apply_exceptions_other_layer_or_check_does_not_cover(div):
    e = exc(key={"zona": 6, "secao": 13})
    assert len(apply_exceptions(div, "3", "soma", [e])) == 3
    assert len(apply_exceptions(div, "2", "outro", [e])) == 3
    assert len(apply_exceptions(div, "2", "soma", [])) == 3


def test_apply_exceptions_key_must_match_all_pairs_and_existing_columns(div):
    assert len(apply_exceptions(div, "2", "soma", [exc(key={"zona": 6, "secao": 99})])) == 3
    assert len(apply_exceptions(div, "2", "soma", [exc(key={"coluna_inexistente": 1})])) == 3


def test_apply_exceptions_rejects_empty_key(div):
    with pytest.raises(ValueError):
        apply_exceptions(div, "2", "soma", [exc(key={})])


def test_apply_exceptions_empty_div_returns_empty():
    empty = pd.DataFrame({"zona": []})
    assert apply_exceptions(empty, "2", "soma", [exc(key={"zona": 1})]).empty


def test_load_exceptions_missing_file_is_empty(tmp_path):
    assert load_exceptions(tmp_path / "nao_existe.json") == []


def test_load_exceptions_reads_and_validates(tmp_path):
    p = tmp_path / "excecoes.json"
    good = exc(key={"zona": 6})
    p.write_text(json.dumps([good]), encoding="utf-8")
    assert load_exceptions(p) == [good]
    for bad in (
        {k: v for k, v in good.items() if k != "approved_on"},   # campo faltando
        {**good, "cause": " "},                                   # causa vazia
        {**good, "key": {}},                                      # chave vazia cobriria tudo
        {**good, "key": "zona=6"},                                # chave nao e dict
    ):
        p.write_text(json.dumps([bad]), encoding="utf-8")
        with pytest.raises(ValueError):
            load_exceptions(p)


def test_compare_impls_flags_asymmetric_rows():
    a = pd.DataFrame({"k": [1, 2, 3], "v": [10, 20, 30]})
    b = pd.DataFrame({"k": [2, 3, 4], "v": [20, 30, 40]})
    out = compare_impls(a, b, ["k"])
    assert sorted(zip(out["k"], out["lado"])) == [(1, "so_a"), (4, "so_b")]


def test_compare_impls_flags_value_differences_and_agrees_when_equal():
    a = pd.DataFrame({"k": [1, 2], "v": [10, 20.0]})
    b = pd.DataFrame({"k": [2, 1], "v": [20.0, 11]})
    out = compare_impls(a, b, ["k"])
    assert out["k"].tolist() == [1] and out["lado"].tolist() == ["valor_diferente"]
    assert out["v_a"].tolist() == [10] and out["v_b"].tolist() == [11]
    assert compare_impls(a, a.copy(), ["k"]).empty


def test_compare_impls_nan_equals_nan_and_rejects_bad_input():
    a = pd.DataFrame({"k": [1], "v": [float("nan")]})
    assert compare_impls(a, a.copy(), ["k"]).empty
    with pytest.raises(ValueError):
        compare_impls(pd.concat([a, a]), a, ["k"])                # chave duplicada
    with pytest.raises(ValueError):
        compare_impls(a, a.rename(columns={"v": "w"}), ["k"])     # colunas diferentes


def test_write_report_writes_json_and_csv_atomically(tmp_path):
    d = pd.DataFrame({"zona": [6], "secao": [13]})
    results = [
        LayerResult("1", "no_duplicates", False, 100, d, 1),
        LayerResult("1", "hash_manifest", True, 4, pd.DataFrame(), 0),
        LayerResult("2", "soma", True, 10, pd.DataFrame(), 0),
    ]
    out = tmp_path / "validacao"
    write_report(results, out)
    c1 = json.loads((out / "camada1.json").read_text(encoding="utf-8"))
    assert c1["layer"] == "1" and c1["passed"] is False
    assert [(c["check"], c["passed"], c["n_checked"], c["n_divergences"], c["unregistered"])
            for c in c1["checks"]] == [("no_duplicates", False, 100, 1, 1), ("hash_manifest", True, 4, 0, 0)]
    assert json.loads((out / "camada2.json").read_text(encoding="utf-8"))["passed"] is True
    assert pd.read_csv(out / "divergencias_no_duplicates.csv").to_dict("records") == [{"zona": 6, "secao": 13}]
    assert (out / "divergencias_hash_manifest.csv").exists()
    assert not list(out.glob("*.tmp"))
    # reescrever substitui (sem restos de uma execucao anterior)
    write_report([LayerResult("1", "no_duplicates", True, 100, pd.DataFrame(), 0)], out)
    assert pd.read_csv(out / "divergencias_no_duplicates.csv").empty


def test_load_bu_columns_projects_only_requested_columns(tmp_path):
    p = tmp_path / "bu.parquet"
    pd.DataFrame({"ano": [2024], "turno": [1], "votos": [5]}).to_parquet(p)
    out = load_bu_columns(p, ["ano", "votos"])
    assert list(out.columns) == ["ano", "votos"] and out["votos"].tolist() == [5]
