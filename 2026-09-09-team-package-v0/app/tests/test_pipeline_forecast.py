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
    fs.save_settings(conn, "2026", {"실적환산": "0"})   # 이 테스트는 물가 환산과 무관 — 그 해 금액 그대로 본다
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
    assert len(out["sites"]) > 0 and all(len(rows) == 20 for rows in out["tables"].values())  # 17 + 정기계약 2 + CRI 1


# ---------------------------------------------------------------- TI = HGPI (2026-11-03 팀장)
def test_canon_grade_maps_ti_token_to_hgpi():
    from budget import forecast_calc as fc
    assert fc.canon_grade("TI") == "HGPI"
    assert fc.canon_grade("MI/TI") == "MI/HGPI" and fc.canon_grade("TI,CI") == "HGPI,CI"
    assert fc.canon_grade("HGPI") == "HGPI" and fc.canon_grade("CI") == "CI"
    assert fc.canon_grade("TIX") == "TIX" and fc.canon_grade(None) is None


def test_ti_and_hgpi_are_one_grade_in_standard_and_forecast(conn):
    """TI 해(2023) · HGPI 해(2024) 실적이 한 등급(HGPI)의 평균이 되고, 미래 TI 해도 그 금액을 쓴다.
    저장된 등급 이력(TI)은 사람이 적은 그대로 남는다."""
    acct = "수선유지비-열원경상정비"
    for y, amt in (("2023", 1000.0), ("2024", 2000.0), ("2025", 5000.0)):
        _seed_run(conn, y, "손익", [("화성지사", acct, amt, "계획집행")])
        dbm.lock_year(conn, y)
    fs.save_grade_history(conn, "2026", pd.DataFrame([
        {"사업장": "화성지사", "연도": 2023, "등급": "TI"}, {"사업장": "화성지사", "연도": 2024, "등급": "HGPI"},
        {"사업장": "화성지사", "연도": 2025, "등급": "MI"}, {"사업장": "화성지사", "연도": 2027, "등급": "TI"}]))
    fs.save_method_map(conn, "2026", pd.DataFrame([{"사업장": "화성지사", "예산과목": acct, "방식": "등급별 평균"}]))
    fs.save_factors(conn, "2026", pd.DataFrame([{"팩터명": "물가상승률", "연간비율": 0.0, "활성": True}]))  # 등급만 보게

    rows = [r for r in pf.run_benchmark(conn, "2026")["rows"] if r["사업장"] == "화성지사" and r["예산과목"] == acct]
    by_grade = {r["등급"]: r["표준금액"] for r in rows}
    assert "TI" not in by_grade, by_grade
    assert by_grade["HGPI"] == pytest.approx(1500.0)          # (TI 1000 + HGPI 2000) / 2
    assert by_grade["MI"] == pytest.approx(5000.0)

    line = {r["예산과목"]: r for r in pf.run_forecast(conn, "2026")["tables"]["화성지사"]}[acct]
    assert line["2027"] == pytest.approx(1500.0)              # 미래 TI 해 = HGPI 표준금액

    saved = fs.load_grade_history(conn, "2026")
    assert set(saved["등급"]) == {"TI", "HGPI", "MI"}         # 저장값은 그대로


def test_site_notes_tag_future_capacity_target(monkeypatch):
    """수원(2029 개체, 지금 소형CHP) 옆 딱지 — 용량 환산 기준 지사들의 묶음(중대형CHP)으로 편입 예정."""
    cap = {"targets": {"수원사업소": {"start": 2029, "rows": pd.DataFrame()}, "청주지사": {"start": 2025}},
           "model": {"refs": {"화성지사": 512, "파주지사": 516}}}
    groups = {"수원사업소": "소형CHP", "화성지사": "중대형CHP", "파주지사": "중대형CHP", "청주지사": "중대형CHP"}
    monkeypatch.setattr(pf, "site_groups", lambda conn, by: groups)
    assert pf.site_notes(None, "2026", cap) == {"수원사업소": "2029년 준공 후 중대형CHP 편입 예정"}   # 이미 바뀐 청주는 딱지 없음


# ---------------------------------------------------------------- 과거 실적 물가 환산(2026-11-03 팀장)
def test_price_index_series_fills_gaps_with_forecast_rate():
    from budget import forecast_calc as fc
    idx = pd.DataFrame([{"연도": 2020, "지수": 100.0}, {"연도": 2022, "지수": 110.0}])
    s = fc.price_index_series(idx, [2019, 2023, 2026], 0.02)
    assert s[2020] == (100.0, "지수") and s[2022] == (110.0, "지수")
    assert s[2021] == (pytest.approx(102.0), "대체")                # 앞 지수에서 전망 물가로 잇기
    assert s[2019][0] == pytest.approx(100 / 1.02) and s[2026][0] == pytest.approx(110 * 1.02 ** 4)
    df = fc.restate_amounts(pd.DataFrame([{"연도": 2020, "금액": 50.0}]), s, 2022)
    assert df["금액"].tolist() == [pytest.approx(55.0)]              # 50 × 110/100
    none = fc.price_index_series(pd.DataFrame(columns=["연도", "지수"]), [2024, 2026], 0.015)
    assert none[2026][0] / none[2024][0] == pytest.approx(1.015 ** 2) and none[2024][1] == "대체"


def test_standard_uses_base_year_value_by_default_and_switch_turns_it_off(conn):
    acct = "수선유지비-열원경상정비"
    for y, amt in (("2023", 1000.0), ("2025", 1100.0)):
        _seed_run(conn, y, "손익", [("화성지사", acct, amt, "계획집행")])
        dbm.lock_year(conn, y)
    fs.save_method_map(conn, "2026", pd.DataFrame([{"사업장": "화성지사", "예산과목": acct, "방식": "최근실적"}]))
    fs.save_factors(conn, "2026", pd.DataFrame([{"팩터명": "물가상승률", "연간비율": 0.02, "활성": True}]))
    fs.save_table(conn, "2026", "price_index", pd.DataFrame([{"연도": 2023, "지수": 100.0, "비고": ""},
                                                            {"연도": 2025, "지수": 110.0, "비고": ""}]))
    assert fs.restate_on(conn, "2026")                                # 기본 켬
    b = pf.run_benchmark(conn, "2026")
    row = next(r for r in b["rows"] if r["사업장"] == "화성지사" and r["예산과목"] == acct)
    assert row["표준금액"] == pytest.approx(1100.0 * (110 * 1.02) / 110)   # 2026 지수 없음 → 2025 지수 × 1.02
    assert b["restate"]["on"] and {y["연도"]: y["출처"] for y in b["restate"]["years"]} == {2023: "지수", 2025: "지수"}
    assert pf.benchmark_frames(conn, "2026")["actuals"]["금액"].sum() == pytest.approx(2100.0)   # 양식 실적 이력은 그 해 금액

    fs.save_settings(conn, "2026", {"실적환산": "0"})
    row = next(r for r in pf.run_benchmark(conn, "2026")["rows"] if r["사업장"] == "화성지사" and r["예산과목"] == acct)
    assert row["표준금액"] == pytest.approx(1100.0)
    assert pf.run_benchmark(conn, "2026")["restate"]["on"] is False


def test_backtest_restates_training_years_to_target_year():
    from budget import forecast_backtest as fb
    from budget import forecast_calc as fc
    acct = "수선유지비-열원경상정비"
    actuals = pd.DataFrame([("화성지사", y, acct, a) for y, a in ((2023, 100.0), (2024, 105.0), (2025, 110.0))],
                           columns=["사업장", "연도", "예산과목", "금액"])
    grades = pd.DataFrame(columns=["사업장", "연도", "등급"])
    s = fc.price_index_series(pd.DataFrame([{"연도": y, "지수": v} for y, v in ((2023, 100.0), (2024, 105.0), (2025, 110.0))]),
                              [2023, 2024, 2025], 0.015)
    plain = fb.run(actuals, grades, 3, [2025])
    real = fb.run(actuals, grades, 3, [2025], series=s)
    assert plain["account"] > 0.01                     # 그 해 금액 그대로면 최근실적 105 로 맞혀 4.5% 틀림
    assert real["account"] == pytest.approx(0.0, abs=1e-9)   # 2025 가치로 바꾸면 110 · 110 → 정확


# ---------------------------------------------------------------- 투자비 실적 표준화(2026-11-03 팀장)
def test_investment_actual_fills_forecast_investment_only_when_switch_is_on(conn):
    fs.save_factors(conn, "2026", pd.DataFrame([{"팩터명": "물가상승률", "연간비율": 0.0, "활성": True}]))
    fs.save_settings(conn, "2026", {"실적환산": "0"})
    acct = "외주비-열원공사비"
    fs.save_table(conn, "2026", "investment_actual", pd.DataFrame(
        [{"사업장": "화성지사", "연도": y, "예산과목": acct, "사업명": f"배관 {y}", "금액": 300.0, "투자유형": ""}
         for y in (2023, 2024, 2025)]
        + [{"사업장": "화성지사", "연도": 2025, "예산과목": acct, "사업명": "GT LTSA 대금", "금액": 9000.0, "투자유형": "LTSA"}]))
    fs.save_table(conn, "2026", "investment_plan", pd.DataFrame([{"사업장": "화성지사", "연도": 2028, "금액": 50.0, "비고": ""}]))

    def invest_row():
        t = pf.forecast_frames(conn, "2026")["tables"]["화성지사"]
        return t[t["예산과목"] == "투자비"].iloc[0]

    assert not fs.invest_std_on(conn, "2026")                          # 기본 끔 — 종전대로
    assert not [r for r in pf.run_benchmark(conn, "2026")["rows"] if r["예산과목"] == acct]
    assert invest_row()[2027] == 0.0

    fs.save_settings(conn, "2026", {"투자비표준화": "1"})
    rows = [r for r in pf.run_benchmark(conn, "2026")["rows"] if r["사업장"] == "화성지사" and r["예산과목"] == acct]
    assert rows and all(r["표준금액"] == pytest.approx(300.0) for r in rows)   # LTSA 사업은 계획표로 — 표준화에서 뺀다
    row = invest_row()
    assert row[2027] == pytest.approx(300.0)                           # 투자계획 없는 해 = 표준금액
    assert row[2028] == pytest.approx(50.0)                            # 투자계획이 있는 해는 그 값


def test_locked_invest_vouchers_win_over_uploaded_invest_actuals_for_same_year(conn):
    """투자비 전표가 마감 실적(자본)에 들어온 해는 예전에 올린 투자비 실적 표를 쓰지 않는다 — 두 번 세지 않게."""
    fs.save_settings(conn, "2026", {"실적환산": "0", "투자비표준화": "1"})
    acct = "외주비-열원공사비"
    _seed_run(conn, "2025", "자본", [("화성지사", acct, 500.0, "계획집행")])
    dbm.lock_year(conn, "2025")
    fs.save_table(conn, "2026", "investment_actual", pd.DataFrame(
        [{"사업장": "화성지사", "연도": y, "예산과목": acct, "사업명": f"배관 {y}", "금액": 300.0, "투자유형": ""}
         for y in (2024, 2025)]
        + [{"사업장": "화성지사", "연도": 2024, "예산과목": acct, "사업명": "GT LTSA 대금", "금액": 9000.0, "투자유형": ""}]))
    actuals, _, _ = pf.actuals_with_reference(conn, "2026")
    got = actuals[actuals["예산과목"] == acct].groupby("연도")["금액"].sum().to_dict()
    assert got == {2024: 300.0, 2025: 500.0}                          # 2025 = 마감 전표만, 2024 = 올린 표
    # LTSA 사업은 실적 모집단에 아예 안 들어간다 — A급정비 규모비(site_scales)에도 섞이지 않게
