"""Normaliza as fontes brutas (dados_brutos/) para Parquet em base/.

Uso: python -I scripts/02_normalizar.py [--so-bu]

Gera `base/bu_secao.parquet` (BU) e, sem `--so-bu`, tambem `locais`, `munzona`,
`detalhe_munzona`, `votacao_secao` e `candidatos` (2024 e 2026 unidos), alem de
`base/exclusoes.json`. Presidente 2026 so existe nos arquivos nacionais `_BR.csv`
(docs/fontes.md 2.2), que entram junto dos `_TO.csv`. Os CSV sao dado nao
confiavel: so sao lidos como texto.
"""
import argparse
import sys
from pathlib import Path

# Com `python -I` o diretorio do script nao entra em sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tocantins.config import BASE, RAW  # noqa: E402
from tocantins.normalize import (  # noqa: E402
    normalize_bu, normalize_candidatos, normalize_detalhe, normalize_locais, normalize_munzona,
    normalize_votacao_secao,
)

BU_KEYS = ["bu24_t1", "bu24_t2", "bu26_t1", "bu26_t2"]

# nome do Parquet -> (funcao, [(chave em dados_brutos/, nome do CSV)])
AUX = {
    "locais.parquet": (normalize_locais, [
        ("locais24", "eleitorado_local_votacao_2024.csv"),
        ("locais26", "eleitorado_local_votacao_2026_TO.csv"),
    ]),
    "munzona.parquet": (normalize_munzona, [
        ("munzona24", "votacao_candidato_munzona_2024_TO.csv"),
        ("munzona26", "votacao_candidato_munzona_2026_TO.csv"),
        ("munzona26", "votacao_candidato_munzona_2026_BR.csv"),  # Presidente 2026
    ]),
    "detalhe_munzona.parquet": (normalize_detalhe, [
        ("detalhe24", "detalhe_votacao_munzona_2024_TO.csv"),
        ("detalhe26", "detalhe_votacao_munzona_2026_TO.csv"),
        ("detalhe26", "detalhe_votacao_munzona_2026_BR.csv"),  # Presidente 2026
    ]),
    "votacao_secao.parquet": (normalize_votacao_secao, [
        ("secao24", "votacao_secao_2024_TO.csv"),
        ("secao26", "votacao_secao_2026_TO.csv"),
    ]),
    "candidatos.parquet": (normalize_candidatos, [
        ("cand24", "consulta_cand_2024_TO.csv"),
        ("cand26", "consulta_cand_2026_TO.csv"),
        ("cand26", "consulta_cand_2026_BR.csv"),  # Presidente/Vice 2026 (SG_UF='BR')
    ]),
}


def bu_csvs() -> list[Path]:
    files = []
    for key in BU_KEYS:
        found = sorted((RAW / key).glob("bweb_*_TO_*.csv"))
        if len(found) != 1:
            raise SystemExit(f"{key}: esperado 1 CSV de BU em {RAW / key}, achei {len(found)}; rode 01_baixar.py")
        files.append(found[0])
    return files


def aux_csvs(spec: list[tuple[str, str]]) -> list[Path]:
    files = [RAW / key / name for key, name in spec]
    missing = [str(f) for f in files if not f.is_file()]
    if missing:
        raise SystemExit("CSV ausente(s): " + ", ".join(missing) + "; rode 01_baixar.py")
    return files


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--so-bu", action="store_true", help="normaliza apenas o BU")
    args = ap.parse_args()

    files = bu_csvs()
    out = BASE / "bu_secao.parquet"
    print(f"BU: {len(files)} CSV -> {out}")
    print(f"BU: {normalize_bu(files, out)} linhas gravadas")
    if args.so_bu:
        return

    for name, (fn, spec) in AUX.items():
        files = aux_csvs(spec)
        out = BASE / name
        print(f"{name}: {len(files)} CSV -> {out}")
        print(f"{name}: {fn(files, out)} linhas gravadas")
    print(f"exclusoes registradas em {BASE / 'exclusoes.json'}")


if __name__ == "__main__":
    main()
