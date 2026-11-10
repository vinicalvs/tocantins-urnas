"""Camada 4: verificacao externa (eleito de Prefeito x resultado oficial; amostra conferida no site)."""
import json
import random
from pathlib import Path

import pandas as pd

from tocantins.validate.result import LayerResult, make_result

LAYER = "4"
PREFEITO = "Prefeito"
N_MAIORES = 5
N_SORTEADOS = 5
SEED = 2026
VISUAL_COLS = ["cargo", "turno", "cd_municipio", "candidato", "votos_site", "votos_base", "ok",
               "data_consulta", "motivo"]
BU_COLUMNS = ["ano", "turno", "cargo", "cd_municipio", "tipo_votavel", "nr_votavel", "nm_votavel", "votos"]
MUNZONA_COLUMNS = ["ano", "turno", "cargo", "cd_municipio", "nr_candidato", "situacao_turno"]


def _top(votos: pd.Series, n: int) -> str:
    """Os n mais votados, ordenados por numero e unidos por '/'; empate na fronteira -> 'empate:a=b'."""
    v = votos.sort_values(ascending=False)
    corte = v.iloc[n - 1]
    if len(v) > n and v.iloc[n] == corte:
        empatados = sorted(int(i) for i in v[v == corte].index)
        return "empate:" + "=".join(map(str, empatados))
    return "/".join(str(int(i)) for i in sorted(v.index[:n]))


def prefeito_winners(bu: pd.DataFrame, munzona: pd.DataFrame) -> pd.DataFrame:
    """Vencedor de Prefeito pelos votos nominais do BU x resultado oficial (munzona).

    Turno 1 de municipio que teve 2o turno (Ruling R7): compara os dois mais votados com os
    candidatos `2º TURNO`; demais casos: o mais votado com o `ELEITO`.
    """
    nom = bu[(bu["cargo"] == PREFEITO) & (bu["tipo_votavel"] == "Nominal")]
    votos = nom.groupby(["ano", "turno", "cd_municipio", "nr_votavel"])["votos"].sum()
    of = munzona[munzona["cargo"] == PREFEITO][["ano", "turno", "cd_municipio", "nr_candidato",
                                                 "situacao_turno"]].drop_duplicates()
    rows = []
    for (ano, turno, mun), v in votos.groupby(level=[0, 1, 2]):
        v = v.droplevel([0, 1, 2])
        o = of[(of["ano"] == ano) & (of["turno"] == turno) & (of["cd_municipio"] == mun)]
        segundo = sorted(int(x) for x in o.loc[o["situacao_turno"] == "2º TURNO", "nr_candidato"])
        eleitos = sorted(int(x) for x in o.loc[o["situacao_turno"].fillna("").str.startswith("ELEITO"),
                                              "nr_candidato"])
        if segundo:
            nr_bu, nr_of = _top(v, 2), "/".join(map(str, segundo))
        else:
            nr_bu, nr_of = _top(v, 1), "/".join(map(str, eleitos))
        rows.append({"ano": int(ano), "turno": int(turno), "cd_municipio": mun, "nr_bu": nr_bu,
                     "nr_oficial": nr_of, "ok": nr_bu == nr_of and nr_of != ""})
    return pd.DataFrame(rows, columns=["ano", "turno", "cd_municipio", "nr_bu", "nr_oficial", "ok"])


def sample_municipios(locais: pd.DataFrame, ano: int, seed: int = SEED) -> list[str]:
    """5 maiores por eleitorado (soma de eleitores_secao no turno 1) + 5 sorteados dos demais."""
    l1 = locais[(locais["ano"] == ano) & (locais["turno"] == 1)]
    tam = (l1.drop_duplicates(["cd_municipio", "zona", "secao"])
           .groupby("cd_municipio")["eleitores_secao"].sum().reset_index())
    tam = tam.sort_values(["eleitores_secao", "cd_municipio"], ascending=[False, True])
    maiores = tam["cd_municipio"].head(N_MAIORES).tolist()
    resto = sorted(set(tam["cd_municipio"]) - set(maiores))
    return maiores + random.Random(seed).sample(resto, N_SORTEADOS)


def expected_table(bu: pd.DataFrame, cd_municipio: str, cargo: str, turno: int) -> pd.DataFrame:
    """Votos por candidato (Nominal) e legenda, com % dos validos (nominais + legenda)."""
    d = bu[(bu["cd_municipio"] == cd_municipio) & (bu["cargo"] == cargo) & (bu["turno"] == turno)
           & bu["tipo_votavel"].isin(["Nominal", "Legenda"])]
    t = (d.groupby(["tipo_votavel", "nr_votavel", "nm_votavel"], as_index=False)["votos"].sum()
         .rename(columns={"nm_votavel": "candidato"}))
    validos = t["votos"].sum()
    t["pct_validos"] = (100 * t["votos"] / validos).round(2) if validos else 0.0
    t = t.sort_values(["votos", "nr_votavel"], ascending=[False, True]).reset_index(drop=True)
    return t[["tipo_votavel", "nr_votavel", "candidato", "votos", "pct_validos"]]


def state_totals(bu: pd.DataFrame, ano: int, cargo: str, turno: int) -> dict[str, int]:
    """Totais estaduais por tipo de votavel (para conferir com o site oficial)."""
    d = bu[(bu["ano"] == ano) & (bu["cargo"] == cargo) & (bu["turno"] == turno)]
    return {k: int(v) for k, v in d.groupby("tipo_votavel")["votos"].sum().items()}


# ----------------------------------------------------------------------------- resultado oficial
# Divulgacao oficial do TSE (resultados.tse.jus.br): um JSON por eleicao x abrangencia x cargo
# (Ruling R29: acesso programatico existe, entao substitui a conferencia visual da spec).

OFICIAL_BASE = "https://resultados.tse.jus.br/oficial"
CD_CARGO = {"Presidente": 1, "Governador": 3, "Senador": 5, "Deputado Federal": 6,
            "Deputado Estadual": 7, "Prefeito": 11, "Vereador": 13}
_ELEICAO = {2024: {1: 619, 2: 620}, 2026: {1: 6259, 2: 6260}}
_ELEICAO_PRESIDENTE = {1: 6257, 2: 6258}


def oficial_url(ano: int, cargo: str, turno: int, cd_municipio: str | None) -> str:
    ele = _ELEICAO_PRESIDENTE[turno] if cargo == "Presidente" else _ELEICAO[ano][turno]
    abr = f"to{cd_municipio}" if cd_municipio else "to"
    return (f"{OFICIAL_BASE}/ele{ano}/{ele}/dados/to/"
            f"{abr}-c{CD_CARGO[cargo]:04d}-e{ele:06d}-u.json")


def fetch_oficial(url: str, cache_dir: Path) -> dict:
    """Le do cache (dados_brutos/oficial/...) ou baixa uma vez; o bruto nunca e sobrescrito."""
    import os

    import requests

    dst = Path(cache_dir) / url.removeprefix(OFICIAL_BASE + "/")
    if not dst.exists():
        resp = requests.get(url, timeout=(15, 60), headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        dst.parent.mkdir(parents=True, exist_ok=True)
        tmp = dst.with_name(dst.name + ".part")
        tmp.write_bytes(resp.content)
        os.replace(tmp, dst)
    return json.loads(dst.read_bytes().decode("utf-8"))


def parse_oficial(doc: dict) -> tuple[pd.DataFrame, dict]:
    """Candidatos (nr_votavel, candidato, votos, situacao, destinacao) e totais do arquivo oficial."""
    rows, legenda = [], {}
    for carg in doc["carg"]:
        for agr in carg.get("agr", []):
            for par in agr.get("par", []):
                # tval = legenda apurada (comparavel ao BU, como vap); tvtl = legenda valida,
                # que zera em partido anulado e soma nominais convertidos para a legenda.
                if "tval" in par:
                    legenda[int(par["n"])] = int(par["tval"])
                for c in par.get("cand", []):
                    rows.append({"nr_votavel": int(c["n"]), "candidato": c.get("nmu", ""),
                                 "votos": int(c["vap"]), "situacao": c.get("st"),
                                 "destinacao": c.get("dvt")})
    v = doc["v"]
    tot = {"brancos": int(v.get("vb", 0)), "nulos": int(v.get("vn", 0)),
           "nulos_tecnicos": int(v.get("vnt", 0)), "legenda": legenda}
    cols = ["nr_votavel", "candidato", "votos", "situacao", "destinacao"]
    return pd.DataFrame(rows, columns=cols), tot


def compare_oficial(bu: pd.DataFrame, doc: dict, ano: int, cargo: str, turno: int,
                    cd_municipio: str | None) -> list[dict]:
    """Reconcilia o BU com o arquivo oficial: cada candidato listado, brancos, nulos, legenda por
    partido e nulos tecnicos (= votos nominais do BU para numeros fora da lista oficial)."""
    d = bu[(bu["ano"] == ano) & (bu["cargo"] == cargo) & (bu["turno"] == turno)]
    if cd_municipio:
        d = d[d["cd_municipio"] == cd_municipio]
    por_tipo = d.groupby(["tipo_votavel", "nr_votavel"])["votos"].sum()

    def base(tipo: str, nr: int | None = None) -> int:
        if tipo not in por_tipo.index.get_level_values(0):
            return 0
        s = por_tipo.loc[tipo]
        return int(s.sum() if nr is None else s.get(nr, 0))

    cands, tot = parse_oficial(doc)
    nominal = por_tipo.loc["Nominal"] if "Nominal" in por_tipo.index.get_level_values(0) else pd.Series(dtype=int)
    # nulo tecnico = voto nominal em numero fora da lista oficial + legenda de partido fora dela
    leg_bu = (por_tipo.loc["Legenda"] if "Legenda" in por_tipo.index.get_level_values(0)
              else pd.Series(dtype=int))
    fora = (int(nominal[~nominal.index.isin(cands["nr_votavel"])].sum())
            + int(leg_bu[~leg_bu.index.isin(list(tot["legenda"]))].sum()))
    pares = [(f"{r.nr_votavel} {r.candidato}", r.votos, base("Nominal", r.nr_votavel))
             for r in cands.itertuples()]
    pares += [("BRANCOS", tot["brancos"], base("Branco")), ("NULOS", tot["nulos"], base("Nulo")),
              ("NULOS_TECNICOS", tot["nulos_tecnicos"], fora)]
    pares += [(f"LEGENDA {p}", v, base("Legenda", p)) for p, v in sorted(tot["legenda"].items())]
    consulta = f"{doc.get('dg', '')} {doc.get('hg', '')}".strip()
    return [{"ano": ano, "cargo": cargo, "turno": turno, "cd_municipio": cd_municipio or "TO",
             "candidato": nome, "votos_site": int(site), "votos_base": int(b), "ok": int(site) == int(b),
             "data_consulta": consulta} for nome, site, b in pares]


def _visual(path: Path) -> tuple[int, pd.DataFrame]:
    """Ruling R6: sem o arquivo a conferencia visual nao foi feita e a camada reprova."""
    path = Path(path)
    if not path.exists():
        return 0, pd.DataFrame([{"motivo": "arquivo_ausente"}], columns=VISUAL_COLS)
    data = pd.DataFrame(json.loads(path.read_text(encoding="utf-8")))
    if data.empty:
        return 0, pd.DataFrame([{"motivo": "arquivo_vazio"}], columns=VISUAL_COLS)
    bad = data[data["ok"] != True].copy()  # noqa: E712 (ok ausente/nulo tambem reprova)
    bad["motivo"] = "divergente"
    return len(data), bad.reindex(columns=VISUAL_COLS)


def run(bu: pd.DataFrame, munzona: pd.DataFrame, visual_path: Path, exceptions: list[dict]) -> list[LayerResult]:
    w = prefeito_winners(bu, munzona)
    n_vis, vis = _visual(visual_path)
    return [
        make_result(LAYER, "prefeito_winners", len(w), w[~w["ok"]], exceptions),
        make_result(LAYER, "visual_amostra", n_vis, vis, exceptions),
    ]
