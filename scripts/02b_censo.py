"""Censo 2022, coligacoes e ligacao setor -> local, gravados em base/.

Saidas: censo_setor, ibge_municipio, coligacoes, ligacao_setor_local (com as duas implementacoes),
local_credibilidade e area_votacao (.parquet). Rode depois de 01_baixar e 02_normalizar.

Uso: python -I scripts/02b_censo.py
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402

from tocantins import censo, coligacoes, crosswalk, ligacao  # noqa: E402
from tocantins.config import BASE, RAW  # noqa: E402


def mapa_ibge() -> dict[str, str]:
    nomes = pd.read_parquet(BASE / "bu_secao.parquet", columns=["cd_municipio", "nm_municipio"]).drop_duplicates()
    ibge = json.loads((RAW / "ibge" / "municipios_17.json").read_text(encoding="utf-8"))
    return crosswalk.build(nomes, ibge, crosswalk.load_overrides())


def main() -> None:
    t0 = time.time()
    setores = censo.build_setores(RAW)
    setores.to_parquet(BASE / "censo_setor.parquet")
    censo.build_municipios(RAW / "sidra").to_parquet(BASE / "ibge_municipio.parquet")
    print(f"censo: {len(setores)} setores, {setores['cd_mun_ibge'].nunique()} municipios ({time.time() - t0:.0f} s)")

    coligacoes.build(pd.read_parquet(BASE / "candidatos.parquet")).to_parquet(BASE / "coligacoes.parquet")

    cw = mapa_ibge()
    locais = pd.read_parquet(BASE / "locais.parquet")
    links, creds, areas_ = [], [], []
    for ano in (2024, 2026):
        loc = ligacao.locais_ano(locais, ano, cw)
        a = ligacao.link_numpy(setores, loc).assign(impl="numpy")
        b = ligacao.link_geopandas(setores, loc).assign(impl="geopandas")
        links += [a.assign(ano=ano), b.assign(ano=ano)]
        cred = ligacao.credibilidade(a, setores, loc)
        creds.append(cred.merge(loc[["cd_municipio", "id", "especial", "lat", "lon"]].rename(columns={"id": "local_id"}),
                                on=["cd_municipio", "local_id"]).assign(ano=ano))
        ar = ligacao.areas(a, setores, loc).assign(ano=ano)
        areas_.append(ar)
        print(f"{ano}: {len(loc)} locais ({int(loc['especial'].sum())} especiais), {len(a)} setores ligados, "
              f"{cred['credivel'].mean():.0%} locais criveis, {ar['area_id'].nunique()} areas")
    pd.concat(links, ignore_index=True).to_parquet(BASE / "ligacao_setor_local.parquet")
    pd.concat(creds, ignore_index=True).to_parquet(BASE / "local_credibilidade.parquet")
    pd.concat(areas_, ignore_index=True).to_parquet(BASE / "area_votacao.parquet")
    print(f"total {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
