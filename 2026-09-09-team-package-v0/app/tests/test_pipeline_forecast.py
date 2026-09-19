# -*- coding: utf-8 -*-
"""3·4단계 입력 조립 — 마감 연도 실적 · 계획본 어댑터 · 지사 목록 · 실행 (Phase 6-6).

v2 는 실적을 checkpoint JSON 이나 classified_*.csv 에서, 당해년도 예산을 budget_{연도}.csv
에서 읽었다. 여기서는 둘 다 이 앱의 DB 다 — 실적은 **마감된 연도**의 최신 분석 결과
(biz_line, 구분 계획집행·신규·신규(소액집행)), 예산은 1단계 계획본(plan_row).
사용자 결정 2026-09-19: 모집단은 마감 연도만. 마감 = 대외 보고에 쓴 확정값이다.
"""
import json

import pandas as pd
import pytest

from budget import config_store
from budget import db as dbm
from budget import forecast_store as fs
from budget import pipeline_forecast as pf


@pytest.fixture()
def conn(tmp_path):
    c = dbm.connect(str(tmp_path / "t.db"))
    yield c
    c.close()


def _seed_run(conn, year, budget, lines):
    """lines: [(처지사, 예산과목, 실적금액, 구분)]"""
    cur = conn.execute("INSERT INTO run(year,budget,created_at,summary_json) VALUES(?,?,?,?)",
                       (year, budget, "2026-01-01 00:00:00", json.dumps({})))
    run_id = cur.lastrowid
    for dept, item, amt, gubun in lines:
        conn.execute("INSERT INTO biz_line(run_id,budget,예산과목,처지사,사업명,연예산,실적금액,구분)"
                     " VALUES(?,?,?,?,?,?,?,?)", (run_id, budget, item, dept, "x", 0.0, amt, gubun))
    conn.commit()
    return run_id


def _seed_plan(conn, year, rows):
    """rows: [(처지사, 예산과목, 연예산)]"""
    cur = conn.execute("INSERT INTO dataset(kind,year,label,uploaded_at) VALUES('plan',?,?,?)",
                       (year, "plan.xlsx", "2026-01-01 00:00:00"))
    ds = cur.lastrowid
    for i, (dept, item, amt) in enumerate(rows):
        conn.execute("INSERT INTO plan_row(dataset_id,주관부서명,부서코드,처지사,부서부,속성,예산코드,예산과목,"
                     "사업명,산출내역,연예산,src_row) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                     (ds, "부", "C", dept, "", "일반", "K", item, f"사업{i}", "", amt, i + 4))
    conn.commit()


# ---------------------------------------------------------------- 실적 모집단
def test_locked_actuals_uses_only_locked_years_and_kept_gubun(conn):
    _seed_run(conn, "2023", "손익", [("화성지사", "수선유지비-열원경상정비", 100.0, "계획집행"),
                                     ("화성지사", "수선유지비-열원경상정비", 5.0, "미시행"),
                                     ("화성지사", "기계장치", 7.0, "신규(소액집행)")])
    _seed_run(conn, "2025", "손익", [("화성지사", "수선유지비-열원경상정비", 200.0, "신규")])
    dbm.lock_year(conn, "2023")            # 2025 는 열려 있다 — 수정 중인 값은 모집단이 아니다

    df, years = pf.locked_actuals(conn)
    assert years == ["2023"]
    assert list(df.columns) == ["사업장", "연도", "예산과목", "금액"]
    assert df["금액"].sum() == pytest.approx(107.0)
    assert set(df["연도"]) == {2023}


def test_locked_actuals_empty_when_no_locked_run(conn):
    df, years = pf.locked_actuals(conn)
    assert df.empty and years == []
    assert list(df.columns) == ["사업장", "연도", "예산과목", "금액"]


def test_locked_year_without_run_is_not_counted(conn):
    dbm.lock_year(conn, "2022")
    _seed_run(conn, "2023", "손익", [("화성지사", "기계장치", 1.0, "계획집행")])
    dbm.lock_year(conn, "2023")
    _, years = pf.locked_actuals(conn)
    assert years == ["2023"]


# ---------------------------------------------------------------- 계획본 어댑터
def test_budget_plan_for_adapts_plan_rows_to_v2_columns(conn):
    _seed_plan(conn, "2026", [("화성지사", "기계장치", 1000.0), ("화성지사", "기계장치", 500.0),
                              ("동탄지사", "외주비-열원공사비", 300.0)])
    df = pf.budget_plan_for(conn, "2026")
    assert list(df.columns) == ["예산과목", pf.DEPT_COL, pf.AMOUNT_COL]
    assert df[pf.AMOUNT_COL].sum() == pytest.approx(1800.0)
    assert set(df[pf.DEPT_COL]) == {"화성지사", "동탄지사"}


def test_budget_plan_for_missing_year_is_empty_frame(conn):
    df = pf.budget_plan_for(conn, "2031")
    assert df.empty and list(df.columns) == ["예산과목", pf.DEPT_COL, pf.AMOUNT_COL]


# ---------------------------------------------------------------- 지사 목록 · 기준연도
def test_forecast_sites_exclude_hq_and_unincluded(conn):
    cfg = config_store.load_dept_config(conn, "2026")
    for x in cfg:
        if x["이름"] == "평택지사":
            x["포함"] = False
    config_store.save_dept_config(conn, "2026", cfg)
    sites = pf.forecast_sites(conn, "2026")
    assert "화성지사" in sites and "양산지사" in sites
    assert "플랜트기술처" not in sites            # 본사 그룹 제외
    assert "평택지사" not in sites                # 포함 해제
    assert pf.site_groups(conn, "2026")["양산지사"] == "중대형CHP"


def test_default_base_year_prefers_existing_state_then_locked_plus_one(conn):
    assert pf.default_base_year(conn) == "2026"          # 아무것도 없음 → v2 기본
    _seed_run(conn, "2024", "손익", [("화성지사", "기계장치", 1.0, "계획집행")])
    dbm.lock_year(conn, "2024")
    assert pf.default_base_year(conn) == "2025"          # 마감 최신 + 1
    fs.save_hq_ratio(conn, "2028", pd.DataFrame([{"사업장": "화성지사", "계약체결금액": 1.0}]))
    assert pf.default_base_year(conn) == "2028"          # 상태가 있으면 그 최신


# ---------------------------------------------------------------- 실행
def test_run_benchmark_and_forecast_end_to_end(conn):
    _seed_run(conn, "2023", "손익", [("화성지사", "수선유지비-열원경상정비", 1000.0, "계획집행")])
    _seed_run(conn, "2025", "손익", [("화성지사", "수선유지비-열원경상정비", 1100.0, "계획집행")])
    dbm.lock_year(conn, "2023")
    dbm.lock_year(conn, "2025")
    _seed_plan(conn, "2026", [("화성지사", "수선유지비-열원경상정비", 1200.0),
                              ("화성지사", "외주비-열원공사비", 50.0)])
    fs.save_factors(conn, "2026", pd.DataFrame([{"팩터명": "물가상승률", "연간비율": 0.1, "활성": True}]))

    bench = pf.run_benchmark(conn, "2026")
    assert bench["years_used"] == ["2023", "2025"]
    assert bench["population"] == {"rows": 2, "total": 2100.0}
    row = next(r for r in bench["rows"] if r["사업장"] == "화성지사")
    assert row["예산과목"] == "수선유지비-열원경상정비" and row["산출방식"] == "최근실적"
    assert row["표준금액"] == pytest.approx(1100.0)

    out = pf.run_forecast(conn, "2026")
    assert out["years"] == list(range(2026, 2036))
    assert "화성지사" in out["sites"] and "플랜트기술처" not in out["sites"]
    hs = {r["예산과목"]: r for r in out["tables"]["화성지사"]}
    line = hs["수선유지비-열원경상정비"]
    assert line["2026"] == pytest.approx(1200.0)          # 당해년도 = 계획본
    assert line["2027"] == pytest.approx(1100.0 * 1.1)    # 다음년도 = 표준금액 × 팩터
    assert hs["투자비"]["2026"] == pytest.approx(50.0)     # 외주비-열원공사비 = 투자비
    assert out["notes"]["budget_plan_missing"] is False
    total = {r["예산과목"]: r for r in out["total_rows"]}
    assert total["수선유지비-열원경상정비"]["2026"] == pytest.approx(1200.0)


def test_run_forecast_with_nothing_still_returns_shape(conn):
    out = pf.run_forecast(conn, "2027")
    assert out["years"] == list(range(2027, 2037))
    assert out["notes"] == {"budget_plan_missing": True, "grade_empty": True, "actuals_empty": True}
    assert len(out["sites"]) > 0 and all(len(rows) == 17 for rows in out["tables"].values())
