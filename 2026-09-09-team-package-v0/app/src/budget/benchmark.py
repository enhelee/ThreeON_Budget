# -*- coding: utf-8 -*-
"""예산 표준화(3단계) — 과년도 실적을 지사×예산과목×정비등급으로 통계 내어 표준금액을 만든다.

Phase 6-2. 전망 앱 v2 `standardization.py` 의 **계산부**를 그대로 옮긴 것이다.
함수 이름·인자·반환 형태를 v2 와 같게 두었고, v2 테스트 15개를 함께 옮겨
`tests/test_benchmark.py` 에서 돌린다 — «같은 계산»이 말이 아니라 실행으로 남는다.

옮기지 않은 것: 파일 IO(`load_*`/`save_*`)와 엑셀 import. 상태는 6-5 에서 DB 표로
가고, 엑셀 파서는 지사 표시명 매핑이 `dept_config` 로 바뀐 뒤에 옮긴다. 한 번에
둘을 바꾸면 깨졌을 때 어느 쪽 탓인지 모른다.

과목 집합과 별칭은 v2 의 `builtin_categories` 상수가 아니라 budget_app 구성에서 온다.
두 집합의 차이는 세 과목뿐이고(budget_app 에만 수선유지비-비저장품(보수자재)·
수선유지비-소모품(자재공기구), v2 에만 외주비-기타) **셋 다 실제 ERP 자료에 0건**이라
결과가 달라지지 않는다(실측 2026-09-19, zrfm2 43,840행 · 과목 15종). 별칭은 두 앱이 동일하다.
"""
import pandas as pd

from . import config_store, normalize

PROFIT_LOSS_ACCOUNTS = {x["과목"] for x in config_store.SEED_ITEMS["손익"]}
CAPITAL_ACCOUNTS = {x["과목"] for x in config_store.SEED_ITEMS["자본"]}
ALL_ACCOUNTS = PROFIT_LOSS_ACCOUNTS | CAPITAL_ACCOUNTS

METHOD_OPTIONS = ["등급별 평균", "최근실적", "3개년 평균", "5개년 평균"]
DEFAULT_METHOD = "등급별 평균"

# 자본 «기계장치» 중 정기(LTSA/CRI) 성격의 투자유형세부는 등급별 표준화에서 뺀다
# — 연도별 집행계획으로 따로 산정하기 때문이다(v2 표준화방향 시트).
LTSA_LIKE_DETAILS = {"LTSA", "CRI"}

CURRENT_YEAR_FALLBACK = 2025      # 정비등급 이력이 하나도 없을 때만 쓰는 기본값


def reference_year_for_undated(grade_history_df: pd.DataFrame) -> int:
    """연도 정보가 없는 테스트모드 업로드분(예: '투자유형 예측 테스트' 결과)에 붙일 '현재' 연도.
    정비등급 이력의 가장 최근 연도를 쓴다 - 임의의 값(예: 9999)을 쓰면 엑셀 양식의 실제 연도 칸과
    매칭이 안 돼 연도별 실적 표가 비어 보이는 문제가 있다. 표준화·중장기예산 테스트 모드가 공유해서 쓴다."""
    if grade_history_df.empty:
        return CURRENT_YEAR_FALLBACK
    return int(grade_history_df["연도"].max())


def get_method_dict(method_map: pd.DataFrame) -> dict:
    """{(사업장, 예산과목): 방식} 딕셔너리로 변환. 없는 조합은 호출측에서 DEFAULT_METHOD를 쓰면 된다."""
    if method_map.empty:
        return {}
    return {(r["사업장"], r["예산과목"]): r["방식"] for _, r in method_map.iterrows()}


def _apply_method(yearly: pd.Series, grade: str, grade_by_year: dict, method: str) -> tuple:
    """yearly: 연도(index)->금액. 반환: (표준금액, 비고)"""
    if yearly.empty:
        return 0.0, "실적없음"

    if method == "최근실적":
        latest_year = yearly.index.max()
        return float(yearly.loc[latest_year]), "최근실적"

    if method == "3개년 평균":
        recent = yearly.sort_index().iloc[-3:]
        return float(recent.mean()), "3개년 평균"

    if method == "5개년 평균":
        recent = yearly.sort_index().iloc[-5:]
        return float(recent.mean()), "5개년 평균"

    # 기본: 등급별 평균 - 이 등급이 적용된 연도만 평균, 없으면 전체 평균으로 대체
    matching_years = [y for y, g in grade_by_year.items() if g == grade and y in yearly.index]
    if matching_years:
        return float(yearly.loc[matching_years].mean()), "등급별 평균"
    return float(yearly.mean()), "등급별 평균(해당등급 실적없음 - 전체평균 대체)"


ETA_SQUARED_THRESHOLD = 0.3


CV_THRESHOLD = 0.15


def recommend_method(yearly: pd.Series, grade_by_year: dict) -> tuple:
    """항목별 실적 패턴(연도 수, 변동성, 등급별 편차)을 통계적으로 분석해 산출방식을 추천한다.
    사람이 미리 방식을 정해둔 항목이 아닐 때 기본값으로 쓰인다.

    - 등급별로 나눴을 때 그룹 간 평균 차이가 전체 분산의 상당 부분을 설명하면(η² 기준)
      '등급별 평균'을 추천한다 - 실제로 등급이 금액을 가르는 경우다.
    - 등급 차이가 뚜렷하지 않아도 연도별 변동이 작으면 '최근실적'으로 충분하다고 본다.
    - 등급도 안 갈리고 변동도 있으면, 데이터가 충분할 때(5개년 이상) '5개년 평균'으로
      완만화하고, 데이터가 적으면 '3개년 평균'을 추천한다.

    반환: (방식, 추천사유)
    """
    n_years = len(yearly)
    if n_years == 0:
        return DEFAULT_METHOD, "실적 없음"
    if n_years == 1:
        return "최근실적", "실적이 1개년뿐이라 그대로 사용"

    mean = yearly.mean()
    std = yearly.std(ddof=0)
    cv = (std / mean) if mean else 0.0

    groups = {}
    for year, amount in yearly.items():
        grade = grade_by_year.get(year)
        if grade is not None:
            groups.setdefault(grade, []).append(amount)
    multi_grade_groups = {g: v for g, v in groups.items() if v}

    eta_sq = None
    if len(multi_grade_groups) >= 2:
        ss_total = ((yearly - mean) ** 2).sum()
        if ss_total > 0:
            ss_between = sum(len(v) * (sum(v) / len(v) - mean) ** 2 for v in multi_grade_groups.values())
            eta_sq = ss_between / ss_total

    if eta_sq is not None and eta_sq >= ETA_SQUARED_THRESHOLD:
        return "등급별 평균", f"등급별 그룹 간 편차가 뚜렷함(설명력 {eta_sq*100:.0f}%) - 등급별로 나눠서 계산"

    if cv < CV_THRESHOLD:
        return "최근실적", f"연도별 변동이 작음(변동계수 {cv*100:.0f}%) - 최근실적만으로 충분"

    if n_years >= 5:
        return "5개년 평균", f"등급 차이는 뚜렷하지 않고 변동성이 있음(변동계수 {cv*100:.0f}%) - 5개년 평균으로 완만화"

    return "3개년 평균", f"데이터가 {n_years}개년뿐이고 변동성이 있음(변동계수 {cv*100:.0f}%) - 3개년 평균"


def get_current_grade(site: str, grade_history_df: pd.DataFrame):
    """해당 지사의 정비등급 이력 중 가장 최근 연도의 등급(없으면 None).
    연도 정보가 없는 데이터(예: '투자유형 예측 테스트' 업로드분)에 임시 등급을 붙일 때 쓴다."""
    site_hist = grade_history_df[grade_history_df["사업장"] == site]
    if site_hist.empty:
        return None
    latest_year = site_hist["연도"].max()
    return site_hist.loc[site_hist["연도"] == latest_year, "등급"].iloc[0]


def has_ltsa_detail(actuals_df: pd.DataFrame) -> bool:
    """'기계장치'에서 LTSA/CRI를 실제로 분리할 수 있는지(투자유형세부_확정 컬럼 존재 여부)."""
    return "투자유형세부_확정" in actuals_df.columns


def compute_standard_amounts(actuals_df: pd.DataFrame, grade_history_df: pd.DataFrame,
                              method_map: pd.DataFrame = None, overrides: pd.DataFrame = None,
                              item_alias: dict = None) -> pd.DataFrame:
    """
    actuals_df: 사업장, 연도, 예산과목, 금액 컬럼 필요. '투자유형세부_확정' 컬럼이 있으면
                기계장치 항목에서 LTSA/CRI 성격의 실적을 제외한 '기타기계장치'만 표준화 대상으로 삼는다.
    grade_history_df: 사업장, 연도, 등급 (load_grade_history()/import_grade_history_from_workbook() 결과)
    method_map에 사람이 지정한 방식이 없는 (사업장,예산과목)은 recommend_method()가 데이터 패턴을
    분석해 자동으로 방식을 고른다(방식출처="자동추천").
    반환: 사업장, 구분(손익/자본), 예산과목, 등급, 표준금액, 산출방식, 방식출처, 추천사유, 비고
    """
    result_cols = ["사업장", "구분", "예산과목", "등급", "표준금액", "산출방식", "방식출처", "추천사유", "비고"]
    if actuals_df.empty:
        return pd.DataFrame(columns=result_cols)

    alias = item_alias if item_alias is not None else config_store.seed_item_alias()
    df = actuals_df.copy()
    df["예산과목"] = df["예산과목"].apply(lambda v: normalize.normalize_item(v, alias))
    df = df[df["예산과목"].isin(ALL_ACCOUNTS)]

    if "투자유형세부_확정" in df.columns:
        machine_mask = df["예산과목"] == "기계장치"
        ltsa_mask = machine_mask & df["투자유형세부_확정"].isin(LTSA_LIKE_DETAILS)
        df = df[~ltsa_mask]
    # 컬럼이 없으면(정식 classified_*.csv 모드) '기계장치'를 LTSA/CRI 분리 없이 총액 그대로 쓴다.
    # 이 경우의 안내는 화면 쪽에서 한 번만 표시한다(has_ltsa_detail() 참고).

    method_dict = get_method_dict(method_map) if method_map is not None else {}
    override_dict = {}
    if overrides is not None and not overrides.empty:
        override_dict = {(r["사업장"], r["예산과목"], r["등급"]): r["표준금액"] for _, r in overrides.iterrows()}

    rows = []
    for (site, account), g in df.groupby(["사업장", "예산과목"]):
        category = "손익" if account in PROFIT_LOSS_ACCOUNTS else "자본"
        yearly = g.groupby("연도")["금액"].sum()

        site_grades = grade_history_df[grade_history_df["사업장"] == site]
        grade_by_year = dict(zip(site_grades["연도"], site_grades["등급"]))
        grades_present = sorted(set(grade_by_year.values())) or ["표준"]

        explicit_method = method_dict.get((site, account))
        if explicit_method:
            method, method_source, reco_reason = explicit_method, "사용자지정", ""
        else:
            method, reco_reason = recommend_method(yearly, grade_by_year)
            method_source = "자동추천"

        for grade in grades_present:
            amount, note = _apply_method(yearly, grade, grade_by_year, method)

            override_key = (site, account, grade)
            is_override = override_key in override_dict
            if is_override:
                amount = override_dict[override_key]
                note = "사용자가 직접 입력"

            rows.append({
                "사업장": site, "구분": category, "예산과목": account, "등급": grade,
                "표준금액": amount,
                "산출방식": "수동수정" if is_override else method,
                "방식출처": "수동수정" if is_override else method_source,
                "추천사유": reco_reason if (not is_override and method_source == "자동추천") else "",
                "비고": note,
            })

    return pd.DataFrame(rows, columns=result_cols) if rows else pd.DataFrame(columns=result_cols)
