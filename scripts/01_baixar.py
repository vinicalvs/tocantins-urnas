"""Baixa todas as fontes do TSE e descompacta cada zip em dados_brutos/<chave>/.

Uso: python -I scripts/01_baixar.py

O conteudo dos zips e dado nao confiavel: so e extraido (com checagem de
caminhos), nunca executado. Cada zip vai para a sua propria pasta nova.
"""
import shutil
import sys
import zipfile
from pathlib import Path

# Com `python -I` o diretorio do script nao entra em sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tocantins.config import RAW, SOURCES  # noqa: E402
from tocantins.download import fetch  # noqa: E402


def safe_extract(zip_path: Path, dest: Path) -> list[str]:
    """Extrai `zip_path` em `dest` (pasta nova), recusando caminhos fora de `dest`."""
    dest_root = dest.resolve()
    names = []
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            target = (dest / info.filename).resolve()
            if target != dest_root and dest_root not in target.parents:
                raise RuntimeError(f"{zip_path.name}: entrada insegura {info.filename!r}")
        zf.extractall(dest)
        names = [i.filename for i in zf.infolist() if not i.is_dir()]
    return names


def extract_once(key: str, zip_path: Path) -> None:
    dest = RAW / key
    if dest.exists():
        print(f"  {key}: ja descompactado em {dest.name}/")
        return
    tmp = RAW / f".{key}.extraindo"
    if tmp.exists():
        shutil.rmtree(tmp)
    try:
        names = safe_extract(zip_path, tmp)
        tmp.rename(dest)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    print(f"  {key}: {len(names)} arquivo(s) -> {dest.name}/")


def main() -> None:
    manifest_path = RAW / "manifesto.json"
    for key, source in SOURCES.items():
        print(f"[{key}] {source.url}")
        entry = fetch(source, RAW, manifest_path)
        print(f"  {entry['size']:,} bytes, sha512 {entry['sha512'][:16]}...")
        extract_once(key, Path(entry["path"]))


if __name__ == "__main__":
    main()
