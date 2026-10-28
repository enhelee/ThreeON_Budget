# -*- coding: utf-8 -*-
"""시나리오 비교(2026-10-27, 경진대회 C) — 저장된 가정 위에 물가·물량 손잡이를 얹어 2~3벌을 나란히."""
import json
import os
import sys

import pandas as pd
import pytest

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from budget import db as dbm, pipeline_forecast as pf   # noqa: E402
from tests.test_forecast_api import _conn, _seed_plan, _seed_run, client   # noqa: E402,F401

LINE = "수선유지비-열원경상정비"


def _seed():
    conn = _conn()
    try:
        _seed_run(conn, "2023", "손익", [("화성지사", LINE, 1000.0, "계획집행")])
        _seed_run(conn, "2025", "손익", [("화성지사", LINE, 1100.0, "계획집행")])
        dbm.lock_year(conn, "2023")
        dbm.lock_year(conn, "2025")
        _seed_plan(conn, "2026", [("화성지사", LINE, 1200.0)])
    finally:
        conn.close()


def test_scenario_inputs_add_a_factor_and_scale_standard_only():
    inp = {"factors": pd.DataFrame([{"팩터명": "물가", "연간비율": 0.015, "활성": True, "적용구분": "손익"}]),
           "std": pd.DataFrame([{"사업장": "A", "예산과목": LINE, "등급": "표준", "표준금액": 100.0}]),
           "overhaul": {"years": {"A": {2027}}, "amount": {"A": 50.0}}}
    out = pf.scenario_inputs(inp, price=1.0, volume=10.0)
    assert list(out["factors"]["팩터명"]) == ["물가", "시나리오 물가 조정"]
    assert out["factors"].iloc[1]["연간비율"] == pytest.approx(0.01)
    assert out["factors"].iloc[1]["적용구분"] == "전체"
    assert out["std"]["표준금액"].iloc[0] == pytest.approx(110.0)
    assert out["overhaul"]["amount"]["A"] == pytest.approx(55.0)
    # 저장된 가정(입력)은 그대로
    assert len(inp["factors"]) == 1 and inp["std"]["표준금액"].iloc[0] == 100.0
    assert inp["overhaul"]["amount"]["A"] == 50.0
    assert pf.scenario_inputs(inp) is not inp and pf.scenario_inputs(inp)["factors"] is inp["factors"]


def test_scenarios_api_first_equals_table_and_knobs_move_later_years(client):
    _seed()
    t = client.get("/api/forecast/table?base_year=2026").json()
    specs = [{"name": "기준", "price": 0, "volume": 0}, {"name": "물가+1", "price": 1, "volume": 0},
             {"name": "물량-10", "price": 0, "volume": -10}]
    r = client.get("/api/forecast/scenarios", params={"base_year": "2026", "specs": json.dumps(specs)})
    assert r.status_code == 200, r.text
    d = r.json()
    base, up, down = d["scenarios"]
    tot = {str(y): sum(row[str(y)] for row in t["total_rows"]) for y in t["years"]}
    assert base["total"] == pytest.approx(tot)                       # 기준 = 지금 전망 표 합계
    assert base["sum10"] == pytest.approx(sum(tot.values()))
    assert up["total"]["2026"] == pytest.approx(base["total"]["2026"])   # 기준연도 = 계획본 → 손잡이 무관
    assert up["total"]["2027"] > base["total"]["2027"]
    hw = lambda s, y: s["by_site"]["화성지사"][y]
    assert hw(up, "2027") - hw(base, "2027") == pytest.approx(1100.0 * 1.015 * 0.01)
    assert hw(down, "2027") == pytest.approx(hw(base, "2027") - 1100.0 * 1.015 * 0.1)
    assert set(d["band"]) == {str(y) for y in d["years"]}
    for lo, hi in d["band"].values():
        assert lo <= hi


def test_scenarios_api_defaults_and_validation(client):
    _seed()
    d = client.get("/api/forecast/scenarios?base_year=2026").json()
    assert [s["name"] for s in d["scenarios"]] == [s["name"] for s in pf.DEFAULT_SCENARIOS]
    too_many = json.dumps([{"name": str(i)} for i in range(4)])
    assert client.get("/api/forecast/scenarios", params={"specs": too_many}).status_code == 400
    assert client.get("/api/forecast/scenarios", params={"specs": "not json"}).status_code == 400
    # 손잡이 범위 밖은 잘라 계산한다(물가 ±10%p · 물량 ±50%)
    wild = json.dumps([{"name": "x", "price": 99, "volume": -99}])
    s = client.get("/api/forecast/scenarios", params={"base_year": "2026", "specs": wild}).json()["scenarios"][0]
    assert (s["price"], s["volume"]) == (pf.PRICE_LIM, -pf.VOLUME_LIM)


def test_scenarios_do_not_write(client):
    _seed()
    client.get("/api/forecast/table?base_year=2026")      # 팩터 기본값(물가 1.5%)은 처음 읽을 때 심긴다 — 그 뒤에 비교
    conn = _conn()
    try:
        before = conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
        factors = len(conn.execute("SELECT * FROM forecast_factor").fetchall())
    finally:
        conn.close()
    client.get("/api/forecast/scenarios?base_year=2026")
    conn = _conn()
    try:
        assert conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0] == before
        assert len(conn.execute("SELECT * FROM forecast_factor").fetchall()) == factors
        assert not conn.execute("SELECT 1 FROM forecast_factor WHERE 팩터명='시나리오 물가 조정'").fetchall()
    finally:
        conn.close()
