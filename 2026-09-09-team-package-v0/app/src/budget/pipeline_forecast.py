# -*- coding: utf-8 -*-
"""3·4단계 입력 조립과 실행 — UI 비의존.

Phase 6-6. 계산부(`benchmark`·`forecast_calc`)와 상태 층(`forecast_store`)은 있다.
여기는 그 사이 — **이 앱의 DB 에서 입력을 꺼내 계산부 모양으로 맞춰 넣는 층**이다.

v2 와 다른 두 곳(설계 §2, 사용자 결정 2026-09-19):
  실적   v2 는 checkpoint JSON / classified_*.csv. 여기서는 **마감된 연도**의 최신 분석
         결과 `biz_line` 중 구분 ∈ {계획집행, 신규, 신규(소액집행)}. 마감 = 대외 보고에
         쓴 확정값이고, 열린 연도는 수정 중이라 표준금액이 흔들린다. 6-3 기준선 테스트가
         이미 이 모집단을 쓴다.
  예산   v2 는 budget_{연도}.csv 의 부서코드를 표시명으로 풀었다. 여기서는 1단계 계획본
         `plan_row` 의 처지사가 이미 정규화돼 있다. 어댑터가 v2 열 이름으로 맞춰 계산부를
         고치지 않는다.

지사 목록은 정비등급 이력의 사업장(v2)이 아니라 `dept_config(base_year)` 의 포함 지사
(본사 제외)다 — 등급 이력이 비어도 표는 나와야 한다(지금 실데이터가 그 상태).
결과는 저장하지 않는다. 22개 지사 × 17행 × 10년은 요청마다 계산해도 1초 안이다.
"""
import json

import pandas as pd

from . import benchmark, config_store, forecast_calc
from . import db as dbm
from . import forecast_store as fs

KEEP = ("계획집행", "신규", "신규(소액집행)")
ACTUAL_COLS = ["사업장", "연도", "예산과목", "금액"]
# v2 예산계획의 열 이름 — 계산부(forecast_calc.investment_by_site 등)가 이 리터럴을 본다.
DEPT_COL = "예산귀속 \n부서코드"
AMOUNT_COL = "연예산 합계"
BUDGET_COLS = ["예산과목", DEPT_COL, AMOUNT_COL]


# ---------------------------------------------------------------- 입력
def locked_actuals(conn):
    """마감 연도의 최신 분석 결과 → (사업장, 연도, 예산과목, 금액), 쓰인 연도 목록."""
    years_used, rows = [], []
    for year in sorted(dbm.locked_years(conn)):
        used = False
        for budget in ("손익", "자본"):
            run = dbm.latest_run(conn, year, budget)
            if not run:
                continue
            used = True
            for dept, item, amt, gubun in conn.execute(
                    "SELECT 처지사,예산과목,실적금액,구분 FROM biz_line WHERE run_id=?", (run["id"],)):
                if gubun in KEEP and amt:
                    rows.append({"사업장": dept, "연도": int(year), "예산과목": item, "금액": float(amt)})
        if used:
            years_used.append(str(year))
    return pd.DataFrame(rows, columns=ACTUAL_COLS), years_used


def budget_plan_for(conn, base_year):
    """기준연도 계획본을 v2 예산계획 모양으로. 없으면 빈 표(계산부가 «계획 없음»으로 처리)."""
    df = dbm.load_plan_df(conn, base_year)
    if df is None or df.empty:
        return pd.DataFrame(columns=BUDGET_COLS)
    return pd.DataFrame({"예산과목": df["예산과목"].astype(str),
                         DEPT_COL: df["처지사"].astype(str),
                         AMOUNT_COL: pd.to_numeric(df["연예산"], errors="coerce").fillna(0.0)},
                        columns=BUDGET_COLS)


def forecast_sites(conn, base_year):
    return [x["이름"] for x in config_store.load_dept_config(conn, base_year)
            if x["포함"] and x["그룹"] != "본사"]


def site_groups(conn, base_year):
    return {x["이름"]: x["그룹"] for x in config_store.load_dept_config(conn, base_year)}


def default_base_year(conn):
    """상태가 있는 최신 기준연도 → 없으면 마감 최신연도+1 → 그것도 없으면 v2 기본(2026)."""
    existing = fs.list_base_years(conn)
    if existing:
        return existing[-1]
    locked = dbm.locked_years(conn)
    return str(int(max(locked)) + 1) if locked else str(forecast_calc.BASE_YEAR)


def records(df: pd.DataFrame) -> list:
    """DataFrame → JSON 안전한 dict 목록(numpy 스칼라·NaN 처리는 pandas 에 맡긴다)."""
    if df is None or df.empty:
        return []
    return json.loads(df.to_json(orient="records", force_ascii=False))


# ---------------------------------------------------------------- 실행
def _standard(conn, base_year):
    actuals, years_used = locked_actuals(conn)
    grade = fs.load_grade_history(conn, base_year)
    std = benchmark.compute_standard_amounts(
        actuals, grade, fs.load_method_map(conn, base_year), fs.load_overrides(conn, base_year),
        item_alias=config_store.load_item_alias(conn))
    return std, actuals, years_used, grade


def run_benchmark(conn, base_year):
    """3단계 — 표준금액 표와 모집단 요약."""
    fs.bind_site_resolvers(conn, base_year)
    std, actuals, years_used, _ = _standard(conn, base_year)
    if not std.empty:
        std = std.sort_values(["사업장", "구분", "예산과목", "등급"]).reset_index(drop=True)
    return {"base_year": str(base_year), "years_used": years_used,
            "population": {"rows": int(len(actuals)),
                           "total": float(actuals["금액"].sum()) if len(actuals) else 0.0},
            "has_ltsa": benchmark.has_ltsa_detail(actuals), "rows": records(std)}


def benchmark_frames(conn, base_year):
    """3단계 입력·결과를 DataFrame 으로 — 엑셀 양식(6-7)이 화면과 같은 계산을 쓴다.
    반환 dict: std · actuals · years_used · grade · sites"""
    fs.bind_site_resolvers(conn, base_year)
    std, actuals, years_used, grade = _standard(conn, base_year)
    return {"std": std, "actuals": actuals, "years_used": years_used, "grade": grade,
            "sites": forecast_sites(conn, base_year)}


def forecast_frames(conn, base_year):
    """4단계 계산 결과(지사별 DataFrame, 연도 int 열)와 그 입력 — 화면(JSON)과 엑셀(양식) 둘이 같은 계산을 쓴다.
    반환 dict: tables · years · years_used · sites · grade · hq_master · budget_df · actuals"""
    fs.bind_site_resolvers(conn, base_year)
    by = int(base_year)
    years = forecast_calc.forecast_years(by)
    std, actuals, years_used, grade = _standard(conn, base_year)
    sites = forecast_sites(conn, base_year)
    budget_df = budget_plan_for(conn, base_year)
    hq_master = fs.load_hq_master(conn, base_year)
    tables = forecast_calc.compute_all_sites(
        sites, grade, std, fs.load_hot_parts(conn, base_year), hq_master,
        fs.load_hq_temp_projects(conn, base_year), fs.load_hq_ratio(conn, base_year),
        fs.load_factors(conn, base_year), fs.load_surprise_projects(conn, base_year),
        forecast_calc.investment_by_site(budget_df), budget_df, base_year=by, years=years)
    return {"tables": tables, "years": years, "years_used": years_used, "sites": sites, "grade": grade,
            "hq_master": hq_master, "budget_df": budget_df, "actuals": actuals}


def run_forecast(conn, base_year):
    """4단계 — 지사별 기준연도~+9년 표와 전사 합계(JSON 용)."""
    f = forecast_frames(conn, base_year)
    years, tables, sites = f["years"], f["tables"], f["sites"]
    years_used, grade, budget_df, actuals = f["years_used"], f["grade"], f["budget_df"], f["actuals"]

    def rows_of(df):
        return [{"예산과목": r["예산과목"], **{str(y): float(r[y]) for y in years}} for _, r in df.iterrows()]

    out_tables = {s: rows_of(t) for s, t in tables.items()}
    total = {}
    for rows in out_tables.values():
        for r in rows:
            acc = total.setdefault(r["예산과목"], {str(y): 0.0 for y in years})
            for y in years:
                acc[str(y)] += r[str(y)]
    return {"base_year": str(base_year), "years": years, "years_used": years_used, "sites": sites,
            "tables": out_tables,
            "total_rows": [{"예산과목": k, **v} for k, v in total.items()],
            "notes": {"budget_plan_missing": bool(budget_df.empty), "grade_empty": bool(grade.empty),
                      "actuals_empty": bool(actuals.empty)}}
