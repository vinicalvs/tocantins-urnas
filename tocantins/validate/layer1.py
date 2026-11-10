"""Camada 1: integridade (hashes, contagem de linhas, municipios, duplicatas, 2o turno de Prefeito)."""
import json
import re
import zipfile
from pathlib import Path

import pandas as pd

from tocantins.download import sha512_file
from tocantins.validate.result import LayerResult, make_result

LAYER = "1"
N_MUNICIPIOS = 139
PREFEITO = 11
# Cargos com 2o turno possivel em todos os municipios (eleicao estadual/nacional).
CARGOS_T2_ESTADUAIS = {1, 3}  # Presidente, Governador
# Cargos que precisam estar no turno 1 de cada ano (spec secao 2 + docs/fontes.md).
EXPECTED_CARGOS = {2024: {11, 13}, 2026: {1, 3, 5, 6, 7}}
# 2o turno de Prefeito so em municipio com mais de 200 mil eleitores (Ruling R16).
LIMIAR_ELEITORES_T2 = 200_000
DUP_KEY = ["ano", "turno", "cd_municipio", "zona", "secao", "cd_cargo", "tipo_votavel", "nr_votavel"]
_BU_KEY = re.compile(r"^bu(\d{2})_t(\d)$")


def _df(rows: list[dict], columns: list[str]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=columns)


def check_hash_manifest(manifest: dict) -> tuple[int, pd.DataFrame]:
    """Recalcula o SHA-512 de cada zip e compara com o manifesto e com o hash publicado."""
    rows = []
    for key, e in manifest.items():
        path = Path(e["path"])
        if not path.exists():
            rows.append({"key": key, "motivo": "arquivo_ausente", "sha512_calculado": None})
            continue
        digest = sha512_file(path)
        if digest.lower() != str(e["sha512"]).lower():
            rows.append({"key": key, "motivo": "sha512_difere_manifesto", "sha512_calculado": digest})
        pub = e.get("published_sha512")
        if pub is not None and digest.lower() != str(pub).lower():
            rows.append({"key": key, "motivo": "sha512_difere_publicado", "sha512_calculado": digest})
    return len(manifest), _df(rows, ["key", "motivo", "sha512_calculado"])


def _csv_rows_in_zip(path: Path) -> int:
    """Linhas de dados (sem cabecalho) dos CSV dentro do zip, lidas em blocos."""
    total = 0
    with zipfile.ZipFile(path) as zf:
        for name in zf.namelist():
            if not name.lower().endswith(".csv"):
                continue
            n, last = 0, b"\n"
            with zf.open(name) as f:
                for chunk in iter(lambda: f.read(1 << 20), b""):
                    n += chunk.count(b"\n")
                    last = chunk[-1:]
            if last != b"\n":
                n += 1
            total += max(n - 1, 0)
    return total


def check_row_counts(manifest: dict, bu: pd.DataFrame) -> tuple[int, pd.DataFrame]:
    """Linhas do CSV de cada zip de BU = linhas da base para o mesmo (ano, turno)."""
    base = bu.groupby(["ano", "turno"]).size()
    rows, n = [], 0
    for key, e in sorted(manifest.items()):
        m = _BU_KEY.match(key)
        if not m:
            continue
        n += 1
        ano, turno = 2000 + int(m.group(1)), int(m.group(2))
        csv_n = _csv_rows_in_zip(Path(e["path"])) if Path(e["path"]).exists() else None
        base_n = int(base.get((ano, turno), 0))
        if csv_n != base_n:
            rows.append({"ano": ano, "turno": turno, "key": key, "linhas_csv": csv_n, "linhas_base": base_n})
    return n, _df(rows, ["ano", "turno", "key", "linhas_csv", "linhas_base"])


def check_municipios(bu: pd.DataFrame, expected_cargos: dict[int, set[int]]) -> tuple[int, pd.DataFrame]:
    """Ruling R17: turno 1 de todo cargo esperado e turno 2 de Governador/Presidente com 139
    municipios; turno 2 de Prefeito nao vazio (o conjunto e conferido em t2_subset_of_t1);
    nenhum outro cargo no turno 2."""
    cols = ["ano", "turno", "cd_cargo", "n_municipios", "esperado"]
    counts = bu.groupby(["ano", "turno", "cd_cargo"])["cd_municipio"].nunique()
    rows = []
    for (ano, turno, cargo), n in counts.items():
        if turno == 1 or cargo in CARGOS_T2_ESTADUAIS:
            if n != N_MUNICIPIOS:
                rows.append({"ano": ano, "turno": turno, "cd_cargo": cargo, "n_municipios": n,
                             "esperado": str(N_MUNICIPIOS)})
        elif cargo != PREFEITO:
            rows.append({"ano": ano, "turno": turno, "cd_cargo": cargo, "n_municipios": n,
                         "esperado": "cargo sem 2o turno"})
    present = {(a, c) for a, t, c in counts.index if t == 1}
    for ano, cargos in sorted(expected_cargos.items()):
        for cargo in sorted(cargos):
            if (ano, cargo) not in present:
                rows.append({"ano": ano, "turno": 1, "cd_cargo": cargo, "n_municipios": 0,
                             "esperado": str(N_MUNICIPIOS)})
    return len(counts), _df(rows, cols)


def check_no_duplicates(bu: pd.DataFrame) -> tuple[int, pd.DataFrame]:
    dup = bu[bu.duplicated(DUP_KEY, keep=False)]
    div = dup.groupby(DUP_KEY, dropna=False).size().rename("n_linhas").reset_index()
    return len(bu), div


def check_t2_subset(bu: pd.DataFrame) -> tuple[int, pd.DataFrame]:
    """Ruling R16: Prefeito tem 2o turno exatamente nos municipios com mais de 200 mil
    eleitores (aptos do T1) em que nenhum candidato teve mais de 50% dos votos validos."""
    cols = ["ano", "cd_municipio", "motivo", "maior_pct_validos", "eleitorado_t1"]
    pref = bu[bu["cd_cargo"] == PREFEITO]
    t1 = pref[pref["turno"] == 1]
    if t1.empty:
        return 0, _df([], cols)
    eleitorado = (t1.drop_duplicates(["ano", "cd_municipio", "zona", "secao"])
                  .groupby(["ano", "cd_municipio"])["aptos"].sum())
    nom = t1[t1["tipo_votavel"] == "Nominal"]
    por_cand = nom.groupby(["ano", "cd_municipio", "nr_votavel"])["votos"].sum()
    validos = por_cand.groupby(level=[0, 1]).sum()
    maior = por_cand.groupby(level=[0, 1]).max()
    pct = (maior / validos).reindex(eleitorado.index)
    exige = (eleitorado > LIMIAR_ELEITORES_T2) & ~(pct > 0.5)
    tem_t2 = set(map(tuple, pref.loc[pref["turno"] == 2, ["ano", "cd_municipio"]]
                     .drop_duplicates().itertuples(index=False)))
    rows = []
    for idx in eleitorado.index:
        motivo = None
        if idx in tem_t2 and not exige[idx]:
            motivo = "t2_indevido"
        elif idx not in tem_t2 and exige[idx]:
            motivo = "t2_ausente"
        if motivo:
            rows.append({"ano": idx[0], "cd_municipio": idx[1], "motivo": motivo,
                         "maior_pct_validos": float(pct[idx]) if pd.notna(pct[idx]) else None,
                         "eleitorado_t1": int(eleitorado[idx])})
    for ano, mun in sorted(tem_t2 - set(eleitorado.index)):
        rows.append({"ano": ano, "cd_municipio": mun, "motivo": "t2_sem_t1",
                     "maior_pct_validos": None, "eleitorado_t1": None})
    return len(eleitorado), _df(rows, cols)


def check_exclusoes(exclusoes_path: Path | None, exceptions: list[dict]) -> tuple[int, pd.DataFrame]:
    """Ruling R18: lista as exclusoes da normalizacao; cada (source, reason) precisa de excecao."""
    cols = ["source", "reason", "n_rows"]
    if exclusoes_path is None or not Path(exclusoes_path).exists():
        return 0, _df([], cols)
    data = json.loads(Path(exclusoes_path).read_text(encoding="utf-8"))
    return len(data), _df([{c: e.get(c) for c in cols} for e in data], cols)


def run(manifest_path: Path, bu: pd.DataFrame, exceptions: list[dict] = (),
        exclusoes_path: Path | None = None,
        expected_cargos: dict[int, set[int]] = EXPECTED_CARGOS) -> list[LayerResult]:
    """Roda os checks da camada 1. `bu` precisa das colunas ano, turno, cd_cargo, cd_municipio,
    zona, secao, aptos, tipo_votavel, nr_votavel, votos."""
    exceptions = list(exceptions)
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    checks = [
        ("hash_manifest", check_hash_manifest(manifest)),
        ("row_counts", check_row_counts(manifest, bu)),
        ("municipios_139", check_municipios(bu, expected_cargos)),
        ("no_duplicates", check_no_duplicates(bu)),
        ("t2_subset_of_t1", check_t2_subset(bu)),
        ("exclusoes_registradas", check_exclusoes(exclusoes_path, exceptions)),
    ]
    return [make_result(LAYER, name, n, div, exceptions) for name, (n, div) in checks]


BU_COLUMNS = ["ano", "turno", "cd_cargo", "cd_municipio", "zona", "secao", "aptos",
              "tipo_votavel", "nr_votavel", "votos"]
