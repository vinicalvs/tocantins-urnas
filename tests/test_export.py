import json
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from tocantins import export

MUN = {"73440": ("PALMAS", 1721000), "92410": ("ARAGUAÍNA", 1702109)}


def bu_row(ano, turno, cargo, cd_cargo, mun, zona, secao, local, tipo, nr, votos, nm=None, sg=None,
           aptos=100, comp=80):
    return {"ano": ano, "turno": turno, "cargo": cargo, "cd_cargo": cd_cargo, "cd_municipio": mun,
            "nm_municipio": MUN[mun][0], "zona": zona, "secao": secao, "local": local, "aptos": aptos,
            "comparecimento": comp, "abstencoes": aptos - comp, "tipo_votavel": tipo, "nr_votavel": nr,
            "nm_votavel": nm or f"CAND {nr}", "nr_partido": int(str(nr)[:2]) if tipo in ("Nominal", "Legenda") else None,
            "sg_partido": sg, "votos": votos}


def secao(ano, turno, cargo, cd_cargo, mun, zona, sec, local, votos, comp=None):
    """votos: {(tipo, nr, sg): qtd}"""
    comp = comp if comp is not None else sum(votos.values())
    return [bu_row(ano, turno, cargo, cd_cargo, mun, zona, sec, local, t, nr, v, sg=sg, comp=comp,
                   nm={"Branco": "Branco", "Nulo": "Nulo"}.get(t, "JOSÉ D'ÁVILA" if nr == 10 else None))
            for (t, nr, sg), v in votos.items()]


@pytest.fixture
def base(tmp_path):
    b = tmp_path / "base"
    b.mkdir()
    bu = pd.DataFrame(
        # Palmas, Prefeito T1: mesmo nr_local 1012 nas zonas 6 e 7
        secao(2024, 1, "Prefeito", 11, "73440", 6, 1, 1012, {("Nominal", 10, "AA"): 30, ("Nominal", 20, "BB"): 20,
                                                              ("Branco", 95, None): 2})
        + secao(2024, 1, "Prefeito", 11, "73440", 7, 5, 1012, {("Nominal", 10, "AA"): 5, ("Nominal", 20, "BB"): 40,
                                                                ("Nominal", 77, "CC"): 3})
        # Palmas T2
        + secao(2024, 2, "Prefeito", 11, "73440", 6, 1, 1012, {("Nominal", 10, "AA"): 25, ("Nominal", 20, "BB"): 30})
        # Araguaina so T1, Vereador com legenda
        + secao(2024, 1, "Prefeito", 11, "92410", 1, 1, 1001, {("Nominal", 10, "AA"): 9})
        + secao(2024, 1, "Vereador", 13, "92410", 1, 1, 1001, {("Nominal", 10111, "AA"): 6, ("Legenda", 10, "AA"): 2,
                                                               ("Nulo", 96, None): 1})
    )
    bu.to_parquet(b / "bu_secao.parquet")
    locais = pd.DataFrame([
        {"ano": 2024, "turno": t, "cd_municipio": m, "zona": z, "secao": s, "local": loc,
         "nm_local": f"ESCOLA {z}-{loc}", "endereco": "RUA A", "bairro": "CENTRO", "lat": lat, "lon": lon,
         "eleitores_secao": 100, "tipo_secao": "Principal"}
        for t, m, z, s, loc, lat, lon in [
            (1, "73440", 6, 1, 1012, -10.18, -48.33), (1, "73440", 7, 5, 1012, None, None),
            (2, "73440", 6, 1, 1012, -10.18, -48.33), (1, "92410", 1, 1, 1001, -7.19, -48.2)]])
    locais.to_parquet(b / "locais.parquet")
    munzona = pd.DataFrame([
        {"ano": 2024, "turno": t, "cargo": c, "cd_municipio": m, "zona": z, "nr_candidato": nr,
         "nm_candidato": f"NOME {nr}", "sg_partido": sg, "votos_nominais": 0, "situacao_turno": st}
        for t, c, m, z, nr, sg, st in [
            (1, "Prefeito", "73440", 6, 10, "AA", "2º TURNO"), (1, "Prefeito", "73440", 6, 20, "BB", "2º TURNO"),
            (2, "Prefeito", "73440", 6, 10, "AA", "NÃO ELEITO"), (2, "Prefeito", "73440", 6, 20, "BB", "ELEITO"),
            (1, "Prefeito", "92410", 1, 10, "AA", "ELEITO"), (1, "Vereador", "92410", 1, 10111, "AA", None)]])
    munzona.to_parquet(b / "munzona.parquet")
    return b


@pytest.fixture
def ibge_dir(tmp_path):
    d = tmp_path / "ibge"
    d.mkdir()
    (d / "municipios_17.json").write_text(json.dumps(
        [{"id": i, "nome": n.title().replace("Í", "í")} for n, i in MUN.values()]), encoding="utf-8")
    (d / "malha_to.geojson").write_text('{"type":"FeatureCollection","features":[]}', encoding="utf-8")
    return d


def seal(valid_dir, status="ok", when=None):
    valid_dir.mkdir(exist_ok=True)
    when = when or datetime.now(timezone.utc) + timedelta(seconds=5)
    (valid_dir / "selo.json").write_text(json.dumps({"status": status, "data": when.isoformat()}), encoding="utf-8")


def run(base, tmp_path, ibge_dir):
    out = tmp_path / "site_dados"
    seal(tmp_path / "validacao")
    stats = export.export_all(base, out, tmp_path / "validacao", ibge_dir=ibge_dir, n_municipios=2)
    return out, stats


def load(p):
    return json.loads(p.read_text(encoding="utf-8"))


def test_export_refuses_without_ok_seal(base, tmp_path, ibge_dir):
    with pytest.raises(export.GateError):
        export.export_all(base, tmp_path / "o", tmp_path / "validacao", ibge_dir=ibge_dir, n_municipios=2)
    seal(tmp_path / "validacao", status="falhou")
    with pytest.raises(export.GateError):
        export.export_all(base, tmp_path / "o", tmp_path / "validacao", ibge_dir=ibge_dir, n_municipios=2)
    assert not (tmp_path / "o").exists()


def test_export_refuses_seal_older_than_base(base, tmp_path, ibge_dir):
    seal(tmp_path / "validacao", when=datetime(2020, 1, 1, tzinfo=timezone.utc))
    with pytest.raises(export.GateError):
        export.export_all(base, tmp_path / "o", tmp_path / "validacao", ibge_dir=ibge_dir, n_municipios=2)


def test_export_omits_missing_turn_files_and_index_lists_only_existing(base, tmp_path, ibge_dir):
    out, _ = run(base, tmp_path, ibge_dir)
    assert (out / "73440" / "2024_prefeito_t2.json").exists()
    assert not (out / "92410" / "2024_prefeito_t2.json").exists()
    idx = {m["cod"]: m for m in load(out / "index.json")["municipios"]}
    assert idx["73440"]["disponivel"] == {"2024": {"prefeito": [1, 2]}}
    assert idx["92410"]["disponivel"] == {"2024": {"prefeito": [1], "vereador": [1]}}
    assert idx["73440"]["ibge"] == "1721000" and idx["92410"]["nome"] == "ARAGUAÍNA"
    assert load(out / "selo_validacao.json")["status"] == "ok"
    assert (out / "malha_to.geojson").exists()


def test_local_without_coords_has_null_latlon_and_is_counted(base, tmp_path, ibge_dir):
    out, stats = run(base, tmp_path, ibge_dir)
    d = load(out / "73440" / "2024_prefeito_t1.json")
    loc = {l["id"]: l for l in d["locais"]}
    assert loc["7-1012"]["lat"] is None and loc["7-1012"]["lon"] is None
    assert loc["6-1012"]["lat"] == -10.18
    idx = {m["cod"]: m for m in load(out / "index.json")["municipios"]}
    assert idx["73440"]["locais_sem_coordenadas"] == 1
    assert stats["locais_sem_coordenadas"] >= 1


def test_local_id_includes_zone(base, tmp_path, ibge_dir):
    out, _ = run(base, tmp_path, ibge_dir)
    d = load(out / "73440" / "2024_prefeito_t1.json")
    loc = {l["id"]: l for l in d["locais"]}
    assert set(loc) == {"6-1012", "7-1012"}
    assert loc["6-1012"]["votos"]["10"] == 30 and loc["7-1012"]["votos"]["10"] == 5
    assert loc["6-1012"]["zona"] == 6 and loc["6-1012"]["aptos"] == 100


def test_votes_in_local_sum_to_municipality_totals(base, tmp_path, ibge_dir):
    out, _ = run(base, tmp_path, ibge_dir)
    for f in ("73440/2024_prefeito_t1.json", "92410/2024_vereador_t1.json"):
        d = load(out / f)
        for c in d["candidatos"]:
            assert sum(l["votos"].get(str(c["nr"]), 0) for l in d["locais"]) == c["votos"]
        assert sum(l["votos"].get("branco", 0) for l in d["locais"]) == d["totais"]["brancos"]


def test_candidates_eleito_validos_and_technical_nulls(base, tmp_path, ibge_dir):
    out, _ = run(base, tmp_path, ibge_dir)
    d = load(out / "73440" / "2024_prefeito_t1.json")
    c = {x["nr"]: x for x in d["candidatos"]}
    assert set(c) == {10, 20}                       # 77 fora da lista oficial: nulo tecnico
    assert d["totais"]["nulos_tecnicos"] == 3 and d["totais"]["validos"] == 95
    assert c[20]["votos"] == 60 and c[20]["pct_validos"] == round(100 * 60 / 95, 2)
    assert c[20]["eleito"] is False and c[20]["partido"] == "BB"
    t2 = {x["nr"]: x for x in load(out / "73440" / "2024_prefeito_t2.json")["candidatos"]}
    assert t2[20]["eleito"] is True and t2[10]["eleito"] is False
    v = load(out / "92410" / "2024_vereador_t1.json")
    assert v["candidatos"][0]["eleito"] is None     # fonte sem situacao
    assert v["partidos"] == [{"sg": "AA", "legenda": 2, "nominais": 6, "total": 8}]
    assert v["locais"][0]["votos"]["legenda:AA"] == 2 and v["locais"][0]["votos"]["nulo"] == 1


def test_state_file_has_candidates_parties_and_municipal_winners(base, tmp_path, ibge_dir):
    out, _ = run(base, tmp_path, ibge_dir)
    s = load(out / "estado" / "2024_prefeito_t1.json")
    venc = {m["cod"]: m for m in s["municipios"]}
    assert venc["73440"]["vencedor"]["nr"] == 20 and venc["92410"]["vencedor"]["partido"] == "AA"
    assert {p["sg"]: p["total"] for p in s["partidos"]} == {"AA": 44, "BB": 60}


def test_json_is_utf8_and_keeps_accents(base, tmp_path, ibge_dir):
    out, _ = run(base, tmp_path, ibge_dir)
    raw = (out / "73440" / "2024_prefeito_t1.json").read_bytes()
    assert "JOSÉ D'ÁVILA".encode("utf-8") in raw
    assert "\\u00c9".encode() not in raw and "Ã".encode("utf-8") not in raw
    assert "ARAGUAÍNA".encode("utf-8") in (out / "index.json").read_bytes()


def test_reexport_replaces_output_without_leftovers(base, tmp_path, ibge_dir):
    out, _ = run(base, tmp_path, ibge_dir)
    (out / "lixo.json").write_text("{}", encoding="utf-8")
    run(base, tmp_path, ibge_dir)
    assert not (out / "lixo.json").exists()


def test_legenda_of_party_without_own_candidates_is_valid(base, tmp_path, ibge_dir):
    # partido federado sem candidato proprio (ex.: PCdoB na federacao do PT) recebe legenda valida
    bu = pd.read_parquet(base / "bu_secao.parquet")
    extra = secao(2024, 1, "Vereador", 13, "92410", 1, 1, 1001, {("Legenda", 65, "PCDOB"): 4})
    pd.concat([bu, pd.DataFrame(extra)], ignore_index=True).to_parquet(base / "bu_secao.parquet")
    out, _ = run(base, tmp_path, ibge_dir)
    v = load(out / "92410" / "2024_vereador_t1.json")
    assert v["totais"]["nulos_tecnicos"] == 0 and v["totais"]["validos"] == 12
    assert {p["sg"]: p["legenda"] for p in v["partidos"]} == {"AA": 2, "PCDOB": 4}


def test_export_publishes_validation_reports_next_to_data(base, tmp_path, ibge_dir):
    v = tmp_path / "validacao"
    v.mkdir()
    (v / "camada1.json").write_text("{}", encoding="utf-8")
    (v / "camadacontrole.json").write_text("{}", encoding="utf-8")
    (v / "divergencias_x.csv").write_text("sem_divergencias\n", encoding="utf-8")
    (v / "excecoes.json").write_text("[]", encoding="utf-8")
    (v / "camada4_oficial.json").write_text("[]", encoding="utf-8")   # grande; fica so no repositorio
    out, _ = run(base, tmp_path, ibge_dir)
    pub = sorted(p.name for p in (out / "validacao").iterdir())
    assert pub == ["camada1.json", "camadacontrole.json", "divergencias_x.csv", "excecoes.json"]
    assert load(out / "index.json")["relatorios"] == pub


def test_state_file_of_statewide_cargo_has_votes_per_municipality(base, tmp_path, ibge_dir):
    bu = pd.read_parquet(base / "bu_secao.parquet")
    dep = (secao(2026, 1, "Deputado Federal", 6, "73440", 6, 1, 1012, {("Nominal", 1010, "AA"): 7,
                                                                      ("Nominal", 2020, "BB"): 3})
           + secao(2026, 1, "Deputado Federal", 6, "92410", 1, 1, 1001, {("Nominal", 1010, "AA"): 4}))
    pd.concat([bu, pd.DataFrame(dep)], ignore_index=True).to_parquet(base / "bu_secao.parquet")
    loc = pd.read_parquet(base / "locais.parquet")
    loc26 = loc[loc["turno"] == 1].assign(ano=2026)
    pd.concat([loc, loc26], ignore_index=True).to_parquet(base / "locais.parquet")
    mz = pd.read_parquet(base / "munzona.parquet")
    mz26 = pd.DataFrame([{**mz.iloc[0].to_dict(), "ano": 2026, "turno": 1, "cargo": "Deputado Federal",
                          "cd_municipio": "73440", "nr_candidato": nr, "sg_partido": sg, "situacao_turno": st}
                         for nr, sg, st in [(1010, "AA", "ELEITO POR QP"), (2020, "BB", "NÃO ELEITO")]])
    pd.concat([mz, mz26], ignore_index=True).to_parquet(base / "munzona.parquet")
    out, _ = run(base, tmp_path, ibge_dir)
    s = load(out / "estado" / "2026_deputado_federal_t1.json")
    by = {c["nr"]: c for c in s["candidatos"]}
    assert by[1010]["votos"] == 11 and by[1010]["municipios"] == {"73440": 7, "92410": 4}
    assert by[2020]["municipios"] == {"73440": 3}
    p = load(out / "estado" / "2024_prefeito_t1.json")
    assert all("municipios" not in c for c in p["candidatos"])      # cargo municipal: ja tem "cod"
    m = load(out / "73440" / "2026_deputado_federal_t1.json")
    assert all("municipios" not in c for c in m["candidatos"])      # so no arquivo estadual
