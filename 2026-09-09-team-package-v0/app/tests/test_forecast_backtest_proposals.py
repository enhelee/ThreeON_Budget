# -*- coding: utf-8 -*-
"""백테스트 제안(2026-10-26 «중장기 전망 백테스트 결과 공유» 6번) — 표준화 방향 작업에 합친 것.

다른 세션의 `feat-forecast-backtest-proposals` 브랜치에서 옮겼다. 겹치는 셋(사업명 정기비용 분리 ·
V3 파서 · 전환 지사)은 이 브랜치의 `regular_type`·`forecast_reference`·«실적사용시작»/«등급 차용»을 쓰고,
나머지를 이 브랜치의 표 이름(reference_actual · site_grade_eq · reference_standard)에 맞췄다.

② A급정비 일정 — 설비별 등급의 MI 해·A 로 바뀐 해에만 1회 금액(자기 과거 → 같은 묶음 × 규모비)
③ 학습 기간(기본 3개년) — 규칙 없는 칸만, 마감 실적 + 참고 엑셀 실적(마감 우선)
⑤ 평가 단위 — 과목 합계·지사 3년 누적 백테스트, 칸별 예측 범위
⑥ 재무팀(참고 엑셀) 표준금액 대비 ±%
"""
import json

import pandas as pd
import pytest

from budget import benchmark, forecast_backtest, forecast_calc
from budget import db as dbm
from budget import forecast_store as fs
from budget import pipeline_forecast as pf

MACHINE = "기계장치"
A_ACCT = forecast_calc.A_OVERHAUL_ACCOUNT
CHECK = "수선유지비-열원경상정비"


@pytest.fixture()
def conn(tmp_path):
    c = dbm.connect(str(tmp_path / "t.db"))
    yield c
    c.close()


def _seed_run(conn, year, budget, lines):
    """lines: [(처지사, 예산과목, 사업명, 실적금액)] — 구분은 계획집행."""
    cur = conn.execute("INSERT INTO run(year,budget,created_at,summary_json) VALUES(?,?,?,?)",
                       (year, budget, "2026-01-01 00:00:00", json.dumps({})))
    for dept, item, name, amt in lines:
        conn.execute("INSERT INTO biz_line(run_id,budget,예산과목,처지사,사업명,연예산,실적금액,구분)"
                     " VALUES(?,?,?,?,?,?,?,?)", (cur.lastrowid, budget, item, dept, name, 0.0, amt, "계획집행"))
    conn.commit()


def _ref(rows):
    """참고 실적 — rows: [(사업장, 연도, 예산과목, 금액[, 유형])]"""
    return pd.DataFrame([{"사업장": r[0], "연도": r[1], "예산과목": r[2], "금액": r[3],
                          "유형": r[4] if len(r) > 4 else "기타"} for r in rows])


def _save_ref(conn, rows):
    fs.save_table(conn, "2026", "reference_actual", _ref(rows))


def _units(rows):
    """설비별 등급 — rows: [(사업장, 설비, 연도, 등급)]"""
    return pd.DataFrame([{"사업장": s, "연도": y, "설비": u, "등급": g} for s, u, y, g in rows])


def _flat_factor(conn):
    fs.save_factors(conn, "2026", pd.DataFrame([{"팩터명": "물가", "연간비율": 0.0, "활성": True}]))


# ---------------------------------------------------------------- 실데이터 사업명(백테스트 세션 실측)
@pytest.mark.parametrize("name,expect", [
    ("공무_GT LTSA(외자 변동비)", "LTSA"),
    ("가스터빈 Ring Segment(1단-96PCS) 고온부품 재생 - 국내", "고온부품재생"),
    ("23년 고온부품 재생정비", "고온부품재생"),
    ("화성 CRI 정비", "CRI"),
    ("일산열병합Critical Point 개선(RCS)", "기타"),          # «Critical» 은 CRI 가 아니다
    ("화성지사 전력감시시스템 UPGRADE", "기타"),
])
def test_real_project_names(name, expect):
    assert benchmark.regular_type(MACHINE, name) == expect


def test_locked_machine_standard_excludes_hot_parts(conn):
    fs.save_settings(conn, "2026", {"실적환산": "0"})   # 이 테스트는 물가 환산과 무관 — 그 해 금액 그대로 본다
    _seed_run(conn, "2025", "자본", [("화성지사", MACHINE, "23년 고온부품 재생정비", 900.0),
                                     ("화성지사", MACHINE, "화성지사 전력감시시스템 UPGRADE", 100.0)])
    dbm.lock_year(conn, "2025")
    rows = pf.run_benchmark(conn, "2026")["rows"]
    m = [r for r in rows if r["사업장"] == "화성지사" and r["예산과목"] == MACHINE]
    assert m and m[0]["표준금액"] == pytest.approx(100.0)      # 1,000 이 아니라 비정기 100 만


# ---------------------------------------------------------------- ③ 학습 기간
def test_reference_merges_with_locked_years_locked_wins(conn):
    _save_ref(conn, [("화성지사", 2024, CHECK, 50.0), ("화성지사", 2025, CHECK, 999.0)])
    _seed_run(conn, "2025", "손익", [("화성지사", CHECK, "x", 100.0)])
    dbm.lock_year(conn, "2025")
    a, locked, ref_years = pf.actuals_with_reference(conn, "2026")
    assert locked == ["2025"] and ref_years == ["2024"]
    assert a[a["연도"] == 2025]["금액"].sum() == pytest.approx(100.0)      # 엑셀 999 가 아니라 마감값


def test_learning_window_defaults_to_three_and_limits_unruled_cells(conn):
    fs.save_settings(conn, "2026", {"실적환산": "0"})   # 이 테스트는 물가 환산과 무관 — 그 해 금액 그대로 본다
    _save_ref(conn, [("화성지사", y, CHECK, float(y - 2000)) for y in range(2016, 2026)])
    fs.save_method_map(conn, "2026", pd.DataFrame([{"사업장": "화성지사", "예산과목": CHECK, "방식": "5개년 평균"}]))
    assert fs.learning_window(conn, "2026") == 3
    std = {r["예산과목"]: r for r in pf.run_benchmark(conn, "2026")["rows"]}
    assert std[CHECK]["표준금액"] == pytest.approx(24.0)                  # 2023~2025 만 남아 3개 평균
    fs.save_settings(conn, "2026", {"학습기간": "10", "모르는키": "x"})
    assert fs.load_settings(conn, "2026") == {"학습기간": "10", "실적환산": "0"}   # 모르는 키는 버린다
    std = {r["예산과목"]: r for r in pf.run_benchmark(conn, "2026")["rows"]}
    assert std[CHECK]["표준금액"] == pytest.approx(23.0)                  # 2021~2025


def test_rules_ignore_learning_window():
    """산정 규칙은 엑셀처럼 연도를 직접 가리킨다 — 학습 기간 밖 해도 그대로 본다."""
    a = _ref([("화성지사", y, CHECK, float(y - 2000)) for y in range(2016, 2026)])
    rules = pd.DataFrame([{"사업장": "화성지사", "예산과목": CHECK, "등급": "*", "방식": "지정연도 평균",
                           "연도목록": "2017,2019"}])
    std = benchmark.compute_standard_amounts(a, pd.DataFrame(columns=["사업장", "연도", "등급"]), rules=rules, window=3)
    assert std.iloc[0]["표준금액"] == pytest.approx(18.0)


def test_recent_window_zero_means_all():
    df = _ref([("a", y, "x", 1.0) for y in (2020, 2021, 2022)])
    assert len(benchmark.recent_window(df, 0)) == 3 and len(benchmark.recent_window(df, 2)) == 2


# ---------------------------------------------------------------- ② A급정비 일정
def test_overhaul_years_mi_or_changed_to_a_only():
    u = _units([("화성지사", "#1 GT", 2023, "TI"), ("화성지사", "#1 GT", 2024, "MI"),
                ("화성지사", "ST", 2022, "C"), ("화성지사", "ST", 2023, "A"), ("화성지사", "ST", 2024, "A"),
                ("강남지사", "일원(ST)", 2023, "A"), ("강남지사", "일원(ST)", 2024, "A"),     # 매년 A
                ("청주지사", "DH", 2023, "C"), ("청주지사", "DH", 2024, "A")])               # DH 줄 제외
    assert forecast_calc.overhaul_years(u, "화성지사") == {2023, 2024}
    assert forecast_calc.overhaul_years(u, "강남지사") == set()
    assert forecast_calc.overhaul_years(u, "청주지사") == set()


def test_overhaul_amounts_own_then_peer_scale():
    a = _ref([("화성지사", 2019, A_ACCT, 800.0), ("화성지사", 2025, A_ACCT, 1000.0),
              ("화성지사", 2025, CHECK, 2000.0), ("파주지사", 2025, CHECK, 1000.0)])
    groups = {"화성지사": "중대형CHP", "파주지사": "중대형CHP"}
    out = forecast_calc.overhaul_amounts(a, ["화성지사", "파주지사"], groups)
    assert out["화성지사"] == pytest.approx(900.0)            # 자기 과거 평균
    # 같은 묶음 × 규모비 — 화성 규모 = 실적 있는 해(2019 800 · 2025 3,000)의 평균 1,900, 파주 1,000
    assert out["파주지사"] == pytest.approx(900.0 * 1000 / 1900)


def test_forecast_puts_overhaul_only_in_schedule_years(conn):
    _save_ref(conn, [("화성지사", 2025, A_ACCT, 1000.0), ("화성지사", 2024, A_ACCT, 0.0), ("화성지사", 2023, A_ACCT, 0.0)])
    _flat_factor(conn)
    fs.save_table(conn, "2026", "site_grade_eq", _units([("화성지사", "#1 GT", 2028, "TI"), ("화성지사", "#1 GT", 2029, "MI")]))
    out = pf.run_forecast(conn, "2026")
    line = {r["예산과목"]: r for r in out["tables"]["화성지사"]}[A_ACCT]
    assert line["2029"] == pytest.approx(1000.0)
    assert line["2027"] == 0 and line["2030"] == 0           # 평균을 해마다 흘리지 않는다
    assert out["overhaul_years"]["화성지사"] == [2029]


def test_overhaul_needs_future_grades_else_keeps_standard(conn):
    """설비별 등급은 과거뿐 — 미래 등급 없이 규칙을 걸면 A급정비가 10년 내내 0 이 된다."""
    _save_ref(conn, [("화성지사", y, A_ACCT, a) for y, a in ((2023, 300.0), (2024, 300.0), (2025, 900.0))])
    _flat_factor(conn)
    fs.save_table(conn, "2026", "site_grade_eq", _units([("화성지사", "#1 GT", 2024, "TI"), ("화성지사", "#1 GT", 2025, "MI")]))
    out = pf.run_forecast(conn, "2026")
    line = {r["예산과목"]: r for r in out["tables"]["화성지사"]}[A_ACCT]
    assert line["2028"] > 0 and out["overhaul_years"] == {}            # 표준금액 그대로
    fs.save_grade_history(conn, "2026", pd.DataFrame([{"사업장": "화성지사", "연도": 2031, "등급": "MI"}]))
    out = pf.run_forecast(conn, "2026")
    line = {r["예산과목"]: r for r in out["tables"]["화성지사"]}[A_ACCT]
    assert line["2031"] == pytest.approx(500.0) and line["2028"] == 0   # 양수 해 평균 (300+300+900)/3


def test_dh_group_grade_history_is_not_overhaul_schedule(conn):
    """DH 지사의 미래 등급 A 는 A급정비 해가 아니다(정비는 매년 수선유지비-정기점검)."""
    fs.save_grade_history(conn, "2026", pd.DataFrame([{"사업장": "중앙지사", "연도": 2027, "등급": "C"},
                                                     {"사업장": "중앙지사", "연도": 2028, "등급": "A"}]))
    assert pf.site_groups(conn, "2026")["중앙지사"] == "DH"
    assert pf.run_forecast(conn, "2026")["overhaul_years"] == {}


# ---------------------------------------------------------------- ⑤ 평가 단위 · 예측 범위
def test_backtest_reports_account_and_site3_errors():
    rows = []
    for y in range(2016, 2026):
        rows += [("화성지사", y, CHECK, 100.0), ("파주지사", y, CHECK, 50.0 + y % 2)]
    runs = forecast_backtest.compare_windows(_ref(rows), pd.DataFrame(columns=["사업장", "연도", "등급"]), (2, 3))
    assert [r["window"] for r in runs] == [2, 3]
    assert runs[0]["targets"] == [2021, 2022, 2023, 2024, 2025]
    assert runs[0]["account"] is not None and runs[0]["account"] < 0.02
    assert runs[0]["site3"] < 0.02


def test_backtest_excludes_planned_machine_parts():
    a = _ref([("화성지사", y, MACHINE, 1000.0 if y % 3 == 0 else 0.0, "고온부품재생") for y in range(2018, 2026)]
             + [("화성지사", y, MACHINE, 100.0) for y in range(2018, 2026)])
    r = forecast_backtest.run(a, pd.DataFrame(columns=["사업장", "연도", "등급"]), 3)
    assert r["cell"] == pytest.approx(0.0)                    # 비정기 100 만 평가 — 고온부품 출렁임은 계획 몫


def test_forecast_ranges_from_window_min_max(conn):
    _save_ref(conn, [("화성지사", 2023, CHECK, 80.0), ("화성지사", 2024, CHECK, 120.0), ("화성지사", 2025, CHECK, 100.0)])
    _flat_factor(conn)
    out = pf.run_forecast(conn, "2026")
    rg = out["ranges"]["화성지사"][CHECK]
    assert rg["2027"] == [80.0, 120.0] and "2026" not in rg


# ---------------------------------------------------------------- ⑥ 재무팀 대비
def test_finance_compare_exact_grade_then_mean():
    std = pd.DataFrame([{"사업장": "a", "예산과목": "x", "등급": "MI", "표준금액": 120.0},
                        {"사업장": "a", "예산과목": "x", "등급": "표준", "표준금액": 90.0},
                        {"사업장": "b", "예산과목": "x", "등급": "MI", "표준금액": 5.0}])
    fin = pd.DataFrame([{"사업장": "a", "예산과목": "x", "등급": "MI", "표준금액": 100.0},
                        {"사업장": "a", "예산과목": "x", "등급": "TI", "표준금액": 50.0}])
    out = pf.finance_compare(std, fin)
    assert out["재무팀대비"].iloc[0] == pytest.approx(0.2)
    assert out["재무팀금액"].iloc[1] == pytest.approx(75.0)        # 같은 등급 없음 → 평균
    assert out["재무팀금액"].iloc[2] is None or pd.isna(out["재무팀금액"].iloc[2])


def test_settings_copy_with_base_year(conn):
    fs.save_settings(conn, "2026", {"학습기간": "5"})
    assert not fs.base_year_is_untouched(conn, "2026")
    fs.copy_base_year(conn, "2026", "2027")
    assert fs.learning_window(conn, "2027") == 5


# ---------------------------------------------------------------- API
from tests.test_forecast_api import client   # noqa: E402,F401  (픽스처 재사용)


def test_api_settings_backtest_finance(client):
    c = dbm.connect()
    try:
        fs.save_table(c, "2026", "reference_actual",
                      _ref([("화성지사", y, CHECK, 100.0 + y % 3) for y in range(2019, 2026)]))
        fs.save_table(c, "2026", "reference_standard", pd.DataFrame(
            [{"사업장": "화성지사", "예산과목": CHECK, "등급": "표준", "표준금액": 80.0, "엑셀수식": "=$B$17"}]))
    finally:
        c.close()
    r = client.put("/api/forecast/settings", json={"base_year": "2026", "values": {"학습기간": "2"}})
    assert r.json()["settings"]["학습기간"] == "2"
    assert client.get("/api/forecast/state?base_year=2026").json()["settings"]["학습기간"] == "2"
    bench = client.get("/api/forecast/benchmark?base_year=2026").json()
    row = [x for x in bench["rows"] if x["사업장"] == "화성지사" and x["예산과목"] == CHECK][0]
    assert bench["window"] == 2 and row["재무팀금액"] == 80.0 and row["재무팀대비"] is not None
    bt = client.get("/api/forecast/backtest?base_year=2026").json()
    assert [x["window"] for x in bt["runs"]] == [2, 3, 5, 10] and bt["sources"]["참고"]
    t = client.get("/api/forecast/table?base_year=2026").json()
    assert "ranges" in t and t["overhaul_years"] == {}
