"""Codigo de municipio do TSE -> codigo IBGE de 7 digitos (por nome normalizado + overrides)."""
import json
import re
import unicodedata
from pathlib import Path

import pandas as pd

N_MUNICIPIOS = 139
OVERRIDES_PATH = Path(__file__).resolve().parent / "data" / "crosswalk_overrides.json"


def normalize_name(nome: str) -> str:
    """Sem acento, maiusculas, hifen vira espaco, espacos colapsados."""
    s = unicodedata.normalize("NFKD", nome)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s.upper().replace("-", " ")).strip()


def load_overrides(path: Path = OVERRIDES_PATH) -> dict[str, str]:
    return json.loads(Path(path).read_text(encoding="utf-8")) if Path(path).exists() else {}


def build(tse: pd.DataFrame, ibge: list[dict], overrides: dict[str, str],
          expected: int = N_MUNICIPIOS) -> dict[str, str]:
    """`tse`: colunas cd_municipio, nm_municipio. Levanta ValueError se nao houver exatamente
    `expected` correspondencias unicas (nome ausente, ambiguo ou id IBGE repetido)."""
    por_nome: dict[str, list[str]] = {}
    for m in ibge:
        por_nome.setdefault(normalize_name(m["nome"]), []).append(str(m["id"]))
    out, erros = {}, []
    for cd, nome in tse[["cd_municipio", "nm_municipio"]].drop_duplicates().itertuples(index=False):
        cd = str(cd)
        if cd in overrides:
            out[cd] = str(overrides[cd])
            continue
        ids = por_nome.get(normalize_name(nome), [])
        if len(ids) != 1:
            erros.append(f"{cd} {nome}: {len(ids)} correspondencias no IBGE")
        else:
            out[cd] = ids[0]
    if len(set(out.values())) != len(out):
        erros.append("id IBGE repetido para codigos TSE diferentes")
    if erros or len(out) != expected:
        raise ValueError(f"crosswalk com {len(out)} de {expected} municipios; " + "; ".join(erros))
    return out
