"""Normaliza as fontes brutas (dados_brutos/) para Parquet em base/.

Uso: python -I scripts/02_normalizar.py [--so-bu]

Task 3 cobre so o BU (`base/bu_secao.parquet`); as demais fontes entram nas
proximas tasks. Os CSV sao dado nao confiavel: so sao lidos como texto.
"""
import argparse
import sys
from pathlib import Path

# Com `python -I` o diretorio do script nao entra em sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tocantins.config import BASE, RAW  # noqa: E402
from tocantins.normalize import normalize_bu  # noqa: E402

BU_KEYS = ["bu24_t1", "bu24_t2", "bu26_t1", "bu26_t2"]


def bu_csvs() -> list[Path]:
    files = []
    for key in BU_KEYS:
        found = sorted((RAW / key).glob("bweb_*_TO_*.csv"))
        if len(found) != 1:
            raise SystemExit(f"{key}: esperado 1 CSV de BU em {RAW / key}, achei {len(found)}; rode 01_baixar.py")
        files.append(found[0])
    return files


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--so-bu", action="store_true", help="normaliza apenas o BU")
    ap.parse_args()  # por ora so o BU existe, com ou sem --so-bu

    files = bu_csvs()
    out = BASE / "bu_secao.parquet"
    print(f"BU: {len(files)} CSV -> {out}")
    n = normalize_bu(files, out)
    print(f"BU: {n} linhas gravadas")


if __name__ == "__main__":
    main()
