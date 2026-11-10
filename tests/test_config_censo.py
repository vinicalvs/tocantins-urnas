"""Fontes do Censo 2022 (setores) e do SIDRA registradas no manifesto."""
from tocantins.config import SOURCES

CENSO = ("censo_malha_to", "censo_basico", "censo_demografia", "censo_alfabetizacao", "censo_cor_raca",
         "censo_domicilio2")
SIDRA = ("sidra_pop_area", "sidra_pib")


def test_censo_sources_registered():
    for k in CENSO + SIDRA:
        s = SOURCES[k]
        assert s.sha_url is None and s.url.startswith("https://")
        assert s.filename.startswith("censo/" if k in CENSO else "sidra/")
    assert "censo_renda" not in SOURCES          # IBGE nao publicou renda por setor (docs/fontes.md secao 6)
    assert SOURCES["censo_malha_to"].filename.endswith("TO_setores_CD2022.gpkg")
