"""Etapa 04: exporta a base validada para JSON do site (site_dados/), com gate no selo de validacao.

Regras (Rulings R31-R33):
- So exporta com `validacao/selo.json` status "ok" e mais novo que os Parquet da base.
- Candidatos = numeros da lista oficial do TSE (munzona). Voto nominal em numero fora da lista e
  "nulo tecnico" (como no resultado oficial) e nao entra nos validos. Legenda conta sempre como
  valida (partido federado sem candidato proprio recebe legenda valida). `validos` = votos apurados
  para candidatos da lista + legenda; inclui votos sub judice/anulados, por isso pode passar o
  "validos" exibido pelo TSE em poucos votos.
- Cargos exportados: Prefeito e Vereador (2024); Deputado Federal, Deputado Estadual, Governador e Senador (2026).
- Coordenadas do local: a linha completa (lat e lon) de menor secao.
- Conjuntura (spec secao 2): ficha do local, IBGE do municipio, entrega dos prefeitos e areas de votacao
  criveis com indicadores do Censo 2022 e votos por cargo (turno 1).
"""
import json
import math
import os
import shutil
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from tocantins import conjuntura, crosswalk
from tocantins.censo import INDICADORES
from tocantins.config import RAW
from tocantins.ligacao import FAIXA

CARGOS = {2024: ["Prefeito", "Vereador"], 2026: ["Deputado Federal", "Deputado Estadual", "Governador", "Senador"]}
MUNICIPAIS = {"Prefeito", "Vereador"}
CENSO_FILES = ["censo_setor.parquet", "ibge_municipio.parquet", "ligacao_setor_local.parquet",
               "local_credibilidade.parquet", "area_votacao.parquet", "coligacoes.parquet"]
BASE_FILES = ["bu_secao.parquet", "locais.parquet", "munzona.parquet"] + CENSO_FILES
# Ficha do local: quantos candidatos por cargo (ausente = todos).
LIMITE_FICHA = {"Vereador": 15, "Deputado Federal": 5, "Deputado Estadual": 5}
ENTREGA = [("Governador", 1), ("Governador", 2), ("Senador", 1)]
NOTAS = {"GOIATINS": "Houve eleição suplementar para prefeito em 25/10/2026; ela não faz parte destes dados."}
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


def _candidatos(d: pd.DataFrame, scope: _Scope, validos: int, por_municipio: bool,
                com_municipios: bool = False) -> list[dict]:
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
    if com_municipios and not scope.municipal:
        # Cargo estadual: votos do candidato em cada municipio (tela Candidato no estado).
        pm = c.groupby(["nr_votavel", "cd_municipio"])["votos"].sum()
        pm = pm[pm > 0]
        por_nr: dict[int, dict[str, int]] = {}
        for (nr, mun), v in pm.items():
            por_nr.setdefault(int(nr), {})[str(mun)] = int(v)
        for item in out:
            item["municipios"] = dict(sorted(por_nr.get(item["nr"], {}).items()))
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
    attrs = attrs.sort_values(["zona", "local", "secao"])
    comp = (attrs.dropna(subset=["lat", "lon"]).drop_duplicates(["zona", "local"])
            .set_index(["zona", "local"])[["lat", "lon"]])
    attrs = attrs.groupby(["zona", "local"]).first()[["nm_local", "endereco", "bairro"]].join(comp)
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


def nota_municipio(nome: str) -> str | None:
    return NOTAS.get(crosswalk.normalize_name(nome))


def _py(v):
    """Valor JSON: numpy -> python, NaN/NA -> None, float inteiro -> int."""
    if v is None or v is pd.NA:
        return None
    if hasattr(v, "item"):
        v = v.item()
    if isinstance(v, float):
        if math.isnan(v):
            return None
        return int(v) if v.is_integer() else round(v, 2)
    return v


def _ind(s: pd.DataFrame) -> dict:
    """{indicador: % (1 casa)} somando numeradores e denominadores dos setores."""
    out = {}
    for i in INDICADORES:
        den = float(s[f"{i}_den"].sum()) if len(s) else 0.0
        out[i] = round(100 * float(s[f"{i}_num"].sum()) / den, 1) if den else None
    return out


def _local_id(d: pd.DataFrame) -> pd.Series:
    return d["zona"].astype(int).astype(str) + "-" + d["local"].astype(int).astype(str)


def _nome_norm(nome) -> str:
    t = unicodedata.normalize("NFKD", str(nome or "")).encode("ascii", "ignore").decode()
    return " ".join(t.upper().split())


def _chave_ficha(fichas: dict, lid: str, nome, ano: int) -> str:
    """O mesmo "zona-local" pode ser outro local em outro ano: junta os anos so com o mesmo nome."""
    f = fichas.get(lid)
    if f is None or not f["nome"] or not nome or _nome_norm(f["nome"]) == _nome_norm(nome)             or any(k.startswith(f"{ano}-") for k in f["cargos"]):
        return lid
    return f"{lid}@{ano}"


def _ficha_cargo(dm: pd.DataFrame, limite: int | None) -> dict[str, list[dict]]:
    """Por local: candidatos mais votados com % sobre os validos do local."""
    lid = _local_id(dm)
    val = dm[dm["cat"].isin(["candidato", "legenda"])].groupby(lid)["votos"].sum()
    c = dm[(dm["cat"] == "candidato") & (dm["votos"] > 0)].assign(lid=lid)
    c = (c.groupby(["lid", "nr_votavel"], as_index=False)
         .agg(votos=("votos", "sum"), nome=("nm_votavel", "first"), partido=("sg_partido", "first"))
         .sort_values(["lid", "votos", "nr_votavel"], ascending=[True, False, True]))
    out = {}
    for k, g in c.groupby("lid", sort=False):
        v = int(val.get(k, 0))
        g = g.head(limite) if limite else g
        out[k] = [{"nr": int(r.nr_votavel), "nome": r.nome, "partido": r.partido, "votos": int(r.votos),
                   "pct": round(100 * r.votos / v, 1) if v else 0.0} for r in g.itertuples()]
    return out


def _areas_cargo(d: pd.DataFrame, ano: int, setores, link, cred, areas) -> list[dict]:
    """Areas de votacao criveis (eleitores/moradores na FAIXA) com votos do cargo e indicadores."""
    c = cred[cred["ano"] == ano][["cd_municipio", "local_id", "eleitores", "moradores"]]
    ar = areas[areas["ano"] == ano].merge(c, on=["cd_municipio", "local_id"])
    tot = ar.groupby(["cd_municipio", "area_id"])[["eleitores", "moradores"]].sum()
    razao = tot["eleitores"] / tot["moradores"].where(tot["moradores"] > 0)
    tot = tot[razao.between(*FAIXA)]
    area_de = {(m, l): a for m, l, a in zip(ar["cd_municipio"], ar["local_id"], ar["area_id"])}
    lk = link[link["ano"] == ano]
    lk = lk.assign(area=[area_de.get(k) for k in zip(lk["cd_municipio"], lk["local_id"])])
    set_area = {k: g for k, g in lk.merge(setores, on="cd_setor").groupby(["cd_municipio", "area"])}
    d = d.assign(area=[area_de.get(k) for k in zip(d["cd_municipio"], _local_id(d))])
    out = []
    for (mun, area), g in d.dropna(subset=["area"]).groupby(["cd_municipio", "area"], sort=True):
        if (mun, area) not in tot.index:
            continue
        t = _totais(g)
        cand = g[g["cat"] == "candidato"].groupby("nr_votavel")["votos"].sum()
        part = g[g["cat"].isin(["candidato", "legenda"])].groupby("sg_partido")["votos"].sum()
        out.append({"id": area, "cod": mun, "eleitores": int(tot.loc[(mun, area), "eleitores"]),
                    "moradores": int(tot.loc[(mun, area), "moradores"]), "aptos": t["aptos"],
                    "comparecimento": t["comparecimento"], "validos": t["validos"],
                    "ind": _ind(set_area.get((mun, area), setores.iloc[:0])),
                    "votos": {str(int(k)): int(v) for k, v in cand.items() if v},
                    "partidos": {str(k): int(v) for k, v in part.items() if v}})
    return out


def _entrega(bu: pd.DataFrame, munzona: pd.DataFrame, coligacoes: pd.DataFrame) -> dict:
    pref = conjuntura.prefeitos(None, munzona)
    out = {}
    for cargo, turno in ENTREGA:
        rows = []
        for r in conjuntura.entrega(bu, pref, coligacoes, cargo, turno).to_dict("records"):
            r = {k: _py(v) for k, v in r.items()}
            rows.append({"cod": r.pop("cd_municipio"),
                         "prefeito": {"nome": r.pop("prefeito_nome"), "partido": r.pop("prefeito_partido")},
                         **{k: v for k, v in r.items() if k != "prefeito_nr"}})
        out[f"{slug(cargo)}-{turno}"] = rows
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
    ficha: dict[str, dict[str, dict]] = {m: {} for m in cw}
    t1: dict[tuple[int, str], pd.DataFrame] = {}
    mun_tot: dict[str, dict[str, dict]] = {m: {} for m in cw}
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
            votos_local = _ficha_cargo(dm, LIMITE_FICHA.get(cargo))
            for l in locs:
                k = _chave_ficha(ficha[mun], l["id"], l["nome"], ano)
                f = ficha[mun].setdefault(k, {"id": l["id"], "nome": None, "bairro": None, "lat": None,
                                              "lon": None, "anos": {}, "cargos": {}, "entorno": None})
                for k in ("nome", "bairro"):
                    f[k] = l[k] or f[k]
                if l["lat"] is not None:
                    f["lat"], f["lon"] = l["lat"], l["lon"]
                if turno == 1:
                    f["anos"][str(ano)] = {"aptos": l["aptos"], "comparecimento": l["comparecimento"]}
                f["cargos"][f"{ano}-{slug(cargo)}-{turno}"] = votos_local.get(l["id"], [])
            if turno == 1:
                mun_tot[mun][str(ano)] = {"aptos": tot["aptos"], "comparecimento": tot["comparecimento"]}
            write(f"{mun}/{nome}", {
                "municipio": {"cod": mun, "nome": nome_mun[mun]}, "ano": ano, "cargo": cargo, "turno": turno,
                "totais": tot, "candidatos": _candidatos(dm, scope, tot["validos"], por_municipio=False),
                "partidos": _partidos(dm), "locais": locs})
            disponivel[mun].setdefault(str(ano), {}).setdefault(slug(cargo), []).append(turno)
        if turno == 1:
            t1[(ano, cargo)] = d
        tot = _totais(d)
        write(f"estado/{nome}", {
            "ano": ano, "cargo": cargo, "turno": turno, "totais": tot,
            "candidatos": _candidatos(d, scope, tot["validos"], por_municipio=scope.municipal,
                                     com_municipios=True),
            "partidos": _partidos(d), "municipios": _vencedores(d, scope)})

    # Censo, ficha do local e conjuntura
    setores = pd.read_parquet(base / "censo_setor.parquet")
    link = pd.read_parquet(base / "ligacao_setor_local.parquet")
    link = link[link["impl"] == "numpy"]
    cred = pd.read_parquet(base / "local_credibilidade.parquet")
    areas = pd.read_parquet(base / "area_votacao.parquet")
    ibge_mun = pd.read_parquet(base / "ibge_municipio.parquet").set_index("cd_mun_ibge")
    setores_de = {k: g["cd_setor"].tolist() for k, g in link.groupby(["ano", "cd_municipio", "local_id"])}
    set_idx = setores.set_index("cd_setor")
    cred_de = {(int(r["ano"]), r["cd_municipio"], r["local_id"]): r for r in cred.to_dict("records")}
    area_de = {(int(a), m, l): x for a, m, l, x in zip(areas["ano"], areas["cd_municipio"], areas["local_id"],
                                                       areas["area_id"])}
    for mun in sorted(cw):
        for f in ficha[mun].values():
            lid = f["id"]
            anos_f = {int(k[:4]) for k in f["cargos"]}
            ano_e = 2026 if 2026 in anos_f and (2026, mun, lid) in cred_de else min(anos_f)
            c = cred_de.get((ano_e, mun, lid))
            if c is not None and c["credivel"]:
                s = set_idx.loc[setores_de.get((ano_e, mun, lid), [])]
                f["entorno"] = {"credivel": True, "ano_ligacao": ano_e, "area_id": area_de.get((ano_e, mun, lid)),
                                "moradores": int(c["moradores"]), "indicadores": _ind(s)}
        if ficha[mun]:
            write(f"{mun}/locais_ficha.json", {"locais": [ficha[mun][k] for k in sorted(ficha[mun])]})
        if cw[mun] in ibge_mun.index:
            im = ibge_mun.loc[cw[mun]]
            write(f"{mun}/ibge.json", {k: _py(im[k]) for k in ("populacao", "area_km2", "densidade",
                                                                "pib_per_capita", "ano_pib")})
    for (ano, cargo), d in sorted(t1.items()):
        write(f"conjuntura/areas_{ano}_{slug(cargo)}.json",
              {"indicadores": list(INDICADORES), "areas": _areas_cargo(d, ano, setores, link, cred, areas)})
    por_ibge = {k: _ind(g) for k, g in setores.groupby("cd_mun_ibge")}
    write("conjuntura/municipios_indicadores.json",
          [{"cod": m, "ind": por_ibge.get(cw[m], _ind(setores.iloc[:0])),
            "aptos": {a: v["aptos"] for a, v in sorted(mun_tot[m].items())},
            "comparecimento": {a: v["comparecimento"] for a, v in sorted(mun_tot[m].items())}} for m in sorted(cw)])
    write("conjuntura/prefeitos_2026.json", _entrega(bu, munzona, pd.read_parquet(base / "coligacoes.parquet")))

    # Relatorios da validacao publicados junto dos dados (link do selo; spec 8.5).
    # camada4_oficial.json (~4 MB) fica so no repositorio.
    relatorios = sorted(p.name for p in valid_dir.glob("*")
                        if p.is_file() and (p.name == "excecoes.json" or p.suffix == ".csv"
                                            or (p.name.startswith("camada") and p.name != "camada4_oficial.json"
                                                and p.suffix == ".json")))
    (tmp / "validacao").mkdir()
    for nome_rel in relatorios:
        shutil.copyfile(valid_dir / nome_rel, tmp / "validacao" / nome_rel)

    ult = locais[locais["ano"] == locais["ano"].max()]
    ult = ult[ult["turno"] == 1].drop_duplicates(["cd_municipio", "zona", "secao"])
    eleitorado = ult.groupby("cd_municipio")["eleitores_secao"].sum()
    index = {"gerado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
             "selo": selo.get("status"),
             "relatorios": relatorios,
             "municipios": [{"cod": m, "ibge": cw[m], "nome": nome_mun[m],
                             "eleitorado": int(eleitorado.get(m, 0)),
                             "disponivel": {a: {c: sorted(t) for c, t in cs.items()}
                                            for a, cs in sorted(disponivel[m].items())},
                             "locais_sem_coordenadas": len(sem_coord[m]),
                             "nota": nota_municipio(nome_mun[m])}
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
