"""Ligacao setor -> local de votacao (duas implementacoes), credibilidade e areas de votacao."""
import pandas as pd
import pytest

from tocantins import ligacao as lg

CW = {"73440": "1721000", "92410": "1702109"}


def loc(ano, mun, zona, secao, local, nome, lat, lon, eleit, turno=1):
    return {"ano": ano, "turno": turno, "cd_municipio": mun, "zona": zona, "secao": secao, "local": local,
            "nm_local": nome, "bairro": "B", "lat": lat, "lon": lon, "eleitores_secao": eleit}


def setores(rows):
    """rows: (cd_setor, cd_mun_ibge, cx, cy, moradores)"""
    return pd.DataFrame(rows, columns=["cd_setor", "cd_mun_ibge", "cx", "cy", "moradores"])


def locais_xy(rows):
    """rows: (id, cd_municipio, x, y, eleitores, especial)"""
    d = pd.DataFrame(rows, columns=["id", "cd_municipio", "x", "y", "eleitores", "especial"])
    d["cd_mun_ibge"] = d["cd_municipio"].map(CW)
    return d


IMPLS = [lg.link_numpy, lg.link_geopandas]


def test_locais_ano_aggregates_sections_and_flags_special():
    raw = pd.DataFrame([
        loc(2026, "73440", 29, 1, 1104, "ESCOLA A", -10.18, -48.33, 300),
        loc(2026, "73440", 29, 2, 1104, "ESCOLA A", -10.18, -48.33, 200),
        loc(2026, "73440", 29, 3, 1200, "ESCOLA B - VOTO EM TRÂNSITO", -10.19, -48.33, 50),
        loc(2026, "73440", 29, 4, 1300, "UNIDADE PRISIONAL", -10.2, -48.3, 10),
        loc(2026, "73440", 29, 5, 1400, "ESCOLA VAZIA", -10.21, -48.3, 0),
        loc(2024, "73440", 29, 1, 1104, "ESCOLA A", -10.18, -48.33, 999),
    ])
    d = lg.locais_ano(raw, 2026, CW).set_index("id")
    assert d.loc["29-1104", "eleitores"] == 500 and not d.loc["29-1104", "especial"]
    assert d.loc["29-1200", "especial"] and d.loc["29-1300", "especial"] and d.loc["29-1400", "especial"]
    assert d.loc["29-1104", "cd_mun_ibge"] == "1721000" and d.loc["29-1104", "x"] > 0


def test_locais_ano_coords_from_one_complete_row():
    raw = pd.DataFrame([
        loc(2026, "73440", 29, 1, 1104, "A", None, -48.33, 300),
        loc(2026, "73440", 29, 2, 1104, "A", -10.18, -48.30, 200),
    ])
    d = lg.locais_ano(raw, 2026, CW).iloc[0]
    assert (d["lat"], d["lon"]) == (-10.18, -48.30)


@pytest.mark.parametrize("impl", IMPLS)
def test_links_to_nearest_same_municipality(impl):
    s = setores([("S1", "1721000", 0, 0, 100)])
    l = locais_xy([("29-1", "73440", 1000, 0, 80, False), ("1-9", "92410", 10, 0, 80, False)])
    assert impl(s, l)["local_id"].tolist() == ["29-1"]


@pytest.mark.parametrize("impl", IMPLS)
def test_special_local_receives_no_sectors(impl):
    s = setores([("S1", "1721000", 0, 0, 100)])
    l = locais_xy([("29-1", "73440", 10, 0, 80, True), ("29-2", "73440", 500, 0, 80, False)])
    assert impl(s, l)["local_id"].tolist() == ["29-2"]


@pytest.mark.parametrize("impl", IMPLS)
def test_tie_breaks_by_smallest_local_id(impl):
    s = setores([("S1", "1721000", 0, 0, 100)])
    l = locais_xy([("29-2", "73440", 10, 0, 80, False), ("29-10", "73440", -10, 0, 80, False)])
    assert impl(s, l)["local_id"].tolist() == ["29-10"]          # ordem de texto: "29-10" < "29-2"


@pytest.mark.parametrize("impl", IMPLS)
def test_local_without_coords_not_linked(impl):
    s = setores([("S1", "1721000", 0, 0, 100)])
    l = locais_xy([("29-1", "73440", None, None, 80, False), ("29-2", "73440", 900, 0, 80, False)])
    assert impl(s, l)["local_id"].tolist() == ["29-2"]


def test_impls_agree_and_report_distance():
    s = setores([(f"S{i}", "1721000", i * 37.0, (i * 53) % 101, 10) for i in range(30)])
    l = locais_xy([(f"29-{j}", "73440", j * 120.0, (j * 7) % 50, 80, False) for j in range(8)])
    a, b = lg.link_numpy(s, l), lg.link_geopandas(s, l)
    assert a.sort_values("cd_setor")["local_id"].tolist() == b.sort_values("cd_setor")["local_id"].tolist()
    assert (a["dist_m"] >= 0).all()


def test_zero_population_sector_linked_but_not_weighted():
    s = setores([("S1", "1721000", 0, 0, 0), ("S2", "1721000", 1, 0, 100)])
    l = locais_xy([("29-1", "73440", 0, 0, 80, False)])
    link = lg.link_numpy(s, l)
    assert sorted(link["cd_setor"]) == ["S1", "S2"]
    c = lg.credibilidade(link, s, l).set_index("local_id")
    assert c.loc["29-1", "moradores"] == 100 and c.loc["29-1", "razao"] == pytest.approx(0.8)


@pytest.mark.parametrize("eleit,ok", [(40, True), (160, True), (39, False), (161, False)])
def test_credibilidade_range_inclusive(eleit, ok):
    s = setores([("S1", "1721000", 0, 0, 100)])
    l = locais_xy([("29-1", "73440", 0, 0, eleit, False)])
    assert bool(lg.credibilidade(lg.link_numpy(s, l), s, l).iloc[0]["credivel"]) is ok


def test_areas_merge_until_in_range():
    # razoes 0,2 / 1,0 / 3,0
    s = setores([("S1", "1721000", 0, 0, 500), ("S2", "1721000", 1000, 0, 100), ("S3", "1721000", 2000, 0, 100)])
    l = locais_xy([("29-1", "73440", 0, 0, 100, False), ("29-2", "73440", 1000, 0, 100, False),
                   ("29-3", "73440", 2000, 0, 300, False)])
    a = lg.areas(lg.link_numpy(s, l), s, l)
    tot = a.merge(lg.credibilidade(lg.link_numpy(s, l), s, l), on="local_id").groupby("area_id")[
        ["eleitores", "moradores"]].sum()
    r = tot["eleitores"] / tot["moradores"]
    assert ((r >= 0.4) & (r <= 1.6)).all() or len(tot) == 1


def test_single_local_municipality_is_one_area():
    s = setores([("S1", "1721000", 0, 0, 1000)])
    l = locais_xy([("29-1", "73440", 0, 0, 100, False)])           # razao 0,1: fora da faixa, mas sozinho
    a = lg.areas(lg.link_numpy(s, l), s, l)
    assert a[["local_id", "area_id"]].values.tolist() == [["29-1", "29-1"]]


def test_areas_deterministic():
    s = setores([(f"S{i}", "1721000", i * 300.0, 0, 50 + i * 40) for i in range(12)])
    l = locais_xy([(f"29-{j}", "73440", j * 900.0, 0, 30 + j * 25, False) for j in range(5)])
    link = lg.link_numpy(s, l)
    assert lg.areas(link, s, l).equals(lg.areas(link, s, l))


def test_same_zona_local_in_two_municipalities_kept_apart():
    # o numero do local so e unico dentro do municipio: a zona 13 cobre varios municipios
    raw = pd.DataFrame([
        loc(2026, "73440", 13, 1, 1015, "ESCOLA PALMAS", -10.18, -48.33, 300),
        loc(2026, "92410", 13, 2, 1015, "ESCOLA OUTRA", -10.44, -49.17, 200),
    ])
    d = lg.locais_ano(raw, 2026, CW)
    assert len(d) == 2 and set(d["cd_mun_ibge"]) == {"1721000", "1702109"}
    s = setores([("S1", "1721000", d["x"].iloc[0], d["y"].iloc[0], 400),
                 ("S2", "1702109", d["x"].iloc[1], d["y"].iloc[1], 250)])
    for impl in IMPLS:
        link = impl(s, d)
        assert sorted(link["cd_setor"]) == ["S1", "S2"]
        c = lg.credibilidade(link, s, d).set_index("cd_municipio")
        assert c.loc["73440", "moradores"] == 400 and c.loc["92410", "moradores"] == 250
    a = lg.areas(lg.link_numpy(s, d), s, d)
    assert sorted(a["cd_municipio"]) == ["73440", "92410"]
