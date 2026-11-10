"""Censo 2022 por setor (leitura em blocos, indicadores) e IBGE municipal (SIDRA)."""
import json
import math

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import Polygon

from tocantins import censo


def _csv(path, first, rows, cols):
    head = ";".join(f'"{c}"' for c in [first] + cols)
    body = "\n".join(";".join(f'"{v}"' for v in r) for r in rows)
    path.write_bytes((head + "\n" + body + "\n").encode("latin1"))
    return path


def test_read_setores_filters_uf_in_chunks(tmp_path):
    p = _csv(tmp_path / "a.csv", "CD_setor",
             [["170025105000001", "1"], ["520010805000001", "2"], ["170025105000002", "3"],
              ["520010805000002", "4"], ["172100005000001", "5"]], ["V01006"])
    d = censo.read_setores(p, ["V01006"], chunksize=2)
    assert list(d.index) == ["170025105000001", "170025105000002", "172100005000001"]
    assert d["V01006"].tolist() == [1.0, 3.0, 5.0]


def test_read_setores_marks_suppressed_X_as_nan_and_sigilo(tmp_path):
    p = _csv(tmp_path / "a.csv", "setor", [["170025105000001", "X", "2"], ["170025105000002", "1", ""]],
             ["V00001", "V00002"])
    d = censo.read_setores(p, ["V00001", "V00002"])
    assert math.isnan(d.loc["170025105000001", "V00001"]) and d.loc["170025105000001", "sigilo"]
    assert math.isnan(d.loc["170025105000002", "V00002"]) and d.loc["170025105000002", "sigilo"]


def test_read_setores_normalizes_code_with_punctuation(tmp_path):
    p = _csv(tmp_path / "a.csv", "CD_SETOR", [["1700251.05.000001", "7"]], ["v0001"])
    d = censo.read_setores(p, ["V0001"])
    assert list(d.index) == ["170025105000001"] and d["V0001"].tolist() == [7.0]


def test_read_setores_decimal_comma(tmp_path):
    p = _csv(tmp_path / "a.csv", "CD_SETOR", [["170025105000001", "0,25"]], ["AREA_KM2"])
    assert censo.read_setores(p, ["AREA_KM2"])["AREA_KM2"].tolist() == [0.25]


def test_indicator_pairs_keep_numerator_and_denominator():
    raw = pd.DataFrame({f"V00{i}": [0.0] for i in range(644, 657)} | {f"V00{i}": [0.0] for i in range(748, 761)},
                       index=["170025105000001"])
    raw["V00644"], raw["V00645"] = 60.0, 40.0
    raw["V00748"], raw["V00749"] = 50.0, 30.0
    out = censo.indicadores(raw)
    assert out.loc["170025105000001", "alfabetizacao_15_num"] == 80
    assert out.loc["170025105000001", "alfabetizacao_15_den"] == 100


def test_indicadores_have_all_spec_pairs():
    assert set(censo.INDICADORES) == {"alfabetizacao_15", "idade_0_14", "idade_15_29", "idade_60", "pretos_pardos",
                                      "agua_rede", "esgoto_rede", "lixo_coletado"}


def test_centroids_are_metric(tmp_path):
    # quadrado de 0,01 grau em torno de (-48.30, -10.20) em SIRGAS 2000 geografico
    sq = Polygon([(-48.305, -10.205), (-48.295, -10.205), (-48.295, -10.195), (-48.305, -10.195)])
    g = gpd.GeoDataFrame({"CD_SETOR": ["172100005000001"], "CD_MUN": ["1721000"], "AREA_KM2": ["1,2"]},
                         geometry=[sq], crs=4674)
    c = censo.centroides(g)
    ref = gpd.GeoSeries.from_xy([-48.30], [-10.20], crs=4674).to_crs(31982).iloc[0]
    assert abs(c.loc["172100005000001", "cx"] - ref.x) < 1 and abs(c.loc["172100005000001", "cy"] - ref.y) < 1
    assert c.loc["172100005000001", "cd_mun_ibge"] == "1721000"
    assert c.loc["172100005000001", "area_km2"] == pytest.approx(1.2)


def _sidra(path, rows):
    head = {"NC": "Nível", "V": "Valor", "D1C": "Município (Código)", "D2C": "Variável (Código)", "D3C": "Ano"}
    path.write_text(json.dumps([head] + [{"NC": "6", "V": v, "D1C": m, "D2C": var, "D3C": "2022"}
                                         for m, var, v in rows]), encoding="utf-8")


def test_build_municipios_parses_sidra_json(tmp_path):
    _sidra(tmp_path / "4714_pop_area_2022.json",
           [("1721000", "93", "302692"), ("1721000", "6318", "2227,329"), ("1721000", "614", "135,9")])
    _sidra(tmp_path / "5938_pib_2022.json", [("1721000", "37", "13000000")])
    m = censo.build_municipios(tmp_path).set_index("cd_mun_ibge")
    assert m.loc["1721000", "populacao"] == 302692
    assert m.loc["1721000", "area_km2"] == pytest.approx(2227.329)
    assert m.loc["1721000", "densidade"] == pytest.approx(135.9)
    assert m.loc["1721000", "pib_per_capita"] == pytest.approx(13_000_000_000 / 302692)
    assert m.loc["1721000", "ano_pib"] == 2022


def test_centroides_merges_sector_split_in_two_polygons():
    a = Polygon([(-48.30, -10.20), (-48.29, -10.20), (-48.29, -10.19), (-48.30, -10.19)])
    b = Polygon([(-48.28, -10.20), (-48.27, -10.20), (-48.27, -10.19), (-48.28, -10.19)])
    g = gpd.GeoDataFrame({"CD_SETOR": ["170190305000016", "170190305000016"], "CD_MUN": ["1701903"] * 2,
                          "AREA_KM2": ["2,0", "2,0"]}, geometry=[a, b], crs=4674)
    c = censo.centroides(g)
    assert list(c.index) == ["170190305000016"]
    ref = gpd.GeoSeries.from_xy([-48.285], [-10.195], crs=4674).to_crs(31982).iloc[0]
    assert abs(c.iloc[0]["cx"] - ref.x) < 5
