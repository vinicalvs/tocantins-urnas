"""Caso de controle: Palmas (73440) turno 1 reproduz os votos de B24.pkl/B26.pkl do projeto anterior."""
from pathlib import Path

import pandas as pd

from tocantins.validate.result import LayerResult, make_result

LAYER = "controle"
PALMAS = "73440"
KEY = ["ano", "cargo", "zona", "secao", "tipo_votavel", "nr_votavel"]
BU_COLUMNS = ["ano", "turno", "cd_municipio", "cargo", "zona", "secao", "tipo_votavel", "nr_votavel", "votos"]


def _load_pickle(path: Path, ano: int) -> pd.DataFrame:
    """Le o pickle do projeto antigo (so leitura) no formato da base."""
    d = pd.read_pickle(path)
    d = d[(d["CD_MUNICIPIO"].astype(str) == PALMAS) & (d["NR_TURNO"].astype(str) == "1")]
    return pd.DataFrame({
        "ano": ano, "cargo": d["DS_CARGO_PERGUNTA"].astype(str),
        "zona": d["NR_ZONA"].astype("int64"), "secao": d["NR_SECAO"].astype("int64"),
        "tipo_votavel": d["DS_TIPO_VOTAVEL"].astype(str), "nr_votavel": d["NR_VOTAVEL"].astype("int64"),
        "votos": d["QT_VOTOS"].astype("int64"),
    })


def palmas_control(bu: pd.DataFrame, palmas_dir: Path, exceptions: list[dict] = ()) -> LayerResult:
    """Compara, por (ano, cargo, zona, secao, tipo, numero), os votos de Palmas turno 1."""
    palmas_dir = Path(palmas_dir)
    ctrl = pd.concat([_load_pickle(palmas_dir / "B24.pkl", 2024), _load_pickle(palmas_dir / "B26.pkl", 2026)])
    ctrl = ctrl.groupby(KEY, as_index=False)["votos"].sum()
    base = bu[(bu["cd_municipio"] == PALMAS) & (bu["turno"] == 1)
              & bu["ano"].isin(ctrl["ano"].unique())]
    base = base.groupby(KEY, as_index=False)["votos"].sum()
    m = base.merge(ctrl, on=KEY, how="outer", suffixes=("_base", "_controle"))
    m[["votos_base", "votos_controle"]] = m[["votos_base", "votos_controle"]].fillna(0).astype("int64")
    div = m[m["votos_base"] != m["votos_controle"]].reset_index(drop=True)
    return make_result(LAYER, "palmas_turno1", len(m), div, list(exceptions))


def fora_do_controle(bu: pd.DataFrame) -> list[str]:
    """Turnos de Palmas alem do 1o (nao cobertos pelos pickles): reportados, nunca reprovados."""
    p = bu.loc[(bu["cd_municipio"] == PALMAS) & (bu["turno"] != 1), ["ano", "turno"]].drop_duplicates()
    return [f"{a} turno {t}" for a, t in sorted(map(tuple, p.values.tolist()))]
