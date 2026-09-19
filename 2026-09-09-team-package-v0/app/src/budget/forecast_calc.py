# -*- coding: utf-8 -*-
"""중장기 소요 전망(4단계) — 지사별 표준금액에 팩터를 복리로 곱해 2026~2035년 표를 만든다.

Phase 6-4. 전망 앱 v2 `longterm_forecast.py` 의 **계산부**를 그대로 옮긴 것이다.
6-2(`benchmark.py`)와 같은 방식으로, 함수 이름·인자·반환 형태를 v2 와 같게 두고
v2 테스트 18개를 함께 옮겨 `tests/test_forecast_calc.py` 에서 돌린다.

옮기지 않은 것: 파일 IO(`load_*`/`save_*`/`append_*`)와 엑셀 import. 상태는 6-5 에서
DB 표로 가고, 엑셀 파서는 지사 표시명 매핑이 `dept_config` 로 바뀐 뒤에 옮긴다.

지사 표시명·유형 해석은 v2 에서 `mapping_config` 가 CSV 를 읽어 하던 일이다. 여기서는
**모듈 수준 훅**으로 두어 기본은 항등이고, 6-5 에서 `dept_config` 기반 해석기를 끼운다.
숨은 파일 읽기를 계산 안에 남겨 두지 않기 위해서다.
"""
import re

import pandas as pd

from . import benchmark, config_store, normalize

# v2 는 builtin_categories 상수를 썼다. 과목 집합은 6-2 에서 budget_app 구성으로
# 통일했으므로 여기서도 같은 것을 본다 — 두 모듈이 어긋날 길을 만들지 않는다.
PROFIT_LOSS_ACCOUNTS = benchmark.PROFIT_LOSS_ACCOUNTS
CAPITAL_ACCOUNTS = benchmark.CAPITAL_ACCOUNTS


def normalize_account_name(name, item_alias=None):
    """예산과목 표기를 정식 명칭으로 통일. 별칭은 budget_app 것을 쓴다(6-2 참조)."""
    return normalize.normalize_item(
        name, item_alias if item_alias is not None else config_store.seed_item_alias())


def get_site_display_name(code):
    """사업장 코드 → 표시명. 기본은 항등이고 6-5 에서 dept_config 해석기로 바꾼다.

    v2 는 site_type_map.csv·dept_code_master.csv 를 읽어 풀었다. 그 파일 의존을
    계산 안에 그대로 들여오지 않으려고 훅으로 남긴다.
    """
    return str(code)


def get_current_site_type(site):
    """사업장 → 현재 지사유형. 기본은 «미매핑», 6-5 에서 dept_config 로 바꾼다."""
    return "미매핑"


FORECAST_YEARS = list(range(2026, 2036))


BASE_YEAR = 2026


INVESTMENT_ACCOUNTS = ["외주비-열원공사비", "외주비-열원기술용역비", "재료비-열원자재비", "외주비-기타"]


GT_GRADE_VALUES = {"MI", "TI", "CI", "간이", "HGPI", "BSI"}


ST_GRADE_VALUES = {"A", "B", "C"}


VALID_GRADE_TOKENS = GT_GRADE_VALUES | ST_GRADE_VALUES


SCHEDULE_PLACEHOLDER_TOKENS = {"", "-", "준공", "정비없음"}


HOT_PARTS_ITEM_TO_LABEL = {
    "고온부품재생": "기계장치_고온부품재생",
    "신품구매": "건설중인자산_재생고온부품",
}


HQ_CATEGORY_TO_ACCOUNT = {
    "경상정비": "수선유지비-열원경상정비",
    "정기유지보수": "수선유지비-열원정기유지보수",
    "정기점검": "수선유지비-열원정기점검",
    "지급수수료": "지급수수료-열원점검수수료",
    "열원보완": "수선유지비-열원보완및개선",
    "열원보완개선": "수선유지비-열원보완및개선",
    "비저장품(보수자재)": "비저장품(보수자재)",
    "소모품(자재공기구)": "소모품(자재공기구)",
    "건물구축물": "건물/구축물",
}


STANDARDIZED_ACCOUNT_TO_HQ_LABEL = {
    "수선유지비-건물/구축물": "건물/구축물",
}


SITE_TABLE_LINES = [
    ("수선유지비-건물/구축물", "표준화:수선유지비-건물/구축물"),
    ("수선유지비-열원정기점검", "표준화:수선유지비-열원정기점검"),
    ("수선유지비-열원경상정비", "표준화:수선유지비-열원경상정비"),
    ("수선유지비-열원정기유지보수", "표준화:수선유지비-열원정기유지보수"),
    ("수선유지비-열원보완및개선", "표준화:수선유지비-열원보완및개선"),
    ("지급수수료-열원점검수수료", "표준화:지급수수료-열원점검수수료"),
    ("건물/구축물", "본사배분:건물/구축물"),
    ("비저장품(보수자재)", "본사배분:비저장품(보수자재)"),
    ("소모품(자재공기구)", "본사배분:소모품(자재공기구)"),
    ("기계장치_고온부품재생", "고온부품:고온부품재생"),
    ("기계장치_기타기계장치", "표준화:기계장치"),
    ("외주비-열원정기점검", "표준화:외주비-열원정기점검"),
    ("공구와기구-열원시설공기구", "표준화:공구와기구-열원시설공기구"),
    ("건설중인자산_재생고온부품", "고온부품:신품구매"),
    ("건설중인자산-자산화예비품", "표준화:건설중인자산-자산화예비품"),
    ("저장품-열원(보수)", "표준화:저장품-열원(보수)"),
]


def forecast_years(base_year: int = BASE_YEAR) -> list:
    """기준연도부터 10개년. v2 의 FORECAST_YEARS(2026~2035)는 base_year=2026 인 경우다.

    6-6. 상태가 기준연도 축을 갖게 되었으니(6-5) 계산도 기준연도를 인자로 받는다.
    기본값을 2026 으로 두어 v2 승계 테스트는 그대로 돈다.
    """
    return list(range(int(base_year), int(base_year) + 10))


def year_multiplier(year: int, factors_df: pd.DataFrame, base_year: int = BASE_YEAR) -> float:
    """등록된 모든 활성 팩터의 (1+연간비율)을 (year-기준연도)년만큼 복리로 곱한 배수."""
    n = year - int(base_year)
    if n <= 0 or factors_df.empty:
        return 1.0
    active = factors_df[factors_df["활성"].astype(bool)] if "활성" in factors_df.columns else factors_df
    multiplier = 1.0
    for _, row in active.iterrows():
        multiplier *= (1 + float(row["연간비율"])) ** n
    return multiplier


def _classify_grade_row(values: dict) -> str | None:
    """연도->값 중 실제 등급 토큰만 보고 GT/ST 중 어디 어휘를 쓰는 행인지 판정. 없으면 None."""
    tokens = [str(v).strip() for v in values.values() if v not in (None, "")]
    if any(t in GT_GRADE_VALUES for t in tokens):
        return "GT"
    if any(t in ST_GRADE_VALUES for t in tokens):
        return "ST"
    return None


def investment_by_site(budget_df: pd.DataFrame) -> pd.DataFrame:
    """예산계획(budget_{year}.csv)에서 투자비 계정과목 합계를 지사별로 집계한다.
    반환: 사업장, 지사유형(본사 여부 판별용), 금액"""
    if budget_df.empty:
        return pd.DataFrame(columns=["사업장", "지사유형", "금액"])
    df = budget_df.copy()
    df["예산과목"] = df["예산과목"].apply(normalize_account_name)
    df = df[df["예산과목"].isin(INVESTMENT_ACCOUNTS)]
    if df.empty:
        return pd.DataFrame(columns=["사업장", "지사유형", "금액"])

    dept_col = "예산귀속 \n부서코드"
    df["사업장"] = df[dept_col].apply(get_site_display_name)
    df["지사유형"] = df["사업장"].apply(get_current_site_type)
    grouped = df.groupby(["사업장", "지사유형"])["연예산 합계"].sum().reset_index()
    return grouped.rename(columns={"연예산 합계": "금액"})


def budget_amount_by_site_account(budget_df: pd.DataFrame) -> dict:
    """예산계획(budget_{연도}.csv)에서 지사×예산과목별 당해년도 확정 금액을 뽑는다.
    표준화 대상 계정과목의 당해년도(BASE_YEAR) 금액은 표준화 계산값 대신 이 값을 쓴다.
    반환: {(사업장,예산과목): 금액}"""
    if budget_df.empty:
        return {}
    df = budget_df.copy()
    df["예산과목"] = df["예산과목"].apply(normalize_account_name)
    dept_col = "예산귀속 \n부서코드"
    df["사업장"] = df[dept_col].apply(get_site_display_name)
    grouped = df.groupby(["사업장", "예산과목"])["연예산 합계"].sum()
    return grouped.to_dict()


def _hq_row_account_label(major: str, minor: str) -> str | None:
    key = minor if major in ("기타본사", "미래개발원", "플랜트") else major
    return HQ_CATEGORY_TO_ACCOUNT.get(key)


HQ_MASTER_FIXED_COLS = ("대분류", "중분류", "세부내역")
# «26년예산»·«27년예산» — 기준연도 총액 열. v2 는 26년예산만 제외했는데 기준연도가
# 파라미터가 되면(6-5) 열 이름도 해마다 바뀌므로 패턴으로 본다. 그대로면 27년예산이
# 지사로 잡혀 본사 배분 합계가 두 배가 된다.
_HQ_BUDGET_COL = re.compile(r"^\d{2,4}년\s*예산$")


def is_hq_master_site_col(col) -> bool:
    """마스터 넓은 표의 열이 지사 열인가(고정 열·기준연도 예산 열이 아닌가)."""
    c = str(col).strip()
    return c not in HQ_MASTER_FIXED_COLS and not _HQ_BUDGET_COL.match(c)


def hq_amount_by_site_account(hq_master_df: pd.DataFrame) -> dict:
    """{(사업장, 예산과목라벨): 금액} - 마스터 표를 계정과목 라벨 기준으로 합산."""
    result = {}
    if hq_master_df.empty:
        return result
    site_cols = [c for c in hq_master_df.columns if is_hq_master_site_col(c)]
    for _, row in hq_master_df.iterrows():
        label = _hq_row_account_label(row.get("대분류", ""), row.get("중분류", ""))
        if label is None:
            continue
        for site in site_cols:
            amount = row.get(site) or 0
            key = (site, label)
            result[key] = result.get(key, 0) + float(amount)
    return result


def allocate_hq_temp_projects(hq_temp_df: pd.DataFrame, hq_ratio_df: pd.DataFrame) -> pd.DataFrame:
    """본사 일시적 사업을 계약체결금액 비율로 지사에 배분한다. 반환: 사업장,연도,예산과목,금액"""
    cols = ["사업장", "연도", "예산과목", "금액"]
    if hq_temp_df.empty or hq_ratio_df.empty:
        return pd.DataFrame(columns=cols)
    total = hq_ratio_df["계약체결금액"].sum()
    if not total:
        return pd.DataFrame(columns=cols)
    ratio = hq_ratio_df.set_index("사업장")["계약체결금액"] / total

    rows = []
    for _, proj in hq_temp_df.iterrows():
        for site, r in ratio.items():
            rows.append({
                "사업장": site, "연도": int(proj["연도"]), "예산과목": proj["예산과목"],
                "금액": float(proj["금액"]) * r,
            })
    return pd.DataFrame(rows, columns=cols)


def _standard_lookup(standard_df: pd.DataFrame) -> dict:
    """{(사업장,예산과목,등급): 표준금액}"""
    if standard_df.empty:
        return {}
    return {(r["사업장"], r["예산과목"], r["등급"]): r["표준금액"] for _, r in standard_df.iterrows()}


def compute_site_table(site: str, grade_hist: pd.DataFrame, standard_df: pd.DataFrame,
                        hot_parts_df: pd.DataFrame, hq_amount_by_site_acct: dict,
                        hq_temp_alloc: pd.DataFrame, factors_df: pd.DataFrame,
                        surprise_df: pd.DataFrame, investment_df: pd.DataFrame,
                        budget_lookup: dict = None, base_year: int = BASE_YEAR,
                        years: list = None) -> pd.DataFrame:
    """한 지사의 기준연도~+9년 예산과목별 금액 표. 반환: 라벨(행) × 연도(열)

    표준화 대상 계정과목(SITE_TABLE_LINES의 "표준화:" 항목)의 당해년도(BASE_YEAR) 금액은
    "지사 자체 몫 + 본사 원가분배 몫"의 합이다("총원가배분(전체) = 본사 + 지사" 원본 양식과 동일한
    구조). 지사 자체 몫은 예산계획(budget_lookup) 확정 금액이 있으면 그 값, 없으면 표준화 금액이다.
    본사 원가분배 몫은 경상정비/정기유지보수/정기점검/지급수수료/열원보완및개선처럼
    HQ_CATEGORY_TO_ACCOUNT에 있는 계정만 값이 있고(hq_amount_by_site_acct), 나머지 계정은 0이라
    그대로 더해도 무해하다. 다음년도부터는 종전대로 표준화 금액에 팩터를 복리로 곱해 예측한다."""
    base_year = int(base_year)
    years = list(years) if years else forecast_years(base_year)
    site_grades = grade_hist[grade_hist["사업장"] == site]
    grade_by_year = dict(zip(site_grades["연도"], site_grades["등급"]))
    latest_known_grade = benchmark.get_current_grade(site, grade_hist)

    std_lookup = _standard_lookup(standard_df)
    budget_lookup = budget_lookup or {}
    hot_parts_lookup = {
        (r["사업장"], r["연도"], r["항목"]): r["금액"] for _, r in hot_parts_df.iterrows()
    } if not hot_parts_df.empty else {}

    hq_temp_lookup = {}
    if hq_temp_alloc is not None and not hq_temp_alloc.empty:
        for _, r in hq_temp_alloc[hq_temp_alloc["사업장"] == site].iterrows():
            key = (r["연도"], r["예산과목"])
            hq_temp_lookup[key] = hq_temp_lookup.get(key, 0) + r["금액"]

    surprise_lookup = {}
    if not surprise_df.empty:
        for _, r in surprise_df[surprise_df["사업장"] == site].iterrows():
            key = (int(r["연도"]), r["예산과목"])
            surprise_lookup[key] = surprise_lookup.get(key, 0) + r["금액"]

    rows = []
    for label, source in SITE_TABLE_LINES:
        row = {"예산과목": label}
        base_multiplier_year_values = {}
        for year in years:
            mult = year_multiplier(year, factors_df, base_year)
            grade = grade_by_year.get(year, latest_known_grade)

            if source.startswith("표준화:"):
                account = source.split(":", 1)[1]
                budget_amount = budget_lookup.get((site, account)) if year == base_year else None
                if budget_amount is not None:
                    site_amount = budget_amount
                else:
                    # 등급 이력이 없는 지사는 benchmark 가 등급을 «표준» 으로 두고 표를 만든다.
                    # v2 는 지사 목록이 등급 이력에서 나와 이 경로가 없었지만, 여기서는 지사가
                    # dept_config 에서 오므로 등급 없는 지사가 정상 입력이다 — 그때 0 이 되면
                    # 기준연도 이후 10년이 통째로 비어 보인다(6-6 실측).
                    base = std_lookup.get((site, account, grade)) if grade else None
                    if base is None:
                        base = std_lookup.get((site, account, "표준"), 0.0)
                    site_amount = base * mult
                # 26년은 지사 자체 예산(예산계획/표준화)에 본사 원가분배 마스터 표의 배분액을 더한다 -
                # "총원가배분(전체) = 본사 + 지사"라 두 금액은 서로 다른 부서코드에 잡힌 별도 예산이며
                # 합쳐야 그 지사의 26년 총액이 된다(경상정비/정기유지보수/정기점검/지급수수료/
                # 열원보완및개선처럼 HQ_CATEGORY_TO_ACCOUNT에 없는 계정은 본사 배분이 0이라 그대로 더해도 무해).
                hq_lookup_account = STANDARDIZED_ACCOUNT_TO_HQ_LABEL.get(account, account)
                hq_part = hq_amount_by_site_acct.get((site, hq_lookup_account), 0.0) if year == base_year else 0.0
                amount = site_amount + hq_part
            elif source.startswith("고온부품:"):
                item = source.split(":", 1)[1]
                amount = hot_parts_lookup.get((site, year, item), 0.0)
            elif source.startswith("본사배분:"):
                account = source.split(":", 1)[1]
                amount = hq_amount_by_site_acct.get((site, account), 0.0) * mult
            else:
                amount = 0.0

            amount += hq_temp_lookup.get((year, label), 0.0)
            amount += surprise_lookup.get((year, label), 0.0)
            row[year] = amount
            base_multiplier_year_values[year] = amount
        rows.append(row)

    site_investment = investment_df[investment_df["사업장"] == site]["금액"].sum() if not investment_df.empty else 0.0
    invest_row = {"예산과목": "투자비"}
    for year in years:
        invest_row[year] = site_investment * year_multiplier(year, factors_df, base_year)
    rows.append(invest_row)

    return pd.DataFrame(rows)


def compute_all_sites(sites: list, grade_hist: pd.DataFrame, standard_df: pd.DataFrame,
                       hot_parts_df: pd.DataFrame, hq_master_df: pd.DataFrame,
                       hq_temp_df: pd.DataFrame, hq_ratio_df: pd.DataFrame,
                       factors_df: pd.DataFrame, surprise_df: pd.DataFrame,
                       investment_df: pd.DataFrame, budget_df: pd.DataFrame = None,
                       base_year: int = BASE_YEAR, years: list = None) -> dict:
    """지사별 표를 한 번에 계산. 반환: {사업장: DataFrame}"""
    hq_amount = hq_amount_by_site_account(hq_master_df)
    hq_temp_alloc = allocate_hq_temp_projects(hq_temp_df, hq_ratio_df)
    budget_lookup = budget_amount_by_site_account(budget_df) if budget_df is not None else {}
    return {
        site: compute_site_table(site, grade_hist, standard_df, hot_parts_df, hq_amount,
                                  hq_temp_alloc, factors_df, surprise_df, investment_df, budget_lookup,
                                  base_year=base_year, years=years)
        for site in sites
    }
