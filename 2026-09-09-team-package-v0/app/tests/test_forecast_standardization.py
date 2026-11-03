# -*- coding: utf-8 -*-
"""표준화 방향(예산표준화 V3 «표준화방향» 시트) 반영 — 2026-10-26.

  1  중대형 CHP: 고온부품·LTSA·CRI 를 빼고 «기타기계장치»만 등급별 표준화
  2  신규 지사: 실적사용시작 이벤트 · 예산 대체
  3  A·B·C(MI·TI·CI) 등급별 — 설비별 등급, 등급별 최근실적
  4-1~3  산정 규칙(지정연도 평균·최대값·등급 차용·보정률·조정액·직접 입력)
  4-4  LTSA 정기계약 계획 · 4-5 CRI 자동 발생 · 4-6 역무 증가(실적사용시작)
  공통  손익/자본 팩터 · 투자계획 · 참고 엑셀 가져오기와 대조
"""
import io
import json

import pandas as pd
import pytest
from openpyxl import Workbook

from budget import benchmark, forecast_calc, forecast_reference as fr
from budget import db as dbm
from budget import forecast_store as fs
from budget import pipeline_forecast as pf

GRADES = pd.DataFrame(columns=["사업장", "연도", "등급"])


def _actuals(rows):
    """rows: [(사업장, 연도, 예산과목, 금액, 유형)]"""
    return pd.DataFrame(rows, columns=["사업장", "연도", "예산과목", "금액", "유형"])


def _rules(rows):
    cols = fs.SPECS["benchmark_rule"]["cols"]
    return pd.DataFrame([{**{c: None for c in cols}, **r} for r in rows], columns=cols)


def _std(std, site, acct, grade):
    return float(std[(std["사업장"] == site) & (std["예산과목"] == acct) & (std["등급"] == grade)]["표준금액"].iloc[0])


# ---------------------------------------------------------------- 1 · 4-4 정기비용 성격
@pytest.mark.parametrize("acct,name,kind", [
    ("기계장치", "#1 GT 고온부품 재생정비", "고온부품재생"),
    ("기계장치", "GT 재생 정비(가스터빈)", "고온부품재생"),
    ("기계장치", "GT 로터 CRI 대가", "CRI"),
    ("기계장치", "GT LTSA 정산", "LTSA"),
    ("수선유지비-열원정기유지보수", "연료전지 장기유지보수(LTSA)", "LTSA"),
    ("수선유지비-열원정기유지보수", "보일러 유지보수 용역", "기타"),
    ("기계장치", "급수펌프 교체", "기타"),
    ("기계장치", "CRITICAL 밸브 교체", "기타"),
    ("수선유지비-열원경상정비", "LTSA 이름이어도 대상 과목이 아님", "기타"),
])
def test_regular_type_keywords(acct, name, kind):
    assert benchmark.regular_type(acct, name) == kind


def test_regular_costs_leave_standardization():
    """기계장치 총액이 아니라 «기타기계장치»만 표준화 — 고온부품·CRI 는 연도별 계획으로 따로 잡는다."""
    a = _actuals([("화성", 2025, "기계장치", 300.0, "기타"), ("화성", 2025, "기계장치", 900.0, "고온부품재생"),
                  ("화성", 2025, "기계장치", 500.0, "CRI"),
                  ("화성", 2025, "수선유지비-열원정기유지보수", 50.0, "기타"),
                  ("화성", 2025, "수선유지비-열원정기유지보수", 400.0, "LTSA")])
    std = benchmark.compute_standard_amounts(a, GRADES)
    assert _std(std, "화성", "기계장치", "표준") == pytest.approx(300.0)
    assert _std(std, "화성", "수선유지비-열원정기유지보수", "표준") == pytest.approx(50.0)
    assert benchmark.has_ltsa_detail(a)


# ---------------------------------------------------------------- 3 · 4-1~3 산정 규칙
def _hist():
    return pd.DataFrame([("화성", 2021, "TI"), ("화성", 2023, "TI"), ("화성", 2024, "간이"), ("화성", 2025, "MI")],
                        columns=["사업장", "연도", "등급"])


def _series(site, acct, values):
    return [(site, y, acct, v, "기타") for y, v in values.items()]


def test_rule_methods_match_excel_shapes():
    a = _actuals(_series("화성", "수선유지비-열원정기점검", {2021: 400.0, 2022: 100.0, 2023: 600.0,
                                                         2024: 200.0, 2025: 900.0})
                 + _series("파주", "수선유지비-열원정기점검", {2025: 1000.0}))
    rules = _rules([
        {"사업장": "화성", "예산과목": "수선유지비-열원정기점검", "등급": "MI", "방식": "등급별 최근실적"},
        {"사업장": "화성", "예산과목": "수선유지비-열원정기점검", "등급": "TI", "방식": "지정연도 평균",
         "연도목록": "2023,2021", "보정률": 1.2},
        {"사업장": "화성", "예산과목": "수선유지비-열원정기점검", "등급": "간이", "방식": "최대값",
         "연도목록": "2022~2024", "조정액": -50.0},
        {"사업장": "파주", "예산과목": "수선유지비-열원정기점검", "등급": "MI", "방식": "등급 차용",
         "참조지사": "화성", "참조등급": "TI", "보정률": 0.5},
        {"사업장": "파주", "예산과목": "수선유지비-열원정기점검", "등급": "TI", "방식": "직접 입력", "조정액": 777.0},
    ])
    std = benchmark.compute_standard_amounts(a, _hist(), rules=rules)
    assert _std(std, "화성", "수선유지비-열원정기점검", "MI") == pytest.approx(900.0)       # 2025(MI)
    assert _std(std, "화성", "수선유지비-열원정기점검", "TI") == pytest.approx(500.0 * 1.2)  # (600+400)/2 ×1.2
    assert _std(std, "화성", "수선유지비-열원정기점검", "간이") == pytest.approx(600.0 - 50)
    assert _std(std, "파주", "수선유지비-열원정기점검", "MI") == pytest.approx(600.0 * 0.5)  # 화성 TI 차용
    assert _std(std, "파주", "수선유지비-열원정기점검", "TI") == pytest.approx(777.0)
    row = std[(std["사업장"] == "화성") & (std["등급"] == "TI")].iloc[0]
    assert row["방식출처"] == "규칙" and "2023·2021" in row["근거"] and "×1.2" in row["근거"]


def test_rule_star_grade_and_budget_substitute():
    """신규 지사(양산): 실적이 쌓이기 전에는 기준연도 계획본을 표준으로."""
    a = _actuals(_series("양산", "수선유지비-열원정기점검", {2025: 10.0}))
    rules = _rules([{"사업장": "양산", "예산과목": "수선유지비-열원정기점검", "등급": "*", "방식": "예산 대체"}])
    std = benchmark.compute_standard_amounts(a, GRADES, rules=rules,
                                             budget_lookup={("양산", "수선유지비-열원정기점검"): 761.7})
    assert _std(std, "양산", "수선유지비-열원정기점검", "표준") == pytest.approx(761.7)


def test_borrow_cycle_does_not_hang():
    rules = _rules([{"사업장": "A", "예산과목": "기계장치", "등급": "MI", "방식": "등급 차용", "참조지사": "B"},
                    {"사업장": "B", "예산과목": "기계장치", "등급": "MI", "방식": "등급 차용", "참조지사": "A"}])
    std = benchmark.compute_standard_amounts(_actuals([]), GRADES, rules=rules)
    assert set(std["표준금액"]) == {0.0}


def test_usage_start_event_drops_earlier_years():
    """4-6 세종: 북세종 준공('24) 이후 역무 증가 — 그 전 실적은 표준화에서 뺀다."""
    a = _actuals(_series("세종", "기계장치", {2022: 10.0, 2023: 20.0, 2024: 900.0, 2025: 1100.0}))
    ev = pd.DataFrame([{"사업장": "세종", "연도": 2024, "유형": "실적사용시작", "예산과목": "", "비고": "북세종"}])
    rules = _rules([{"사업장": "세종", "예산과목": "기계장치", "등급": "*", "방식": "지정연도 평균"}])
    std = benchmark.compute_standard_amounts(a, GRADES, rules=rules, events=ev)
    assert _std(std, "세종", "기계장치", "표준") == pytest.approx(1000.0)


# ---------------------------------------------------------------- 4-4 · 4-5 · 공통 — 전망
def _table(**kw):
    empty = pd.DataFrame()
    std = pd.DataFrame(columns=["사업장", "예산과목", "등급", "표준금액"])
    args = dict(site="화성", grade_hist=kw.pop("grade", GRADES), standard_df=kw.pop("std", std),
                hot_parts_df=empty, hq_amount_by_site_acct={}, hq_temp_alloc=empty,
                factors_df=kw.pop("factors", pd.DataFrame([{"팩터명": "물가", "연간비율": 0.0, "활성": True}])),
                surprise_df=empty, investment_df=kw.pop("invest", empty), base_year=2026)
    args.update(kw)
    t = forecast_calc.compute_site_table(**args)
    return t.set_index("예산과목")


def test_cri_events_follow_mi_with_lag_and_inflation():
    grade = pd.DataFrame([("화성", 2025, "MI"), ("화성", 2031, "MI"), ("파주", 2028, "MI")],
                         columns=["사업장", "연도", "등급"])
    rules = pd.DataFrame([{"사업장": "화성", "짝지사": "파주", "지급시차": 3, "기준단가": 1000.0,
                           "단가기준연도": 2022, "활성": True, "비고": ""}])
    factors = pd.DataFrame([{"팩터명": "건설", "연간비율": 0.1, "활성": True, "적용구분": "자본"}])
    ev = forecast_calc.cri_events(grade, rules, factors, list(range(2026, 2036)))
    assert ev["지급연도"].tolist() == [2028, 2034]
    assert ev.iloc[0]["금액"] == pytest.approx(1000.0 * 1.1 ** 6)
    assert ev.iloc[0]["짝지사"] == "파주" and ev.iloc[0]["반출연도"] == 2026
    t = _table(cri_df=ev)
    assert t.loc["기계장치_CRI", 2028] == pytest.approx(1000.0 * 1.1 ** 6)
    assert t.loc["기계장치_CRI", 2027] == 0


def test_regular_contracts_go_to_their_lines_without_factor():
    c = pd.DataFrame([{"사업장": "화성", "연도": 2027, "항목": "GT LTSA", "예산과목": "수선유지비-열원정기유지보수",
                       "금액": 2100.0, "비고": ""},
                      {"사업장": "화성", "연도": 2027, "항목": "기타 LTSA", "예산과목": "기계장치", "금액": 50.0, "비고": ""}])
    t = _table(contracts_df=c, factors=pd.DataFrame([{"팩터명": "물가", "연간비율": 0.05, "활성": True}]))
    assert t.loc["수선유지비-열원정기유지보수_LTSA", 2027] == pytest.approx(2100.0)
    assert t.loc["기계장치_LTSA", 2027] == pytest.approx(50.0)


def test_contracts_not_added_on_top_of_base_year_plan():
    """기준연도는 계획본이 확정값 — 계획본의 정기유지보수에 LTSA 가 이미 들어 있다."""
    c = pd.DataFrame([{"사업장": "화성", "연도": y, "항목": "GT LTSA", "예산과목": "수선유지비-열원정기유지보수",
                       "금액": 2100.0, "비고": ""} for y in (2026, 2027)])
    t = _table(contracts_df=c, budget_lookup={("화성", "수선유지비-열원정기유지보수"): 9000.0})
    assert t.loc["수선유지비-열원정기유지보수_LTSA", 2026] == 0
    assert t.loc["수선유지비-열원정기유지보수", 2026] == 9000.0
    assert t.loc["수선유지비-열원정기유지보수_LTSA", 2027] == pytest.approx(2100.0)


def test_factor_scope_splits_pl_and_capital():
    std = pd.DataFrame([("화성", "수선유지비-열원경상정비", "표준", 100.0), ("화성", "공구와기구-열원시설공기구", "표준", 100.0)],
                       columns=["사업장", "예산과목", "등급", "표준금액"])
    f = pd.DataFrame([{"팩터명": "생산자물가", "연간비율": 0.02, "활성": True, "적용구분": "손익"},
                      {"팩터명": "건설공사비", "연간비율": 0.06, "활성": True, "적용구분": "자본"}])
    t = _table(std=std, factors=f)
    assert t.loc["수선유지비-열원경상정비", 2027] == pytest.approx(102.0)
    assert t.loc["공구와기구-열원시설공기구", 2027] == pytest.approx(106.0)


def test_investment_plan_replaces_repetition():
    inv = pd.DataFrame([{"사업장": "화성", "지사유형": "", "금액": 500.0}])
    plan = pd.DataFrame([{"사업장": "화성", "연도": 2028, "금액": 70.0, "비고": ""}])
    t = _table(invest=inv, invest_plan_df=plan)
    assert t.loc["투자비", 2026] == 500.0 and t.loc["투자비", 2027] == 0 and t.loc["투자비", 2028] == 70.0
    t_old = _table(invest=inv)                       # 투자계획 표를 안 넘기면 v2 동작(반복)
    assert t_old.loc["투자비", 2030] == 500.0


# ---------------------------------------------------------------- 참고 엑셀 가져오기
ACCTS = ["저장품-열원(보수)", "건 물", "구축물", "기계장치", "공구와기구-열원시설공기구", "건가-외주비-열원정기점검",
         "건설중인자산-재생고온부품", "건설중인자산-자산화예비품", "투자비", "자본소계", None,
         "수선유지비-건물/구축물", "수선유지비-열원정기점검", "수선유지비-열원경상정비", "수선유지비-열원정기유지보수",
         "수선유지비-열원보완개선및기타", "지급수수료-열원점검수수료", "손익소계"]
YEARS = [2025, 2024, 2023, 2022, 2021]


def _branch(wb, name, check, machine, regular, grades, std_formulas):
    ws = wb.create_sheet(name)
    for i, y in enumerate(YEARS):
        ws.cell(3, 2 + i, y)
    for r, lab in enumerate(ACCTS, start=4):
        if lab:
            ws.cell(r, 1, lab)
    for i, y in enumerate(YEARS):
        ws.cell(16, 2 + i, check[y])                  # 수선유지비-열원정기점검
        ws.cell(7, 2 + i, machine[y])                 # 기계장치
    ws.cell(23, 1, "#1 GT")
    ws.cell(24, 1, "ST")
    for i, y in enumerate(YEARS):
        ws.cell(23, 2 + i, grades[y])
        ws.cell(24, 2 + i, "A")
    ws.cell(27, 1, "기계장치")
    ws.cell(28, 1, " - (정기) 고온부품재생, LTSA")
    ws.cell(29, 1, " - (정기) CRI")
    ws.cell(31, 1, " - (비정기, 표준화) 기타기계장치")
    for i, y in enumerate(YEARS):
        ws.cell(28, 2 + i, regular.get(y, 0))
    ws.cell(33, 1, "손익예산 Standization")
    for c, g in zip("DEF", ["MI", "TI", "간이"]):
        ws[f"{c}33"] = g
    ws["G33"] = "비고"
    ws.cell(35, 1, "수선유지비-열원정기점검")
    ws.cell(41, 1, "자본예산 Standization")
    for c, g in zip("DEF", ["MI", "TI", "간이"]):
        ws[f"{c}41"] = g
    ws.cell(43, 1, " - (비정기, 표준화) 기타기계장치")
    for cell, f in std_formulas.items():
        ws[cell] = f
    return ws


def reference_workbook():
    wb = Workbook()
    wb.active.title = "표준화방향"
    wb["표준화방향"]["B3"] = "CRI: 동일기종 다른지사(화성->파주, 파주->화성) 에 장착"
    g = wb.create_sheet("중대형chp")
    g["B3"], g["C3"] = "2025년", "2024년"
    g["B4"], g["C4"] = "=화성!B4+파주!B4", "=화성!C4"
    hw = _branch(wb, "화성", check={2025: 900, 2024: 200, 2023: 600, 2022: 100, 2021: 400},
                 machine={2025: 1300, 2024: 50, 2023: 700, 2022: 2600, 2021: 80},
                 regular={2025: 1000, 2023: 500}, grades={2025: "MI", 2024: "간이", 2023: "TI", 2022: "간이", 2021: "TI"},
                 std_formulas={"D35": "=B16", "E35": "=AVERAGE(D16,F16)*1.2", "F35": "=$B$16",
                               "D43": "=B31", "E43": "=AVERAGE($B$31:$D$31)", "F43": "=MAX(C31,E31)"})
    hw["E29"] = 2565                                  # 2022 CRI
    _branch(wb, "파주", check={2025: 300, 2024: 300, 2023: 300, 2022: 300, 2021: 300},
            machine={y: 100 for y in YEARS}, regular={},
            grades={2025: "간이", 2024: "TI", 2023: "간이", 2022: "MI", 2021: "간이"},
            std_formulas={"D35": "=화성!D35", "E35": "=(B16+C16)/2", "F35": "12345"})
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_parse_reference_reads_actuals_grades_rules_history_cri():
    p = fr.parse_reference(reference_workbook(), ["화성지사", "파주지사"])
    act = pd.DataFrame(p["reference_actual"])
    m = act[(act["사업장"] == "화성지사") & (act["예산과목"] == "기계장치") & (act["연도"] == 2025)]
    assert dict(zip(m["유형"], m["금액"])) == {"기타": 300.0, "고온부품재생": 1000.0}
    m22 = act[(act["사업장"] == "화성지사") & (act["예산과목"] == "기계장치") & (act["연도"] == 2022)]
    assert dict(zip(m22["유형"], m22["금액"])) == {"기타": 35.0, "CRI": 2565.0}
    eq = pd.DataFrame(p["site_grade_eq"])
    assert set(eq["설비"]) == {"#1 GT", "ST"}
    rep = pd.DataFrame(p["site_grade"])                # 표준화 표 어휘(MI·TI·간이)와 맞는 GT 행이 대표
    assert rep[(rep["사업장"] == "화성지사") & (rep["연도"] == 2023)]["등급"].iloc[0] == "TI"
    rules = {(r["사업장"], r["예산과목"], r["등급"]): r for r in p["benchmark_rule"]}
    assert rules[("화성지사", "수선유지비-열원정기점검", "MI")]["방식"] == "등급별 최근실적"
    r = rules[("화성지사", "수선유지비-열원정기점검", "TI")]
    assert r["방식"] == "지정연도 평균" and r["연도목록"] == "2023,2021" and r["보정률"] == pytest.approx(1.2)
    assert rules[("화성지사", "수선유지비-열원정기점검", "간이")]["방식"] == "최근실적"
    assert rules[("화성지사", "기계장치", "TI")]["방식"] == "3개년 평균"
    assert rules[("화성지사", "기계장치", "간이")]["방식"] == "최대값"
    assert rules[("파주지사", "수선유지비-열원정기점검", "MI")]["방식"] == "등급 차용"
    assert rules[("파주지사", "수선유지비-열원정기점검", "MI")]["참조지사"] == "화성지사"
    assert rules[("파주지사", "수선유지비-열원정기점검", "TI")]["방식"] == "직접 입력"    # (B+C)/2 는 모르는 모양
    hist = pd.DataFrame(p["site_history"])
    assert hist[hist["사업장"] == "화성지사"]["그룹"].tolist() == ["중대형CHP"]
    assert hist[hist["사업장"] == "파주지사"]["시작연도"].tolist() == [2025]
    cri = {r["사업장"]: r for r in p["cri_rule"]}
    assert cri["화성지사"]["짝지사"] == "파주지사" and cri["화성지사"]["지급시차"] == 2   # CRI 이전 MI 없음 → 기본 2년
    assert cri["화성지사"]["기준단가"] == 2565.0 and cri["화성지사"]["단가기준연도"] == 2022
    assert any("수식 결과값" in w for w in p["warnings"])     # openpyxl 로 만든 파일은 값이 없다


def test_reference_rules_reproduce_with_engine():
    p = fr.parse_reference(reference_workbook(), ["화성지사", "파주지사"])
    f = fr.to_frames(p)
    std = benchmark.compute_standard_amounts(f["reference_actual"], f["site_grade"], rules=f["benchmark_rule"])
    assert _std(std, "화성지사", "수선유지비-열원정기점검", "TI") == pytest.approx((600 + 400) / 2 * 1.2)
    assert _std(std, "화성지사", "기계장치", "MI") == pytest.approx(300.0)                  # 기타기계장치 2025
    assert _std(std, "화성지사", "기계장치", "TI") == pytest.approx((300 + 50 + 200) / 3)
    assert _std(std, "파주지사", "수선유지비-열원정기점검", "MI") == pytest.approx(900.0)   # 화성 MI 차용


# ---------------------------------------------------------------- 파이프라인 · API
from tests.test_forecast_api import client, _seed_plan   # noqa: E402,F401  (픽스처 재사용)


def _seed_run_named(conn, year, budget, lines):
    """lines: [(처지사, 예산과목, 사업명, 실적금액)]"""
    cur = conn.execute("INSERT INTO run(year,budget,created_at,summary_json) VALUES(?,?,?,?)",
                       (year, budget, "2026-01-01 00:00:00", json.dumps({})))
    for dept, item, name, amt in lines:
        conn.execute("INSERT INTO biz_line(run_id,budget,예산과목,처지사,사업명,연예산,실적금액,구분)"
                     " VALUES(?,?,?,?,?,?,?,?)", (cur.lastrowid, budget, item, dept, name, 0.0, amt, "계획집행"))
    conn.commit()


@pytest.fixture()
def conn(tmp_path):
    c = dbm.connect(str(tmp_path / "t.db"))
    yield c
    c.close()


def test_locked_actuals_detail_tags_and_manual_override(conn):
    fs.save_settings(conn, "2026", {"실적환산": "0"})   # 이 테스트는 물가 환산과 무관 — 그 해 금액 그대로 본다
    _seed_run_named(conn, "2025", "자본", [("화성지사", "기계장치", "#1 GT 고온부품 재생", 900.0),
                                         ("화성지사", "기계장치", "급수펌프 교체", 300.0),
                                         ("화성지사", "기계장치", "밸브 정비", 70.0)])
    dbm.lock_year(conn, "2025")
    fs.save_table(conn, "2026", "actual_tag", pd.DataFrame([{"사업장": "화성지사", "연도": 2025, "예산과목": "기계장치",
                                                             "사업명": "밸브 정비", "유형": "CRI"}]))
    d, years = pf.locked_actuals_detail(conn, "2026")
    kinds = dict(zip(d["사업명"], zip(d["유형"], d["유형출처"])))
    assert kinds["#1 GT 고온부품 재생"] == ("고온부품재생", "자동")
    assert kinds["밸브 정비"] == ("CRI", "수동")
    std = pf.run_benchmark(conn, "2026")
    mach = [r for r in std["rows"] if r["사업장"] == "화성지사" and r["예산과목"] == "기계장치"]
    assert mach[0]["표준금액"] == pytest.approx(300.0) and std["has_ltsa"] is True
    br = pf.regular_breakdown(conn, "2026")
    s = br["summary"][0]
    assert s["총액"] == 1270.0 and s["고온부품재생"] == 900.0 and s["CRI"] == 70.0 and s["기타"] == 300.0


def test_reference_fills_unlocked_years_and_compare(conn):
    fs.save_settings(conn, "2026", {"실적환산": "0"})   # 이 테스트는 물가 환산과 무관 — 그 해 금액 그대로 본다
    _seed_run_named(conn, "2025", "손익", [("화성지사", "수선유지비-열원정기점검", "정기점검", 950.0)])
    dbm.lock_year(conn, "2025")
    p = fr.parse_reference(reference_workbook(), ["화성지사", "파주지사"])
    f = fr.to_frames(p)
    for name in ("reference_actual", "benchmark_rule"):
        fs.save_table(conn, "2026", name, f[name])
    fs.save_table(conn, "2026", "reference_standard",
                  pd.DataFrame([{"사업장": "화성지사", "예산과목": "수선유지비-열원정기점검", "등급": "TI",
                                 "표준금액": 600.0, "엑셀수식": "=AVERAGE(D16,F16)*1.2"}]))
    fs.save_grade_history(conn, "2026", f["site_grade"])
    merged, years, ref_years = pf.actuals_with_reference(conn, "2026")
    assert years == ["2025"] and "2023" in ref_years and "2025" not in ref_years   # 마감 연도는 앱 값
    cmp_ = pf.compare_reference(conn, "2026")
    a = {(r["사업장"], r["연도"], r["예산과목"]): r for r in cmp_["actual"]["rows"]}
    assert a[("화성지사", 2025, "수선유지비-열원정기점검")]["차이"] == pytest.approx(50.0)     # 950 vs 900
    s = cmp_["standard"]["rows"][0]
    assert s["앱"] == pytest.approx(600.0) and s["차이"] == pytest.approx(0.0)              # 2023·2021 은 엑셀 값


def test_api_reference_preview_apply_and_new_tables(client):
    files = {"file": ("ref.xlsx", reference_workbook(),
                      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    pre = client.post("/api/forecast/reference?base_year=2026", files=files).json()
    assert pre["counts"]["benchmark_rule"] > 0 and "sample" in pre
    assert client.get("/api/forecast/state?base_year=2026").json()["benchmark_rule"] == []   # 미리보기는 저장 안 함
    files = {"file": ("ref.xlsx", reference_workbook(),
                      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    done = client.post("/api/forecast/reference?base_year=2026&apply=true", files=files).json()
    assert done["applied"] is True
    st = client.get("/api/forecast/state?base_year=2026").json()
    assert st["benchmark_rule"] and st["site_history"] and st["cri_rule"]
    assert st["reference"]["reference_actual"] > 0 and "등급 차용" in st["options"]["rule_methods"]
    r = client.put("/api/forecast/state/investment-plan",
                   json={"base_year": "2026", "rows": [{"사업장": "화성지사", "연도": 2028, "금액": 70, "비고": "증설"}]})
    assert r.status_code == 200 and r.json()["rows"][0]["금액"] == 70.0
    t = client.get("/api/forecast/table?base_year=2026").json()
    assert "기계장치_CRI" in [x["예산과목"] for x in t["tables"]["화성지사"]] and "cri_events" in t
    assert t["tables"]["화성지사"][-1]["2028"] == 70.0                                       # 투자비 = 투자계획
    assert client.get("/api/forecast/compare?base_year=2026").status_code == 200
    assert client.get("/api/forecast/regular?base_year=2026").status_code == 200
    assert client.put("/api/forecast/state/nope", json={"base_year": "2026", "rows": []}).status_code == 404


def test_copy_base_year_carries_new_tables(conn):
    fs.save_table(conn, "2026", "cri_rule", pd.DataFrame([{"사업장": "화성지사", "짝지사": "파주지사", "지급시차": 3,
                                                           "기준단가": 1.0, "단가기준연도": 2022, "활성": True, "비고": ""}]))
    fs.copy_base_year(conn, "2026", "2027")
    assert fs.load_table(conn, "2027", "cri_rule")["짝지사"].tolist() == ["파주지사"]
    assert not fs.base_year_is_untouched(conn, "2026")
