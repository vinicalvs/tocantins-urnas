"""Censo 2022 por setor censitario (TO) e indicadores municipais do IBGE (SIDRA).

Arquivos nacionais lidos em blocos, so colunas usadas, filtrando setores do Tocantins (codigo 17...).
Variaveis: docs/fontes.md secao 6.1.
"""
import json
from pathlib import Path

import pandas as pd

UF_TO = "17"
CRS_METRICO = 31982  # SIRGAS 2000 / UTM 22S


def _v(a: int, b: int, width: int = 5) -> list[str]:
    return [f"V{i:0{width}d}" for i in range(a, b + 1)]


# indicador -> (colunas do numerador, colunas do denominador)
INDICADORES: dict[str, tuple[list[str], list[str]]] = {
    "alfabetizacao_15": (_v(748, 760), _v(644, 656)),
    "idade_0_14": (_v(1031, 1033), ["V01006"]),
    "idade_15_29": (_v(1034, 1036), ["V01006"]),
    "idade_60": (_v(1040, 1041), ["V01006"]),
    "pretos_pardos": (["V01318", "V01320"], _v(1317, 1321)),
    "agua_rede": (["V00111"], _v(111, 118)),
    "esgoto_rede": (_v(309, 310), _v(309, 316)),
    "lixo_coletado": (_v(397, 398), _v(397, 402)),
}

# arquivo (chave em SOURCES, sem o prefixo censo_) -> colunas lidas
ARQUIVOS: dict[str, list[str]] = {
    "basico": ["V0001", "V0007"],
    "demografia": ["V01006"] + _v(1031, 1041),
    "alfabetizacao": _v(644, 656) + _v(748, 760),
    "cor_raca": _v(1317, 1321),
    "domicilio2": _v(111, 118) + _v(309, 316) + _v(397, 402),
}


def _code(s: pd.Series) -> pd.Series:
    return s.astype(str).str.replace(r"\D", "", regex=True).str[:15]


def _num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s.astype(str).str.strip().str.replace(",", ".", regex=False), errors="coerce")


def read_setores(csv: Path, cols: list[str], uf_prefix: str = UF_TO, chunksize: int = 200_000) -> pd.DataFrame:
    """Le `cols` (nomes sem diferenciar caixa) de um CSV nacional do IBGE, so setores da UF.

    A 1a coluna e o codigo do setor (o nome varia: CD_SETOR, CD_setor, setor). `X` e vazio viram NaN e
    marcam `sigilo=True`.
    """
    header = pd.read_csv(csv, sep=";", encoding="latin1", dtype=str, nrows=0).columns
    first = header[0]
    by_upper = {c.upper(): c for c in header}
    use = [by_upper[c.upper()] for c in cols]
    parts = []
    for ch in pd.read_csv(csv, sep=";", encoding="latin1", dtype=str, usecols=[first] + use,
                          chunksize=chunksize, keep_default_na=False):
        ch[first] = _code(ch[first])
        ch = ch[ch[first].str.startswith(uf_prefix)]
        if not ch.empty:
            parts.append(ch)
    d = pd.concat(parts) if parts else pd.DataFrame(columns=[first] + use)
    d = d.rename(columns={first: "cd_setor", **{by_upper[c.upper()]: c.upper() for c in cols}})
    d = d.drop_duplicates("cd_setor").set_index("cd_setor")
    vals = [c.upper() for c in cols]
    raw = d[vals]
    num = raw.apply(_num)
    num["sigilo"] = num[vals].isna().any(axis=1)
    return num


def indicadores(raw: pd.DataFrame) -> pd.DataFrame:
    """Um par `<ind>_num, <ind>_den` por indicador (soma das colunas; NaN de sigilo conta como 0)."""
    out = pd.DataFrame(index=raw.index)
    for ind, (num, den) in INDICADORES.items():
        out[f"{ind}_num"] = raw.reindex(columns=num).fillna(0).sum(axis=1)
        out[f"{ind}_den"] = raw.reindex(columns=den).fillna(0).sum(axis=1)
    return out


def centroides(gdf) -> pd.DataFrame:
    """Centroide de cada setor em EPSG:31982, codigo IBGE do municipio e area (km2).

    A malha real traz setores partidos em mais de um poligono com os mesmos atributos: as partes sao unidas.
    """
    gdf = gdf.assign(CD_SETOR=_code(gdf["CD_SETOR"]))
    if gdf["CD_SETOR"].duplicated().any():
        gdf = gdf.dissolve(by="CD_SETOR", aggfunc="first", as_index=False)
    g = gdf.to_crs(CRS_METRICO)
    c = g.geometry.centroid
    return pd.DataFrame({"cd_mun_ibge": gdf["CD_MUN"].astype(str).values, "cx": c.x.values, "cy": c.y.values,
                         "area_km2": _num(gdf["AREA_KM2"]).values},
                        index=pd.Index(_code(gdf["CD_SETOR"]).values, name="cd_setor"))


def build_setores(raw_dir: Path) -> pd.DataFrame:
    """base/censo_setor.parquet: centroides, moradores, domicilios, area, densidade, sigilo e pares de indicadores."""
    import geopandas as gpd

    raw_dir = Path(raw_dir)
    geo = centroides(gpd.read_file(raw_dir / "censo" / "TO_setores_CD2022.gpkg"))
    partes, sigilo = [], pd.Series(False, index=geo.index)
    for nome, cols in ARQUIVOS.items():
        csv = next((raw_dir / f"censo_{nome}").glob("*.csv"))
        d = read_setores(csv, cols)
        sigilo = sigilo | d["sigilo"].reindex(geo.index, fill_value=False)
        partes.append(d.drop(columns="sigilo"))
    raw = pd.concat(partes, axis=1).reindex(geo.index)
    out = geo.join(indicadores(raw))
    out["moradores"] = raw["V0001"].fillna(0)
    out["domicilios"] = raw["V0007"].fillna(0)
    out["sigilo"] = sigilo
    out["densidade"] = out["moradores"] / out["area_km2"].where(out["area_km2"] > 0)
    return out.reset_index()


def _sidra(path: Path) -> pd.DataFrame:
    rows = json.loads(Path(path).read_text(encoding="utf-8"))[1:]
    return pd.DataFrame([{"cd_mun_ibge": r["D1C"], "var": r["D2C"], "v": r["V"]} for r in rows])


def build_municipios(sidra_dir: Path) -> pd.DataFrame:
    """base/ibge_municipio.parquet: populacao, area, densidade (Censo 2022) e PIB per capita 2022."""
    sidra_dir = Path(sidra_dir)
    p = _sidra(sidra_dir / "4714_pop_area_2022.json").pivot(index="cd_mun_ibge", columns="var", values="v")
    pib = _sidra(sidra_dir / "5938_pib_2022.json").set_index("cd_mun_ibge")["v"]
    out = pd.DataFrame({"populacao": _num(p["93"]).astype("Int64"), "area_km2": _num(p["6318"]),
                        "densidade": _num(p["614"])})
    out["pib_per_capita"] = _num(pib).reindex(out.index) * 1000 / out["populacao"].astype(float)
    out["ano_pib"] = 2022
    return out.reset_index()
