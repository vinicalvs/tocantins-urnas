import pandas as pd
import pytest

from tocantins import crosswalk


def test_crosswalk_matches_accent_and_case_variants():
    tse = pd.DataFrame({"cd_municipio": ["73440", "92410", "73300"],
                        "nm_municipio": ["PALMAS", "ARAGUAÍNA", "PAU D'ARCO"]})
    ibge = [{"id": 1721000, "nome": "Palmas"}, {"id": 1702109, "nome": "Araguaína"},
            {"id": 1716307, "nome": "Pau D'Arco"}]
    assert crosswalk.build(tse, ibge, {}, expected=3) == {
        "73440": "1721000", "92410": "1702109", "73300": "1716307"}


def test_crosswalk_hyphen_and_override():
    tse = pd.DataFrame({"cd_municipio": ["1", "2"], "nm_municipio": ["SANTA ROSA DO TOCANTINS", "NOME ANTIGO"]})
    ibge = [{"id": 1, "nome": "Santa-Rosa do Tocantins"}, {"id": 2, "nome": "Nome Novo"}]
    assert crosswalk.build(tse, ibge, {"2": "2"}, expected=2) == {"1": "1", "2": "2"}


def test_crosswalk_raises_when_not_139():
    tse = pd.DataFrame({"cd_municipio": ["73440"], "nm_municipio": ["PALMAS"]})
    with pytest.raises(ValueError):
        crosswalk.build(tse, [{"id": 1721000, "nome": "Palmas"}], {})


def test_crosswalk_raises_on_ambiguous_or_missing_name():
    tse = pd.DataFrame({"cd_municipio": ["1", "2"], "nm_municipio": ["A", "B"]})
    with pytest.raises(ValueError):
        crosswalk.build(tse, [{"id": 1, "nome": "A"}], {}, expected=2)
    with pytest.raises(ValueError):
        crosswalk.build(tse, [{"id": 1, "nome": "A"}, {"id": 2, "nome": "A"}, {"id": 3, "nome": "B"}], {},
                        expected=2)
