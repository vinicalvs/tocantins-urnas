"""Conjuntura: o candidato da coligacao do prefeito de 2024 venceu no municipio em 2026?

- Prefeito: eleito de 2024 (turno 2 onde houve, senao turno 1), do munzona.
- Candidato da coligacao: candidatura de 2026 cujo `partidos` contem o partido do prefeito; havendo mais de
  uma, a do proprio partido, senao a mais votada no municipio. Fora da disputa (ex.: 2o turno) = sem_candidato.
- Entregou: ficou entre os `VAGAS[cargo]` mais votados do municipio (Governador 1, Senador 2).
- Margem: votos dele - votos do k-esimo mais votado entre os OUTROS (k = vagas), isto e, contra o primeiro
  que ficaria de fora; positiva se e so se entregou. `margem_pp` sobre os votos nominais do municipio.
- Empate de votos: menor numero primeiro.
"""
import pandas as pd

from tocantins.coligacoes import norm_sigla

VAGAS = {"Governador": 1, "Senador": 2}
COLS = ["cd_municipio", "prefeito_nr", "prefeito_nome", "prefeito_partido", "status", "cand_nr", "cand_nome",
        "cand_partido", "cand_votos", "venc_nr", "venc_nome", "venc_partido", "margem_votos", "margem_pp"]


def prefeitos(bu, munzona: pd.DataFrame) -> pd.DataFrame:
    """cd_municipio, nr, nome, partido do prefeito eleito em 2024. `bu` nao e usado (interface do plano)."""
    p = munzona[(munzona["ano"] == 2024) & (munzona["cargo"] == "Prefeito")]
    p = p[p["situacao_turno"].astype(str).str.upper().str.startswith("ELEITO")]
    p = p.sort_values(["cd_municipio", "turno"], ascending=[True, False]).drop_duplicates("cd_municipio")
    return (p.rename(columns={"nr_candidato": "nr", "nm_candidato": "nome", "sg_partido": "partido"})
            [["cd_municipio", "nr", "nome", "partido"]].reset_index(drop=True))


def entrega(bu: pd.DataFrame, prefeitos: pd.DataFrame, coligacoes: pd.DataFrame, cargo: str,
            turno: int) -> pd.DataFrame:
    vagas = VAGAS[cargo]
    b = bu[(bu["ano"] == 2026) & (bu["cargo"] == cargo) & (bu["turno"] == turno) & (bu["tipo_votavel"] == "Nominal")]
    votos = (b.groupby(["cd_municipio", "nr_votavel"], as_index=False)
             .agg(votos=("votos", "sum"), nome=("nm_votavel", "first"), partido=("sg_partido", "first")))
    col = coligacoes[(coligacoes["ano"] == 2026) & (coligacoes["cargo"] == cargo)]
    membros = {int(r.nr_candidato): {norm_sigla(x) for x in r.partidos} for r in col.itertuples()}
    proprio = {int(r.nr_candidato): norm_sigla(r.sg_partido) for r in col.itertuples()}
    rows = []
    for p in prefeitos.itertuples(index=False):
        v = votos[votos["cd_municipio"] == p.cd_municipio].assign(neg=lambda d: -d["votos"])
        v = v.sort_values(["neg", "nr_votavel"]).reset_index(drop=True)
        r = {"cd_municipio": p.cd_municipio, "prefeito_nr": p.nr, "prefeito_nome": p.nome,
             "prefeito_partido": p.partido, "status": "sem_candidato"}
        if not v.empty:
            r |= {"venc_nr": int(v.at[0, "nr_votavel"]), "venc_nome": v.at[0, "nome"], "venc_partido": v.at[0, "partido"]}
        sp = norm_sigla(p.partido)
        cands = v[[sp in membros.get(int(n), set()) for n in v["nr_votavel"]]]
        if not cands.empty:
            own = cands[[proprio.get(int(n)) == sp for n in cands["nr_votavel"]]]
            c = (own if not own.empty else cands).iloc[0]
            pos = int(c.name)
            outros = v.drop(index=pos)["votos"].to_numpy()
            ref = outros[vagas - 1] if len(outros) >= vagas else 0
            validos = v["votos"].sum()
            margem = int(c["votos"]) - int(ref)
            r |= {"status": "entregou" if pos < vagas else "nao_entregou", "cand_nr": int(c["nr_votavel"]),
                  "cand_nome": c["nome"], "cand_partido": c["partido"], "cand_votos": int(c["votos"]),
                  "margem_votos": margem, "margem_pp": 100 * margem / validos if validos else None}
        rows.append(r)
    return pd.DataFrame(rows, columns=COLS)
