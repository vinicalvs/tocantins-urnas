"""Etapa 03: roda as 5 camadas + controles de Palmas e grava validacao/selo.json.

Saida 0 se o selo for "ok", 1 se "falhou" (a exportacao depende do selo ok).
Pre-requisito da camada 4: python -I scripts/conferir_oficial.py

Uso: python -I scripts/03_validar.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tocantins.config import BASE, RAW, VALID  # noqa: E402
from tocantins.validate import control, layer5, runner  # noqa: E402
from tocantins.validate.result import load_exceptions  # noqa: E402


def main() -> int:
    inputs = runner.load_inputs(BASE)
    results = runner.run_all(BASE, VALID, RAW / "manifesto.json", inputs=inputs)
    seal = runner.write_seal(results, VALID / "selo.json", manifest_path=RAW / "manifesto.json",
                             exceptions=load_exceptions(VALID / "excecoes.json"),
                             extra={"fora_do_controle": control.fora_do_controle(inputs["bu"]),
                                    "credibilidade": layer5.resumo(inputs["credibilidade"])})
    for r in results:
        print(f"camada {r.layer:9} {r.check:36} {'ok' if r.passed else 'FALHOU':7} "
              f"verificados={r.n_checked} divergencias={len(r.divergences)} sem_registro={r.unregistered}")
    print(f"selo: {seal['status']}  excecoes usadas={len(seal['excecoes_usadas'])} "
          f"nao usadas={len(seal['excecoes_nao_usadas'])}  fora do controle={seal['fora_do_controle']}")
    return 0 if seal["status"] == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
