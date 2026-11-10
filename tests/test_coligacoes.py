"""Partidos de cada candidatura: proprio partido + coligacao + federacoes citadas."""
import pandas as pd

from tocantins import coligacoes as col


def row(sg, comp=None, fed=None, cargo="GOVERNADOR", nr=44, ano=2026):
    return {"ano": ano, "turno": 1, "cargo": cargo, "nr_candidato": nr, "sg_partido": sg,
            "composicao_coligacao": comp, "composicao_federacao": fed}


def test_own_party_is_in_set():
    assert col.partidos_da_candidatura(row("NOVO", "NOVO")) == frozenset({"NOVO"})


def test_coligacao_composition_split_on_slash():
    assert col.partidos_da_candidatura(row("PL", "PL / PP / REPUBLICANOS")) == {"PL", "PP", "REPUBLICANOS"}


def test_federation_in_composition_expands_to_members():
    comp = "PDT / PSB / PSD / FEDERAÇÃO BRASIL DA ESPERANÇA - FE BRASIL (13-PT / 65-PC do B / 43-PV)"
    assert col.partidos_da_candidatura(row("PSD", comp)) == {"PDT", "PSB", "PSD", "PT", "PCDOB", "PV"}


def test_federation_composition_field_adds_members():
    assert col.partidos_da_candidatura(row("UNIÃO", None, "44-UNIÃO/11-PP")) == {"UNIAO", "PP"}


def test_norm_sigla_variants():
    assert col.norm_sigla("PC do B") == col.norm_sigla("PCdoB") == "PCDOB"
    assert col.norm_sigla("UNIÃO") == "UNIAO" and col.norm_sigla(" pl ") == "PL"


def test_build_dedupes_turns_and_titles_cargo():
    df = pd.DataFrame([row("PSOL", "FEDERAÇÃO PSOL REDE (50-PSOL / 18-REDE)", "50-PSOL/18-REDE", nr=50),
                       {**row("PSOL", "FEDERAÇÃO PSOL REDE (50-PSOL / 18-REDE)", "50-PSOL/18-REDE", nr=50),
                        "turno": 2}])
    b = col.build(df)
    assert len(b) == 1
    r = b.iloc[0]
    assert r["cargo"] == "Governador" and r["nr_candidato"] == 50 and list(r["partidos"]) == ["PSOL", "REDE"]
