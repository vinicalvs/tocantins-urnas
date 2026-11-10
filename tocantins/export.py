"""Etapa 04: exporta a base validada para JSON do site (site_dados/), com gate no selo de validacao.

Regras (Rulings R31-R33):
- So exporta com `validacao/selo.json` status "ok" e mais novo que os Parquet da base.
- Candidatos = numeros da lista oficial do TSE (munzona). Voto nominal em numero fora da lista e
  "nulo tecnico" (como no resultado oficial) e nao entra nos validos. Legenda conta sempre como
  valida (partido federado sem candidato proprio recebe legenda valida). `validos` = votos apurados
  para candidatos da lista + legenda; inclui votos sub judice/anulados, por isso pode passar o
  "validos" exibido pelo TSE em poucos votos.
- Cargos exportados: Prefeito e Vereador (2024), Deputado Federal e Deputado Estadual (2026).
"""
import json
import os
import shutil
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from tocantins import crosswalk
from tocantins.config import RAW

CARGOS = {2024: ["Prefeito", "Vereador"], 2026: ["Deputado Federal", "Deputado Estadual"]}
MUNICIPAIS = {"Prefeito", "Vereador"}
BASE_FILES = ["bu_secao.parquet", "locais.parquet", "munzona.parquet"]
BU_COLUMNS = ["ano", "turno", "cargo", "cd_municipio", "nm_municipio", "zona", "secao", "local", "aptos",
              "comparecimento", "abstencoes", "tipo_votavel", "nr_votavel", "nm_votavel", "sg_partido", "votos"]


class GateError(Exception):
    """Exportacao bloqueada: validacao ausente, reprovada ou anterior a base."""


def slug(cargo: str) -> str:
    """Ruling R8: minusculas, ASCII, espaco -> '_'."""
    s = unicodedata.normalize("NFKD", cargo)
    return "".join(c for c in s if not unicodedata.combining(c)).lower().replace(" ", "_")


def check_gate(base: Path, valid_dir: Path) -> dict:
    p = Path(valid_dir) / "selo.json"
    if not p.exists():
        raise GateError(f"{p} ausente: rode scripts/03_validar.py")
    selo = json.loads(p.read_text(encoding="utf-8"))
    if selo.get("status") != "ok":
        raise GateError(f"selo de validacao com status {selo.get('status')!r}: exportacao bloqueada")
    data = datetime.fromisoformat(selo["data"])
    for f in BASE_FILES:
        fp = Path(base) / f
        if fp.exists() and datetime.fromtimestamp(fp.stat().st_mtime, timezone.utc) > data:
            raise GateError(f"{fp} e mais novo que o selo ({selo['data']}): valide de novo")
    return selo


def _dump(path: Path, obj) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    path.write_bytes(data)
    return len(data)


def _eleito(sit) -> bool | None:
    if sit is None or (isinstance(sit, float) and pd.isna(sit)):
        return None
    return str(sit).upper().startswith("ELEITO")


def _num(x):
    return None if pd.isna(x) else float(x)


class _Scope:
    """Uma (ano, cargo, turno): votos do BU classificados contra a lista oficial."""

    def __init__(self, d: pd.DataFrame, mz: pd.DataFrame, cargo: str):
        self.municipal = cargo in MUNICIPAIS
        of = mz.sort_values("situacao_turno", na_position="last").drop_duplicates(
            ["cd_municipio", "nr_candidato"] if self.municipal else ["nr_candidato"])
        if self.municipal:
            listed = set(zip(of["cd_municipio"], of["nr_candidato"]))
            self.sit = {(m, int(n)): s for m, n, s in zip(of["cd_municipio"], of["nr_candidato"], of["situacao_turno"])}
            in_list = [(m, n) in listed for m, n in zip(d["cd_municipio"], d["nr_votavel"])]
        else:
            listed = set(of["nr_candidato"])
            self.sit = {int(n): s for n, s in zip(of["nr_candidato"], of["situacao_turno"])}
            in_list = d["nr_votavel"].isin(listed).tolist()
        t = d["tipo_votavel"]
        in_list = pd.Series(in_list, index=d.index, dtype=bool)
        cat = pd.Series("outro", index=d.index)
        cat[(t == "Nominal") & in_list] = "candidato"
        cat[(t == "Nominal") & ~in_list] = "nulo_tecnico"
        cat[t == "Legenda"] = "legenda"
        cat[t == "Branco"] = "branco"
        cat[t == "Nulo"] = "nulo"
        self.d = d.assign(cat=cat)

    def eleito(self, mun: str, nr: int):
        return _eleito(self.sit.get((mun, nr) if self.municipal else nr))


def _totais(d: pd.DataFrame) -> dict:
    secs = d.drop_duplicates(["cd_municipio", "zona", "secao"])
    by = d.groupby("cat")["votos"].sum()
    g = lambda k: int(by.get(k, 0))  # noqa: E731
    return {"aptos": int(secs["aptos"].sum()), "comparecimento": int(secs["comparecimento"].sum()),
            "abstencoes": int(secs["abstencoes"].sum()), "brancos": g("branco"), "nulos": g("nulo"),
            "nulos_tecnicos": g("nulo_tecnico"), "validos": g("candidato") + g("legenda")}


def _candidatos(d: pd.DataFrame, scope: _Scope, validos: int, por_municipio: bool) -> list[dict]:
    c = d[d["cat"] == "candidato"]
    keys = (["cd_municipio"] if por_municipio else []) + ["nr_votavel"]
    g = (c.groupby(keys, as_index=False)
         .agg(votos=("votos", "sum"), nome=("nm_votavel", "first"), partido=("sg_partido", "first"),
              mun=("cd_municipio", "first"))
         .sort_values(["votos", "nr_votavel"], ascending=[False, True]))
    out = []
    for r in g.itertuples(index=False):
        item = {"nr": int(r.nr_votavel), "nome": r.nome, "partido": r.partido, "votos": int(r.votos),
                "pct_validos": round(100 * r.votos / validos, 2) if validos else 0.0,
                "eleito": scope.eleito(r.mun, int(r.nr_votavel))}
        if por_municipio:
            item = {"cod": r.cd_municipio, **item}
        out.append(item)
    return out


def _partidos(d: pd.DataFrame) -> list[dict]:
    v = d[d["cat"].isin(["candidato", "legenda"])]
    p = v.pivot_table(index="sg_partido", columns="cat", values="votos", aggfunc="sum", fill_value=0)
    rows = [{"sg": sg, "legenda": int(r.get("legenda", 0)), "nominais": int(r.get("candidato", 0)),
             "total": int(r.get("legenda", 0) + r.get("candidato", 0))} for sg, r in p.iterrows()]
    return sorted(rows, key=lambda x: (-x["total"], x["sg"]))


def _locais(d: pd.DataFrame, loc: pd.DataFrame) -> tuple[list[dict], int]:
    attrs = loc.merge(d[["zona", "secao", "local"]].drop_duplicates(), on=["zona", "secao"],
                      suffixes=("_cad", ""))
    attrs = (attrs.sort_values(["lat"], na_position="last")
             .groupby(["zona", "local"]).first()[["nm_local", "endereco", "bairro", "lat", "lon"]])
    secs = d.drop_duplicates(["zona", "secao"]).groupby(["zona", "local"])[["aptos", "comparecimento"]].sum()
    lab = d["nr_votavel"].astype(str).where(d["cat"] == "candidato", d["cat"])
    lab = lab.where(d["cat"] != "legenda", "legenda:" + d["sg_partido"].astype(str))
    v = d.assign(lab=lab).groupby(["zona", "local", "lab"])["votos"].sum()
    out, sem = [], 0
    for (zona, local), s in secs.iterrows():
        a = attrs.loc[(zona, local)] if (zona, local) in attrs.index else None
        lat = _num(a["lat"]) if a is not None else None
        lon = _num(a["lon"]) if a is not None else None
        if lat is None or lon is None:
            lat = lon = None
            sem += 1
        votos = {k: int(x) for k, x in v.loc[(zona, local)].items() if x}
        out.append({"id": f"{zona}-{local}", "zona": int(zona),
                    "nome": None if a is None else a["nm_local"],
                    "endereco": None if a is None else a["endereco"],
                    "bairro": None if a is None else a["bairro"],
                    "lat": lat, "lon": lon, "aptos": int(s["aptos"]),
                    "comparecimento": int(s["comparecimento"]), "votos": votos})
    return out, sem


def _vencedores(d: pd.DataFrame, scope: _Scope) -> list[dict]:
    out = []
    for mun, dm in d.groupby("cd_municipio"):
        tot = _totais(dm)
        cands = _candidatos(dm, scope, tot["validos"], por_municipio=False)
        parts = _partidos(dm)
        out.append({"cod": mun,
                    "vencedor": {k: cands[0][k] for k in ("nr", "nome", "partido", "votos", "pct_validos")}
                    if cands else None,
                    "partido_mais_votado": {"sg": parts[0]["sg"], "total": parts[0]["total"]} if parts else None,
                    "validos": tot["validos"]})
    return out


def export_all(base: Path, out: Path, valid_dir: Path, ibge_dir: Path = RAW / "ibge",
               n_municipios: int = crosswalk.N_MUNICIPIOS) -> dict:
    """Escreve site_dados/ inteiro numa pasta temporaria e troca no fim (sem restos antigos)."""
    base, out, valid_dir, ibge_dir = Path(base), Path(out), Path(valid_dir), Path(ibge_dir)
    selo = check_gate(base, valid_dir)
    escopo = [(a, c) for a, cs in CARGOS.items() for c in cs]
    bu = pd.read_parquet(base / "bu_secao.parquet", columns=BU_COLUMNS)
    bu = bu[pd.Series(list(zip(bu["ano"], bu["cargo"])), index=bu.index).isin(escopo)]
    locais = pd.read_parquet(base / "locais.parquet")
    munzona = pd.read_parquet(base / "munzona.parquet")

    ibge = json.loads((ibge_dir / "municipios_17.json").read_text(encoding="utf-8"))
    nomes = bu[["cd_municipio", "nm_municipio"]].drop_duplicates()
    cw = crosswalk.build(nomes, ibge, crosswalk.load_overrides(), expected=n_municipios)

    tmp = out.with_name(out.name + ".tmp")
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True)
    stats = {"arquivos": 0, "bytes": 0, "maior": ("", 0), "locais_sem_coordenadas": 0}

    def write(rel: str, obj) -> None:
        n = _dump(tmp / rel, obj)
        stats["arquivos"] += 1
        stats["bytes"] += n
        if n > stats["maior"][1]:
            stats["maior"] = (rel, n)

    disponivel: dict[str, dict] = {m: {} for m in cw}
    sem_coord: dict[str, set] = {m: set() for m in cw}
    nome_mun = dict(zip(nomes["cd_municipio"], nomes["nm_municipio"]))
    for (ano, cargo, turno), d in bu.groupby(["ano", "cargo", "turno"]):
        ano, turno = int(ano), int(turno)
        mz = munzona[(munzona["ano"] == ano) & (munzona["cargo"] == cargo) & (munzona["turno"] == turno)]
        scope = _Scope(d, mz, cargo)
        d = scope.d
        lt = locais[(locais["ano"] == ano) & (locais["turno"] == turno)]
        nome = f"{ano}_{slug(cargo)}_t{turno}.json"
        for mun, dm in d.groupby("cd_municipio"):
            tot = _totais(dm)
            locs, _ = _locais(dm, lt[lt["cd_municipio"] == mun])
            sem_coord[mun] |= {(ano, l["id"]) for l in locs if l["lat"] is None}
            write(f"{mun}/{nome}", {
                "municipio": {"cod": mun, "nome": nome_mun[mun]}, "ano": ano, "cargo": cargo, "turno": turno,
                "totais": tot, "candidatos": _candidatos(dm, scope, tot["validos"], por_municipio=False),
                "partidos": _partidos(dm), "locais": locs})
            disponivel[mun].setdefault(str(ano), {}).setdefault(slug(cargo), []).append(turno)
        tot = _totais(d)
        write(f"estado/{nome}", {
            "ano": ano, "cargo": cargo, "turno": turno, "totais": tot,
            "candidatos": _candidatos(d, scope, tot["validos"], por_municipio=scope.municipal),
            "partidos": _partidos(d), "municipios": _vencedores(d, scope)})

    ult = locais[locais["ano"] == locais["ano"].max()]
    ult = ult[ult["turno"] == 1].drop_duplicates(["cd_municipio", "zona", "secao"])
    eleitorado = ult.groupby("cd_municipio")["eleitores_secao"].sum()
    index = {"gerado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
             "selo": selo.get("status"),
             "municipios": [{"cod": m, "ibge": cw[m], "nome": nome_mun[m],
                             "eleitorado": int(eleitorado.get(m, 0)),
                             "disponivel": {a: {c: sorted(t) for c, t in cs.items()}
                                            for a, cs in sorted(disponivel[m].items())},
                             "locais_sem_coordenadas": len(sem_coord[m])}
                            for m in sorted(cw, key=lambda k: nome_mun[k])]}
    write("index.json", index)
    write("selo_validacao.json", selo)
    shutil.copyfile(ibge_dir / "malha_to.geojson", tmp / "malha_to.geojson")
    stats["locais_sem_coordenadas"] = sum(len(s) for s in sem_coord.values())
    stats["municipios"] = len(index["municipios"])

    old = out.with_name(out.name + ".old")
    if old.exists():
        shutil.rmtree(old)
    if out.exists():
        os.replace(out, old)
    os.replace(tmp, out)
    if old.exists():
        shutil.rmtree(old)
    return stats
