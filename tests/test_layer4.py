import json

import pandas as pd

from tocantins.validate import layer4


def bu_mun(mun, votos, turno=1, ano=2024, cargo="Prefeito", cd_cargo=11):
    """votos: {nr: qtd} (Nominal), mais 5 brancos."""
    rows = [{"ano": ano, "turno": turno, "cargo": cargo, "cd_cargo": cd_cargo, "cd_municipio": mun,
             "zona": 1, "secao": 1, "tipo_votavel": "Nominal", "nr_votavel": nr,
             "nm_votavel": f"CAND {nr}", "votos": v} for nr, v in votos.items()]
    rows.append({**rows[0], "tipo_votavel": "Branco", "nr_votavel": 95, "nm_votavel": "Branco", "votos": 5})
    return rows


def mz(mun, situacoes, turno=1, ano=2024, cargo="Prefeito"):
    return [{"ano": ano, "turno": turno, "cargo": cargo, "cd_municipio": mun, "zona": 1,
             "nr_candidato": nr, "situacao_turno": s} for nr, s in situacoes.items()]


def test_prefeito_winner_ok_and_mismatch_is_flagged():
    bu = pd.DataFrame(bu_mun("1", {10: 60, 20: 40}) + bu_mun("2", {10: 30, 20: 70}))
    munzona = pd.DataFrame(mz("1", {10: "ELEITO", 20: "NÃO ELEITO"}) + mz("2", {10: "ELEITO", 20: "NÃO ELEITO"}))
    w = layer4.prefeito_winners(bu, munzona).set_index("cd_municipio")
    assert w.loc["1", "ok"] and w.loc["1", "nr_bu"] == "10" and w.loc["1", "nr_oficial"] == "10"
    assert not w.loc["2", "ok"] and w.loc["2", "nr_bu"] == "20" and w.loc["2", "nr_oficial"] == "10"


def test_prefeito_t2_uses_t2_votes():
    bu = pd.DataFrame(bu_mun("1", {10: 45, 20: 35, 30: 20}) + bu_mun("1", {10: 40, 20: 60}, turno=2))
    munzona = pd.DataFrame(mz("1", {10: "2º TURNO", 20: "2º TURNO", 30: "NÃO ELEITO"})
                           + mz("1", {10: "NÃO ELEITO", 20: "ELEITO"}, turno=2))
    w = layer4.prefeito_winners(bu, munzona).set_index("turno")
    assert w.loc[2, "nr_bu"] == "20" and w.loc[2, "ok"]
    # turno 1 de municipio com 2o turno: compara os dois mais votados com os "2º TURNO"
    assert w.loc[1, "nr_bu"] == "10/20" and w.loc[1, "nr_oficial"] == "10/20" and w.loc[1, "ok"]


def test_prefeito_winner_tie_is_flagged():
    bu = pd.DataFrame(bu_mun("1", {10: 50, 20: 50}))
    munzona = pd.DataFrame(mz("1", {10: "ELEITO", 20: "NÃO ELEITO"}))
    w = layer4.prefeito_winners(bu, munzona)
    assert not w["ok"].iloc[0] and w["nr_bu"].iloc[0] == "empate:10=20"


def test_sample_is_deterministic_and_has_10_distinct():
    locais = pd.DataFrame([{"ano": 2024, "turno": t, "cd_municipio": str(100 + i), "zona": 1, "secao": s,
                            "eleitores_secao": 1000 - i} for i in range(30) for s in (1, 2) for t in (1, 2)])
    a = layer4.sample_municipios(locais, 2024)
    b = layer4.sample_municipios(locais, 2024)
    assert a == b and len(a) == 10 and len(set(a)) == 10
    assert a[:5] == ["100", "101", "102", "103", "104"]
    assert not set(a[5:]) & set(a[:5])
    assert layer4.sample_municipios(locais, 2024, seed=1) != a


def test_expected_table_has_votes_and_pct_validos():
    bu = pd.DataFrame(bu_mun("1", {10: 60, 20: 40}) + bu_mun("2", {10: 1}))
    t = layer4.expected_table(bu, "1", "Prefeito", 1)
    assert t[["nr_votavel", "votos"]].values.tolist() == [[10, 60], [20, 40]]
    assert t["pct_validos"].tolist() == [60.0, 40.0]
    assert t["candidato"].tolist() == ["CAND 10", "CAND 20"]


def test_run_visual_missing_file_fails(tmp_path):
    bu = pd.DataFrame(bu_mun("1", {10: 60, 20: 40}))
    munzona = pd.DataFrame(mz("1", {10: "ELEITO", 20: "NÃO ELEITO"}))
    res = {r.check: r for r in layer4.run(bu, munzona, tmp_path / "nao_existe.json", [])}
    assert res["prefeito_winners"].passed
    assert not res["visual_amostra"].passed


def test_run_visual_with_mismatch_fails_and_all_ok_passes(tmp_path):
    bu = pd.DataFrame(bu_mun("1", {10: 60, 20: 40}))
    munzona = pd.DataFrame(mz("1", {10: "ELEITO", 20: "NÃO ELEITO"}))
    p = tmp_path / "camada4_visual.json"
    linha = {"cargo": "Prefeito", "turno": 1, "cd_municipio": "1", "candidato": "CAND 10", "votos_site": 60,
             "votos_base": 60, "ok": True, "data_consulta": "2026-11-10"}
    p.write_text(json.dumps([linha, {**linha, "candidato": "CAND 20", "votos_site": 41, "votos_base": 40,
                                     "ok": False}]), encoding="utf-8")
    r = {r.check: r for r in layer4.run(bu, munzona, p, [])}["visual_amostra"]
    assert not r.passed and r.divergences["candidato"].tolist() == ["CAND 20"]
    p.write_text(json.dumps([linha]), encoding="utf-8")
    assert {r.check: r for r in layer4.run(bu, munzona, p, [])}["visual_amostra"].passed


def doc_oficial(cands, vb=5, vn=0, vnt=0, legenda=None):
    """Arquivo -u.json minimo do resultados.tse.jus.br. cands: [(nr, nome, votos)]"""
    par = [{"n": "10", "sg": "P10", "cand": [{"n": str(nr), "nmu": nm, "vap": str(v), "dvt": "Válido", "st": "x"}
                                            for nr, nm, v in cands]}]
    if legenda is not None:
        par[0]["tval"] = str(legenda)        # legenda apurada (como vap dos candidatos)
        par[0]["tvtl"] = "0"                 # legenda valida: difere quando o partido e anulado
    return {"dg": "15/10/2026", "hg": "09:22:26", "carg": [{"cd": "11", "agr": [{"par": par}]}],
            "v": {"vb": str(vb), "vn": str(vn), "vnt": str(vnt)}}


def test_parse_oficial_reads_candidates_and_totals():
    cands, tot = layer4.parse_oficial(doc_oficial([(10, "A", 60), (20, "B", 40)], vb=5, vn=2, vnt=3, legenda=7))
    assert cands[["nr_votavel", "candidato", "votos"]].values.tolist() == [[10, "A", 60], [20, "B", 40]]
    assert tot == {"brancos": 5, "nulos": 2, "nulos_tecnicos": 3, "legenda": {10: 7}}


def test_compare_oficial_reconciles_candidates_totals_and_technical_nulls():
    bu = pd.DataFrame(bu_mun("1", {10: 60, 20: 40, 30: 3}))   # 30: candidato fora da lista oficial
    doc = doc_oficial([(10, "A", 60), (20, "B", 40)], vb=5, vnt=3)
    rows = layer4.compare_oficial(bu, doc, ano=2024, cargo="Prefeito", turno=1, cd_municipio="1")
    by = {r["candidato"]: r for r in rows}
    assert all(r["ok"] for r in rows), rows
    assert by["NULOS_TECNICOS"]["votos_base"] == 3 and by["BRANCOS"]["votos_site"] == 5
    doc2 = doc_oficial([(10, "A", 61), (20, "B", 40)], vb=5, vnt=3)
    bad = [r for r in layer4.compare_oficial(bu, doc2, 2024, "Prefeito", 1, "1") if not r["ok"]]
    assert [(r["candidato"], r["votos_site"], r["votos_base"]) for r in bad] == [("10 A", 61, 60)]


def test_compare_oficial_state_level_sums_all_municipios():
    bu = pd.DataFrame(bu_mun("1", {10: 60}) + bu_mun("2", {10: 40}))
    rows = layer4.compare_oficial(bu, doc_oficial([(10, "A", 100)], vb=10), 2024, "Prefeito", 1, None)
    assert all(r["ok"] for r in rows) and rows[0]["cd_municipio"] == "TO"


def test_oficial_url():
    assert layer4.oficial_url(2024, "Vereador", 1, "73440") == \
        "https://resultados.tse.jus.br/oficial/ele2024/619/dados/to/to73440-c0013-e000619-u.json"
    assert layer4.oficial_url(2024, "Prefeito", 2, "73440").endswith("ele2024/620/dados/to/to73440-c0011-e000620-u.json")
    assert layer4.oficial_url(2026, "Deputado Federal", 1, None).endswith("ele2026/6259/dados/to/to-c0006-e006259-u.json")


def test_compare_oficial_party_outside_official_list_counts_as_technical_null():
    bu = pd.DataFrame(bu_mun("1", {10: 60}) + [{**bu_mun("1", {10: 60})[0], "tipo_votavel": "Legenda",
                                                "nr_votavel": 23, "votos": 2}])
    rows = layer4.compare_oficial(bu, doc_oficial([(10, "A", 60)], vb=5, vnt=2), 2024, "Prefeito", 1, "1")
    by = {r["candidato"]: r for r in rows}
    assert by["NULOS_TECNICOS"]["votos_base"] == 2 and by["NULOS_TECNICOS"]["ok"]
    assert "LEGENDA 23" not in by


def _alvo(tmp_path, doc, mun="1"):
    """Grava o doc oficial no cache e um camada4_oficial.json antigo dizendo que tudo bateu."""
    url = layer4.oficial_url(2024, "Prefeito", 1, mun)
    dst = tmp_path / "cache" / url.removeprefix(layer4.OFICIAL_BASE + "/")
    dst.parent.mkdir(parents=True)
    dst.write_text(json.dumps(doc), encoding="utf-8")
    p = tmp_path / "camada4_oficial.json"
    p.write_text(json.dumps([{"ano": 2024, "cargo": "Prefeito", "turno": 1, "cd_municipio": mun,
                              "candidato": "10 A", "votos_site": 60, "votos_base": 60, "ok": True,
                              "data_consulta": "x", "fonte": url}]), encoding="utf-8")
    return p


def test_run_visual_recomputes_against_current_base_not_stale_file(tmp_path):
    munzona = pd.DataFrame(mz("1", {10: "ELEITO", 20: "NÃO ELEITO"}))
    p = _alvo(tmp_path, doc_oficial([(10, "A", 60), (20, "B", 40)], vb=5))
    ok = pd.DataFrame(bu_mun("1", {10: 60, 20: 40}))
    assert {r.check: r for r in layer4.run(ok, munzona, p, [], tmp_path / "cache")}["visual_amostra"].passed
    mudou = pd.DataFrame(bu_mun("1", {10: 59, 20: 40}))           # base re-normalizada, arquivo antigo
    r = {r.check: r for r in layer4.run(mudou, munzona, p, [], tmp_path / "cache")}["visual_amostra"]
    assert not r.passed and r.divergences["candidato"].tolist() == ["10 A"]


def test_run_visual_missing_cached_official_file_fails(tmp_path):
    munzona = pd.DataFrame(mz("1", {10: "ELEITO"}))
    p = _alvo(tmp_path, doc_oficial([(10, "A", 60)]))
    r = {r.check: r for r in layer4.run(pd.DataFrame(bu_mun("1", {10: 60})), munzona, p, [],
                                        tmp_path / "outro_cache")}["visual_amostra"]
    assert not r.passed and r.divergences["motivo"].tolist() == ["cache_ausente"]
