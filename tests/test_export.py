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
    censo_files(b)
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


# ------------------------------------------------------------ Censo, ficha do local e conjuntura
from tocantins.censo import INDICADORES  # noqa: E402


def censo_files(b):
    """Setores S1,S2 (Palmas) e S3 (Araguaina); 6-1012 crivel, 7-1012 nao crivel, 1-1001 crivel."""
    setores = []
    for cd, mun, mor in [("172100005000001", "1721000", 100), ("172100005000002", "1721000", 400),
                         ("170210905000001", "1702109", 80)]:
        r = {"cd_setor": cd, "cd_mun_ibge": mun, "cx": 0.0, "cy": 0.0, "area_km2": 1.0, "moradores": mor,
             "domicilios": mor // 3, "sigilo": False, "densidade": float(mor)}
        for ind in INDICADORES:
            r[f"{ind}_num"], r[f"{ind}_den"] = mor / 2, mor
        setores.append(r)
    pd.DataFrame(setores).to_parquet(b / "censo_setor.parquet")
    pd.DataFrame([{"cd_mun_ibge": "1721000", "populacao": 500, "area_km2": 2227.3, "densidade": 0.2,
                   "pib_per_capita": 39484.1, "ano_pib": 2022},
                  {"cd_mun_ibge": "1702109", "populacao": 80, "area_km2": 4000.0, "densidade": 0.02,
                   "pib_per_capita": 30000.0, "ano_pib": 2022}]).to_parquet(b / "ibge_municipio.parquet")
    links, creds, areas = [], [], []
    for ano in (2024, 2026):
        for cd, mun, lid, eleit, mor in [("172100005000001", "73440", "6-1012", 100, 100),
                                         ("172100005000002", "73440", "7-1012", 100, 400),
                                         ("170210905000001", "92410", "1-1001", 100, 80)]:
            for impl in ("numpy", "geopandas"):
                links.append({"cd_setor": cd, "cd_municipio": mun, "local_id": lid, "dist_m": 1.0, "impl": impl,
                              "ano": ano})
            creds.append({"local_id": lid, "cd_municipio": mun, "eleitores": eleit, "moradores": mor,
                          "razao": eleit / mor, "credivel": 0.4 <= eleit / mor <= 1.6, "especial": False,
                          "lat": -10.0, "lon": -48.0, "ano": ano})
            areas.append({"cd_municipio": mun, "local_id": lid, "area_id": lid, "ano": ano})
    pd.DataFrame(links).to_parquet(b / "ligacao_setor_local.parquet")
    pd.DataFrame(creds).to_parquet(b / "local_credibilidade.parquet")
    pd.DataFrame(areas).to_parquet(b / "area_votacao.parquet")
    pd.DataFrame([{"ano": a, "cargo": c, "nr_candidato": nr, "sg_partido": sg, "partidos": ps}
                  for a, c, nr, sg, ps in [(2024, "Prefeito", 10, "AA", ["AA"]), (2024, "Prefeito", 20, "BB", ["BB"]),
                                           (2026, "Governador", 45, "AA", ["AA", "CC"]),
                                           (2026, "Governador", 22, "BB", ["BB"]),
                                           (2026, "Senador", 451, "AA", ["AA"]), (2026, "Senador", 222, "BB", ["BB"]),
                                           (2026, "Senador", 333, "CC", ["CC"])]]
                 ).to_parquet(b / "coligacoes.parquet")


@pytest.fixture
def base26(base):
    """Acrescenta 2026 (Governador t1/t2, Senador, Deputado Federal) e 17 vereadores em Araguaina."""
    bu = pd.read_parquet(base / "bu_secao.parquet")
    novos = (secao(2024, 1, "Vereador", 13, "92410", 1, 2, 1001,
                   {("Nominal", 10200 + i, "AA"): 20 - i for i in range(17)})
             + secao(2026, 1, "Deputado Federal", 6, "92410", 1, 1, 1001,
                     {("Nominal", 1000 + i, "AA"): 10 - i for i in range(7)}))
    for mun, z, s, loc in [("73440", 6, 1, 1012), ("92410", 1, 1, 1001)]:
        novos += secao(2026, 1, "Governador", 3, mun, z, s, loc, {("Nominal", 45, "AA"): 30, ("Nominal", 22, "BB"): 20})
        novos += secao(2026, 2, "Governador", 3, mun, z, s, loc, {("Nominal", 45, "AA"): 25, ("Nominal", 22, "BB"): 30})
        novos += secao(2026, 1, "Senador", 5, mun, z, s, loc, {("Nominal", 451, "AA"): 30, ("Nominal", 222, "BB"): 20,
                                                                  ("Nominal", 333, "CC"): 25})
    novos += secao(2026, 1, "Governador", 3, "92410", 1, 2, 1001, {("Nominal", 45, "AA"): 1})
    novos += secao(2026, 1, "Governador", 3, "92410", 1, 3, 1001, {("Nominal", 22, "BB"): 1})
    pd.concat([bu, pd.DataFrame(novos)], ignore_index=True).to_parquet(base / "bu_secao.parquet")
    loc = pd.read_parquet(base / "locais.parquet")
    extra = [{"ano": a, "turno": t, "cd_municipio": m, "zona": z, "secao": s, "local": l, "nm_local": f"ESCOLA {z}-{l}",
              "endereco": "RUA A", "bairro": "CENTRO", "lat": la, "lon": lo, "eleitores_secao": 100,
              "tipo_secao": "Principal"}
             for a, t, m, z, s, l, la, lo in [
                 (2024, 1, "92410", 1, 2, 1001, -7.19, -48.2),
                 (2026, 1, "73440", 6, 1, 1012, -10.18, -48.33), (2026, 2, "73440", 6, 1, 1012, -10.18, -48.33),
                 (2026, 1, "92410", 1, 1, 1001, -7.0, None), (2026, 1, "92410", 1, 2, 1001, -7.3, -48.4),
                 (2026, 1, "92410", 1, 3, 1001, -7.5, -48.5), (2026, 2, "92410", 1, 1, 1001, -7.3, -48.4)]]
    pd.concat([loc, pd.DataFrame(extra)], ignore_index=True).to_parquet(base / "locais.parquet")
    mz = pd.read_parquet(base / "munzona.parquet")
    rows = [(2024, 1, "Vereador", "92410", 1, 10200 + i, "AA", None) for i in range(17)]
    rows += [(2026, 1, "Deputado Federal", "92410", 1, 1000 + i, "AA", None) for i in range(7)]
    for mun, z in [("73440", 6), ("92410", 1)]:
        rows += [(2026, 1, "Governador", mun, z, 45, "AA", "2º TURNO"), (2026, 1, "Governador", mun, z, 22, "BB", "2º TURNO"),
                 (2026, 2, "Governador", mun, z, 45, "AA", "NÃO ELEITO"), (2026, 2, "Governador", mun, z, 22, "BB", "ELEITO"),
                 (2026, 1, "Senador", mun, z, 451, "AA", "ELEITO"), (2026, 1, "Senador", mun, z, 333, "CC", "ELEITO"),
                 (2026, 1, "Senador", mun, z, 222, "BB", "NÃO ELEITO")]
    mz = pd.concat([mz, pd.DataFrame([{"ano": a, "turno": t, "cargo": c, "cd_municipio": m, "zona": z,
                                       "nr_candidato": nr, "nm_candidato": f"NOME {nr}", "sg_partido": sg,
                                       "votos_nominais": 0, "situacao_turno": st}
                                      for a, t, c, m, z, nr, sg, st in rows])], ignore_index=True)
    mz.to_parquet(base / "munzona.parquet")
    return base


def test_governador_and_senador_exported_with_t2_where_exists(base26, tmp_path, ibge_dir):
    out, _ = run(base26, tmp_path, ibge_dir)
    for f in ("73440/2026_governador_t1.json", "73440/2026_governador_t2.json", "92410/2026_senador_t1.json",
              "estado/2026_governador_t2.json", "estado/2026_senador_t1.json"):
        assert (out / f).exists(), f
    idx = {m["cod"]: m for m in load(out / "index.json")["municipios"]}
    assert idx["73440"]["disponivel"]["2026"]["governador"] == [1, 2]
    assert idx["73440"]["disponivel"]["2026"]["senador"] == [1]


def _ficha(out, mun):
    return {l["id"]: l for l in load(out / mun / "locais_ficha.json")["locais"]}


def test_locais_ficha_limits_and_keys(base26, tmp_path, ibge_dir):
    out, _ = run(base26, tmp_path, ibge_dir)
    l = _ficha(out, "92410")["1-1001"]
    assert set(l) == {"id", "nome", "bairro", "lat", "lon", "anos", "cargos", "entorno"}
    assert set(l["anos"]) == {"2024", "2026"} and set(l["anos"]["2024"]) == {"aptos", "comparecimento"}
    assert len(l["cargos"]["2024-vereador-1"]) == 15 and len(l["cargos"]["2026-deputado_federal-1"]) == 5
    gov = l["cargos"]["2026-governador-1"]
    assert [c["nr"] for c in gov] == [45, 22] and set(gov[0]) == {"nr", "nome", "partido", "votos", "pct"}
    assert "2026-governador-2" in l["cargos"] and "2026-senador-1" in l["cargos"]


def test_ficha_entorno_null_when_not_credible(base26, tmp_path, ibge_dir):
    out, _ = run(base26, tmp_path, ibge_dir)
    f = _ficha(out, "73440")
    assert f["7-1012"]["entorno"] is None
    e = f["6-1012"]["entorno"]
    assert e["credivel"] is True and e["area_id"] == "6-1012" and e["moradores"] == 100
    assert set(e["indicadores"]) == set(INDICADORES) and e["indicadores"]["alfabetizacao_15"] == 50.0


def test_areas_file_only_credible_and_votes_sum_to_area_validos(base26, tmp_path, ibge_dir):
    out, _ = run(base26, tmp_path, ibge_dir)
    a = load(out / "conjuntura" / "areas_2024_prefeito.json")
    assert set(a["indicadores"]) == set(INDICADORES)
    assert {(x["cod"], x["id"]) for x in a["areas"]} == {("73440", "6-1012"), ("92410", "1-1001")}
    for x in a["areas"]:
        assert sum(x["partidos"].values()) == x["validos"] and x["validos"] > 0
    assert (out / "conjuntura" / "areas_2026_senador.json").exists()
    mi = {m["cod"]: m for m in load(out / "conjuntura" / "municipios_indicadores.json")}
    assert mi["73440"]["ind"]["alfabetizacao_15"] == 50.0 and set(mi["73440"]["aptos"]) == {"2024", "2026"}


def test_prefeitos_file_has_three_keys(base26, tmp_path, ibge_dir):
    out, _ = run(base26, tmp_path, ibge_dir)
    p = load(out / "conjuntura" / "prefeitos_2026.json")
    assert set(p) == {"governador-1", "governador-2", "senador-1"}
    pal = {r["cod"]: r for r in p["governador-1"]}["73440"]
    assert pal["prefeito"] == {"nome": "NOME 20", "partido": "BB"} and pal["status"] == "nao_entregou"
    assert {r["cod"]: r for r in p["governador-2"]}["73440"]["status"] == "entregou"
    ibge = load(out / "73440" / "ibge.json")
    assert ibge == {"populacao": 500, "area_km2": 2227.3, "densidade": 0.2, "pib_per_capita": 39484.1, "ano_pib": 2022}


def test_goiatins_note_in_index(base, tmp_path, ibge_dir):
    out, _ = run(base, tmp_path, ibge_dir)
    assert all(m["nota"] is None for m in load(out / "index.json")["municipios"])
    assert "25/10/2026" in export.nota_municipio("GOIATINS") and export.nota_municipio("PALMAS") is None


def test_local_coords_from_one_complete_row(base26, tmp_path, ibge_dir):
    out, _ = run(base26, tmp_path, ibge_dir)
    loc = {l["id"]: l for l in load(out / "92410" / "2026_governador_t1.json")["locais"]}["1-1001"]
    assert (loc["lat"], loc["lon"]) == (-7.3, -48.4)          # secao 1 incompleta; secao 2 e a menor completa


def test_ficha_splits_same_id_with_different_names_across_years(base26, tmp_path, ibge_dir):
    # mesmo "zona-local" em 2024 e 2026, mas outra escola em 2026: nao misturar nome e resultados
    loc = pd.read_parquet(base26 / "locais.parquet")
    m = (loc["ano"] == 2026) & (loc["cd_municipio"] == "73440")
    loc.loc[m, "nm_local"] = "OUTRA ESCOLA"
    loc.to_parquet(base26 / "locais.parquet")
    out, _ = run(base26, tmp_path, ibge_dir)
    fs = [l for l in load(out / "73440" / "locais_ficha.json")["locais"] if l["id"] == "6-1012"]
    assert len(fs) == 2
    velho, novo = sorted(fs, key=lambda l: min(l["anos"]))
    assert velho["nome"] == "ESCOLA 6-1012" and all(k.startswith("2024-") for k in velho["cargos"])
    assert set(velho["anos"]) == {"2024"} and velho["entorno"]["ano_ligacao"] == 2024
    assert novo["nome"] == "OUTRA ESCOLA"
    assert all(k.startswith("2026-") for k in novo["cargos"]) and set(novo["anos"]) == {"2026"}
