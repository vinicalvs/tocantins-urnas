import json
import os
import time

import pytest

from tocantins.config import Source
from tocantins.download import HashMismatch, fetch, parse_sha512_text, sha512_file


def make_source(srv, with_sha=True):
    return Source(
        key="teste",
        url=srv.zip_url,
        sha_url=srv.sha_url if with_sha else None,
        filename="arquivo.zip",
    )


def test_parse_sha512_text_takes_first_token():
    assert parse_sha512_text("abc123  file.zip\n") == "abc123"


def test_fetch_downloads_and_verifies_hash(fake_tse, tmp_path):
    raw, manifest = tmp_path / "raw", tmp_path / "manifesto.json"
    entry = fetch(make_source(fake_tse), raw, manifest)
    assert (raw / "arquivo.zip").exists()
    assert entry["sha512"] == entry["published_sha512"]
    assert entry["sha512"] == sha512_file(raw / "arquivo.zip")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert len(data) == 1
    assert data["teste"]["key"] == "teste"
    for campo in ("url", "path", "size", "downloaded_at"):
        assert campo in data["teste"]


def test_fetch_is_idempotent(fake_tse, tmp_path):
    raw, manifest = tmp_path / "raw", tmp_path / "manifesto.json"
    src = make_source(fake_tse)
    first = fetch(src, raw, manifest)
    mtime = (raw / "arquivo.zip").stat().st_mtime_ns
    time.sleep(0.05)
    second = fetch(src, raw, manifest)
    assert fake_tse.hits["/arquivo.zip"] == 1
    assert (raw / "arquivo.zip").stat().st_mtime_ns == mtime
    assert second == first


def test_fetch_raises_on_hash_mismatch_and_keeps_no_partial_file(fake_tse, tmp_path):
    fake_tse.sha_text = "0" * 128 + "  arquivo.zip\n"
    raw, manifest = tmp_path / "raw", tmp_path / "manifesto.json"
    with pytest.raises(HashMismatch):
        fetch(make_source(fake_tse), raw, manifest)
    assert os.listdir(raw) == []
    assert not manifest.exists()


def test_fetch_without_sha_url_records_computed_hash(fake_tse, tmp_path):
    raw, manifest = tmp_path / "raw", tmp_path / "manifesto.json"
    entry = fetch(make_source(fake_tse, with_sha=False), raw, manifest)
    assert entry["published_sha512"] is None
    assert entry["sha512"] == sha512_file(raw / "arquivo.zip")
    assert "/arquivo.zip.sha512" not in fake_tse.hits
