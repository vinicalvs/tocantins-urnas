import json

import duckdb
import pytest

import tocantins.normalize as nz
from conftest import (
    CAND_HEADER, DETALHE_HEADER, LOCAIS_HEADER, MUNZONA_HEADER, SECAO_HEADER,
    cand_row, detalhe_row, locais_row, munzona_row, secao_row, bu_row, write_bu_csv, write_csv_rows,
)
from tocantins.normalize import (
    normalize_bu, normalize_candidatos, normalize_detalhe, normalize_locais, normalize_munzona,
    normalize_votacao_secao, record_exclusoes,
)


def q(out, sql):
    return duckdb.sql(sql.replace("{p}", f"'{out.as_posix()}'")).fetchall()


def cols(out):
    return dict(q(out, "select column_name, column_type from (describe select * from {p})"))


def exclusoes(base, source=None):
    data = json.loads((base / "exclusoes.json").read_text(encoding="utf-8"))
    return data if source is None else [e for e in data if e["source"] == source]


# ---------------------------------------------------------------- locais
def run_locais(tmp_path, rows, name="a.csv"):
    csv = write_csv_rows(tmp_path / name, LOCAIS_HEADER, rows)
    out = tmp_path / "base" / "locais.parquet"
    return normalize_locais([csv], out), out


def test_locais_comma_decimal_and_missing_coords(tmp_path):
    rows = [
        locais_row(NR_SECAO="1", NR_LATITUDE="-10,184", NR_LONGITUDE="-48,333"),
        locais_row(NR_SECAO="2", NR_LATITUDE="-1", NR_LONGITUDE="-1"),
        locais_row(NR_SECAO="3", NR_LATITUDE="", NR_LONGITUDE=""),
        locais_row(NR_SECAO="4", NR_LATITUDE="-10.1528383", NR_LONGITUDE="-48.2"),  # 2024: ponto
        locais_row(NR_SECAO="5", NR_LATITUDE="-23,5", NR_LONGITUDE="-60,6"),  # fora do TO
        locais_row(NR_SECAO="6", NR_LATITUDE="-10,2", NR_LONGITUDE="-70,0"),  # lon implausivel
        locais_row(NR_SECAO="7", NR_LATITUDE="#NULO#", NR_LONGITUDE="#NE"),
    ]
    n, out = run_locais(tmp_path, rows)
    assert n == 7  # nenhuma linha some por falta de coordenada
    got = {s: (la, lo) for s, la, lo in q(out, "select secao, lat, lon from {p}")}
    assert got[1] == (-10.184, -48.333)
    assert got[2] == (None, None)
    assert got[3] == (None, None)
    assert got[4] == (-10.1528383, -48.2)
    assert got[5] == (None, None)
    assert got[6][0] == -10.2 and got[6][1] is None
    assert got[7] == (None, None)


def test_locais_same_local_number_in_two_zones_kept_distinct(tmp_path):
    rows = [
        locais_row(NR_ZONA="6", NR_SECAO="10", NR_LOCAL_VOTACAO="1012"),
        locais_row(NR_ZONA="7", NR_SECAO="10", NR_LOCAL_VOTACAO="1012", NM_LOCAL_VOTACAO="OUTRA ESCOLA"),
        locais_row(NR_ZONA="7", NR_SECAO="11", NR_LOCAL_VOTACAO="1012", NM_LOCAL_VOTACAO="OUTRA ESCOLA"),
    ]
    n, out = run_locais(tmp_path, rows)
    assert n == 3
    got = q(out, "select zona, secao, local from {p} order by 1, 2")
    assert got == [(6, 10, 1012), (7, 10, 1012), (7, 11, 1012)]
    assert q(out, "select count(distinct (zona, secao)) from {p}")[0][0] == 3


def test_locais_filters_only_TO_and_records_exclusion(tmp_path):
    rows = [locais_row(), locais_row(SG_UF="SP", CD_MUNICIPIO="71072"), locais_row(SG_UF="SP", NR_SECAO="2")]
    n, out = run_locais(tmp_path, rows)
    assert n == 1
    assert q(out, "select count(*) from {p}")[0][0] == 1
    exc = exclusoes(out.parent, "locais")
    assert [(e["reason"], e["n_rows"]) for e in exc] == [("SG_UF diferente de TO", 2)]


def test_locais_schema_year_turno_and_agregada(tmp_path):
    rows = [
        locais_row(),
        locais_row(NR_SECAO="13", DS_TIPO_SECAO_AGREGADA="Agregada"),
        locais_row(AA_ELEICAO="2024", NR_TURNO="2", NR_LATITUDE="-10.5", NR_LONGITUDE="-48.5"),
    ]
    n, out = run_locais(tmp_path, rows)
    c = cols(out)
    assert list(c) == [
        "ano", "turno", "cd_municipio", "zona", "secao", "local", "nm_local", "endereco", "bairro",
        "lat", "lon", "eleitores_secao", "tipo_secao",
    ]
    assert c["cd_municipio"] == "VARCHAR" and c["lat"] == "DOUBLE" and c["lon"] == "DOUBLE"
    for k in ("ano", "turno", "zona", "secao", "local", "eleitores_secao"):
        assert c[k] == "INTEGER", k
    assert q(out, "select distinct ano, turno from {p} order by 1, 2") == [(2024, 2), (2026, 1)]
    assert {r[0] for r in q(out, "select distinct tipo_secao from {p}")} == {"Principal", "Agregada"}
    assert q(out, "select nm_local from {p} limit 1") == [("ESCOLA MUNICIPAL JOÃO",)]


def test_locais_multiline_address_is_collapsed(tmp_path):
    n, out = run_locais(tmp_path, [locais_row(DS_ENDERECO="QUADRA 104 SUL\r\n  AV NS 1")])
    assert q(out, "select endereco from {p}") == [("QUADRA 104 SUL AV NS 1",)]


# --------------------------------------------------------------- munzona
def test_munzona_keeps_situacao_turno(tmp_path):
    csv = write_csv_rows(tmp_path / "m.csv", MUNZONA_HEADER, [
        munzona_row(DS_SIT_TOT_TURNO="ELEITO POR MÉDIA"),
        munzona_row(NR_CANDIDATO="16", DS_SIT_TOT_TURNO="#NULO"),
        munzona_row(NR_CANDIDATO="17", DS_SIT_TOT_TURNO="NÃO ELEITO"),
    ])
    out = tmp_path / "base" / "munzona.parquet"
    assert normalize_munzona([csv], out) == 3
    got = {r[0]: r[1] for r in q(out, "select nr_candidato, situacao_turno from {p}")}
    assert got == {15: "ELEITO POR MÉDIA", 16: None, 17: "NÃO ELEITO"}
    vals = [r[0] for r in q(out, "select distinct situacao_turno from {p} where situacao_turno is not null")]
    assert not any("Ã" in v.replace("NÃO", "") or "�" in v for v in vals)
    assert q(out, "select distinct nm_candidato from {p}") == [("MARIA DA CONCEIÇÃO",)]


def test_munzona_schema_votes_not_nullified_and_text_municipio(tmp_path):
    csv = write_csv_rows(tmp_path / "m.csv", MUNZONA_HEADER, [
        munzona_row(QT_VOTOS_NOMINAIS="0", CD_MUNICIPIO="00123"),
        munzona_row(QT_VOTOS_NOMINAIS="-1", NR_CANDIDATO="16"),
    ])
    out = tmp_path / "base" / "munzona.parquet"
    normalize_munzona([csv], out)
    c = cols(out)
    assert list(c) == [
        "ano", "turno", "cargo", "cd_municipio", "zona", "nr_candidato", "nm_candidato",
        "sg_partido", "votos_nominais", "situacao_turno",
    ]
    assert c["cd_municipio"] == "VARCHAR" and c["votos_nominais"] == "INTEGER"
    assert q(out, "select cd_municipio, votos_nominais from {p} order by nr_candidato") == [("00123", 0), ("73440", -1)]


def test_munzona_year_from_file_unites_years_and_includes_presidente_from_BR(tmp_path):
    to24 = write_csv_rows(tmp_path / "to24.csv", MUNZONA_HEADER, [
        munzona_row(ANO_ELEICAO="2024", CD_ELEICAO="619", DS_CARGO="Prefeito"),
    ])
    to26 = write_csv_rows(tmp_path / "to26.csv", MUNZONA_HEADER, [munzona_row()])
    br26 = write_csv_rows(tmp_path / "br26.csv", MUNZONA_HEADER, [
        munzona_row(CD_ELEICAO="6257", DS_CARGO="Presidente", SG_UE="BR"),
        munzona_row(CD_ELEICAO="6258", NR_TURNO="2", DS_CARGO="Presidente", SG_UE="BR"),
        munzona_row(CD_ELEICAO="6257", DS_CARGO="Presidente", SG_UF="SP", CD_MUNICIPIO="71072"),
    ])
    out = tmp_path / "base" / "munzona.parquet"
    n = normalize_munzona([to24, to26, br26], out)
    assert n == 4
    assert q(out, "select ano, turno, cargo, count(*) from {p} group by all order by all") == [
        (2024, 1, "Prefeito", 1), (2026, 1, "Governador", 1), (2026, 1, "Presidente", 1),
        (2026, 2, "Presidente", 1),
    ]
    assert [(e["reason"], e["n_rows"]) for e in exclusoes(out.parent, "munzona")] == [("SG_UF diferente de TO", 1)]


def test_munzona_goiatins_suplementar_excluded_and_recorded(tmp_path):
    csv = write_csv_rows(tmp_path / "m.csv", MUNZONA_HEADER, [
        munzona_row(ANO_ELEICAO="2024", CD_ELEICAO="619", DS_CARGO="Prefeito"),
        munzona_row(ANO_ELEICAO="2024", CD_ELEICAO="6286", DS_CARGO="Prefeito", NR_CANDIDATO="20"),
        munzona_row(ANO_ELEICAO="2024", CD_ELEICAO="6286", DS_CARGO="Prefeito", NR_CANDIDATO="21"),
    ])
    out = tmp_path / "base" / "munzona.parquet"
    assert normalize_munzona([csv], out) == 1
    assert q(out, "select count(*) from {p}")[0][0] == 1
    exc = exclusoes(out.parent, "munzona")
    assert len(exc) == 1 and exc[0]["n_rows"] == 2 and "6286" in exc[0]["reason"]
    assert exc[0]["source"] == "munzona"


def test_ordinary_code_must_match_the_year(tmp_path):
    # 6259 e ordinaria em 2026, mas nao em 2024
    csv = write_csv_rows(tmp_path / "m.csv", MUNZONA_HEADER, [
        munzona_row(), munzona_row(ANO_ELEICAO="2024", CD_ELEICAO="6259"),
    ])
    out = tmp_path / "base" / "munzona.parquet"
    assert normalize_munzona([csv], out) == 1
    assert exclusoes(out.parent, "munzona")[0]["n_rows"] == 1


# --------------------------------------------------------------- detalhe
def test_detalhe_schema_and_values(tmp_path):
    csv = write_csv_rows(tmp_path / "d.csv", DETALHE_HEADER, [
        detalhe_row(), detalhe_row(ANO_ELEICAO="2024", CD_ELEICAO="619", DS_CARGO="Prefeito", SG_UF="SP"),
        detalhe_row(ANO_ELEICAO="2024", CD_ELEICAO="6286", DS_CARGO="Prefeito"),
    ])
    out = tmp_path / "base" / "detalhe_munzona.parquet"
    assert normalize_detalhe([csv], out) == 1
    c = cols(out)
    assert list(c) == [
        "ano", "turno", "cargo", "cd_municipio", "zona", "aptos", "comparecimento", "abstencoes",
        "brancos", "nulos",
    ]
    assert c["cd_municipio"] == "VARCHAR"
    assert q(out, "select * from {p}") == [(2026, 1, "Governador", "73440", 6, 1000, 800, 200, 20, 30)]
    assert sorted((e["reason"], e["n_rows"]) for e in exclusoes(out.parent, "detalhe_munzona")) == [
        ("CD_ELEICAO=6286 fora das eleicoes ordinarias de 2024 (suplementar de Goiatins, 25/10/2026)", 1),
        ("SG_UF diferente de TO", 1),
    ]


# ---------------------------------------------------------------- secao
def test_votacao_secao_schema_keeps_branco_nulo_and_excludes_goiatins(tmp_path):
    csv = write_csv_rows(tmp_path / "s.csv", SECAO_HEADER, [
        secao_row(),
        secao_row(NR_VOTAVEL="95", NM_VOTAVEL="VOTO BRANCO", SQ_CANDIDATO="-1", QT_VOTOS="0"),
        secao_row(NR_VOTAVEL="96", NM_VOTAVEL="VOTO NULO", SQ_CANDIDATO="-1"),
        secao_row(CD_ELEICAO="6286", CD_MUNICIPIO="95338", NR_ZONA="32", ANO_ELEICAO="2024"),
    ])
    out = tmp_path / "base" / "votacao_secao.parquet"
    assert normalize_votacao_secao([csv], out) == 3
    c = cols(out)
    assert list(c) == ["ano", "turno", "cargo", "cd_municipio", "zona", "secao", "nr_votavel", "votos"]
    assert q(out, "select nr_votavel, votos from {p} order by 1") == [(15, 7), (95, 0), (96, 7)]
    assert exclusoes(out.parent, "votacao_secao")[0]["n_rows"] == 1


# ------------------------------------------------------------ candidatos
def test_candidatos_schema_null_tokens_and_BR_presidente(tmp_path):
    to24 = write_csv_rows(tmp_path / "c24.csv", CAND_HEADER, [
        cand_row(),
        cand_row(CD_ELEICAO="6286", SG_UE="95338", NR_CANDIDATO="30"),
    ])
    to26 = write_csv_rows(tmp_path / "c26.csv", CAND_HEADER, [
        cand_row(ANO_ELEICAO="2026", CD_ELEICAO="6259", SG_UE="TO", CD_CARGO="3", DS_CARGO="GOVERNADOR",
                 DS_SITUACAO_CANDIDATURA="#NE", DS_SIT_TOT_TURNO="#NULO", NR_CANDIDATO="12"),
    ])
    br26 = write_csv_rows(tmp_path / "c26br.csv", CAND_HEADER, [
        cand_row(ANO_ELEICAO="2026", CD_ELEICAO="6257", SG_UF="BR", SG_UE="BR", CD_CARGO="1",
                 DS_CARGO="PRESIDENTE", DS_SITUACAO_CANDIDATURA="#NE", NR_CANDIDATO="13"),
        cand_row(ANO_ELEICAO="2026", CD_ELEICAO="6257", SG_UF="BR", SG_UE="BR", CD_CARGO="9",
                 DS_CARGO="1º SUPLENTE", NR_CANDIDATO="14"),
    ])
    out = tmp_path / "base" / "candidatos.parquet"
    assert normalize_candidatos([to24, to26, br26], out) == 3
    c = cols(out)
    assert list(c) == [
        "ano", "turno", "cargo", "cd_municipio", "nr_candidato", "sq_candidato", "nm_urna",
        "sg_partido", "situacao", "situacao_turno",
    ]
    assert c["cd_municipio"] == "VARCHAR" and c["sq_candidato"] == "BIGINT"
    got = q(out, "select ano, cargo, cd_municipio, nr_candidato, situacao, situacao_turno from {p} order by 1, 4")
    assert got == [
        (2024, "PREFEITO", "73440", 15, "Deferido", "ELEITO"),
        (2026, "GOVERNADOR", None, 12, None, None),
        (2026, "PRESIDENTE", None, 13, None, "ELEITO"),
    ]
    reasons = sorted((e["reason"], e["n_rows"]) for e in exclusoes(out.parent, "candidatos"))
    assert len(reasons) == 2 and sum(n for _, n in reasons) == 2


def test_candidatos_filters_only_TO(tmp_path):
    csv = write_csv_rows(tmp_path / "c.csv", CAND_HEADER, [cand_row(), cand_row(SG_UF="SP")])
    out = tmp_path / "base" / "candidatos.parquet"
    assert normalize_candidatos([csv], out) == 1


# ------------------------------------------------- comportamento comum
SPECS = [
    (normalize_locais, LOCAIS_HEADER, locais_row, "locais.parquet", "locais"),
    (normalize_munzona, MUNZONA_HEADER, munzona_row, "munzona.parquet", "munzona"),
    (normalize_detalhe, DETALHE_HEADER, detalhe_row, "detalhe_munzona.parquet", "detalhe_munzona"),
    (normalize_votacao_secao, SECAO_HEADER, secao_row, "votacao_secao.parquet", "votacao_secao"),
    (normalize_candidatos, CAND_HEADER, cand_row, "candidatos.parquet", "candidatos"),
]
IDS = [s[4] for s in SPECS]


@pytest.mark.parametrize("fn,header,row,fname,source", SPECS, ids=IDS)
def test_empty_exclusion_list_recorded_and_rerun_idempotent(tmp_path, fn, header, row, fname, source):
    csv = write_csv_rows(tmp_path / "a.csv", header, [row()])
    out = tmp_path / "base" / fname
    assert fn([csv], out) == 1
    assert exclusoes(out.parent, source) == []
    record_exclusoes(out.parent / "exclusoes.json", "outra", [{"source": "outra", "reason": "r", "n_rows": 3}])
    # reexecucao: troca so as proprias entradas e preserva as de outras fontes
    assert fn([csv], out) == 1
    assert exclusoes(out.parent, "outra") == [{"source": "outra", "reason": "r", "n_rows": 3}]
    assert q(out, "select count(*) from {p}")[0][0] == 1


@pytest.mark.parametrize("fn,header,row,fname,source", SPECS, ids=IDS)
def test_missing_required_column_fails_loudly(tmp_path, fn, header, row, fname, source):
    p = tmp_path / "bad.csv"
    p.write_bytes(b'"A";"B"\r\n"1";"2"\r\n')
    out = tmp_path / "base" / fname
    with pytest.raises(ValueError):
        fn([p], out)
    assert not out.exists()


@pytest.mark.parametrize("fn,header,row,fname,source", SPECS, ids=IDS)
def test_failed_rerun_keeps_previous_outputs_and_no_tmp(tmp_path, monkeypatch, fn, header, row, fname, source):
    csv = write_csv_rows(tmp_path / "a.csv", header, [row()])
    out = tmp_path / "base" / fname
    fn([csv], out)
    good, good_exc = out.read_bytes(), (out.parent / "exclusoes.json").read_bytes()

    def boom(*a, **k):
        raise OSError("disco cheio")

    monkeypatch.setattr(nz, "_stage_exclusoes", boom)
    other = write_csv_rows(tmp_path / "b.csv", header, [row(), row()])
    with pytest.raises(OSError):
        fn([other], out)
    assert out.read_bytes() == good
    assert (out.parent / "exclusoes.json").read_bytes() == good_exc
    assert [p.name for p in out.parent.iterdir() if p.name.endswith(".tmp")] == []


# ---------------------------------------------------- exclusoes (R15)
def test_record_exclusoes_replaces_only_same_source(tmp_path):
    path = tmp_path / "exclusoes.json"
    record_exclusoes(path, "a", [{"source": "a", "reason": "x", "n_rows": 1}])
    record_exclusoes(path, "b", [{"source": "b", "reason": "y", "n_rows": 2}])
    record_exclusoes(path, "a", [{"source": "a", "reason": "z", "n_rows": 5}])
    data = json.loads(path.read_text(encoding="utf-8"))
    assert sorted((e["source"], e["reason"], e["n_rows"]) for e in data) == [("a", "z", 5), ("b", "y", 2)]
    record_exclusoes(path, "a", [])
    assert [e["source"] for e in json.loads(path.read_text(encoding="utf-8"))] == ["b"]
    assert not (tmp_path / "exclusoes.json.tmp").exists()


def test_record_exclusoes_refuses_corrupt_file(tmp_path):
    path = tmp_path / "exclusoes.json"
    path.write_text('{"nao": "uma lista"}', encoding="utf-8")
    with pytest.raises(ValueError):
        record_exclusoes(path, "a", [])
    assert path.read_text(encoding="utf-8") == '{"nao": "uma lista"}'


def test_normalize_bu_rerun_does_not_erase_other_sources(bu_csv, tmp_path):
    out = tmp_path / "base" / "bu_secao.parquet"
    normalize_bu([bu_csv], out)
    exc = out.parent / "exclusoes.json"
    record_exclusoes(exc, "munzona", [{"source": "munzona", "reason": "r", "n_rows": 2}])
    normalize_bu([bu_csv], out)
    assert json.loads(exc.read_text(encoding="utf-8")) == [{"source": "munzona", "reason": "r", "n_rows": 2}]
