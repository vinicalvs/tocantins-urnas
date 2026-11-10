"""Ligacao setor censitario -> local de votacao e areas de votacao (metodo de Palmas generalizado).

- Cada setor vai para o local mais proximo do MESMO municipio (centroide, EPSG:31982), por ano.
- Locais especiais (transito, penal/prisional, 0 eleitores) e locais sem coordenadas nao recebem setores.
- Empate de distancia: menor `local_id` (ordem de texto), nas duas implementacoes.
- `local_id` = "zona-local" so e unico DENTRO do municipio (a zona cobre varios municipios): toda chave de
  local e o par (cd_municipio, local_id).
- Ligacao crivel: 0,4 <= eleitores / moradores <= 1,6.
- Area de votacao: locais vizinhos fundidos ate a razao de cada area ficar na faixa (algoritmo no plano, Task 4).
"""
import unicodedata

import numpy as np
import pandas as pd

from tocantins.censo import CRS_METRICO

FAIXA = (0.4, 1.6)
_ESPECIAIS = ("TRANSITO", "PENAL", "PRISIONAL")
LINK_COLS = ["cd_setor", "cd_municipio", "local_id", "dist_m"]


def _sem_acento(s: str) -> str:
    return unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().upper()


def especial(nome: str, eleitores: float) -> bool:
    return eleitores <= 0 or any(k in _sem_acento(nome) for k in _ESPECIAIS)


def locais_ano(locais: pd.DataFrame, ano: int, crosswalk: dict[str, str]) -> pd.DataFrame:
    """Um registro por local (turno 1 do ano): id, municipio, nome, eleitores, coordenadas, x/y metricos."""
    import geopandas as gpd

    d = locais[(locais["ano"] == ano) & (locais["turno"] == 1)].copy()
    d["id"] = d["zona"].astype(int).astype(str) + "-" + d["local"].astype(int).astype(str)
    d = d.sort_values(["cd_municipio", "id", "secao"])
    base = d.groupby(["cd_municipio", "id"], as_index=False).agg(nome=("nm_local", "first"),
                                               bairro=("bairro", "first"), eleitores=("eleitores_secao", "sum"))
    # coordenadas de UMA linha completa (lat e lon presentes): a de menor secao
    comp = d.dropna(subset=["lat", "lon"]).drop_duplicates(["cd_municipio", "id"])[["cd_municipio", "id", "lat", "lon"]]
    out = base.merge(comp, on=["cd_municipio", "id"], how="left")
    out["cd_mun_ibge"] = out["cd_municipio"].map(crosswalk)
    out["especial"] = [especial(n, e) for n, e in zip(out["nome"], out["eleitores"])]
    ok = out["lat"].notna() & out["lon"].notna()
    out["x"] = np.nan
    out["y"] = np.nan
    if ok.any():
        pts = gpd.GeoSeries.from_xy(out.loc[ok, "lon"], out.loc[ok, "lat"], crs=4674).to_crs(CRS_METRICO)
        out.loc[ok, "x"] = pts.x.values
        out.loc[ok, "y"] = pts.y.values
    return out


def _elegiveis(locais: pd.DataFrame) -> pd.DataFrame:
    e = locais[~locais["especial"].astype(bool) & locais["x"].notna() & locais["y"].notna()]
    return e.sort_values("id")


def link_numpy(setores: pd.DataFrame, locais: pd.DataFrame) -> pd.DataFrame:
    """Distancia euclidiana em matriz, por municipio; np.argmin pega o 1o minimo (locais ordenados por id)."""
    loc = _elegiveis(locais)
    out = []
    for mun, s in setores.groupby("cd_mun_ibge", sort=True):
        l = loc[loc["cd_mun_ibge"] == mun]
        if l.empty:
            continue
        dx = s["cx"].to_numpy()[:, None] - l["x"].to_numpy()[None, :]
        dy = s["cy"].to_numpy()[:, None] - l["y"].to_numpy()[None, :]
        dist = np.hypot(dx, dy)
        k = dist.argmin(axis=1)
        out.append(pd.DataFrame({"cd_setor": s["cd_setor"].to_numpy(), "cd_municipio": l["cd_municipio"].to_numpy()[k],
                                 "local_id": l["id"].to_numpy()[k],
                                 "dist_m": dist[np.arange(len(s)), k]}))
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame(columns=LINK_COLS)


def link_geopandas(setores: pd.DataFrame, locais: pd.DataFrame) -> pd.DataFrame:
    """geopandas.sjoin_nearest por municipio; empates resolvidos pelo menor local_id."""
    import geopandas as gpd

    loc = _elegiveis(locais)
    out = []
    for mun, s in setores.groupby("cd_mun_ibge", sort=True):
        l = loc[loc["cd_mun_ibge"] == mun]
        if l.empty:
            continue
        gs = gpd.GeoDataFrame(s[["cd_setor"]], geometry=gpd.points_from_xy(s["cx"], s["cy"]), crs=CRS_METRICO)
        gl = gpd.GeoDataFrame({"local_id": l["id"].to_numpy(), "cd_municipio": l["cd_municipio"].to_numpy()}, geometry=gpd.points_from_xy(l["x"], l["y"]),
                              crs=CRS_METRICO)
        j = gpd.sjoin_nearest(gs, gl, how="left", distance_col="dist_m")
        j = j.sort_values(["cd_setor", "local_id"]).drop_duplicates("cd_setor")
        out.append(pd.DataFrame(j[LINK_COLS]))
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame(columns=LINK_COLS)


def credibilidade(link: pd.DataFrame, setores: pd.DataFrame, locais: pd.DataFrame) -> pd.DataFrame:
    """Por local: moradores ligados, eleitores, razao e `credivel` (faixa inclusiva)."""
    mor = (link.merge(setores[["cd_setor", "moradores"]], on="cd_setor")
           .groupby(["cd_municipio", "local_id"])["moradores"].sum().rename("moradores").reset_index())
    d = locais[["id", "cd_municipio", "eleitores"]].rename(columns={"id": "local_id"})
    d = d.merge(mor, on=["cd_municipio", "local_id"], how="left")
    d["moradores"] = d["moradores"].fillna(0)
    d["razao"] = d["eleitores"] / d["moradores"].where(d["moradores"] > 0)
    d["credivel"] = d["razao"].between(*FAIXA).fillna(False).astype(bool)
    return d


def areas(link: pd.DataFrame, setores: pd.DataFrame, locais: pd.DataFrame) -> pd.DataFrame:
    """local_id -> area_id (menor local_id da area). So locais que receberam setores."""
    cred = credibilidade(link, setores, locais)
    usados = set(zip(link["cd_municipio"], link["local_id"]))
    cred = cred[[k in usados for k in zip(cred["cd_municipio"], cred["local_id"])]]
    rows = []
    for mun, c in cred.groupby("cd_municipio", sort=True):
        xy = locais[locais["cd_municipio"] == mun].set_index("id")[["x", "y"]]
        grupos = {}
        for r in c.sort_values("local_id").itertuples(index=False):
            grupos[r.local_id] = {"locais": [r.local_id], "eleit": float(r.eleitores), "mor": float(r.moradores)}

        def centro(g):
            p = xy.loc[g["locais"]]
            w = c.set_index("local_id").loc[g["locais"], "eleitores"].astype(float)
            w = w if w.sum() > 0 else pd.Series(1.0, index=w.index)
            return (p["x"] * w).sum() / w.sum(), (p["y"] * w).sum() / w.sum()

        def fora(g):
            r = g["eleit"] / g["mor"] if g["mor"] > 0 else np.inf
            return not (FAIXA[0] <= r <= FAIXA[1])

        while len(grupos) > 1:
            ruins = sorted((g["eleit"] + g["mor"], k) for k, g in grupos.items() if fora(g))
            if not ruins:
                break
            a = ruins[0][1]
            ax, ay = centro(grupos[a])
            b = min((np.hypot(ax - centro(g)[0], ay - centro(g)[1]), k) for k, g in grupos.items() if k != a)[1]
            novo = {"locais": grupos[a]["locais"] + grupos[b]["locais"], "eleit": grupos[a]["eleit"] + grupos[b]["eleit"],
                    "mor": grupos[a]["mor"] + grupos[b]["mor"]}
            del grupos[a], grupos[b]
            grupos[min(novo["locais"])] = novo
        for k, g in grupos.items():
            area_id = min(g["locais"])
            rows += [{"cd_municipio": mun, "local_id": lid, "area_id": area_id} for lid in g["locais"]]
    return pd.DataFrame(rows, columns=["cd_municipio", "local_id", "area_id"]).sort_values(
        ["cd_municipio", "local_id"]).reset_index(drop=True)
