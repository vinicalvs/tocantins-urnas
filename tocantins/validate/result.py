"""Framework comum das camadas: resultado, excecoes registradas, comparacao e relatorio."""
import json
import os
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

EXCEPTION_FIELDS = ("layer", "check", "key", "cause", "approved_on")
EMPTY_CSV_HEADER = "sem_divergencias"


@dataclass
class LayerResult:
    layer: str
    check: str
    passed: bool
    n_checked: int
    divergences: pd.DataFrame
    unregistered: int


def make_result(layer: str, check: str, n_checked: int, div: pd.DataFrame,
                exceptions: list[dict]) -> LayerResult:
    """Monta o resultado: passa so se toda divergencia estiver coberta por excecao registrada."""
    left = apply_exceptions(div, layer, check, exceptions)
    return LayerResult(layer, check, left.empty, int(n_checked), div.reset_index(drop=True), len(left))


def _validate_exception(e, i: int) -> None:
    if not isinstance(e, dict):
        raise ValueError(f"excecao {i}: deve ser objeto, nao {type(e).__name__}")
    missing = [f for f in EXCEPTION_FIELDS if f not in e]
    if missing:
        raise ValueError(f"excecao {i}: campos faltando {missing}")
    for f in ("layer", "check", "cause", "approved_on"):
        if not isinstance(e[f], str) or not e[f].strip():
            raise ValueError(f"excecao {i}: '{f}' deve ser texto nao vazio")
    if not isinstance(e["key"], dict) or not e["key"]:
        raise ValueError(f"excecao {i}: 'key' deve ser objeto nao vazio (chave vazia cobriria tudo)")


def load_exceptions(path: Path) -> list[dict]:
    """Le `excecoes.json`; arquivo ausente = nenhuma excecao. Entrada mal formada levanta ValueError."""
    path = Path(path)
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"{path}: esperada uma lista de excecoes")
    for i, e in enumerate(data):
        _validate_exception(e, i)
    return data


def apply_exceptions(div: pd.DataFrame, layer: str, check: str, exceptions: list[dict]) -> pd.DataFrame:
    """Devolve so as divergencias NAO cobertas por excecao desta camada e check.

    Uma excecao cobre a linha cujas colunas coincidem com todos os pares de `key`;
    se alguma coluna de `key` nao existe em `div`, a excecao nao cobre nada.
    """
    for i, e in enumerate(exceptions):
        _validate_exception(e, i)
    covered = pd.Series(False, index=div.index)
    for e in exceptions:
        if e["layer"] != layer or e["check"] != check:
            continue
        if not set(e["key"]) <= set(div.columns):
            continue
        m = pd.Series(True, index=div.index)
        for col, val in e["key"].items():
            m &= div[col] == val
        covered |= m
    return div[~covered].reset_index(drop=True)


def compare_impls(a: pd.DataFrame, b: pd.DataFrame, key: list[str]) -> pd.DataFrame:
    """Diferenca simetrica por chave entre duas implementacoes; vazio = concordam.

    Saida: colunas de `key`, `lado` (`so_a` | `so_b` | `valor_diferente`) e, para cada
    coluna de valor `v`, `v_a` e `v_b`. Comparacao exata; NaN = NaN.
    """
    if set(a.columns) != set(b.columns):
        raise ValueError(f"colunas diferentes: {sorted(a.columns)} x {sorted(b.columns)}")
    for name, df in (("a", a), ("b", b)):
        if df.duplicated(key).any():
            raise ValueError(f"chave duplicada na implementacao {name}")
    values = [c for c in a.columns if c not in key]
    m = a.merge(b, on=key, how="outer", suffixes=("_a", "_b"), indicator=True)
    lado = pd.Series(None, index=m.index, dtype=object)
    lado[m["_merge"] == "left_only"] = "so_a"
    lado[m["_merge"] == "right_only"] = "so_b"
    both = m["_merge"] == "both"
    diff = pd.Series(False, index=m.index)
    for c in values:
        va, vb = m[f"{c}_a"], m[f"{c}_b"]
        diff |= ~((va == vb) | (va.isna() & vb.isna()))
    lado[both & diff] = "valor_diferente"
    m["lado"] = lado
    cols = key + ["lado"] + [f"{c}_{s}" for c in values for s in ("a", "b")]
    return m.loc[m["lado"].notna(), cols].sort_values(key).reset_index(drop=True)


def _atomic_write(path: Path, text: str) -> None:
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def write_report(results: list[LayerResult], out_dir: Path) -> None:
    """Grava `camada<N>.json` por camada e `divergencias_<check>.csv` por check (escrita atomica)."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    layers: dict[str, list[LayerResult]] = {}
    for r in results:
        layers.setdefault(r.layer, []).append(r)
        div = r.divergences
        csv = div.to_csv(index=False) if len(div.columns) else EMPTY_CSV_HEADER + "\n"
        _atomic_write(out_dir / f"divergencias_{r.check}.csv", csv)
    for layer, rs in layers.items():
        doc = {
            "layer": layer,
            "passed": all(r.passed for r in rs),
            "checks": [
                {"check": r.check, "passed": bool(r.passed), "n_checked": int(r.n_checked),
                 "n_divergences": len(r.divergences), "unregistered": int(r.unregistered)}
                for r in rs
            ],
        }
        _atomic_write(out_dir / f"camada{layer}.json", json.dumps(doc, ensure_ascii=False, indent=2))


def load_bu_columns(parquet: Path, columns: list[str]) -> pd.DataFrame:
    """Le do Parquet do BU so as colunas pedidas (Ruling R5)."""
    return pd.read_parquet(parquet, columns=columns)
