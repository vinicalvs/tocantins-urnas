import json

import duckdb
import pytest

from conftest import bu_row, write_bu_csv
from tocantins.normalize import BU_COLUMNS, TIPO_VOTAVEL_MAP, normalize_bu, to_utf8

TEXT_COLS = [
    "cargo", "cd_municipio", "nm_municipio", "tipo_votavel", "nm_votavel",
    "sg_partido", "secoes_agregadas",
]


def run(csvs, tmp_path):
    out = tmp_path / "base" / "bu_secao.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    n = normalize_bu(csvs, out)
    return n, out


def q(out, sql):
    return duckdb.sql(sql.replace("{p}", f"'{out.as_posix()}'")).fetchall()


def test_nulo_tokens_become_null(bu_csv, tmp_path):
    n, out = run([bu_csv], tmp_path)
    rows = q(out, "select nr_votavel, nr_partido, sg_partido, votos from {p}")
    sem_partido = [r for r in rows if r[0] == 22123][0]
    assert sem_partido == (22123, None, None, 0)  # QT_VOTOS 0 permanece 0
    branco = [r for r in rows if r[0] == 95][0]
    assert branco[1] is None and branco[2] is None and branco[3] == 2
    assert q(out, "select count(*) from {p} where sg_partido like '#%'")[0][0] == 0


def test_ne_and_minus3_become_null(tmp_path):
    csv = write_bu_csv(tmp_path / "a.csv", [bu_row(NR_PARTIDO="-3", SG_PARTIDO="#NE", NM_VOTAVEL="#NE")])
    n, out = run([csv], tmp_path)
    assert q(out, "select nr_partido, sg_partido, nm_votavel from {p}") == [(None, None, None)]


def test_votos_never_nullified(tmp_path):
    # QT_VOTOS e contagem: nenhum token vira nulo (e um valor invalido falha alto)
    csv = write_bu_csv(tmp_path / "a.csv", [bu_row(QT_VOTOS="-1")])
    n, out = run([csv], tmp_path)
    assert q(out, "select votos from {p}") == [(-1,)]
    csv2 = write_bu_csv(tmp_path / "b.csv", [bu_row(QT_VOTOS="#NULO#")])
    with pytest.raises(Exception):
        run([csv2], tmp_path)


def test_no_mojibake(bu_csv, tmp_path):
    n, out = run([bu_csv], tmp_path)
    nomes = {r[0] for r in q(out, "select distinct nm_votavel from {p}")}
    assert "JOSÉ D'ÁVILA 'ZÉ'" in nomes
    assert q(out, "select distinct nm_municipio from {p}") == [("GUARAÍ",)]
    for col in TEXT_COLS:
        vals = [r[0] for r in q(out, f"select distinct {col} from {{p}}") if r[0] is not None]
        assert not any("Ã" in v or "�" in v for v in vals), col


def test_cd_municipio_is_text_with_leading_digits_kept(bu_csv, tmp_path):
    n, out = run([bu_csv], tmp_path)
    assert q(out, "select typeof(cd_municipio) from {p} limit 1") == [("VARCHAR",)]
    assert q(out, "select distinct cd_municipio from {p}") == [("73377",)]
    # zeros a esquerda sao preservados (nao ha cast numerico)
    csv = write_bu_csv(bu_csv.parent / "z.csv", [bu_row(CD_MUNICIPIO="00123")])
    n, out2 = run([csv], bu_csv.parent / "z")
    assert q(out2, "select cd_municipio from {p}") == [("00123",)]


def test_secoes_agregadas_preserved(bu_csv, tmp_path):
    n, out = run([bu_csv], tmp_path)
    vals = {r[0] for r in q(out, "select distinct secoes_agregadas from {p}")}
    assert vals == {None, "10 / 114"}


def test_row_count_matches_input(bu_csv, tmp_path):
    n, out = run([bu_csv], tmp_path)
    assert n == 4
    assert q(out, "select count(*) from {p}")[0][0] == 4
    # sem linhas descartadas: exclusoes.json existe e esta vazio (R13)
    assert json.loads((out.parent / "exclusoes.json").read_text(encoding="utf-8")) == []


def test_schema_and_types(bu_csv, tmp_path):
    n, out = run([bu_csv], tmp_path)
    cols = dict(q(out, "select column_name, column_type from (describe select * from {p})"))
    assert list(cols) == [
        "ano", "turno", "cd_eleicao", "cd_cargo", "cargo", "cd_municipio", "nm_municipio", "zona",
        "secao", "local", "aptos", "comparecimento", "abstencoes", "cd_tipo_urna", "tipo_votavel",
        "nr_votavel", "nm_votavel", "nr_partido", "sg_partido", "votos", "secoes_agregadas",
    ]
    for c in ("ano", "turno", "cd_eleicao", "cd_cargo", "zona", "secao", "local", "aptos",
              "comparecimento", "abstencoes", "cd_tipo_urna", "nr_votavel", "nr_partido", "votos"):
        assert cols[c] == "INTEGER", c
    for c in TEXT_COLS:
        assert cols[c] == "VARCHAR", c


def test_tipo_votavel_normalized(bu_csv, tmp_path):
    n, out = run([bu_csv], tmp_path)
    assert {r[0] for r in q(out, "select distinct tipo_votavel from {p}")} == {"Nominal", "Branco", "Legenda"}
    assert set(TIPO_VOTAVEL_MAP.values()) <= {"Nominal", "Legenda", "Branco", "Nulo", "Anulado"}


def test_unmapped_tipo_votavel_fails_loudly(tmp_path):
    csv = write_bu_csv(tmp_path / "x.csv", [bu_row(), bu_row(CD_TIPO_VOTAVEL="9", DS_TIPO_VOTAVEL="Misterioso")])
    with pytest.raises(ValueError, match="Misterioso"):
        run([csv], tmp_path)
    assert not (tmp_path / "base" / "bu_secao.parquet").exists()


def test_inconsistent_code_and_description_fails(tmp_path):
    csv = write_bu_csv(tmp_path / "x.csv", [bu_row(CD_TIPO_VOTAVEL="1", DS_TIPO_VOTAVEL="Nulo")])
    with pytest.raises(ValueError):
        run([csv], tmp_path)


def test_cd_eleicao_preserved_and_turns_unioned(tmp_path):
    a = write_bu_csv(tmp_path / "a.csv", [
        bu_row(CD_ELEICAO="6257", CD_CARGO_PERGUNTA="1", DS_CARGO_PERGUNTA="Presidente"),
        bu_row(CD_ELEICAO="6259"),
    ])
    b = write_bu_csv(tmp_path / "b.csv", [bu_row(NR_TURNO="2", CD_ELEICAO="6260")])
    n, out = run([a, b], tmp_path)
    assert n == 3
    got = q(out, "select turno, cd_eleicao, cargo from {p} order by 1, 2")
    assert got == [(1, 6257, "Presidente"), (1, 6259, "Deputado Estadual"), (2, 6260, "Deputado Estadual")]


def test_all_rows_kept_regardless_of_urna_type(tmp_path):
    csv = write_bu_csv(tmp_path / "u.csv", [
        bu_row(), bu_row(CD_TIPO_URNA="2", DS_TIPO_URNA="Outra"), bu_row(CD_TIPO_URNA="3", DS_TIPO_URNA="X"),
    ])
    n, out = run([csv], tmp_path)
    assert n == 3
    assert sorted(r[0] for r in q(out, "select cd_tipo_urna from {p}")) == [1, 2, 3]


def test_wrong_header_fails(tmp_path):
    p = tmp_path / "bad.csv"
    p.write_bytes(b'"A";"B"\r\n"1";"2"\r\n')
    with pytest.raises(ValueError):
        run([p], tmp_path)


def test_bu_columns_has_45():
    assert len(BU_COLUMNS) == 45


def test_to_utf8_decodes_latin1_once_across_blocks(tmp_path):
    src = tmp_path / "s.csv"
    text = "JOSÉ D'ÁVILA 'ZÉ' ÇÃO;GUARAÍ\r\n" * 5000
    src.write_bytes(text.encode("latin-1"))
    dst = to_utf8(src, tmp_path / "d.csv", block_size=1000)
    assert dst.read_bytes().decode("utf-8") == text


def _no_leftovers(base_dir):
    return [p.name for p in base_dir.iterdir() if p.name.endswith(".tmp") or p.name.startswith(".utf8_")]


def test_failed_rerun_keeps_previous_outputs_and_leaves_no_tmp(bu_csv, tmp_path, monkeypatch):
    import tocantins.normalize as nz

    n, out = run([bu_csv], tmp_path)
    exc = out.parent / "exclusoes.json"
    good_parquet, good_exc = out.read_bytes(), exc.read_bytes()

    # falha no meio da regravacao, depois de o Parquet novo ja ter sido escrito
    def boom(*a, **k):
        raise OSError("disco cheio")

    monkeypatch.setattr(nz, "_write_exclusoes", boom)
    other = write_bu_csv(tmp_path / "outro.csv", [bu_row(QT_VOTOS="99")])
    with pytest.raises(OSError):
        normalize_bu([other], out)
    assert out.read_bytes() == good_parquet
    assert exc.read_bytes() == good_exc
    assert _no_leftovers(out.parent) == []

    # falha antes de qualquer escrita (tipo_votavel desconhecido)
    monkeypatch.undo()
    bad = write_bu_csv(tmp_path / "ruim.csv", [bu_row(CD_TIPO_VOTAVEL="9", DS_TIPO_VOTAVEL="X")])
    with pytest.raises(ValueError):
        normalize_bu([bad], out)
    assert out.read_bytes() == good_parquet
    assert _no_leftovers(out.parent) == []


def test_successful_write_leaves_both_outputs_and_no_tmp(bu_csv, tmp_path):
    n, out = run([bu_csv], tmp_path)
    assert out.exists() and (out.parent / "exclusoes.json").exists()
    assert _no_leftovers(out.parent) == []
