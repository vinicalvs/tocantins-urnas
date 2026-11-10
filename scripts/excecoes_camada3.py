"""Registra em validacao/excecoes.json as excecoes investigadas da camada 3.

1. bu_vs_munzona_nominal: votos nominais do BU para candidatos ausentes do munzona sao
   "nulos tecnicos" (candidatura indeferida/cancelada: a urna conta como nominal, a
   totalizacao como nulo). So vira excecao a zona em que a soma dessas divergencias e
   EXATAMENTE o QT_VOTOS_NULOS_TECNICOS do detalhe_votacao_munzona bruto; o resto fica
   sem registro e reprova a camada. A chave inclui votos_bu, entao mudanca reabre o achado.
2. cobertura_fontes: votacao_secao nao publica Presidente (docs/fontes.md secao 2, item 2).

Uso: python -I scripts/excecoes_camada3.py
"""
import json
import os
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import duckdb  # noqa: E402

from tocantins.config import BASE, RAW, VALID  # noqa: E402
from tocantins.validate import layer3, result  # noqa: E402

TAG = "[camada3-auto] "
CAUSA_NT = (TAG + "Nulo tecnico: voto nominal da urna para candidato com candidatura indeferida/cancelada; "
            "o munzona nao lista o candidato. Soma da zona = QT_VOTOS_NULOS_TECNICOS do detalhe bruto ({nt}).")
CAUSA_PRES = (TAG + "votacao_secao do TSE nao publica Presidente (so cargos estaduais); "
              "Presidente por secao vem so do BU (docs/fontes.md secao 2, item 2).")
DETALHE_CSV = [
    RAW / "detalhe24" / "detalhe_votacao_munzona_2024_TO.csv",
    RAW / "detalhe26" / "detalhe_votacao_munzona_2026_TO.csv",
    RAW / "detalhe26" / "detalhe_votacao_munzona_2026_BR.csv",
]


def nulos_tecnicos() -> dict[tuple, int]:
    files = "[" + ", ".join("'" + str(p).replace("'", "''") + "'" for p in DETALHE_CSV) + "]"
    rows = duckdb.sql(f"""
        SELECT ANO_ELEICAO::INT, NR_TURNO::INT, DS_CARGO, CD_MUNICIPIO, NR_ZONA::INT,
               SUM(QT_VOTOS_NULOS_TECNICOS::INT)
        FROM read_csv({files}, delim=';', all_varchar=true, encoding='latin-1', union_by_name=true)
        WHERE SG_UF = 'TO' AND CD_ELEICAO <> '6286'
        GROUP BY ALL
    """).fetchall()
    return {tuple(r[:5]): int(r[5]) for r in rows}


def main() -> None:
    r = result.load_bu_columns
    bu = r(BASE / "bu_secao.parquet", layer3.BU_COLUMNS)
    mz = r(BASE / "munzona.parquet", layer3.MUNZONA_COLUMNS)
    vs = r(BASE / "votacao_secao.parquet", layer3.SECAO_COLUMNS)
    dt = r(BASE / "detalhe_munzona.parquet", layer3.DETALHE_COLUMNS)
    div = layer3.conform("bu_vs_munzona_nominal", layer3.pandas_impl(bu, mz, vs, dt)["bu_vs_munzona_nominal"])
    nt = nulos_tecnicos()
    hoje = date.today().isoformat()

    novas, sem = [], 0
    for zkey, g in div.groupby(["ano", "turno", "cargo", "cd_municipio", "zona"]):
        zkey = tuple(int(x) if i in (0, 1, 4) else x for i, x in enumerate(zkey))
        esperado = nt.get(zkey, 0)
        if (g["votos_ref"] == 0).all() and int(g["votos_bu"].sum()) == esperado:
            for row in g.to_dict("records"):
                key = {k: (int(v) if k not in ("cargo", "cd_municipio") else v) for k, v in row.items()}
                novas.append({"layer": "3", "check": "bu_vs_munzona_nominal", "key": key,
                              "cause": CAUSA_NT.format(nt=esperado), "approved_on": hoje})
        else:
            sem += len(g)
            print("SEM EXPLICACAO:", zkey, "divergencias", int(g["votos_bu"].sum()), "nulos tecnicos", esperado)
    for turno in (1, 2):
        novas.append({"layer": "3", "check": "cobertura_fontes",
                      "key": {"fonte": "votacao_secao", "ano": 2026, "turno": turno, "cargo": "Presidente",
                              "lado": "so_bu"},
                      "cause": CAUSA_PRES, "approved_on": hoje})

    path = VALID / "excecoes.json"
    atuais = result.load_exceptions(path)
    mantidas = [e for e in atuais if not e["cause"].startswith(TAG)]
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(mantidas + novas, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    print(f"{len(novas)} excecoes da camada 3 gravadas; {sem} divergencias sem explicacao")


if __name__ == "__main__":
    main()
