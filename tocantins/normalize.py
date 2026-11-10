"""Normalizacao das fontes do TSE para Parquet (camada `base/`).

Regra de encoding: os CSV do TSE sao latin-1. Cada arquivo e decodificado
exatamente uma vez, em streaming (blocos de 1 MB), para um UTF-8 temporario;
so entao o DuckDB le o texto (`all_varchar=true`). Nunca pandas no arquivo todo.
"""
import codecs
import csv
import json
import os
import tempfile
from pathlib import Path

import duckdb

BLOCK_SIZE = 1024 * 1024  # 1 MB

# Cabecalho real do BU (45 colunas, identico em 2024/2026 T1/T2; docs/fontes.md 4.1).
BU_COLUMNS = [
    "DT_GERACAO", "HH_GERACAO", "ANO_ELEICAO", "CD_TIPO_ELEICAO", "NM_TIPO_ELEICAO", "CD_PLEITO",
    "DT_PLEITO", "NR_TURNO", "CD_ELEICAO", "DS_ELEICAO", "SG_UF", "CD_MUNICIPIO", "NM_MUNICIPIO",
    "NR_ZONA", "NR_SECAO", "NR_LOCAL_VOTACAO", "CD_CARGO_PERGUNTA", "DS_CARGO_PERGUNTA",
    "NR_PARTIDO", "SG_PARTIDO", "NM_PARTIDO", "DT_BU_RECEBIDO", "QT_APTOS", "QT_COMPARECIMENTO",
    "QT_ABSTENCOES", "CD_TIPO_URNA", "DS_TIPO_URNA", "CD_TIPO_VOTAVEL", "DS_TIPO_VOTAVEL",
    "NR_VOTAVEL", "NM_VOTAVEL", "QT_VOTOS", "NR_URNA_EFETIVADA", "CD_CARGA_1_URNA_EFETIVADA",
    "CD_CARGA_2_URNA_EFETIVADA", "CD_FLASHCARD_URNA_EFETIVADA", "DT_CARGA_URNA_EFETIVADA",
    "DS_CARGO_PERGUNTA_SECAO", "DS_SECOES_AGREGADAS", "DT_ABERTURA", "DT_ENCERRAMENTO",
    "QT_ELEI_BIOM_SEM_HABILITACAO", "DT_EMISSAO_BU", "NR_JUNTA_APURADORA", "NR_TURMA_APURADORA",
]

# Valores canonicos de `tipo_votavel` na base.
TIPO_VOTAVEL_VALORES = ("Nominal", "Legenda", "Branco", "Nulo", "Anulado")

# (CD_TIPO_VOTAVEL, DS_TIPO_VOTAVEL) reais do BU -> tipo_votavel canonico
# (docs/fontes.md 4.1, tabela de CD/DS_TIPO_VOTAVEL). Os 4 arquivos so trazem
# estes 4 pares; "Anulado" existe no vocabulario da base (totalizacao) mas
# nenhum codigo do BU o produz. Par desconhecido => ValueError, nunca passa calado.
TIPO_VOTAVEL_MAP = {
    ("1", "Nominal"): "Nominal",
    ("2", "Branco"): "Branco",
    ("3", "Nulo"): "Nulo",
    ("4", "Legenda"): "Legenda",
}

# Sentinelas de "ausente" nas colunas de codigo/identificacao (NUNCA em QT_VOTOS).
NULL_TOKENS = ("#NULO#", "#NULO", "#NE", "-1", "-3")


def to_utf8(src: Path, dst: Path, block_size: int = BLOCK_SIZE) -> Path:
    """Decodifica `src` (latin-1) uma unica vez e grava UTF-8 em `dst`, em blocos."""
    decoder = codecs.getincrementaldecoder("latin-1")()
    with open(src, "rb") as fin, open(dst, "w", encoding="utf-8", newline="") as fout:
        while True:
            block = fin.read(block_size)
            if not block:
                break
            fout.write(decoder.decode(block))
        fout.write(decoder.decode(b"", final=True))
    return dst


def _check_header(utf8_csv: Path, original: Path) -> None:
    with open(utf8_csv, encoding="utf-8", newline="") as f:
        header = next(csv.reader(f, delimiter=";", quotechar='"'), [])
    if header != BU_COLUMNS:
        raise ValueError(
            f"{original.name}: cabecalho do BU diferente do esperado "
            f"({len(header)} colunas contra {len(BU_COLUMNS)}); "
            f"faltam {sorted(set(BU_COLUMNS) - set(header))}, sobram {sorted(set(header) - set(BU_COLUMNS))}"
        )


def _clean(col: str) -> str:
    """Expressao SQL: sentinelas de ausente viram NULL (col varchar)."""
    toks = ", ".join(f"'{t}'" for t in NULL_TOKENS)
    return f'(CASE WHEN trim("{col}") IN ({toks}) THEN NULL ELSE "{col}" END)'


def _int(col: str) -> str:
    return f"CAST({_clean(col)} AS INTEGER)"


def _write_exclusoes(path: Path, exclusoes: list[dict]) -> None:
    path.write_text(json.dumps(exclusoes, ensure_ascii=False, indent=2), encoding="utf-8")


def normalize_bu(csv_files: list[Path], out_parquet: Path) -> int:
    """Une os CSV de BU (latin-1) num unico Parquet; devolve as linhas gravadas.

    Nenhuma linha e removida. `exclusoes.json` (ao lado do Parquet) e gravado
    sempre, com a lista {"reason","source","n_rows"} de linhas descartadas
    (vazia para o BU).
    """
    csv_files = [Path(f) for f in csv_files]
    out_parquet = Path(out_parquet)
    out_parquet.parent.mkdir(parents=True, exist_ok=True)

    exclusoes = out_parquet.parent / "exclusoes.json"
    tmp_parquet = out_parquet.with_name(out_parquet.name + ".tmp")
    tmp_exclusoes = exclusoes.with_name(exclusoes.name + ".tmp")
    try:
        with tempfile.TemporaryDirectory(prefix="tocantins_utf8_") as tmp:
            utf8_files = []
            for i, src in enumerate(csv_files):
                dst = to_utf8(src, Path(tmp) / f"{i}.csv")
                _check_header(dst, src)
                utf8_files.append(str(dst))

            con = duckdb.connect()
            try:
                lista = "[" + ", ".join("'" + f.replace("'", "''") + "'" for f in utf8_files) + "]"
                con.execute(
                    f"CREATE VIEW raw AS SELECT * FROM read_csv({lista}, delim=';', quote='\"', "
                    "escape='\"', header=true, all_varchar=true)"
                )
                n_in = con.execute("SELECT count(*) FROM raw").fetchone()[0]

                pares = ", ".join(f"('{c}', '{d}')" for c, d in TIPO_VOTAVEL_MAP)
                desconhecidos = con.execute(
                    "SELECT DISTINCT CD_TIPO_VOTAVEL, DS_TIPO_VOTAVEL FROM raw "
                    f"WHERE (CD_TIPO_VOTAVEL, DS_TIPO_VOTAVEL) NOT IN ({pares}) "
                    "OR CD_TIPO_VOTAVEL IS NULL OR DS_TIPO_VOTAVEL IS NULL"
                ).fetchall()
                if desconhecidos:
                    raise ValueError(
                        "CD/DS_TIPO_VOTAVEL sem mapeamento em TIPO_VOTAVEL_MAP: "
                        + ", ".join(f"({c!r}, {d!r})" for c, d in desconhecidos)
                    )
                case = " ".join(
                    f"WHEN CD_TIPO_VOTAVEL = '{c}' AND DS_TIPO_VOTAVEL = '{d}' THEN '{v}'"
                    for (c, d), v in TIPO_VOTAVEL_MAP.items()
                )

                select = f"""
                    SELECT
                        CAST(ANO_ELEICAO AS INTEGER)            AS ano,
                        CAST(NR_TURNO AS INTEGER)               AS turno,
                        CAST(CD_ELEICAO AS INTEGER)             AS cd_eleicao,
                        CAST(CD_CARGO_PERGUNTA AS INTEGER)      AS cd_cargo,
                        {_clean('DS_CARGO_PERGUNTA')}           AS cargo,
                        {_clean('CD_MUNICIPIO')}                AS cd_municipio,
                        {_clean('NM_MUNICIPIO')}                AS nm_municipio,
                        CAST(NR_ZONA AS INTEGER)                AS zona,
                        CAST(NR_SECAO AS INTEGER)               AS secao,
                        {_int('NR_LOCAL_VOTACAO')}              AS "local",
                        CAST(QT_APTOS AS INTEGER)               AS aptos,
                        CAST(QT_COMPARECIMENTO AS INTEGER)      AS comparecimento,
                        CAST(QT_ABSTENCOES AS INTEGER)          AS abstencoes,
                        CAST(CD_TIPO_URNA AS INTEGER)           AS cd_tipo_urna,
                        CASE {case} END                         AS tipo_votavel,
                        {_int('NR_VOTAVEL')}                    AS nr_votavel,
                        {_clean('NM_VOTAVEL')}                  AS nm_votavel,
                        {_int('NR_PARTIDO')}                    AS nr_partido,
                        {_clean('SG_PARTIDO')}                  AS sg_partido,
                        CAST(QT_VOTOS AS INTEGER)               AS votos,
                        {_clean('DS_SECOES_AGREGADAS')}         AS secoes_agregadas
                    FROM raw
                """
                con.sql(select).write_parquet(str(tmp_parquet), compression="zstd")
                n_out = con.execute("SELECT count(*) FROM read_parquet(?)", [str(tmp_parquet)]).fetchone()[0]
            finally:
                con.close()

        if n_out != n_in:
            raise RuntimeError(f"BU: {n_in} linhas lidas, {n_out} gravadas (nada deveria ser removido)")
        _write_exclusoes(tmp_exclusoes, [])
        # So aqui as saidas anteriores sao substituidas (Parquet primeiro, depois exclusoes.json).
        os.replace(tmp_parquet, out_parquet)
        os.replace(tmp_exclusoes, exclusoes)
        return n_out
    except BaseException:
        # Falha em qualquer ponto: saidas anteriores intactas, sem temporarios.
        tmp_parquet.unlink(missing_ok=True)
        tmp_exclusoes.unlink(missing_ok=True)
        raise
