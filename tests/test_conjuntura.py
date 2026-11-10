"""Entrega dos prefeitos de 2024 para Governador e Senador em 2026."""
import pandas as pd
import pytest

from tocantins import coligacoes, conjuntura

M = "73440"


def bu(rows, ano=2026):
    """rows: (cargo, turno, mun, nr, nome, partido, votos) -- votos nominais por candidato."""
    return pd.DataFrame([{"ano": ano, "cargo": c, "turno": t, "cd_municipio": m, "tipo_votavel": "Nominal",
                          "nr_votavel": nr, "nm_votavel": n, "sg_partido": p, "votos": v}
                         for c, t, m, nr, n, p, v in rows])


def munzona(rows):
    """rows: (turno, mun, nr, nome, partido, situacao)"""
    return pd.DataFrame([{"ano": 2024, "cargo": "Prefeito", "turno": t, "cd_municipio": m, "zona": 1,
                          "nr_candidato": nr, "nm_candidato": n, "sg_partido": p, "votos_nominais": 1,
                          "situacao_turno": s} for t, m, nr, n, p, s in rows])


def colig(rows):
    """rows: (cargo, nr, sg_partido, partidos)"""
    return pd.DataFrame([{"ano": 2026, "cargo": c, "nr_candidato": nr, "sg_partido": p, "partidos": sorted(ps)}
                         for c, nr, p, ps in rows])


def pref(partido, mun=M):
    return pd.DataFrame([{"cd_municipio": mun, "nr": 10, "nome": "PREFEITO", "partido": partido}])


def test_prefeito_uses_t2_where_it_happened():
    mz = munzona([(1, M, 10, "A", "MDB", "2º TURNO"), (1, M, 22, "B", "PL", "2º TURNO"),
                  (2, M, 22, "B", "PL", "ELEITO"), (2, M, 10, "A", "MDB", "NÃO ELEITO"),
                  (1, "92410", 44, "C", "UNIÃO", "ELEITO")])
    p = conjuntura.prefeitos(None, mz).set_index("cd_municipio")
    assert p.loc[M, "nr"] == 22 and p.loc[M, "partido"] == "PL"
    assert p.loc["92410", "nr"] == 44 and len(p) == 2


def test_governador_entregou_and_margin():
    b = bu([("Governador", 1, M, 15, "G1", "MDB", 600), ("Governador", 1, M, 22, "G2", "PL", 400)])
    c = colig([("Governador", 15, "MDB", {"MDB", "PSDB"}), ("Governador", 22, "PL", {"PL"})])
    e = conjuntura.entrega(b, pref("PSDB"), c, "Governador", 1).iloc[0]
    assert e["status"] == "entregou" and e["cand_nr"] == 15 and e["venc_nr"] == 15
    assert e["margem_votos"] == 200 and e["margem_pp"] == pytest.approx(20.0)


def test_governador_t2_coalition_out_is_sem_candidato():
    b = bu([("Governador", 2, M, 15, "G1", "MDB", 600), ("Governador", 2, M, 22, "G2", "PL", 400)])
    c = colig([("Governador", 15, "MDB", {"MDB"}), ("Governador", 22, "PL", {"PL"}),
               ("Governador", 40, "PSB", {"PSB", "PT"})])
    e = conjuntura.entrega(b, pref("PT"), c, "Governador", 2).iloc[0]
    assert e["status"] == "sem_candidato" and pd.isna(e["cand_nr"]) and pd.isna(e["margem_votos"])
    assert e["venc_nr"] == 15


def test_senador_two_seats_second_place_counts_as_entregou():
    b = bu([("Senador", 1, M, 151, "S1", "MDB", 500), ("Senador", 1, M, 222, "S2", "PL", 300),
            ("Senador", 1, M, 444, "S3", "UNIÃO", 250)])
    c = colig([("Senador", 151, "MDB", {"MDB"}), ("Senador", 222, "PL", {"PL"}), ("Senador", 444, "UNIÃO", {"UNIÃO"})])
    e = conjuntura.entrega(b, pref("PL"), c, "Senador", 1).iloc[0]
    assert e["status"] == "entregou" and e["margem_votos"] == 50       # contra o 1o fora das 2 vagas
    e3 = conjuntura.entrega(b, pref("UNIÃO"), c, "Senador", 1).iloc[0]
    assert e3["status"] == "nao_entregou" and e3["margem_votos"] == -50


def test_federation_member_mayor_finds_candidate():
    cand = pd.DataFrame([{"ano": 2026, "cargo": "GOVERNADOR", "nr_candidato": 45, "sg_partido": "PSDB",
                          "sg_federacao": "PSDB CIDADANIA", "composicao_federacao": "45-PSDB/23-CIDADANIA",
                          "nm_coligacao": "X", "composicao_coligacao": "MDB / FEDERAÇÃO PSDB CIDADANIA (45-PSDB / 23-CIDADANIA)"}])
    c = coligacoes.build(cand)
    b = bu([("Governador", 1, M, 45, "G", "PSDB", 300), ("Governador", 1, M, 22, "H", "PL", 700)])
    e = conjuntura.entrega(b, pref("CIDADANIA"), c, "Governador", 1).iloc[0]
    assert e["cand_nr"] == 45 and e["status"] == "nao_entregou" and e["margem_votos"] == -400


def test_own_party_preferred_over_coalition_partner():
    b = bu([("Senador", 1, M, 151, "S1", "MDB", 900), ("Senador", 1, M, 155, "S2", "PSDB", 100),
            ("Senador", 1, M, 222, "S3", "PL", 50)])
    c = colig([("Senador", 151, "MDB", {"MDB", "PSDB"}), ("Senador", 155, "PSDB", {"MDB", "PSDB"}),
               ("Senador", 222, "PL", {"PL"})])
    assert conjuntura.entrega(b, pref("PSDB"), c, "Senador", 1).iloc[0]["cand_nr"] == 155
    c2 = colig([("Senador", 151, "MDB", {"MDB", "PP"}), ("Senador", 155, "PSDB", {"PSDB", "PP"}),
                ("Senador", 222, "PL", {"PL"})])
    assert conjuntura.entrega(b, pref("PP"), c2, "Senador", 1).iloc[0]["cand_nr"] == 151   # mais votado
