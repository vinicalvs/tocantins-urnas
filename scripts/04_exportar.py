"""Etapa 04: exporta site_dados/ a partir da base validada (bloqueia sem selo ok).

Uso: python -I scripts/04_exportar.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tocantins.config import BASE, SITE_DATA, VALID  # noqa: E402
from tocantins.export import GateError, export_all  # noqa: E402


def main() -> int:
    try:
        s = export_all(BASE, SITE_DATA, VALID)
    except GateError as e:
        print(f"EXPORTACAO BLOQUEADA: {e}")
        return 1
    print(f"municipios={s['municipios']} arquivos={s['arquivos']} total={s['bytes'] / 1e6:.1f} MB "
          f"maior={s['maior'][0]} ({s['maior'][1] / 1e6:.2f} MB) "
          f"locais_sem_coordenadas={s['locais_sem_coordenadas']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
