"""Normalizacao das fontes do TSE para Parquet (camada `base/`).

Regra de encoding: os CSV do TSE sao latin-1. Cada arquivo e decodificado
exatamente uma vez, em streaming (blocos de 1 MB), para um UTF-8 temporario;
so entao o DuckDB le o texto (`all_varchar=true`). Nunca pandas no arquivo todo.
"""
import codecs
import csv
import json
import os
import re
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


def _read_exclusoes(path: Path) -> list[dict]:
    """Lista atual de exclusoes (vazia se o arquivo nao existe); formato invalido falha alto."""
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list) or not all(isinstance(e, dict) and "source" in e for e in data):
        raise ValueError(f"{path}: esperado uma lista JSON de {{source, reason, n_rows}}; nao vou sobrescrever")
    return data


def _stage_exclusoes(path: Path, source: str, entries: list[dict]) -> Path:
    """Grava em `<path>.tmp` a lista com as entradas de `source` SUBSTITUIDAS por `entries`.

    Entradas de outras fontes ficam intactas. Quem chama faz o os.replace (ou usa
    `record_exclusoes`). Devolve o caminho do temporario.
    """
    path = Path(path)
    novas = [{"source": source, "reason": e["reason"], "n_rows": int(e["n_rows"])} for e in entries]
    merged = [e for e in _read_exclusoes(path) if e["source"] != source] + novas
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return tmp


def record_exclusoes(path: Path, source: str, entries: list[dict]) -> None:
    """Registra em `path` (lista JSON unica) as exclusoes de `source`, de forma atomica.

    Substitui apenas as entradas com o mesmo `source` (lista vazia limpa as da fonte);
    as de outras fontes sao preservadas. Escrita em tmp + os.replace.
    """
    path = Path(path)
    tmp = _stage_exclusoes(path, source, entries)
    os.replace(tmp, path)


def normalize_bu(csv_files: list[Path], out_parquet: Path) -> int:
    """Une os CSV de BU (latin-1) num unico Parquet; devolve as linhas gravadas.

    Nenhuma linha e removida. As entradas `source="bu"` de `exclusoes.json` (ao
    lado do Parquet) sao regravadas como lista vazia; as de outras fontes ficam.
    """
    csv_files = [Path(f) for f in csv_files]
    out_parquet = Path(out_parquet)
    out_parquet.parent.mkdir(parents=True, exist_ok=True)

    exclusoes = out_parquet.parent / "exclusoes.json"
    tmp_parquet = out_parquet.with_name(out_parquet.name + ".tmp")
    tmp_exclusoes = exclusoes.with_name(exclusoes.name + ".tmp")
    tmp_exclusoes.unlink(missing_ok=True)
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
        tmp_exclusoes = _stage_exclusoes(exclusoes, "bu", [])
        # So aqui as saidas anteriores sao substituidas (Parquet primeiro, depois exclusoes.json).
        os.replace(tmp_parquet, out_parquet)
        os.replace(tmp_exclusoes, exclusoes)
        return n_out
    except BaseException:
        # Falha em qualquer ponto: saidas anteriores intactas, sem temporarios.
        tmp_parquet.unlink(missing_ok=True)
        tmp_exclusoes.unlink(missing_ok=True)
        raise


# ---------------------------------------------------------------------------
# Fontes auxiliares (Task 4): locais, munzona, detalhe, votacao_secao, candidatos.
# O ano vem da propria coluna de cada arquivo (ANO_ELEICAO / AA_ELEICAO): os Parquet
# unem 2024 e 2026. Nenhuma linha some sem registro em `exclusoes.json`.
# ---------------------------------------------------------------------------

# CD_ELEICAO das eleicoes ordinarias por ano (docs/fontes.md 2.1, 2.3 e 4.1).
ELEICOES_ORDINARIAS = {2024: (619, 620), 2026: (6257, 6258, 6259, 6260)}

# Eleicoes fora do conjunto ordinario ja identificadas (so para a mensagem da exclusao).
ELEICOES_CONHECIDAS = {6286: "suplementar de Goiatins, 25/10/2026"}

# Limites plausiveis de latitude/longitude em Tocantins; fora disso a coordenada vira nula.
LAT_RANGE = (-14.0, -5.0)
LON_RANGE = (-51.0, -45.0)

# Em cand, o BR traz Presidente (1) e Vice-Presidente (2) com SG_UF='BR' (docs/fontes.md 2.2).
_UF_TO = "\"SG_UF\" = 'TO'"
_UF_TO_CAND = "(\"SG_UF\" = 'TO' OR (\"SG_UF\" = 'BR' AND \"CD_CARGO\" IN ('1', '2')))"


def _ws(col: str) -> str:
    """`_clean` + espacos/quebras de linha internos colapsados num so espaco."""
    return f"regexp_replace(trim({_clean(col)}), '\\s+', ' ', 'g')"


def _coord(col: str, lo: float, hi: float) -> str:
    # virgula (2026) ou ponto (2024) decimal; -1, vazio, texto ou fora do intervalo => NULL
    v = f"TRY_CAST(replace(trim(\"{col}\"), ',', '.') AS DOUBLE)"
    return f"(CASE WHEN {v} BETWEEN {lo} AND {hi} THEN {v} END)"


def _ordinaria(ano_col: str) -> str:
    termos = " OR ".join(
        f"(TRY_CAST(\"{ano_col}\" AS INTEGER) = {ano} AND TRY_CAST(\"CD_ELEICAO\" AS INTEGER) IN "
        f"({', '.join(str(c) for c in codigos)}))"
        for ano, codigos in ELEICOES_ORDINARIAS.items()
    )
    return f"({termos})"


def _normalize_aux(
    csv_files: list[Path], out: Path, *, source: str, ano_col: str, select: str,
    uf_scope: str, uf_reason: str, by_eleicao: bool = True, parallel: bool = True,
) -> int:
    csv_files = [Path(f) for f in csv_files]
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    exclusoes = out.parent / "exclusoes.json"
    tmp_parquet = out.with_name(out.name + ".tmp")
    tmp_exclusoes = exclusoes.with_name(exclusoes.name + ".tmp")
    tmp_parquet.unlink(missing_ok=True)
    tmp_exclusoes.unlink(missing_ok=True)

    ordinaria = _ordinaria(ano_col) if by_eleicao else "TRUE"
    classify = (
        f"CASE WHEN NOT coalesce({uf_scope}, false) THEN 'uf' "
        f"WHEN NOT coalesce({ordinaria}, false) THEN 'eleicao' END"
    )
    needed = set(re.findall(r'"([A-Z][A-Z0-9_]*)"', select + uf_scope + ordinaria + f'"{ano_col}"'))

    try:
        with tempfile.TemporaryDirectory(prefix="tocantins_utf8_") as tmp:
            utf8_files, headers = [], []
            for i, src in enumerate(csv_files):
                dst = to_utf8(src, Path(tmp) / f"{i}.csv")
                with open(dst, encoding="utf-8", newline="") as f:
                    header = next(csv.reader(f, delimiter=";", quotechar='"'), [])
                missing = sorted(needed - set(header))
                if missing:
                    raise ValueError(f"{src.name}: faltam colunas esperadas de {source}: {missing}")
                headers.append(header)
                utf8_files.append(str(dst))
            if any(h != headers[0] for h in headers):
                raise ValueError(f"{source}: os CSV tem cabecalhos diferentes entre si")

            con = duckdb.connect()
            try:
                lista = "[" + ", ".join("'" + f.replace("'", "''") + "'" for f in utf8_files) + "]"
                con.execute(
                    f"CREATE VIEW raw AS SELECT * FROM read_csv({lista}, delim=';', quote='\"', "
                    f"escape='\"', header=true, all_varchar=true, parallel={'true' if parallel else 'false'})"
                )
                cd_col = '"CD_ELEICAO"' if by_eleicao else "NULL"
                grupos = con.execute(
                    f"""SELECT kind, CASE WHEN kind = 'eleicao' THEN cd END, CASE WHEN kind = 'eleicao' THEN ano END,
                               count(*)
                        FROM (SELECT {classify} AS kind, {cd_col} AS cd, "{ano_col}" AS ano FROM raw)
                        GROUP BY ALL ORDER BY ALL"""
                ).fetchall()
                n_in = sum(g[3] for g in grupos)
                entries = []
                for kind, cd, ano, n in grupos:
                    if kind is None:
                        continue
                    if kind == "uf":
                        reason = uf_reason
                    else:
                        reason = f"CD_ELEICAO={cd} fora das eleicoes ordinarias de {ano}"
                        extra = ELEICOES_CONHECIDAS.get(int(cd)) if cd and cd.lstrip("-").isdigit() else None
                        if extra:
                            reason += f" ({extra})"
                    entries.append({"reason": reason, "n_rows": n})
                n_keep = n_in - sum(e["n_rows"] for e in entries)

                con.sql(
                    f"SELECT {select} FROM raw WHERE ({classify}) IS NULL"
                ).write_parquet(str(tmp_parquet), compression="zstd")
                n_out = con.execute("SELECT count(*) FROM read_parquet(?)", [str(tmp_parquet)]).fetchone()[0]
            finally:
                con.close()

        if n_out != n_keep:
            raise RuntimeError(f"{source}: esperava {n_keep} linhas ({n_in} lidas), gravei {n_out}")
        tmp_exclusoes = _stage_exclusoes(exclusoes, source, entries)
        os.replace(tmp_parquet, out)
        os.replace(tmp_exclusoes, exclusoes)
        return n_out
    except BaseException:
        tmp_parquet.unlink(missing_ok=True)
        tmp_exclusoes.unlink(missing_ok=True)
        raise


def normalize_locais(csv_files: list[Path], out: Path) -> int:
    """`base/locais.parquet`: uma linha por (ano, turno, municipio, zona, secao).

    Lat/lon: virgula ou ponto decimal; -1, vazio ou fora de LAT_RANGE/LON_RANGE viram nulo
    (a linha e mantida). O CSV de 2024 e nacional e tem quebras de linha dentro de aspas:
    leitura com parallel=false e filtro SG_UF='TO'. Secoes agregadas sao mantidas.
    """
    select = f"""
        CAST("AA_ELEICAO" AS INTEGER)           AS ano,
        CAST("NR_TURNO" AS INTEGER)             AS turno,
        {_clean('CD_MUNICIPIO')}                AS cd_municipio,
        CAST("NR_ZONA" AS INTEGER)              AS zona,
        CAST("NR_SECAO" AS INTEGER)             AS secao,
        {_int('NR_LOCAL_VOTACAO')}              AS "local",
        {_ws('NM_LOCAL_VOTACAO')}               AS nm_local,
        {_ws('DS_ENDERECO')}                    AS endereco,
        {_ws('NM_BAIRRO')}                      AS bairro,
        {_coord('NR_LATITUDE', *LAT_RANGE)}     AS lat,
        {_coord('NR_LONGITUDE', *LON_RANGE)}    AS lon,
        CAST("QT_ELEITOR_SECAO" AS INTEGER)     AS eleitores_secao,
        {_clean('DS_TIPO_SECAO_AGREGADA')}      AS tipo_secao
    """
    return _normalize_aux(
        csv_files, out, source="locais", ano_col="AA_ELEICAO", select=select, uf_scope=_UF_TO,
        uf_reason="SG_UF diferente de TO", by_eleicao=False, parallel=False,
    )


def normalize_munzona(csv_files: list[Path], out: Path) -> int:
    """`base/munzona.parquet` (votacao_candidato_munzona). Inclui Presidente 2026 do `_BR.csv`."""
    select = f"""
        CAST("ANO_ELEICAO" AS INTEGER)          AS ano,
        CAST("NR_TURNO" AS INTEGER)             AS turno,
        {_clean('DS_CARGO')}                    AS cargo,
        {_clean('CD_MUNICIPIO')}                AS cd_municipio,
        CAST("NR_ZONA" AS INTEGER)              AS zona,
        {_int('NR_CANDIDATO')}                  AS nr_candidato,
        {_clean('NM_CANDIDATO')}                AS nm_candidato,
        {_clean('SG_PARTIDO')}                  AS sg_partido,
        CAST("QT_VOTOS_NOMINAIS" AS INTEGER)    AS votos_nominais,
        {_clean('DS_SIT_TOT_TURNO')}            AS situacao_turno
    """
    return _normalize_aux(
        csv_files, out, source="munzona", ano_col="ANO_ELEICAO", select=select, uf_scope=_UF_TO,
        uf_reason="SG_UF diferente de TO",
    )


def normalize_detalhe(csv_files: list[Path], out: Path) -> int:
    """`base/detalhe_munzona.parquet` (detalhe_votacao_munzona). `nulos` = QT_VOTOS_NULOS (nulos de urna)."""
    select = f"""
        CAST("ANO_ELEICAO" AS INTEGER)          AS ano,
        CAST("NR_TURNO" AS INTEGER)             AS turno,
        {_clean('DS_CARGO')}                    AS cargo,
        {_clean('CD_MUNICIPIO')}                AS cd_municipio,
        CAST("NR_ZONA" AS INTEGER)              AS zona,
        CAST("QT_APTOS" AS INTEGER)             AS aptos,
        CAST("QT_COMPARECIMENTO" AS INTEGER)    AS comparecimento,
        CAST("QT_ABSTENCOES" AS INTEGER)        AS abstencoes,
        CAST("QT_VOTOS_BRANCOS" AS INTEGER)     AS brancos,
        CAST("QT_VOTOS_NULOS" AS INTEGER)       AS nulos
    """
    return _normalize_aux(
        csv_files, out, source="detalhe_munzona", ano_col="ANO_ELEICAO", select=select, uf_scope=_UF_TO,
        uf_reason="SG_UF diferente de TO",
    )


def normalize_votacao_secao(csv_files: list[Path], out: Path) -> int:
    """`base/votacao_secao.parquet`: uma linha por (ano, turno, cargo, municipio, zona, secao, votavel)."""
    select = f"""
        CAST("ANO_ELEICAO" AS INTEGER)          AS ano,
        CAST("NR_TURNO" AS INTEGER)             AS turno,
        {_clean('DS_CARGO')}                    AS cargo,
        {_clean('CD_MUNICIPIO')}                AS cd_municipio,
        CAST("NR_ZONA" AS INTEGER)              AS zona,
        CAST("NR_SECAO" AS INTEGER)             AS secao,
        {_int('NR_VOTAVEL')}                    AS nr_votavel,
        CAST("QT_VOTOS" AS INTEGER)             AS votos
    """
    return _normalize_aux(
        csv_files, out, source="votacao_secao", ano_col="ANO_ELEICAO", select=select, uf_scope=_UF_TO,
        uf_reason="SG_UF diferente de TO",
    )


def normalize_candidatos(csv_files: list[Path], out: Path) -> int:
    """`base/candidatos.parquet` (consulta_cand). Inclui Presidente/Vice de 2026 (`_BR.csv`, SG_UF='BR').

    `cd_municipio` vem de SG_UE quando e numerico (municipal 2024); fica nulo nas eleicoes
    gerais (SG_UE = 'TO'/'BR'). `turno` e acrescentado a lista do plano: o mesmo SQ_CANDIDATO
    aparece nos dois turnos com `situacao_turno` diferente.
    """
    select = f"""
        CAST("ANO_ELEICAO" AS INTEGER)          AS ano,
        CAST("NR_TURNO" AS INTEGER)             AS turno,
        {_clean('DS_CARGO')}                    AS cargo,
        (CASE WHEN regexp_matches(trim("SG_UE"), '^[0-9]+$') THEN trim("SG_UE") END) AS cd_municipio,
        {_int('NR_CANDIDATO')}                  AS nr_candidato,
        CAST({_clean('SQ_CANDIDATO')} AS BIGINT) AS sq_candidato,
        {_clean('NM_URNA_CANDIDATO')}           AS nm_urna,
        {_clean('SG_PARTIDO')}                  AS sg_partido,
        {_clean('DS_SITUACAO_CANDIDATURA')}     AS situacao,
        {_clean('DS_SIT_TOT_TURNO')}            AS situacao_turno
    """
    return _normalize_aux(
        csv_files, out, source="candidatos", ano_col="ANO_ELEICAO", select=select, uf_scope=_UF_TO_CAND,
        uf_reason="SG_UF diferente de TO (exceto Presidente e Vice-Presidente com SG_UF=BR)",
    )
