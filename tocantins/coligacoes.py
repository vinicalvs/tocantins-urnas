"""Partidos de cada candidatura: o proprio partido + a coligacao + as federacoes citadas.

Formatos reais (consulta_cand 2026, docs/fontes.md secao 6.2):
- composicao da coligacao: "MDB / FEDERAÇÃO PSDB CIDADANIA (45-PSDB / 23-CIDADANIA)"
- composicao da federacao: "44-UNIÃO/11-PP"
"""
import re
import unicodedata

import pandas as pd


def norm_sigla(s: str) -> str:
    """Caixa alta, sem acento e sem espacos: "PC do B" -> "PCDOB", "UNIÃO" -> "UNIAO"."""
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", "", s).upper()


def _siglas_federacao(texto: str) -> set[str]:
    """ "13-PT / 65-PC do B" -> {PT, PCDOB} (tira o numero e o hifen)."""
    out = set()
    for parte in str(texto).split("/"):
        parte = re.sub(r"^\s*\d+\s*-\s*", "", parte).strip()
        if parte:
            out.add(norm_sigla(parte))
    return out


def _vazio(x) -> bool:
    return x is None or (isinstance(x, float) and pd.isna(x)) or str(x).strip() == ""


def partidos_da_candidatura(row) -> frozenset[str]:
    partidos = {norm_sigla(row["sg_partido"])}
    comp = row.get("composicao_coligacao")
    if not _vazio(comp):
        # separa no nivel de cima por " / ", sem quebrar o que esta entre parenteses
        nivel, atual = 0, ""
        tokens = []
        for ch in str(comp):
            nivel += (ch == "(") - (ch == ")")
            if ch == "/" and nivel == 0:
                tokens.append(atual)
                atual = ""
            else:
                atual += ch
        tokens.append(atual)
        for t in tokens:
            m = re.search(r"\((.*)\)", t)
            if m:
                partidos |= _siglas_federacao(m.group(1))
            elif t.strip():
                partidos.add(norm_sigla(t))
    fed = row.get("composicao_federacao")
    if not _vazio(fed):
        partidos |= _siglas_federacao(fed)
    return frozenset(partidos)


def build(candidatos: pd.DataFrame) -> pd.DataFrame:
    """base/coligacoes.parquet: uma linha por (ano, cargo, nr_candidato), cargo no formato do BU."""
    d = candidatos.drop_duplicates(["ano", "cargo", "nr_candidato"]).copy()
    d["cargo"] = d["cargo"].str.title()
    d["partidos"] = [sorted(partidos_da_candidatura(r)) for r in d.to_dict("records")]
    return d[["ano", "cargo", "nr_candidato", "sg_partido", "partidos"]].reset_index(drop=True)
