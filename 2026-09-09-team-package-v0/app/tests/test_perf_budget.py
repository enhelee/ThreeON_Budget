# -*- coding: utf-8 -*-
"""속도 예산 — 화면 전환에 쓰이는 API 의 DB 질의 수가 데이터 양에 따라 늘지 않게.

운영은 앱(Render 싱가포르)과 DB(Supabase 서울)가 떨어져 있어 질의 1회가 ~75ms,
연결 1회가 ~0.5초다(2026-10-15 실측). 재배정 193건에 질의 390회를 보내던 /api/pending 이
화면마다 30초를 만들었다. 기능을 고치다 같은 모양(행마다 질의·전부 받아 pandas 로 거르기·
값 하나를 매번 다시 계산)이 다시 들어오면 이 테스트가 먼저 깨진다.

질의 수는 응답의 Server-Timing 헤더(ServerTimingMiddleware)에서 읽는다 — 운영에서
개발자 도구로 보는 것과 같은 숫자다.
"""
import os
import re
import sys

import pytest

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from budget import db as dbm, forecast_calc, pipeline_db   # noqa: E402
from tests.test_db_pipeline import env   # noqa: E402,F401  (계획 2행 + 전표 3건 픽스처)


@pytest.fixture()
def seeded(env, tmp_path, monkeypatch):
    """2023 손익 분석 1회 + 재배정 2건 + 미매핑 전표 1건(처지사 없는 미반영)."""
    conn, out = env
    run = pipeline_db.run_actual_db(conn, out, "2023", "손익", make_files=False)
    detail = dbm.load_match_detail(conn, run["run_id"])
    ids = {r["전표번호"]: int(r["erp_row_id"]) for _, r in detail.iterrows()}
    dbm.add_override(conn, "2023", "손익", ids["D1"], "화성 정기점검 보수공사")
    dbm.add_override(conn, "2023", "손익", ids["D3"], "화성 옥외배관 도색공사")
    conn.execute("UPDATE match_line SET 구분='미반영', 처지사정규=NULL"
                 " WHERE run_id=? AND erp_row_id=?", (run["run_id"], ids["D2"]))
    conn.commit()

    monkeypatch.setenv("APP_PASSWORD", "")
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setattr(dbm, "DEFAULT_DB", str(tmp_path / "budget.db"))
    import server
    from budget import auth as authm
    monkeypatch.setattr(server, "AUTH", authm.AuthConfig())
    from fastapi.testclient import TestClient
    return TestClient(server.app), conn, run["run_id"], ids


def _timing(resp):
    h = resp.headers["Server-Timing"]
    q = int(re.search(r'queries=(\d+)', h).group(1))
    c = int(re.search(r'connections=(\d+)', h).group(1))
    return q, c


def test_server_timing_header_reports_db_usage(seeded):
    client, *_ = seeded
    r = client.get("/api/lock-state")
    assert r.status_code == 200
    h = r.headers["Server-Timing"]
    assert re.search(r"app;dur=[\d.]+", h)
    assert _timing(r) == (1, 1)                  # 열린 연도 1질의 · 연결 1번
    assert "Server-Timing" in client.get("/healthz").headers   # DB 안 쓰는 응답에도


def test_nav_state_equals_the_three_apis_with_one_connection(seeded):
    client, *_ = seeded
    r = client.get("/api/nav-state?year=2023")
    d = r.json()
    assert d["years"] == client.get("/api/overview").json()["years"]
    assert d["pending"] == client.get("/api/pending?year=2023").json()
    assert d["open"] == client.get("/api/lock-state").json()["open"]
    assert d["year"] == "2023"
    assert _timing(r)[1] == 1                    # 셋을 연결 하나로


def test_nav_state_without_year_uses_latest_data_year(seeded):
    """첫 진입(연도 없음) — 화면이 고를 연도(자료가 있는 최신 연도)로 미반영을 센다."""
    client, *_ = seeded
    d = client.get("/api/nav-state").json()
    assert d["year"] == max(r["year"] for r in d["years"])
    assert d["pending"] == client.get(f"/api/pending?year={d['year']}").json()


# 화면 전환에 쓰이는 API 의 질의 수 상한. 지금 값보다 조금 넉넉하게 — 기능이 늘며 한두 개 느는
# 것은 괜찮지만, 행마다 질의하는 모양(수십~수백)이 들어오면 깨진다.
QUERY_BUDGET = {
    "/api/nav-state?year=2023": 30,
    "/api/pending?year=2023": 20,
    "/api/status?year=2023": 20,
    "/api/branches?year=2023": 10,
    "/api/branch-detail?year=2023&branch=화성지사": 10,
    "/api/overrides?year=2023": 5,
}


@pytest.mark.parametrize("url,limit", sorted(QUERY_BUDGET.items()))
def test_query_budget_per_screen_api(seeded, url, limit):
    client, *_ = seeded
    r = client.get(url)
    assert r.status_code == 200, r.text
    q, c = _timing(r)
    assert c == 1, f"{url}: 연결 {c}번"
    assert q <= limit, f"{url}: 질의 {q}회 > 상한 {limit}"


@pytest.mark.parametrize("url", ["/api/nav-state?year=2023", "/api/pending?year=2023"])
def test_query_count_does_not_grow_with_overrides(seeded, url):
    """재배정이 30건 늘어도 질의 수는 같아야 한다 — 30초 사고의 재발 방지."""
    client, conn, _run, ids = seeded
    before = _timing(client.get(url))[0]
    for i in range(30):
        dbm.add_override(conn, "2023", "손익", ids["D1"], f"다른 사업 {i}")
    assert _timing(client.get(url))[0] == before


def test_match_detail_sql_filters_equal_pandas_filters(seeded):
    """지사·미매핑 필터를 SQL 로 옮겨도 행·순서·값이 예전(전부 받아 pandas 로 거르기)과 같다.

    dtype 은 다를 수 있다 — 전체에 NaN 이 섞이면 매칭행이 float(1.0), 거른 결과엔 int(1).
    화면 코드는 int(mrow)·pd.isna 로 읽으므로 값만 같으면 된다.
    """
    from pandas.testing import assert_frame_equal as _eq

    def assert_frame_equal(a, b, **kw):          # 결측 표기(None·NaN)도 값으로는 같다
        _eq(a.astype(object).where(a.notna(), None), b.astype(object).where(b.notna(), None), **kw)
    _client, conn, run_id, _ids = seeded
    full = dbm.load_match_detail(conn, run_id)
    for branch in sorted(full["처지사정규"].dropna().unique()):
        want = full[full["처지사정규"] == branch].reset_index(drop=True)
        got = dbm.load_match_detail(conn, run_id, branch=branch)
        assert_frame_equal(got, want, check_dtype=False)
    want = full[(full["구분"] == "미반영") & (full["처지사정규"].isna())].reset_index(drop=True)
    got = dbm.load_match_detail(conn, run_id, unmapped=True)
    assert len(got) == 1                         # 픽스처의 미매핑 1건
    assert_frame_equal(got, want, check_dtype=False)


def test_unmapped_virtual_branch_still_listed_and_detailed(seeded):
    client, *_ = seeded
    rows = client.get("/api/branches?year=2023").json()["rows"]
    um = [r for r in rows if r["branch"].endswith(" (미매핑)")]
    assert len(um) == 1 and um[0]["unmapped"] == 1
    d = client.get("/api/branch-detail", params={"year": "2023", "branch": um[0]["branch"]}).json()
    assert d["unmapped"] is True and len(d["biz"][0]["전표"]) == 1


def test_forecast_multiplier_computed_once_per_year(monkeypatch):
    """배수는 연도에만 달린다 — 행(예산과목)마다 다시 구하면 지사 19 × 17행 × 10년 = 3,230번
    팩터 표를 훑는다(운영 전망 표 13초의 92%). 지사 하나에 연도 수만큼만 불려야 한다."""
    import pandas as pd
    calls = []
    orig = forecast_calc.year_multiplier
    monkeypatch.setattr(forecast_calc, "year_multiplier",
                        lambda *a, **k: calls.append(a[0]) or orig(*a, **k))
    factors = pd.DataFrame([{"이름": "물가", "연간비율": 0.02, "활성": True}])
    empty = pd.DataFrame()
    grade = pd.DataFrame(columns=["사업장", "연도", "등급"])
    t = forecast_calc.compute_site_table(
        "화성", grade, pd.DataFrame(columns=["사업장", "예산과목", "등급", "표준금액"]),
        empty, {("화성", "비저장품(보수자재)"): 1000.0}, empty, factors, empty, empty,
        base_year=2026)
    assert sorted(calls) == list(range(2026, 2036))
    row = t[t["예산과목"] == "비저장품(보수자재)"].iloc[0]
    assert row[2027] == pytest.approx(1000.0 * 1.02)
    assert row[2030] == pytest.approx(1000.0 * 1.02 ** 4)
