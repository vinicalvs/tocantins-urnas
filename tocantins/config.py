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
    return {s.key: s for s in sources}


SOURCES: dict[str, Source] = _build()
