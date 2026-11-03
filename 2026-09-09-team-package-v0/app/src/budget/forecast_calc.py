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


# 같은 정비등급의 다른 이름 → 계산에 쓰는 이름(2026-11-03 팀장: TI = HGPI).
#   저장된 입력(등급 이력·규칙·수동수정·참고 엑셀)은 사람이 적은 그대로 두고, 계산 직전에만 바꿔 읽는다
#   (pipeline_forecast._standard 등). 화면은 «HGPI/TI» 로 묶어 보인다(web views/forecast.js SAME_GRADES).
SAME_GRADE = {"TI": "HGPI"}
_SAME_GRADE_RE = re.compile(r"(?<![0-9A-Za-z])(" + "|".join(map(re.escape, SAME_GRADE)) + r")(?![0-9A-Za-z])")


def canon_grade(value):
    """등급 문자열의 TI 토큰을 HGPI 로 — «MI/TI»·«TI,CI» 같은 묶음 표기도 토큰 단위로. 문자열이 아니면 그대로."""
    if not isinstance(value, str):
        return value
    return _SAME_GRADE_RE.sub(lambda m: SAME_GRADE[m.group(1)], value)


# 표준금액을 만들지 않는 등급 · 그 등급이 있는 지사(2026-11-03 팀장).
#   BSI = 일시적인 등급(2020년 한 번) — 표준금액이 필요 없다.
#   CI = 이 지사들만 CI 정비를 한다(삼송은 2031 일정에 CI 가 있어 남김). 다른 지사의 CI 줄은 지운다.
#   ⚠ 지사 이름을 코드에 둔 임시 기준 — 지사 구성이 바뀌면 여기를 고친다(나중에 기준정보 표로 옮길 것).
DROP_GRADES = {"BSI"}
GRADE_SITES = {"CI": {"광교지사", "동탄지사", "강남지사", "삼송지사"}}


def prune_grades(std: pd.DataFrame) -> pd.DataFrame:
    """표준금액 표에서 DROP_GRADES 줄과, GRADE_SITES 밖 지사의 그 등급 줄을 뺀다."""
    if std is None or std.empty or "등급" not in std.columns:
        return std
    keep = ~std["등급"].isin(DROP_GRADES)
    for grade, sites in GRADE_SITES.items():
        keep &= ~((std["등급"] == grade) & ~std["사업장"].isin(sites))
    return std[keep].reset_index(drop=True)


def canon_grades(df: pd.DataFrame, cols=("등급",)) -> pd.DataFrame:
    """df 의 등급 열(들)을 canon_grade 로 바꾼 사본. 빈 표·열 없음은 그대로 돌려준다."""
    if df is None or df.empty:
        return df
    present = [c for c in cols if c in df.columns]
    if not present:
        return df
    df = df.copy()
    for c in present:
        df[c] = df[c].map(canon_grade)
    return df


SCHEDULE_PLACEHOLDER_TOKENS = {"", "-", "준공", "정비없음"}


HOT_PARTS_ITEM_TO_LABEL = {
    "고온부품재생": "기계장치_고온부품재생",
    "신품구매": "건설중인자산-재생고온부품",
}


# 고온부품 줄이 기준연도 계획본에서는 어느 과목 안에 들어 있나(그 과목 계획본이 있으면 기준연도 고온부품 = 0)
HOT_PARTS_PLAN_ACCOUNT = {"고온부품재생": "기계장치", "신품구매": "건설중인자산-재생고온부품"}


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
    ("건설중인자산-재생고온부품", "고온부품:신품구매"),
    ("건설중인자산-자산화예비품", "표준화:건설중인자산-자산화예비품"),
    ("저장품-열원(보수)", "표준화:저장품-열원(보수)"),
    # 표준화 방향 4-4·4-5 — 등급별 표준화 대신 연도별 계획으로 잡는 정기비용(2026-10-26)
    ("수선유지비-열원정기유지보수_LTSA", "정기계약:손익"),
    ("기계장치_LTSA", "정기계약:자본"),
    ("기계장치_CRI", "CRI:"),
]
PL_LINES = {"수선유지비-건물/구축물", "수선유지비-열원정기점검", "수선유지비-열원경상정비",
            "수선유지비-열원정기유지보수", "수선유지비-열원보완및개선", "지급수수료-열원점검수수료",
            "비저장품(보수자재)", "소모품(자재공기구)", "수선유지비-열원정기유지보수_LTSA"}


def forecast_years(base_year: int = BASE_YEAR) -> list:
    """기준연도부터 10개년. v2 의 FORECAST_YEARS(2026~2035)는 base_year=2026 인 경우다.

    6-6. 상태가 기준연도 축을 갖게 되었으니(6-5) 계산도 기준연도를 인자로 받는다.
    기본값을 2026 으로 두어 v2 승계 테스트는 그대로 돈다.
    """
    return list(range(int(base_year), int(base_year) + 10))


def year_multiplier(year: int, factors_df: pd.DataFrame, base_year: int = BASE_YEAR, scope: str = None) -> float:
    """등록된 모든 활성 팩터의 (1+연간비율)을 (year-기준연도)년만큼 복리로 곱한 배수.

    scope('손익'|'자본')를 주면 적용구분이 «전체»이거나 그 구분인 팩터만 곱한다(2026-10-26) —
    손익은 생산자물가, 자본은 건설공사비처럼 따로 걸기 위해서다. 적용구분 열이 없으면 전부.
    """
    n = year - int(base_year)
    if n <= 0 or factors_df.empty:
        return 1.0
    active = factors_df[factors_df["활성"].astype(bool)] if "활성" in factors_df.columns else factors_df
    if scope and "적용구분" in active.columns:
        active = active[active["적용구분"].fillna("전체").isin(["전체", "", scope])]
    multiplier = 1.0
    for _, row in active.iterrows():
        multiplier *= (1 + float(row["연간비율"])) ** n
    return multiplier


# ── 과거 실적의 기준연도 가치 환산(2026-11-03 팀장) ─────────────────────────────
# 표준금액은 과거 실적의 평균인데, 실적은 그 해 금액(명목)이다. 생산자물가지수로 기준연도 가치로 바꾼 뒤
# 표준화한다 — 환산 실적(y) = 실적(y) × 지수(기준연도) ÷ 지수(y). 손익·자본 모두 같은 지수(생산자물가지수).
# 지수가 없는 해(기준연도처럼 아직 안 나온 해 포함)는 가까운 지수에서 전망 물가(팩터) 비율로 늘이거나 줄여 채운다.

def fallback_rate(factors_df: pd.DataFrame, base_year: int = BASE_YEAR) -> float:
    """지수 빈 해를 채울 연간 비율 = 활성 팩터 전부의 1년 배수 − 1 (기본 물가상승률 1.5%)."""
    return year_multiplier(int(base_year) + 1, factors_df, int(base_year)) - 1.0


def price_index_series(index_df: pd.DataFrame, years, rate: float) -> dict:
    """{연도: (지수, 출처)} — 출처 «지수»(표에 적힌 값) | «대체»(빈 해를 rate 로 채운 값).
    표가 비면 첫 해를 100 으로 두고 rate 로만 잇는다."""
    years = sorted({int(y) for y in years})
    known = {}
    if index_df is not None and not index_df.empty:
        for y, v in zip(index_df["연도"], index_df["지수"]):
            try:
                y, v = int(y), float(v)
            except (TypeError, ValueError):
                continue
            if v > 0:
                known[y] = v
    if not years:
        return {}
    lo, hi = min(years + list(known)), max(years + list(known))
    out = {y: (v, "지수") for y, v in known.items()}
    if not known:
        return {y: (100.0 * (1 + rate) ** (y - lo), "대체") for y in range(lo, hi + 1)}
    first, last = min(known), max(known)
    for y in range(first - 1, lo - 1, -1):
        out[y] = (out[y + 1][0] / (1 + rate), "대체")
    for y in range(first + 1, hi + 1):
        if y not in out:
            out[y] = (out[y - 1][0] * (1 + rate), "대체")
    return {y: out[y] for y in range(lo, hi + 1)}


def restate_amounts(df: pd.DataFrame, series: dict, to_year: int, col: str = "금액") -> pd.DataFrame:
    """df 의 금액을 to_year 가치로 — 금액 × 지수(to_year) ÷ 지수(그 해). series 는 price_index_series 결과."""
    if df is None or df.empty or not series:
        return df
    to = series[int(to_year)][0]
    df = df.copy()
    df[col] = [float(a) * to / series[int(y)][0] for a, y in zip(df[col], df["연도"])]
    return df


def line_scope(label: str) -> str:
    """전망 표 행의 손익/자본 구분 — 팩터 적용구분을 고르는 데 쓴다."""
    return "손익" if label in PL_LINES else "자본"


def cri_events(grade_hist: pd.DataFrame, cri_rules: pd.DataFrame, factors_df: pd.DataFrame,
               years: list) -> pd.DataFrame:
    """CRI 자동 발생(표준화 방향 4-5). MI 가 잡힌 해(과거 이력 포함) + 지급시차 년이 전망 기간에
    들면 그 해에 기준단가 × 자본 물가배수(단가기준연도 → 지급연도)를 MI 지사에 잡는다.
    엑셀 메모: «MI+1년 로터 반출, +2~+3년 대가 지급», 반출 로터는 짝지사(동일 기종)에 장착.
    반환: 사업장, MI연도, 반출연도, 지급연도, 짝지사, 금액"""
    cols = ["사업장", "MI연도", "반출연도", "지급연도", "짝지사", "금액"]
    if cri_rules is None or cri_rules.empty or grade_hist.empty:
        return pd.DataFrame(columns=cols)
    lo, hi = min(years), max(years)
    out = []
    for _, rule in cri_rules.iterrows():
        if not bool(rule.get("활성", True)):
            continue
        site, lag = rule["사업장"], int(rule["지급시차"])
        mask = (grade_hist["사업장"] == site) & grade_hist["등급"].astype(str).str.contains("MI")
        for mi in sorted(int(y) for y in grade_hist.loc[mask, "연도"]):
            pay = mi + lag
            if lo <= pay <= hi:
                amt = float(rule["기준단가"]) * year_multiplier(pay, factors_df, int(rule["단가기준연도"]), "자본")
                out.append({"사업장": site, "MI연도": mi, "반출연도": mi + 1, "지급연도": pay,
                            "짝지사": rule.get("짝지사") or "", "금액": amt})
    return pd.DataFrame(out, columns=cols)


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


# ── A급정비 — 정비등급 일정 기반 (백테스트 제안 ②, 2026-10-26) ──────────────────
# 평균으로 잡으면 «나간 해는 못 맞히고 안 나간 해마다 조금씩» 넣는다(2019~2025 지사별 오차 247%,
# 맞힌 해 0/8). 일정으로 잡으면 64%, 7/8, 총액 +2%.
A_OVERHAUL_ACCOUNT = "외주비-열원정기점검"
# DH 정비는 매년 수선유지비-정기점검으로 잡히고 A 해에도 튀지 않는다(청주 1.1배). SRF·PLB 도 같다.
_NOT_OVERHAUL_UNIT = re.compile(r"DH|SRF|PLB")


def overhaul_years(unit_grades: pd.DataFrame, site: str) -> set:
    """그 지사에 A급정비가 드는 해 — 어느 설비든 MI 인 해, 또는 등급이 A 로 «바뀐» 해.
    매년 A 인 줄(DH 지사의 등급 줄, 강남 일원 ST)은 바뀐 적이 없어 저절로 빠진다."""
    if unit_grades is None or unit_grades.empty:
        return set()
    years = set()
    for unit, g in unit_grades[unit_grades["사업장"] == site].groupby("설비"):
        if _NOT_OVERHAUL_UNIT.search(str(unit)):
            continue
        prev = None
        for y, grade in sorted(zip(g["연도"].astype(int), g["등급"].astype(str))):
            if grade == "MI" or (grade == "A" and prev is not None and prev != "A"):
                years.add(y)
            prev = grade
    return years


def site_scales(actuals: pd.DataFrame, before_year: int = None, n: int = 3) -> dict:
    """{지사: 규모} — 규모 = 직전 n 개년 연평균 실적(전 과목). 규모비로 다른 지사 금액을 옮길 때 쓴다."""
    a = actuals if before_year is None or actuals.empty else actuals[actuals["연도"] < before_year]
    if a.empty:
        return {}
    yearly = a.groupby(["사업장", "연도"])["금액"].sum()
    return {site: float(g.sort_index().iloc[-n:].mean()) for site, g in yearly.groupby(level=0)}


def overhaul_amounts(actuals: pd.DataFrame, sites: list, site_groups: dict, before_year: int = None) -> dict:
    """{지사: A급정비 1회 금액}. 자기 과거(양수인 해의 평균) → 없으면 같은 묶음 지사 금액 × 규모비."""
    a = actuals[actuals["예산과목"] == A_OVERHAUL_ACCOUNT] if not actuals.empty else actuals
    if before_year is not None and not a.empty:
        a = a[a["연도"] < before_year]
    own = {}
    if not a.empty:
        for site, g in a.groupby("사업장"):
            yearly = g.groupby("연도")["금액"].sum()
            yearly = yearly[yearly > 0]
            if len(yearly):
                own[site] = float(yearly.mean())
    scale = site_scales(actuals, before_year)
    out = {}
    for site in sites:
        out[site] = own[site] if site in own else (_peer_amount(site, own, scale, site_groups) or 0.0)
    return out


def _peer_amount(site, own, scale, site_groups):
    peers = [p for p in own if p != site and site_groups.get(p) == site_groups.get(site) and scale.get(p)]
    if not peers or not scale.get(site):
        return None
    return sum(own[p] * scale[site] / scale[p] for p in peers) / len(peers)


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
                        years: list = None, contracts_df: pd.DataFrame = None,
                        cri_df: pd.DataFrame = None, invest_plan_df: pd.DataFrame = None,
                        overhaul: dict = None, switch: dict = None) -> pd.DataFrame:
    """한 지사의 기준연도~+9년 예산과목별 금액 표. 반환: 라벨(행) × 연도(열)

    표준화 대상 계정과목(SITE_TABLE_LINES의 "표준화:" 항목)의 당해년도(BASE_YEAR) 금액은
    "지사 자체 몫 + 본사 원가분배 몫"의 합이다("총원가배분(전체) = 본사 + 지사" 원본 양식과 동일한
    구조). 지사 자체 몫은 예산계획(budget_lookup) 확정 금액이 있으면 그 값, 없으면 표준화 금액이다.
    본사 원가분배 몫은 경상정비/정기유지보수/정기점검/지급수수료/열원보완및개선처럼
    HQ_CATEGORY_TO_ACCOUNT에 있는 계정만 값이 있고(hq_amount_by_site_acct), 나머지 계정은 0이라
    그대로 더해도 무해하다. 다음년도부터는 종전대로 표준화 금액에 팩터를 복리로 곱해 예측한다.
    overhaul = {"years": {지사: {연도…}}, "amount": {지사: 1회 금액}} 에 그 지사가 있으면 A급정비
    (외주비-열원정기점검)는 표준금액 대신 «정비 해에만 1회 금액 × 팩터»다(기준연도 계획본이 있으면 계획본).
    switch = {지사: {"start": 연도, "lookup": {(사업장,예산과목,등급): 표준금액}, "overhaul": 1회 금액|None}} 에
    그 지사가 있으면 start 해부터 표준금액(과 A급정비 1회 금액)을 그 값으로 바꾼다 — 설비를 새로 짓는 지사(수원 2029)."""
    base_year = int(base_year)
    years = list(years) if years else forecast_years(base_year)
    site_grades = grade_hist[grade_hist["사업장"] == site]
    grade_by_year = dict(zip(site_grades["연도"], site_grades["등급"]))
    latest_known_grade = benchmark.get_current_grade(site, grade_hist)

    std_lookup = _standard_lookup(standard_df)
    sw = (switch or {}).get(site)
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

    # 배수는 연도에만 달린다 — 행(예산과목)마다 다시 구하면 지사 19 × 행 17 × 10년 = 3,230번
    # 팩터 표를 거르고 iterrows 한다(전망 표 시간의 92%, 운영 13초 — 2026-10-15 실측).
    scoped = "적용구분" in factors_df.columns and         factors_df["적용구분"].fillna("전체").isin(["손익", "자본"]).any()
    if scoped:
        mult_by_scope = {sc: {year: year_multiplier(year, factors_df, base_year, sc) for year in years}
                         for sc in ("손익", "자본")}
    else:                           # 구분 없는 팩터뿐이면 배수는 하나 — 연도 수만큼만 구한다(성능 가드)
        same = {year: year_multiplier(year, factors_df, base_year) for year in years}
        mult_by_scope = {"손익": same, "자본": same}
    contract_lookup = {}
    if contracts_df is not None and not contracts_df.empty:
        for _, r in contracts_df[contracts_df["사업장"] == site].iterrows():
            sc = "손익" if str(r["예산과목"]).startswith(("수선유지비", "지급수수료")) else "자본"
            key = (int(r["연도"]), sc)
            contract_lookup[key] = contract_lookup.get(key, 0.0) + float(r["금액"])
    cri_lookup = {}
    if cri_df is not None and not cri_df.empty:
        for _, r in cri_df[cri_df["사업장"] == site].iterrows():
            cri_lookup[int(r["지급연도"])] = cri_lookup.get(int(r["지급연도"]), 0.0) + float(r["금액"])

    rows = []
    for label, source in SITE_TABLE_LINES:
        row = {"예산과목": label}
        base_multiplier_year_values = {}
        mult_by_year = mult_by_scope[line_scope(label)]
        for year in years:
            mult = mult_by_year[year]
            grade = grade_by_year.get(year, latest_known_grade)

            if source.startswith("표준화:"):
                account = source.split(":", 1)[1]
                budget_amount = budget_lookup.get((site, account)) if year == base_year else None
                if budget_amount is not None:
                    site_amount = budget_amount
                elif account == A_OVERHAUL_ACCOUNT and overhaul and site in overhaul["years"]:
                    once = overhaul["amount"].get(site, 0.0)
                    if sw and year >= sw["start"] and sw.get("overhaul") is not None:
                        once = sw["overhaul"]
                    site_amount = once * mult if year in overhaul["years"][site] else 0.0
                else:
                    # 등급 이력이 없는 지사는 benchmark 가 등급을 «표준» 으로 두고 표를 만든다.
                    # v2 는 지사 목록이 등급 이력에서 나와 이 경로가 없었지만, 여기서는 지사가
                    # dept_config 에서 오므로 등급 없는 지사가 정상 입력이다 — 그때 0 이 되면
                    # 기준연도 이후 10년이 통째로 비어 보인다(6-6 실측).
                    lookup = sw["lookup"] if sw and year >= sw["start"] else std_lookup
                    base = lookup.get((site, account, grade)) if grade else None
                    if base is None:
                        base = lookup.get((site, account, "표준"), 0.0)
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
                # 기준연도에 그 과목 계획본이 있으면 고온부품은 이미 그 안에 있다 — LTSA·CRI 처럼 또 더하지 않는다(2026-10-28 사용자 결정)
                if year == base_year and budget_lookup.get((site, HOT_PARTS_PLAN_ACCOUNT[item])) is not None:
                    amount = 0.0
                else:
                    amount = hot_parts_lookup.get((site, year, item), 0.0)
            elif source.startswith(("정기계약:", "CRI:")):
                # 기준연도에 그 과목의 확정 예산(계획본)이 있으면 LTSA·CRI 는 이미 그 안에 있다 — 또 더하지 않는다.
                scope = source.split(":", 1)[1] or "자본"
                plan_account = "수선유지비-열원정기유지보수" if scope == "손익" else "기계장치"
                if year == base_year and budget_lookup.get((site, plan_account)) is not None:
                    amount = 0.0
                elif source.startswith("CRI:"):
                    amount = cri_lookup.get(year, 0.0)
                else:
                    amount = contract_lookup.get((year, scope), 0.0)
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
    if invest_plan_df is None:
        # v2 동작: 기준연도 투자비를 팩터만 곱해 10년 반복
        for year in years:
            invest_row[year] = site_investment * mult_by_scope["자본"][year]
    else:
        # 표준화 방향(투자비는 표준화 대상이 아님): 기준연도 = 계획본(투자계획에 그 해 값이 있으면 그것),
        # 이후 = 투자계획에 적은 값만. 반복하지 않는다.
        plan = invest_plan_df[invest_plan_df["사업장"] == site] if not invest_plan_df.empty else invest_plan_df
        by_year = plan.groupby("연도")["금액"].sum().to_dict() if not plan.empty else {}
        for year in years:
            if year in by_year:
                invest_row[year] = float(by_year[year])
            else:
                invest_row[year] = float(site_investment) if year == base_year else 0.0
    rows.append(invest_row)

    return pd.DataFrame(rows)


def compute_all_sites(sites: list, grade_hist: pd.DataFrame, standard_df: pd.DataFrame,
                       hot_parts_df: pd.DataFrame, hq_master_df: pd.DataFrame,
                       hq_temp_df: pd.DataFrame, hq_ratio_df: pd.DataFrame,
                       factors_df: pd.DataFrame, surprise_df: pd.DataFrame,
                       investment_df: pd.DataFrame, budget_df: pd.DataFrame = None,
                       base_year: int = BASE_YEAR, years: list = None, contracts_df: pd.DataFrame = None,
                       cri_rules: pd.DataFrame = None, invest_plan_df: pd.DataFrame = None,
                       overhaul: dict = None, switch: dict = None) -> dict:
    """지사별 표를 한 번에 계산. 반환: {사업장: DataFrame}"""
    hq_amount = hq_amount_by_site_account(hq_master_df)
    hq_temp_alloc = allocate_hq_temp_projects(hq_temp_df, hq_ratio_df)
    budget_lookup = budget_amount_by_site_account(budget_df) if budget_df is not None else {}
    years = list(years) if years else forecast_years(base_year)
    cri_df = cri_events(grade_hist, cri_rules, factors_df, years)
    return {
        site: compute_site_table(site, grade_hist, standard_df, hot_parts_df, hq_amount,
                                  hq_temp_alloc, factors_df, surprise_df, investment_df, budget_lookup,
                                  base_year=base_year, years=years, contracts_df=contracts_df,
                                  cri_df=cri_df, invest_plan_df=invest_plan_df, overhaul=overhaul,
                                  switch=switch)
        for site in sites
    }
