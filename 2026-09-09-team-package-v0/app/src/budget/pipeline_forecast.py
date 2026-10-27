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

from . import benchmark, config_store, forecast_calc, matching, normalize
from . import db as dbm
from . import forecast_store as fs

KEEP = ("계획집행", "신규", "신규(소액집행)")
ACTUAL_COLS = ["사업장", "연도", "예산과목", "금액"]
# v2 예산계획의 열 이름 — 계산부(forecast_calc.investment_by_site 등)가 이 리터럴을 본다.
DEPT_COL = "예산귀속 \n부서코드"
AMOUNT_COL = "연예산 합계"
BUDGET_COLS = ["예산과목", DEPT_COL, AMOUNT_COL]


# ---------------------------------------------------------------- 입력
def _run_lines(conn, run_id):
    """한 실행의 사업 단위 실적 (처지사, 예산과목, 사업명, 금액, 구분).

    본사 배정·지사 집행 과목(경상정비)은 biz_line 이 아니라 전표(match_line)에서 다시 모은다 —
    매칭이 그 실적을 본사 계획행에 붙여도(matching.HQ_ALLOC_ITEMS) 전망은 지사별 실적이
    필요하기 때문이다. 전표의 처지사는 지사 그대로라 옛 실행(전부 지사 «신규»)과 새 실행이
    같은 모양으로 나온다.
    """
    alloc = set(matching.HQ_ALLOC_ITEMS)
    if alloc:
        marks = ",".join("?" * len(alloc))
        # 전표 행이 없는 실행(테스트·옛 DB)은 biz_line 그대로 쓴다.
        if not conn.execute(f"SELECT 1 FROM match_line WHERE run_id=? AND 과목정규 IN ({marks}) LIMIT 1",
                            (run_id, *alloc)).fetchone():
            alloc = set()
    for dept, item, name, amt, gubun in conn.execute(
            "SELECT 처지사,예산과목,사업명,실적금액,구분 FROM biz_line WHERE run_id=?", (run_id,)):
        if item not in alloc:
            yield dept, item, name, amt, gubun
    if not alloc:
        return
    for dept, item, name, gubun, amt in conn.execute(
            "SELECT m.처지사정규, m.과목정규, m.매칭사업명, m.구분, SUM(e.금액천원)"
            " FROM match_line m JOIN erp_row e ON e.id = m.erp_row_id"
            f" WHERE m.run_id=? AND m.과목정규 IN ({marks}) AND m.구분 IN ('계획집행','신규')"
            " GROUP BY m.처지사정규, m.과목정규, m.매칭사업명, m.구분", (run_id, *alloc)):
        name = str(name or "")
        if name.startswith("[신규] "):
            name = name[len("[신규] "):]
        yield dept, item, name, amt, gubun


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
            for dept, item, _name, amt, gubun in _run_lines(conn, run["id"]):
                if gubun in KEEP and amt:
                    rows.append({"사업장": dept, "연도": int(year), "예산과목": item, "금액": float(amt)})
        if used:
            years_used.append(str(year))
    return pd.DataFrame(rows, columns=ACTUAL_COLS), years_used


DETAIL_COLS = ["사업장", "연도", "예산과목", "사업명", "금액", "유형", "유형출처"]


def locked_actuals_detail(conn, base_year):
    """마감 실적을 사업 단위로 — 정기비용 성격(«유형»)을 붙인다(표준화 방향 1·4-4).

    유형은 사람이 고친 값(actual_tag, 기준연도 축)이 먼저고, 없으면 사업명 키워드
    (`benchmark.regular_type`)로 판정한다. 기계장치의 고온부품재생·LTSA·CRI 와
    정기유지보수의 LTSA 는 표준화에서 빠지고 연도별 계획(고온부품·정기계약·CRI)으로 잡힌다.
    """
    alias = config_store.load_item_alias(conn)
    tags = fs.load_table(conn, base_year, "actual_tag")
    tag = {(r["사업장"], int(r["연도"]), r["예산과목"], r["사업명"]): r["유형"] for _, r in tags.iterrows()}
    years_used, rows = [], []
    for year in sorted(dbm.locked_years(conn)):
        used = False
        for budget in ("손익", "자본"):
            run = dbm.latest_run(conn, year, budget)
            if not run:
                continue
            used = True
            for dept, item, name, amt, gubun in _run_lines(conn, run["id"]):
                if gubun not in KEEP or not amt:
                    continue
                acct = normalize.normalize_item(item, alias)
                key = (dept, int(year), acct, name or "")
                if key in tag:
                    kind, src = tag[key], "수동"
                else:
                    kind, src = benchmark.regular_type(acct, name), "자동"
                rows.append({"사업장": dept, "연도": int(year), "예산과목": acct, "사업명": name or "",
                             "금액": float(amt), "유형": kind, "유형출처": src})
        if used:
            years_used.append(str(year))
    return pd.DataFrame(rows, columns=DETAIL_COLS), years_used


def regular_breakdown(conn, base_year):
    """정기비용 분리 현황 — 기계장치·정기유지보수 실적을 지사×연도×유형으로, 그리고 판정한 사업 목록."""
    fs.bind_site_resolvers(conn, base_year)
    detail, years_used = locked_actuals_detail(conn, base_year)
    d = detail[detail["예산과목"].isin(list(benchmark.REGULAR_EXCLUDED))] if not detail.empty else detail
    summary = []
    if not d.empty:
        piv = d.groupby(["사업장", "연도", "예산과목", "유형"])["금액"].sum().reset_index()
        for (site, year, acct), g in piv.groupby(["사업장", "연도", "예산과목"]):
            row = {"사업장": site, "연도": int(year), "예산과목": acct, "총액": float(g["금액"].sum())}
            for t in fs.TAG_TYPES:
                row[t] = float(g.loc[g["유형"] == t, "금액"].sum())
            summary.append(row)
    projects = d.groupby(["사업장", "연도", "예산과목", "사업명", "유형", "유형출처"])["금액"].sum()         .reset_index().sort_values(["사업장", "연도", "예산과목", "금액"], ascending=[True, True, True, False])         if not d.empty else d
    return {"years_used": years_used, "summary": summary, "projects": records(projects)}


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


def default_base_year(conn, existing=None):
    """상태가 있는 최신 기준연도 → 없으면 마감 최신연도+1 → 그것도 없으면 v2 기본(2026).
    existing: 이미 읽은 fs.list_base_years 결과(같은 요청에서 두 번 읽지 않게)."""
    if existing is None:
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
def actuals_with_reference(conn, base_year):
    """마감 실적 + 참고 엑셀 실적(마감되지 않은 연도만). 앱에 마감 연도가 2~3개뿐이어도
    엑셀이 가진 10년 이력으로 «5개년 평균»·«등급별 최근실적»이 엑셀과 같은 모집단을 쓴다.
    같은 연도는 마감 실적이 이긴다 — 마감 = 대외 보고 확정값."""
    actuals, years_used = locked_actuals_detail(conn, base_year)
    ref = fs.load_table(conn, base_year, "reference_actual")
    if ref.empty:
        return actuals, years_used, []
    locked = {int(y) for y in years_used}
    ref = ref[~ref["연도"].isin(locked) & (ref["금액"] != 0)].copy()
    if ref.empty:
        return actuals, years_used, []
    ref["사업명"] = ""
    ref["유형출처"] = "참고엑셀"
    merged = pd.concat([actuals, ref[DETAIL_COLS]], ignore_index=True)
    return merged, years_used, sorted({str(y) for y in ref["연도"]})


def _standard(conn, base_year):
    actuals, years_used, ref_years = actuals_with_reference(conn, base_year)
    years_used = years_used + [f"{y}(참고)" for y in ref_years]
    window = fs.learning_window(conn, base_year)
    grade = fs.load_grade_history(conn, base_year)
    budget_lookup = forecast_calc.budget_amount_by_site_account(budget_plan_for(conn, base_year))
    std = benchmark.compute_standard_amounts(
        actuals, grade, fs.load_method_map(conn, base_year), fs.load_overrides(conn, base_year),
        item_alias=config_store.load_item_alias(conn), rules=fs.load_table(conn, base_year, "benchmark_rule"),
        events=fs.load_table(conn, base_year, "site_event"), budget_lookup=budget_lookup, window=window)
    return std, actuals, years_used, grade


def finance_compare(std, fin):
    """앱 표준금액 옆에 재무팀(참고 엑셀) 표준금액·대비(앱÷재무팀−1). 같은 등급이 없으면 그 칸 평균(제안 ⑥)."""
    std = std.copy()
    exact, mean = {}, {}
    if not fin.empty:
        exact = {(r["사업장"], r["예산과목"], r["등급"]): float(r["표준금액"]) for _, r in fin.iterrows()}
        mean = fin.groupby(["사업장", "예산과목"])["표준금액"].mean().to_dict()
    vals = [exact.get((r["사업장"], r["예산과목"], r["등급"]), mean.get((r["사업장"], r["예산과목"])))
            for _, r in std.iterrows()]
    std["재무팀금액"] = vals
    std["재무팀대비"] = [(float(a) / f - 1.0) if f else None for a, f in zip(std["표준금액"], vals)]
    return std


def overhaul_plan(conn, base_year, sites, actuals):
    """A급정비 일정(제안 ②). 설비별 등급 + 대표 정비등급(미래 일정 포함)을 한 지사의 «설비 줄»들로 본다.
    **기준연도 뒤 등급이 하나라도 있는 지사만** 일정으로 계산한다 — 설비별 등급은 과거뿐이라, 미래 일정
    없이 규칙을 걸면 그 지사 A급정비가 10년 내내 0 이 된다. 해당 지사가 없으면 None(표준금액 그대로)."""
    units = fs.load_table(conn, base_year, "site_grade_eq")
    grade = fs.load_grade_history(conn, base_year)
    groups = site_groups(conn, base_year)
    # DH 묶음 지사의 등급 줄(A/B/C)은 A급정비가 아니다 — 설비 줄의 «DH» 제외와 같은 이유.
    grade = grade[grade["사업장"].map(groups).fillna("") != "DH"] if not grade.empty else grade
    if not grade.empty:
        units = pd.concat([units, grade.assign(설비="정비등급 이력")[["사업장", "연도", "설비", "등급"]]],
                          ignore_index=True)
    if units.empty:
        return None
    future = set(units[units["연도"] > int(base_year)]["사업장"])
    scheduled = [s for s in sites if s in future]
    if not scheduled:
        return None
    amounts = forecast_calc.overhaul_amounts(actuals, sites, groups)
    return {"years": {s: forecast_calc.overhaul_years(units, s) for s in scheduled}, "amount": amounts}


def forecast_ranges(actuals, sites, years, base_year, factors, window):
    """칸별 예측 범위(제안 ⑤) — 학습 기간 안 그 지사·과목의 연 실적 최소~최대 × 팩터.
    기준연도(계획본)와 표준화 아닌 줄(고온부품·정기계약·CRI·본사배분·투자비·A급정비 일정)은 범위가 없다."""
    a = benchmark.recent_window(benchmark.drop_regular(actuals), window)
    if a.empty:
        return {}
    yearly = a.groupby(["사업장", "예산과목", "연도"])["금액"].sum()
    lohi = yearly.groupby(level=[0, 1]).agg(["min", "max"])
    std_lines = {label: src.split(":", 1)[1] for label, src in forecast_calc.SITE_TABLE_LINES
                 if src.startswith("표준화:") and label != forecast_calc.A_OVERHAUL_ACCOUNT}
    acct_of = {"기계장치_기타기계장치": "기계장치"}
    out = {}
    for site in sites:
        rng = {}
        for label, acct in std_lines.items():
            acct = acct_of.get(label, acct)
            if (site, acct) not in lohi.index:
                continue
            lo, hi = lohi.loc[(site, acct)]
            scope = forecast_calc.line_scope(label)
            rng[label] = {str(y): [float(lo) * forecast_calc.year_multiplier(y, factors, base_year, scope),
                                   float(hi) * forecast_calc.year_multiplier(y, factors, base_year, scope)]
                          for y in years if y != int(base_year)}
        if rng:
            out[site] = rng
    return out


def compare_reference(conn, base_year):
    """참고 엑셀과 대조 — ① 마감 연도 실적(지사×연도×예산과목) ② 표준금액(지사×예산과목×등급)."""
    fs.bind_site_resolvers(conn, base_year)
    ref_act = fs.load_table(conn, base_year, "reference_actual")
    ref_std = fs.load_table(conn, base_year, "reference_standard")
    detail, years_used = locked_actuals_detail(conn, base_year)
    actual_rows = []
    if not ref_act.empty and years_used:
        locked = [int(y) for y in years_used]
        a = detail.groupby(["사업장", "연도", "예산과목"])["금액"].sum() if not detail.empty else pd.Series(dtype=float)
        r = ref_act[ref_act["연도"].isin(locked)].groupby(["사업장", "연도", "예산과목"])["금액"].sum()
        keys = sorted(set(a.index) | set(r.index))
        for k in keys:
            av, rv = float(a.get(k, 0.0)), float(r.get(k, 0.0))
            actual_rows.append({"사업장": k[0], "연도": int(k[1]), "예산과목": k[2], "앱": av, "엑셀": rv,
                                "차이": av - rv})
    std_rows = []
    if not ref_std.empty:
        std = _standard(conn, base_year)[0]
        app = {(x["사업장"], x["예산과목"], x["등급"]): x for _, x in std.iterrows()} if not std.empty else {}
        for _, x in ref_std.iterrows():
            k = (x["사업장"], x["예산과목"], x["등급"])
            mine = app.get(k)
            av = float(mine["표준금액"]) if mine is not None else None
            std_rows.append({"사업장": k[0], "예산과목": k[1], "등급": k[2], "앱": av, "엑셀": float(x["표준금액"]),
                             "차이": None if av is None else av - float(x["표준금액"]),
                             "산출방식": mine["산출방식"] if mine is not None else "", "근거": mine["근거"] if mine is not None else "",
                             "엑셀수식": x["엑셀수식"]})
    def summary(rows):
        n = len(rows)
        same = sum(1 for r in rows if r["차이"] is not None and abs(r["차이"]) < 1)
        return {"rows": n, "same": same, "app_total": sum(r["앱"] or 0 for r in rows),
                "excel_total": sum(r["엑셀"] for r in rows)}
    return {"base_year": str(base_year), "locked_years": years_used,
            "actual": {"summary": summary(actual_rows), "rows": actual_rows},
            "standard": {"summary": summary(std_rows), "rows": std_rows}}


def run_benchmark(conn, base_year):
    """3단계 — 표준금액 표와 모집단 요약."""
    fs.bind_site_resolvers(conn, base_year)
    std, actuals, years_used, _ = _standard(conn, base_year)
    std = finance_compare(std, fs.load_table(conn, base_year, "reference_standard"))
    if not std.empty:
        std = std.sort_values(["사업장", "구분", "예산과목", "등급"]).reset_index(drop=True)
    return {"base_year": str(base_year), "years_used": years_used, "window": fs.learning_window(conn, base_year),
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


def forecast_inputs(conn, base_year):
    """4단계 계산의 입력 한 벌(DB 에서 읽기만) — 시나리오 비교가 한 번 읽고 여러 번 계산하려고 나눴다."""
    fs.bind_site_resolvers(conn, base_year)
    std, actuals, years_used, grade = _standard(conn, base_year)
    sites = forecast_sites(conn, base_year)
    budget_df = budget_plan_for(conn, base_year)
    return {"base_year": int(base_year), "years": forecast_calc.forecast_years(int(base_year)),
            "std": std, "actuals": actuals, "years_used": years_used, "grade": grade, "sites": sites,
            "budget_df": budget_df, "hq_master": fs.load_hq_master(conn, base_year),
            "overhaul": overhaul_plan(conn, base_year, sites, actuals),
            "hot_parts": fs.load_hot_parts(conn, base_year), "hq_temp": fs.load_hq_temp_projects(conn, base_year),
            "hq_ratio": fs.load_hq_ratio(conn, base_year), "factors": fs.load_factors(conn, base_year),
            "surprise": fs.load_surprise_projects(conn, base_year),
            "contracts": fs.load_table(conn, base_year, "regular_contract"),
            "cri_rules": fs.load_table(conn, base_year, "cri_rule"),
            "invest_plan": fs.load_table(conn, base_year, "investment_plan"),
            "window": fs.learning_window(conn, base_year)}


def scenario_inputs(inp, price=0.0, volume=0.0):
    """시나리오 = 저장된 가정 위에 손잡이 둘을 얹은 입력(저장된 가정은 바꾸지 않는다).

    price   물가 연 %p 가감 — 활성 팩터는 그대로 두고 «시나리오 물가 조정» 팩터(전체)를 하나 더 건다.
            배수가 (1+기존)(1+가감) 이라 기존 팩터가 손익·자본으로 나뉘어 있어도 둘 다 같은 폭으로 움직인다.
    volume  물량 % — 표준금액(표준화 대상 과목)과 A급정비 1회 금액에 (1+volume/100) 을 곱한다.
            기준연도 계획본·정기계약·고온부품·본사배분·투자계획처럼 «정해진 금액»은 건드리지 않는다.
    """
    out = dict(inp)
    if price:
        f = inp["factors"]
        row = {"팩터명": "시나리오 물가 조정", "연간비율": float(price) / 100.0, "활성": True, "적용구분": "전체"}
        out["factors"] = pd.concat([f, pd.DataFrame([row])], ignore_index=True) if not f.empty \
            else pd.DataFrame([row])
    if volume:
        k = 1 + float(volume) / 100.0
        if not inp["std"].empty:
            out["std"] = inp["std"].assign(표준금액=inp["std"]["표준금액"] * k)
        if inp["overhaul"]:
            out["overhaul"] = {**inp["overhaul"],
                               "amount": {s: v * k for s, v in inp["overhaul"]["amount"].items()}}
    return out


def compute_tables(inp):
    """입력 한 벌 → 지사별 10개년 표 + CRI 일정."""
    tables = forecast_calc.compute_all_sites(
        inp["sites"], inp["grade"], inp["std"], inp["hot_parts"], inp["hq_master"],
        inp["hq_temp"], inp["hq_ratio"], inp["factors"], inp["surprise"],
        forecast_calc.investment_by_site(inp["budget_df"]), inp["budget_df"],
        base_year=inp["base_year"], years=inp["years"], contracts_df=inp["contracts"],
        cri_rules=inp["cri_rules"], invest_plan_df=inp["invest_plan"], overhaul=inp["overhaul"])
    cri = forecast_calc.cri_events(inp["grade"], inp["cri_rules"], inp["factors"], inp["years"])
    return tables, cri


def forecast_frames(conn, base_year):
    """4단계 계산 결과(지사별 DataFrame, 연도 int 열)와 그 입력 — 화면(JSON)과 엑셀(양식) 둘이 같은 계산을 쓴다.
    반환 dict: tables · years · years_used · sites · grade · hq_master · budget_df · actuals"""
    inp = forecast_inputs(conn, base_year)
    tables, cri = compute_tables(inp)
    return {"tables": tables, "years": inp["years"], "years_used": inp["years_used"], "sites": inp["sites"],
            "grade": inp["grade"], "hq_master": inp["hq_master"], "budget_df": inp["budget_df"],
            "actuals": inp["actuals"], "cri": cri, "factors": inp["factors"], "overhaul": inp["overhaul"],
            "window": inp["window"]}


# ── 시나리오 비교(2026-10-27, 경진대회 C) ─────────────────────────────────
# 10개년 전망이 가정 한 벌로만 보이면 «전망을 믿을 수 있나»에 답이 «오차 25~36%»뿐이다. 가정 2~3벌을
# 나란히 놓으면 질문이 «어떤 가정이 얼마를 움직이나»로 바뀐다(Pigment 식 side-by-side).
DEFAULT_SCENARIOS = [{"name": "기준(현재 가정)", "price": 0.0, "volume": 0.0},
                     {"name": "보수(물가↑·물량↑)", "price": 1.0, "volume": 10.0},
                     {"name": "절감(물가↓·물량↓)", "price": -0.5, "volume": -10.0}]
SCENARIO_MAX = 3
PRICE_LIM, VOLUME_LIM = 10.0, 50.0           # 손잡이 범위(연 %p · %) — 오타로 터무니없는 값이 들어오지 않게


def _site_year_totals(tables, years):
    return {s: {str(y): float(t[y].sum()) for y in years} for s, t in tables.items()}


def run_scenarios(conn, base_year, specs=None):
    """시나리오마다 전사·지사 연도별 합계. 첫 시나리오가 비교 기준이다.

    반환: years · sites · scenarios[{name, price, volume, total{연도}, sum10, by_site{지사{연도}}}]
          · band{연도: [하한, 상한]} — 첫 시나리오 합계에 «학습 기간 실적 범위»(전망 표의 예측 범위)를 더한 띠
    """
    specs = (specs or DEFAULT_SCENARIOS)[:SCENARIO_MAX]
    inp = forecast_inputs(conn, base_year)
    years = inp["years"]
    out = []
    first_tables = None
    for sp in specs:
        price = max(-PRICE_LIM, min(PRICE_LIM, float(sp.get("price") or 0)))
        volume = max(-VOLUME_LIM, min(VOLUME_LIM, float(sp.get("volume") or 0)))
        tables, _ = compute_tables(scenario_inputs(inp, price, volume))
        if first_tables is None:
            first_tables = tables
        by_site = _site_year_totals(tables, years)
        total = {str(y): sum(v[str(y)] for v in by_site.values()) for y in years}
        out.append({"name": str(sp.get("name") or f"시나리오 {len(out) + 1}")[:20], "price": price,
                    "volume": volume, "total": total, "sum10": sum(total.values()), "by_site": by_site})
    # 예측 범위 띠 — 범위가 있는 칸(표준화 과목)만 그 칸 값 대신 하한·상한을 넣은 합계
    ranges = forecast_ranges(inp["actuals"], inp["sites"], years, inp["base_year"],
                             scenario_inputs(inp, specs[0].get("price") or 0)["factors"], inp["window"])
    base_total = out[0]["total"] if out else {}
    band = {}
    for y in years:
        lo = hi = base_total.get(str(y), 0.0)
        for site, rng in ranges.items():
            t = first_tables.get(site)
            if t is None:
                continue
            for label, by_year in rng.items():
                cell = by_year.get(str(y))
                if not cell:
                    continue
                v = float(t.loc[t["예산과목"] == label, y].sum())
                lo += cell[0] - v
                hi += cell[1] - v
        band[str(y)] = [min(lo, hi), max(lo, hi)]
    return {"base_year": str(base_year), "years": years, "sites": inp["sites"], "scenarios": out, "band": band,
            "notes": {"budget_plan_missing": bool(inp["budget_df"].empty),
                      "actuals_empty": bool(inp["actuals"].empty)}}


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
            "tables": out_tables, "cri_events": records(f["cri"]),
            "ranges": forecast_ranges(actuals, sites, years, int(base_year), f["factors"], f["window"]),
            "overhaul_years": {s: sorted(v) for s, v in (f["overhaul"] or {}).get("years", {}).items()},
            "total_rows": [{"예산과목": k, **v} for k, v in total.items()],
            "notes": {"budget_plan_missing": bool(budget_df.empty), "grade_empty": bool(grade.empty),
                      "actuals_empty": bool(actuals.empty)}}
