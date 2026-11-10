"""Download idempotente de fontes do TSE com verificacao SHA-512."""
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import requests

from tocantins.config import Source

CHUNK = 1024 * 1024
TIMEOUT = (15, 120)


class HashMismatch(Exception):
    """O hash do arquivo baixado difere do hash publicado pelo TSE."""


def sha512_file(path: Path) -> str:
    h = hashlib.sha512()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


_HEX = set("0123456789abcdefABCDEF")


def parse_sha512_text(text: str) -> str:
    """Extrai o hash (primeiro token hexadecimal) de um arquivo .sha512, em minusculas."""
    tokens = text.split()
    if not tokens:
        raise ValueError("corpo do .sha512 vazio: nenhum hash sha512 encontrado")
    token = tokens[0]
    if not set(token) <= _HEX:
        raise ValueError(
            f"corpo do .sha512 mal formado: primeiro token nao e hexadecimal ({token[:40]!r})"
        )
    return token.lower()


def _load_manifest(manifest_path: Path) -> dict:
    if manifest_path.exists():
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    return {}


def _save_manifest(manifest_path: Path, manifest: dict) -> None:
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = manifest_path.with_name(manifest_path.name + ".tmp")
    tmp.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, manifest_path)


def _published_hash(source: Source) -> str | None:
    if source.sha_url is None:
        return None
    resp = requests.get(source.sha_url, timeout=TIMEOUT)
    resp.raise_for_status()
    return parse_sha512_text(resp.text)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def fetch(source: Source, raw_dir: Path, manifest_path: Path) -> dict:
    """Baixa `source` para `raw_dir`; idempotente e nunca sobrescreve dado bruto.

    Se o arquivo ja existe e consta no manifesto, nao faz requisicao alguma.
    O download vai para `<filename>.part` e so vira arquivo final apos o
    SHA-512 conferir com o publicado (quando houver).
    """
    raw_dir = Path(raw_dir)
    manifest_path = Path(manifest_path)
    raw_dir.mkdir(parents=True, exist_ok=True)
    final = raw_dir / source.filename
    final.parent.mkdir(parents=True, exist_ok=True)
    manifest = _load_manifest(manifest_path)

    if final.exists():
        entry = manifest.get(source.key)
        if entry is not None:
            if entry["size"] != final.stat().st_size:
                raise RuntimeError(
                    f"{final} diverge do manifesto (tamanho); dado bruto nao sera sobrescrito"
                )
            return entry
        # Arquivo existente sem registro: registra sem baixar de novo.
        digest = sha512_file(final)
        published = _published_hash(source)
        if published is not None and published.lower() != digest.lower():
            raise HashMismatch(f"{source.key}: {digest} != publicado {published}")
        entry = _entry(source, final, digest, published, _now())
        manifest[source.key] = entry
        _save_manifest(manifest_path, manifest)
        return entry

    published = _published_hash(source)
    part = raw_dir / (source.filename + ".part")
    h = hashlib.sha512()
    try:
        with requests.get(source.url, stream=True, timeout=TIMEOUT) as resp:
            resp.raise_for_status()
            with open(part, "wb") as f:
                for chunk in resp.iter_content(CHUNK):
                    f.write(chunk)
                    h.update(chunk)
        digest = h.hexdigest()
        if published is not None and published.lower() != digest.lower():
            raise HashMismatch(f"{source.key}: {digest} != publicado {published}")
        os.replace(part, final)
    except BaseException:
        part.unlink(missing_ok=True)
        raise

    entry = _entry(source, final, digest, published, _now())
    manifest[source.key] = entry
    _save_manifest(manifest_path, manifest)
    return entry


def _entry(source: Source, final: Path, digest: str, published: str | None, when: str) -> dict:
    return {
        "key": source.key,
        "url": source.url,
        "path": str(final),
        "size": final.stat().st_size,
        "sha512": digest,
        "published_sha512": published,
        "downloaded_at": when,
    }
