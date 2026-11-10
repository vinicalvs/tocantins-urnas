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
