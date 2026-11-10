import hashlib
import json
import zipfile

import pandas as pd
import pytest

from tocantins.validate import layer1

MUNIS = [str(73000 + i) for i in range(139)]
CARGOS = {2024: {11}}


def bu_rows(ano=2024, turno=1, cd_cargo=11, munis=MUNIS, aptos=1000, votos=(60, 40)):
    """Uma secao por municipio, dois candidatos nominais (10 e 20)."""
    rows = []
    for m in munis:
        for nr, v in zip((10, 20), votos):
            rows.append({
                "ano": ano, "turno": turno, "cd_cargo": cd_cargo, "cd_municipio": m,
                "zona": 1, "secao": 1, "aptos": aptos, "tipo_votavel": "Nominal",
                "nr_votavel": nr, "votos": v,
            })
    return pd.DataFrame(rows)


def make_zip(path, n_rows):
    lines = ["A;B"] + [f'"{i}";"x"' for i in range(n_rows)]
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(path.stem + ".csv", "\n".join(lines) + "\n")
        zf.writestr("_leiame.pdf", "pdf")


def make_manifest(tmp_path, entries):
    """entries: {key: (n_csv_rows, published_override)}"""
    manifest = {}
    for key, (n, published) in entries.items():
        z = tmp_path / f"{key}.zip"
        make_zip(z, n)
        digest = hashlib.sha512(z.read_bytes()).hexdigest()
        manifest[key] = {
            "key": key, "url": "u", "path": str(z), "size": z.stat().st_size,
            "sha512": digest, "published_sha512": digest if published is None else published,
            "downloaded_at": "2026-11-10T00:00:00+00:00",
        }
    p = tmp_path / "manifesto.json"
    p.write_text(json.dumps(manifest), encoding="utf-8")
    return p


def by_check(results):
    return {r.check: r for r in results}


@pytest.fixture
def clean_bu():
    return bu_rows()


@pytest.fixture
def manifest(tmp_path, clean_bu):
    return make_manifest(tmp_path, {"bu24_t1": (len(clean_bu), None)})


def run(manifest, bu, **kw):
    kw.setdefault("expected_cargos", CARGOS)
    return by_check(layer1.run(manifest, bu, **kw))


def test_layer1_clean_data_passes_all_checks(manifest, clean_bu):
    res = run(manifest, clean_bu)
    assert set(res) >= {"hash_manifest", "row_counts", "municipios_139", "no_duplicates", "t2_subset_of_t1"}
    assert all(r.passed for r in res.values()), {k: r.divergences for k, r in res.items() if not r.passed}


def test_layer1_flags_duplicate_section_rows(tmp_path, clean_bu):
    bu = pd.concat([clean_bu, clean_bu.iloc[[0]]], ignore_index=True)
    m = make_manifest(tmp_path, {"bu24_t1": (len(bu), None)})
    r = run(m, bu)["no_duplicates"]
    assert not r.passed and r.unregistered == 1
    assert r.divergences[["cd_municipio", "nr_votavel"]].values.tolist() == [[MUNIS[0], 10]]


def test_layer1_flags_missing_municipio(tmp_path):
    bu = bu_rows(munis=MUNIS[:138])
    m = make_manifest(tmp_path, {"bu24_t1": (len(bu), None)})
    r = run(m, bu)["municipios_139"]
    assert not r.passed
    assert r.divergences["n_municipios"].tolist() == [138]


def test_layer1_flags_missing_expected_cargo(manifest, clean_bu):
    r = run(manifest, clean_bu, expected_cargos={2024: {11, 13}})["municipios_139"]
    assert not r.passed and 13 in r.divergences["cd_cargo"].tolist()


def test_layer1_t2_subset(tmp_path):
    # municipio grande (> 200 mil aptos) mas candidato com 60% dos validos no T1: T2 indevido
    t1 = bu_rows(aptos=250_000)
    t2 = bu_rows(turno=2, munis=[MUNIS[0]], aptos=250_000)
    bu = pd.concat([t1, t2], ignore_index=True)
    m = make_manifest(tmp_path, {"bu24_t1": (len(t1), None), "bu24_t2": (len(t2), None)})
    r = run(m, bu)["t2_subset_of_t1"]
    assert not r.passed
    assert r.divergences["cd_municipio"].tolist() == [MUNIS[0]]


def test_layer1_t2_allowed_when_required_and_small_city_flagged(tmp_path):
    # MUNIS[0]: 250 mil aptos, ninguem com maioria -> T2 exigido e presente: ok
    # MUNIS[1]: sem maioria mas 1000 aptos -> T2 indevido
    t1 = bu_rows(votos=(50, 50))
    t1.loc[t1["cd_municipio"] == MUNIS[0], "aptos"] = 250_000
    t2 = bu_rows(turno=2, munis=MUNIS[:2])
    bu = pd.concat([t1, t2], ignore_index=True)
    m = make_manifest(tmp_path, {"bu24_t1": (len(t1), None), "bu24_t2": (len(t2), None)})
    r = run(m, bu)["t2_subset_of_t1"]
    assert r.divergences["cd_municipio"].tolist() == [MUNIS[1]]


def test_layer1_t2_missing_where_required_is_flagged(tmp_path):
    t1 = bu_rows(votos=(50, 50))
    t1.loc[t1["cd_municipio"] == MUNIS[0], "aptos"] = 250_000
    m = make_manifest(tmp_path, {"bu24_t1": (len(t1), None)})
    r = run(m, t1)["t2_subset_of_t1"]
    assert not r.passed and r.divergences["motivo"].tolist() == ["t2_ausente"]


def test_layer1_hash_manifest_fails_when_published_and_computed_differ(tmp_path, clean_bu):
    m = make_manifest(tmp_path, {"bu24_t1": (len(clean_bu), "ab" * 64)})
    r = run(m, clean_bu)["hash_manifest"]
    assert not r.passed and r.divergences["key"].tolist() == ["bu24_t1"]


def test_layer1_hash_manifest_fails_when_file_changed(manifest, clean_bu):
    entry = json.loads(manifest.read_text(encoding="utf-8"))["bu24_t1"]
    with open(entry["path"], "ab") as f:
        f.write(b"x")
    r = run(manifest, clean_bu)["hash_manifest"]
    assert not r.passed


def test_layer1_row_counts_flags_lost_rows(tmp_path, clean_bu):
    m = make_manifest(tmp_path, {"bu24_t1": (len(clean_bu) + 5, None)})
    r = run(m, clean_bu)["row_counts"]
    assert not r.passed
    assert r.divergences[["linhas_csv", "linhas_base"]].values.tolist() == [[len(clean_bu) + 5, len(clean_bu)]]


def test_layer1_exception_covers_divergence(tmp_path):
    bu = bu_rows(munis=MUNIS[:138])
    m = make_manifest(tmp_path, {"bu24_t1": (len(bu), None)})
    exc = [{"layer": "1", "check": "municipios_139", "key": {"ano": 2024, "turno": 1, "cd_cargo": 11},
            "cause": "teste", "approved_on": "2026-11-10"}]
    r = run(m, bu, exceptions=exc)["municipios_139"]
    assert r.passed and r.unregistered == 0 and len(r.divergences) == 1


def test_layer1_exclusoes_must_be_registered(manifest, clean_bu, tmp_path):
    excl = tmp_path / "exclusoes.json"
    excl.write_text(json.dumps([{"source": "locais", "reason": "SG_UF diferente de TO", "n_rows": 9}]),
                    encoding="utf-8")
    r = run(manifest, clean_bu, exclusoes_path=excl)["exclusoes_registradas"]
    assert not r.passed and r.divergences["source"].tolist() == ["locais"]
    exc = [{"layer": "1", "check": "exclusoes_registradas",
            "key": {"source": "locais", "reason": "SG_UF diferente de TO"},
            "cause": "base so do Tocantins", "approved_on": "2026-11-10"}]
    assert run(manifest, clean_bu, exclusoes_path=excl, exceptions=exc)["exclusoes_registradas"].passed
