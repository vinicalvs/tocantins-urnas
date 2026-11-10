"""Teste de fumaca: so passa depois de `python -I scripts/01_baixar.py`."""
import json

from tocantins.config import RAW, SOURCES

BU_KEYS = ("bu24_t1", "bu24_t2", "bu26_t1", "bu26_t2")


def test_manifest_has_all_sources_with_matching_hash():
    manifest = json.loads((RAW / "manifesto.json").read_text(encoding="utf-8"))
    for key in SOURCES:
        assert key in manifest, f"{key} ausente do manifesto"
    for key in BU_KEYS:
        entry = manifest[key]
        assert entry["published_sha512"] is not None
        assert entry["sha512"] == entry["published_sha512"]
