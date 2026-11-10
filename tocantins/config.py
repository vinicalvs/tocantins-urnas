"""Configuracao: caminhos do projeto e fontes de dados do TSE."""
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "dados_brutos"
BASE = ROOT / "base"
VALID = ROOT / "validacao"
SITE_DATA = ROOT / "site_dados"
# Somente leitura (B24.pkl, B26.pkl); nunca modificar.
PALMAS_DIR = ROOT.parent / "Palmas_Urnas_e_Censo"


@dataclass(frozen=True)
class Source:
    key: str
    url: str
    sha_url: str | None
    filename: str


_CDN = "https://cdn.tse.jus.br/estatistica/sead/"
_BU24 = _CDN + "eleicoes/eleicoes2024/buweb/"
_BU26 = _CDN + "eleicoes/eleicoes2026/buweb/"
_ODSELE = _CDN + "odsele/"


def _bu(key: str, base: str, name: str) -> Source:
    url = base + name
    return Source(key, url, url + ".sha512", name)


def _odsele(key: str, path: str) -> Source:
    return Source(key, _ODSELE + path, None, path.rsplit("/", 1)[-1])


def _build() -> dict[str, Source]:
    sources = [
        _bu("bu24_t1", _BU24, "bweb_1t_TO_091020241636.zip"),
        _bu("bu24_t2", _BU24, "bweb_2t_TO_281020241046.zip"),
        _bu("bu26_t1", _BU26, "bweb_1t_TO_051020261403.zip"),
        _bu("bu26_t2", _BU26, "bweb_2t_TO_261020260742.zip"),
    ]
    for ano in (2024, 2026):
        a = str(ano)[2:]
        sources += [
            _odsele(f"munzona{a}", f"votacao_candidato_munzona/votacao_candidato_munzona_{ano}.zip"),
            _odsele(f"detalhe{a}", f"detalhe_votacao_munzona/detalhe_votacao_munzona_{ano}.zip"),
            _odsele(f"secao{a}", f"votacao_secao/votacao_secao_{ano}_TO.zip"),
            _odsele(f"locais{a}", f"eleitorado_locais_votacao/eleitorado_local_votacao_{ano}.zip"),
            _odsele(f"cand{a}", f"consulta_cand/consulta_cand_{ano}.zip"),
            _odsele(f"totaliz{a}", f"relatorio_resultado_totalizacao/Relatorio_Resultado_Totalizacao_{ano}_TO.zip"),
        ]
    # IBGE (sem .sha512 publicado): lista de municipios e malha municipal do Tocantins (crosswalk e mapa).
    _ibge = "https://servicodados.ibge.gov.br/api/"
    sources += [
        Source("ibge_municipios", _ibge + "v1/localidades/estados/17/municipios", None, "ibge/municipios_17.json"),
        Source("ibge_malha", _ibge + "v3/malhas/estados/17?intrarregiao=municipio"
               "&formato=application/vnd.geo+json&qualidade=minima", None, "ibge/malha_to.geojson"),
    ]
    # Censo 2022 por setor (IBGE, arquivos nacionais; sem .sha512) e malha de setores do TO.
    _cs = "https://ftp.ibge.gov.br/Censos/Censo_Demografico_2022/Agregados_por_Setores_Censitarios/"
    _set = _cs + "Agregados_por_Setor_csv/"
    sources += [
        Source("censo_malha_to", _cs + "malha_com_atributos/setores/gpkg/UF/TO/TO_setores_CD2022.gpkg", None,
               "censo/TO_setores_CD2022.gpkg"),
        Source("censo_basico", _set + "Agregados_por_setores_basico_BR_20260520.zip", None,
               "censo/Agregados_por_setores_basico_BR_20260520.zip"),
        Source("censo_demografia", _set + "Agregados_por_setores_demografia_BR.zip", None,
               "censo/Agregados_por_setores_demografia_BR.zip"),
        Source("censo_alfabetizacao", _set + "Agregados_por_setores_alfabetizacao_BR.zip", None,
               "censo/Agregados_por_setores_alfabetizacao_BR.zip"),
        Source("censo_cor_raca", _set + "Agregados_por_setores_cor_ou_raca_BR.zip", None,
               "censo/Agregados_por_setores_cor_ou_raca_BR.zip"),
        Source("censo_domicilio2", _set + "Agregados_por_setores_caracteristicas_domicilio2_BR_20250417.zip", None,
               "censo/Agregados_por_setores_caracteristicas_domicilio2_BR_20250417.zip"),
    ]
    # SIDRA: populacao/area/densidade do Censo 2022 (tabela 4714) e PIB municipal 2022 (tabela 5938, var. 37).
    _sidra = "https://apisidra.ibge.gov.br/values/"
    sources += [
        Source("sidra_pop_area", _sidra + "t/4714/n6/in%20n3%2017/v/93,6318,614/p/2022", None,
               "sidra/4714_pop_area_2022.json"),
        Source("sidra_pib", _sidra + "t/5938/n6/in%20n3%2017/v/37/p/2022", None, "sidra/5938_pib_2022.json"),
    ]
    return {s.key: s for s in sources}


SOURCES: dict[str, Source] = _build()
