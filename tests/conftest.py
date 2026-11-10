import hashlib
import io
import threading
import zipfile
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest


def make_zip_bytes() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("dados.csv", "a;b\n1;2\n")
    return buf.getvalue()


class FakeTSE:
    """Servidor HTTP local que serve um zip pequeno e seu .sha512."""

    def __init__(self):
        self.zip_bytes = make_zip_bytes()
        self.sha_text = (
            hashlib.sha512(self.zip_bytes).hexdigest() + "  arquivo.zip\n"
        )
        self.hits: dict[str, int] = {}
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                outer.hits[self.path] = outer.hits.get(self.path, 0) + 1
                if self.path == "/arquivo.zip":
                    body = outer.zip_bytes
                elif self.path == "/arquivo.zip.sha512":
                    body = outer.sha_text.encode()
                else:
                    self.send_error(404)
                    return
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"

    @property
    def zip_url(self) -> str:
        return f"{self.base_url}/arquivo.zip"

    @property
    def sha_url(self) -> str:
        return f"{self.base_url}/arquivo.zip.sha512"

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()


@pytest.fixture
def fake_tse():
    srv = FakeTSE()
    yield srv
    srv.close()


# ---------------------------------------------------------------------------
# Fixtures do BU (Task 3): CSV latin-1 minimo com o cabecalho real de 45 colunas
# (copiado de docs/fontes.md secao 4.1; o plano falava em 46 por engano).
# ---------------------------------------------------------------------------
BU_HEADER = (
    "DT_GERACAO;HH_GERACAO;ANO_ELEICAO;CD_TIPO_ELEICAO;NM_TIPO_ELEICAO;CD_PLEITO;DT_PLEITO;NR_TURNO;"
    "CD_ELEICAO;DS_ELEICAO;SG_UF;CD_MUNICIPIO;NM_MUNICIPIO;NR_ZONA;NR_SECAO;NR_LOCAL_VOTACAO;"
    "CD_CARGO_PERGUNTA;DS_CARGO_PERGUNTA;NR_PARTIDO;SG_PARTIDO;NM_PARTIDO;DT_BU_RECEBIDO;QT_APTOS;"
    "QT_COMPARECIMENTO;QT_ABSTENCOES;CD_TIPO_URNA;DS_TIPO_URNA;CD_TIPO_VOTAVEL;DS_TIPO_VOTAVEL;"
    "NR_VOTAVEL;NM_VOTAVEL;QT_VOTOS;NR_URNA_EFETIVADA;CD_CARGA_1_URNA_EFETIVADA;"
    "CD_CARGA_2_URNA_EFETIVADA;CD_FLASHCARD_URNA_EFETIVADA;DT_CARGA_URNA_EFETIVADA;"
    "DS_CARGO_PERGUNTA_SECAO;DS_SECOES_AGREGADAS;DT_ABERTURA;DT_ENCERRAMENTO;"
    "QT_ELEI_BIOM_SEM_HABILITACAO;DT_EMISSAO_BU;NR_JUNTA_APURADORA;NR_TURMA_APURADORA"
).split(";")


def bu_row(**over) -> dict:
    """Uma linha de BU (todas as 45 colunas, valores como no CSV real)."""
    row = {
        "DT_GERACAO": "05/10/2026", "HH_GERACAO": "14:03:43", "ANO_ELEICAO": "2026",
        "CD_TIPO_ELEICAO": "0", "NM_TIPO_ELEICAO": "Eleição Ordinária", "CD_PLEITO": "3220",
        "DT_PLEITO": "2026-10-04 00:00:00", "NR_TURNO": "1", "CD_ELEICAO": "6259",
        "DS_ELEICAO": "Eleições Gerais Estaduais 2026", "SG_UF": "TO", "CD_MUNICIPIO": "73377",
        "NM_MUNICIPIO": "GUARAÍ", "NR_ZONA": "20", "NR_SECAO": "86", "NR_LOCAL_VOTACAO": "1023",
        "CD_CARGO_PERGUNTA": "7", "DS_CARGO_PERGUNTA": "Deputado Estadual",
        "NR_PARTIDO": "22", "SG_PARTIDO": "PL", "NM_PARTIDO": "PARTIDO LIBERAL",
        "DT_BU_RECEBIDO": "2026-10-04 18:10:49", "QT_APTOS": "324", "QT_COMPARECIMENTO": "269",
        "QT_ABSTENCOES": "55", "CD_TIPO_URNA": "1", "DS_TIPO_URNA": "Apurada",
        "CD_TIPO_VOTAVEL": "1", "DS_TIPO_VOTAVEL": "Nominal", "NR_VOTAVEL": "22122",
        "NM_VOTAVEL": "JOSÉ D'ÁVILA 'ZÉ'", "QT_VOTOS": "6", "NR_URNA_EFETIVADA": "2152885",
        "CD_CARGA_1_URNA_EFETIVADA": "310.744.491.852.810.270.",
        "CD_CARGA_2_URNA_EFETIVADA": "818.968", "CD_FLASHCARD_URNA_EFETIVADA": "3C5F3F07",
        "DT_CARGA_URNA_EFETIVADA": "2026-09-24 13:31:00", "DS_CARGO_PERGUNTA_SECAO": "1 - 86",
        "DS_SECOES_AGREGADAS": "#NULO#", "DT_ABERTURA": "2026-10-04 08:00:01",
        "DT_ENCERRAMENTO": "2026-10-04 17:15:19", "QT_ELEI_BIOM_SEM_HABILITACAO": "11",
        "DT_EMISSAO_BU": "2026-10-04 17:17:14", "NR_JUNTA_APURADORA": "-1",
        "NR_TURMA_APURADORA": "-1",
    }
    unknown = set(over) - set(row)
    assert not unknown, unknown
    row.update(over)
    return row


def write_bu_csv(path, rows: list[dict]):
    """Grava `rows` como CSV real do TSE: latin-1, `;`, aspas em tudo, CRLF."""
    def q(v):
        return '"' + str(v).replace('"', '""') + '"'

    lines = [";".join(q(c) for c in BU_HEADER)]
    for r in rows:
        lines.append(";".join(q(r[c]) for c in BU_HEADER))
    path.write_bytes(("\r\n".join(lines) + "\r\n").encode("latin-1"))
    return path


@pytest.fixture
def bu_csv(tmp_path):
    """CSV de BU minimo com os casos que a normalizacao precisa tratar."""
    rows = [
        # nominal com acento, aspas simples e apostrofo
        bu_row(),
        # candidato sem partido: NR_PARTIDO -1, SG_PARTIDO #NULO#, e QT_VOTOS 0
        bu_row(NR_PARTIDO="-1", SG_PARTIDO="#NULO#", NM_PARTIDO="#NULO#", NR_VOTAVEL="22123",
               NM_VOTAVEL="MARIA", QT_VOTOS="0"),
        # branco
        bu_row(NR_PARTIDO="-1", SG_PARTIDO="#NULO#", NM_PARTIDO="#NULO#", CD_TIPO_VOTAVEL="2",
               DS_TIPO_VOTAVEL="Branco", NR_VOTAVEL="95", NM_VOTAVEL="Branco", QT_VOTOS="2"),
        # secao agregada
        bu_row(NR_SECAO="10", DS_SECOES_AGREGADAS="10 / 114", CD_TIPO_VOTAVEL="4",
               DS_TIPO_VOTAVEL="Legenda", NR_VOTAVEL="22", NM_VOTAVEL="Legenda", QT_VOTOS="3"),
    ]
    return write_bu_csv(tmp_path / "bweb_1t_TO_fake.csv", rows)
