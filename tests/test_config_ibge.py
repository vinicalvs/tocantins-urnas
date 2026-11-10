"""As entradas do IBGE usadas pela exportacao sao fontes registradas (baixadas e com hash no manifesto)."""
import json

from tocantins.config import RAW, SOURCES
from tocantins.download import fetch


def test_ibge_sources_point_to_the_files_the_export_reads():
    m, g = SOURCES["ibge_municipios"], SOURCES["ibge_malha"]
    assert m.url == "https://servicodados.ibge.gov.br/api/v1/localidades/estados/17/municipios"
    assert g.url.startswith("https://servicodados.ibge.gov.br/api/v3/malhas/estados/17?intrarregiao=municipio")
    assert m.sha_url is None and g.sha_url is None
    assert RAW / m.filename == RAW / "ibge" / "municipios_17.json"
    assert RAW / g.filename == RAW / "ibge" / "malha_to.geojson"


def test_fetch_registers_existing_file_in_subfolder_without_network(tmp_path):
    src = SOURCES["ibge_municipios"]
    f = tmp_path / src.filename
    f.parent.mkdir(parents=True)
    f.write_text("[]", encoding="utf-8")
    entry = fetch(src, tmp_path, tmp_path / "manifesto.json")
    assert entry["key"] == "ibge_municipios" and entry["published_sha512"] is None
    assert "ibge_municipios" in json.loads((tmp_path / "manifesto.json").read_text(encoding="utf-8"))
