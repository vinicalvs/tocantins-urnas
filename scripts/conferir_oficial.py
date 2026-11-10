"""Camada 4: confere a base com o resultado oficial publicado em resultados.tse.jus.br.

Alvos (spec secao 6, com Ruling R29):
- Prefeito 2024: os 139 municipios no turno 1 e os municipios do turno 2.
- Vereador 2024: os 139 municipios (o total estadual e a soma deles; nao ha arquivo estadual).
- Deputado Federal, Deputado Estadual, Governador (turnos 1 e 2) e Senador 2026: amostra de 10 municipios
  (5 maiores + 5 sorteados, semente 2026) e o arquivo estadual.

Os JSON oficiais ficam em dados_brutos/oficial/ (baixados uma vez, nunca sobrescritos).
Saida: validacao/camada4_oficial.json (uma linha por candidato/total conferido).

Uso: python -I scripts/conferir_oficial.py
"""
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tocantins.config import BASE, RAW, VALID  # noqa: E402
from tocantins.validate import layer4, result  # noqa: E402

CACHE = RAW / "oficial"
OUT = VALID / "camada4_oficial.json"


def alvos(bu, locais) -> list[tuple[int, str, int, str | None]]:
    pref = bu[bu["cargo"] == "Prefeito"]
    t1 = sorted(pref.loc[pref["turno"] == 1, "cd_municipio"].unique())
    t2 = sorted(pref.loc[pref["turno"] == 2, "cd_municipio"].unique())
    out = [(2024, "Prefeito", 1, m) for m in t1] + [(2024, "Prefeito", 2, m) for m in t2]
    out += [(2024, "Vereador", 1, m) for m in t1]
    amostra = layer4.sample_municipios(locais, 2026)
    for cargo, turno in (("Deputado Federal", 1), ("Deputado Estadual", 1), ("Governador", 1), ("Governador", 2),
                         ("Senador", 1)):
        out += [(2026, cargo, turno, m) for m in amostra] + [(2026, cargo, turno, None)]
    return out


def main() -> None:
    bu = result.load_bu_columns(BASE / "bu_secao.parquet", layer4.BU_COLUMNS)
    locais = result.load_bu_columns(BASE / "locais.parquet",
                                    ["ano", "turno", "cd_municipio", "zona", "secao", "eleitores_secao"])
    rows = []
    for ano, cargo, turno, mun in alvos(bu, locais):
        url = layer4.oficial_url(ano, cargo, turno, mun)
        cached = (CACHE / url.removeprefix(layer4.OFICIAL_BASE + "/")).exists()
        doc = layer4.fetch_oficial(url, CACHE)
        if not cached:
            time.sleep(0.1)
        for r in layer4.compare_oficial(bu, doc, ano, cargo, turno, mun):
            rows.append({**r, "fonte": url})
    tmp = OUT.with_name(OUT.name + ".tmp")
    tmp.write_text(json.dumps(rows, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    os.replace(tmp, OUT)
    bad = [r for r in rows if not r["ok"]]
    print(f"{len(rows)} linhas conferidas; {len(bad)} divergentes")
    for r in bad[:50]:
        print("DIVERGE", r["ano"], r["cargo"], r["turno"], r["cd_municipio"], r["candidato"],
              "site", r["votos_site"], "base", r["votos_base"])


if __name__ == "__main__":
    main()
