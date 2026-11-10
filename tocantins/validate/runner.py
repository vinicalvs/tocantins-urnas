"""Roda as 4 camadas + o controle Palmas e grava relatorio e selo de validacao."""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pandas as pd

from tocantins.config import PALMAS_DIR
from tocantins.validate import control, layer1, layer2, layer3, layer4
from tocantins.validate.result import LayerResult, apply_exceptions, load_bu_columns, load_exceptions, write_report

VISUAL_FILE = "camada4_oficial.json"


def _bu_columns() -> list[str]:
    cols: list[str] = []
    for c in layer1.BU_COLUMNS + layer2.BU_COLUMNS + layer3.BU_COLUMNS + layer4.BU_COLUMNS + control.BU_COLUMNS:
        if c not in cols:
            cols.append(c)
    return cols


def load_inputs(base: Path) -> dict[str, pd.DataFrame]:
    base = Path(base)
    return {
        "bu": load_bu_columns(base / "bu_secao.parquet", _bu_columns()),
        "locais": load_bu_columns(base / "locais.parquet", layer2.LOCAIS_COLUMNS),
        "munzona": load_bu_columns(base / "munzona.parquet",
                                   sorted(set(layer3.MUNZONA_COLUMNS + layer4.MUNZONA_COLUMNS))),
        "votacao_secao": load_bu_columns(base / "votacao_secao.parquet", layer3.SECAO_COLUMNS),
        "detalhe": load_bu_columns(base / "detalhe_munzona.parquet", layer3.DETALHE_COLUMNS),
    }


def run_all(base: Path, valid_dir: Path, raw_manifest: Path, palmas_dir: Path = PALMAS_DIR,
            inputs: dict[str, pd.DataFrame] | None = None) -> list[LayerResult]:
    """Roda camadas 1-4 e o controle; grava `camada<N>.json` e `divergencias_*.csv` em `valid_dir`."""
    base, valid_dir = Path(base), Path(valid_dir)
    exc = load_exceptions(valid_dir / "excecoes.json")
    d = inputs or load_inputs(base)
    con = duckdb.connect()
    for name in ("bu", "locais", "munzona", "votacao_secao", "detalhe"):
        con.register(name, d[name])
    results = []
    results += layer1.run(raw_manifest, d["bu"], exc, exclusoes_path=base / "exclusoes.json")
    results += layer2.run(d["bu"], d["locais"], con, exc)
    results += layer3.run(d["bu"], d["munzona"], d["votacao_secao"], d["detalhe"], con, exc)
    results += layer4.run(d["bu"], d["munzona"], valid_dir / VISUAL_FILE, exc)
    results.append(control.palmas_control(d["bu"], palmas_dir, exc))
    write_report(results, valid_dir)
    return results


def _used(e: dict, results: list[LayerResult]) -> bool:
    for r in results:
        if r.layer == e["layer"] and r.check == e["check"] and len(r.divergences):
            if len(apply_exceptions(r.divergences, r.layer, r.check, [e])) < len(r.divergences):
                return True
    return False


def write_seal(results: list[LayerResult], path: Path, manifest_path: Path | None = None,
               exceptions: list[dict] = (), extra: dict | None = None) -> dict:
    """Grava o selo: status ok so se todos os checks passaram (divergencias cobertas por excecao)."""
    camadas: dict[str, bool] = {}
    for r in results:
        camadas[r.layer] = camadas.get(r.layer, True) and bool(r.passed)
    hashes = {}
    if manifest_path is not None and Path(manifest_path).exists():
        man = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
        hashes = {k: v["sha512"] for k, v in sorted(man.items())}
    resumo = lambda e: {k: e[k] for k in ("layer", "check", "key", "cause", "approved_on")}  # noqa: E731
    seal = {
        "status": "ok" if all(camadas.values()) and results else "falhou",
        "data": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "camadas": camadas,
        "falhas": [{"layer": r.layer, "check": r.check, "unregistered": int(r.unregistered)}
                   for r in results if not r.passed],
        "checks": [{"layer": r.layer, "check": r.check, "passed": bool(r.passed), "n_checked": int(r.n_checked),
                    "n_divergences": len(r.divergences)} for r in results],
        "hashes": hashes,
        "excecoes_usadas": [resumo(e) for e in exceptions if _used(e, results)],
        "excecoes_nao_usadas": [resumo(e) for e in exceptions if not _used(e, results)],
        **(extra or {}),
    }
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(seal, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    return seal
