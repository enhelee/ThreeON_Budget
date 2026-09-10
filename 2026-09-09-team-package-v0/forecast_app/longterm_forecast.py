"""중장기 예산 예측(2026~2035) 계산 엔진.

지사별 표준화 금액(standardization.py)에 팩터(물가상승률 등)를 복리로 곱해 미래 연도
금액을 추정하고, 별도로 관리되는 정기점검보수공사 일정(미래 정비등급)·고온부품 계획·
투자비·본사 원가분배·돌발사업을 더해 지사별 10개년 표를 만든다.

26년만 상세(본사원가분배/총원가배분) 시트를 만들고, 27~35년은 지사별 표 합계만 쓴다.
"""
import os
import io
import re
import glob
import json
import pandas as pd
from openpyxl import load_workbook
from builtin_categories import normalize_account_name, PROFIT_LOSS_ACCOUNTS, CAPITAL_ACCOUNTS
from mapping_config import get_site_display_name, get_current_site_type
import standardization as std

FORECAST_YEARS = list(range(2026, 2036))
BASE_YEAR = 2026

FACTORS_PATH = "longterm_factors.csv"  # 컬럼: 팩터명, 연간비율, 활성
HOT_PARTS_PATH = "hot_parts_plan.csv"  # 컬럼: 사업장, 연도, 항목(고온부품재생/신품구매), 금액
HQ_MASTER_PATH = "hq_master_table.csv"  # 컬럼: 대분류, 중분류, 세부내역, 26년예산, <지사들...>
HQ_RATIO_PATH = "hq_allocation_ratio.csv"  # 컬럼: 사업장, 계약체결금액
HQ_TEMP_PROJECTS_PATH = "hq_temp_projects.csv"  # 컬럼: 사업명, 예산과목, 연도, 금액
SURPRISE_PATH = "surprise_projects.csv"  # 컬럼: 사업장, 연도, 예산과목, 금액, 사유
# Test 모드에서 올리는 모든 백데이터는 이 폴더 하나에 모아 저장한다 - 세션이 끊기거나 앱을
# 다시 켜도 파일로 남아있어, 테스트할 때마다 다시 업로드하지 않아도 된다.
TEST_DATA_DIR = "test_data"
TEST_ACTUALS_PATH = os.path.join(TEST_DATA_DIR, "longterm_test_actuals.csv")  # 컬럼: 사업장, 연도, 예산과목, 금액
TEST_BUDGET_PLAN_PATH = os.path.join(TEST_DATA_DIR, "longterm_test_budget_plan.csv")  # 실제 budget_{연도}.csv와 동일 구조

# 26년 투자비로 간주하는 예산계획 계정과목 (표준화 대상과 겹치는 3개 계정도 포함되지만,
# 실무상 이 계정들의 실적은 '표준화'가 아니라 이 투자비 라인 하나로만 다뤄서 이중계산을 피한다)
INVESTMENT_ACCOUNTS = ["외주비-열원공사비", "외주비-열원기술용역비", "재료비-열원자재비", "외주비-기타"]

# 정기점검보수공사 일정의 정비등급 어휘 - GT계열이 있으면 그 지사의 대표등급, 없으면 ST계열을 쓴다.
GT_GRADE_VALUES = {"MI", "TI", "CI", "간이", "HGPI", "BSI"}
ST_GRADE_VALUES = {"A", "B", "C"}
VALID_GRADE_TOKENS = GT_GRADE_VALUES | ST_GRADE_VALUES
SCHEDULE_PLACEHOLDER_TOKENS = {"", "-", "준공", "정비없음"}

# 고온부품(26) 시트의 항목명 -> 지사별 탭에서 쓸 라인 라벨
HOT_PARTS_ITEM_TO_LABEL = {
    "고온부품재생": "기계장치_고온부품재생",
    "신품구매": "건설중인자산_재생고온부품",
}

# 본사 원가분배 마스터 표의 (대분류, 중분류) -> 지사별 탭 예산과목 라벨.
# '기타본사'/'미래개발원'은 중분류(정기점검/정기유지보수/열원보완/지급수수료/건물구축물)로 판정하고,
# '플랜트'는 중분류(경상정비)로, 그 외는 대분류 자체로 판정한다.
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

# HQ_CATEGORY_TO_ACCOUNT의 "건물구축물"은 본사배분 라벨 "건물/구축물"로 매핑되지만, 표준화 대상
# 계정과목명은 "수선유지비-건물/구축물"이라 표기가 다르다("26년" 원본 시트에서는 같은 한 줄이다).
# 26년 본사 배분 몫을 더할 때만 이 별칭으로 hq_amount_by_site_acct를 찾는다.
STANDARDIZED_ACCOUNT_TO_HQ_LABEL = {
    "수선유지비-건물/구축물": "건물/구축물",
}

# 지사별 탭에 나타날 손익/자본 라인 순서(라벨, 산출방식). 산출방식: "표준화:<계정과목>" / "고온부품:<항목>" / "본사배분"
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


# ---------------------------------------------------------------- 팩터
def load_factors() -> pd.DataFrame:
    if os.path.exists(FACTORS_PATH):
        return pd.read_csv(FACTORS_PATH)
    return pd.DataFrame([{"팩터명": "물가상승률", "연간비율": 0.015, "활성": True}])


def save_factors(df: pd.DataFrame):
    df.to_csv(FACTORS_PATH, index=False)


def year_multiplier(year: int, factors_df: pd.DataFrame) -> float:
    """등록된 모든 활성 팩터의 (1+연간비율)을 (year-2026)년만큼 복리로 곱한 배수."""
    n = year - BASE_YEAR
    if n <= 0 or factors_df.empty:
        return 1.0
    active = factors_df[factors_df["활성"].astype(bool)] if "활성" in factors_df.columns else factors_df
    multiplier = 1.0
    for _, row in active.iterrows():
        multiplier *= (1 + float(row["연간비율"])) ** n
    return multiplier


# ---------------------------------------------------------------- 정비등급 스케줄 파싱
def _classify_grade_row(values: dict) -> str | None:
    """연도->값 중 실제 등급 토큰만 보고 GT/ST 중 어디 어휘를 쓰는 행인지 판정. 없으면 None."""
    tokens = [str(v).strip() for v in values.values() if v not in (None, "")]
    if any(t in GT_GRADE_VALUES for t in tokens):
        return "GT"
    if any(t in ST_GRADE_VALUES for t in tokens):
        return "ST"
    return None


def import_schedule_from_workbook(file_bytes) -> pd.DataFrame:
    """'정기점검보수공사 일정' 시트에서 지사별 미래(2026~) 정비등급을 읽어온다.
    GT계열 등급이 있는 지사는 그 행을, 없이 ST계열만 있는 지사는 그 행을 대표등급으로 쓴다.
    반환은 standardization.load_grade_history()와 같은 (사업장,연도,등급) 스키마라
    표준화 페이지의 정비등급 이력에 그대로 병합해 쓸 수 있다."""
    wb = load_workbook(io.BytesIO(file_bytes), data_only=True)
    sheet_name = next((n for n in wb.sheetnames if "정기점검보수공사" in n), None)
    if sheet_name is None:
        return pd.DataFrame(columns=["사업장", "연도", "등급"])
    ws = wb[sheet_name]

    year_row = None
    for r in range(1, 6):
        for c in range(1, ws.max_column + 1):
            v = ws.cell(row=r, column=c).value
            if isinstance(v, (int, float)) and 2020 < v < 2050:
                year_row = r
                break
        if year_row:
            break
    if year_row is None:
        return pd.DataFrame(columns=["사업장", "연도", "등급"])

    year_by_gt_col = {
        c: int(ws.cell(row=year_row, column=c).value)
        for c in range(1, ws.max_column + 1)
        if isinstance(ws.cell(row=year_row, column=c).value, (int, float))
        and 2020 < ws.cell(row=year_row, column=c).value < 2050
    }
    data_start_row = year_row + 3  # 연도행, '등급'행, GT/ST/기간행 다음부터 실제 데이터

    short_to_full = std._site_sheet_name_map()
    short_names_sorted = sorted(short_to_full.keys(), key=len, reverse=True)

    site_rows: dict[str, list[int]] = {}
    current_site = None
    r = data_start_row
    blank_run = 0
    while r <= ws.max_row:
        row_values = [ws.cell(row=r, column=c).value for c in range(1, ws.max_column + 1)]
        if all(v in (None, "") for v in row_values):
            blank_run += 1
            if blank_run >= 3:
                break
            r += 1
            continue
        blank_run = 0

        label = ws.cell(row=r, column=1).value
        if label is not None and str(label).strip():
            raw = str(label).replace(" ", "").strip()
            match = next((s for s in short_names_sorted if raw.startswith(s)), None)
            current_site = short_to_full.get(match) if match else None

        if current_site:
            site_rows.setdefault(current_site, []).append(r)
        r += 1

    rows = []
    for site, row_list in site_rows.items():
        candidates = []
        for row_idx in row_list:
            gt_values = {year: ws.cell(row=row_idx, column=col).value for col, year in year_by_gt_col.items()}
            st_values = {year: ws.cell(row=row_idx, column=col + 1).value for col, year in year_by_gt_col.items()}
            gt_class = _classify_grade_row(gt_values)
            if gt_class == "GT":
                candidates.append(("GT", gt_values))
                continue
            st_class = _classify_grade_row(st_values)
            if st_class == "ST":
                candidates.append(("ST", st_values))

        chosen = next((c for c in candidates if c[0] == "GT"), None) or (candidates[0] if candidates else None)
        if chosen is None:
            continue
        _, values = chosen
        for year, grade in values.items():
            if grade is None:
                continue
            grade = str(grade).strip()
            if grade not in VALID_GRADE_TOKENS:
                continue
            rows.append({"사업장": site, "연도": year, "등급": grade})

    return pd.DataFrame(rows, columns=["사업장", "연도", "등급"])


# ---------------------------------------------------------------- 고온부품
def load_hot_parts() -> pd.DataFrame:
    if os.path.exists(HOT_PARTS_PATH):
        return pd.read_csv(HOT_PARTS_PATH, dtype={"사업장": str})
    return pd.DataFrame(columns=["사업장", "연도", "항목", "금액"])


def save_hot_parts(df: pd.DataFrame):
    df.to_csv(HOT_PARTS_PATH, index=False)


def import_hot_parts_from_workbook(file_bytes) -> pd.DataFrame:
    """'고온부품(26)' 시트에서 지사×연도×항목(고온부품재생/신품구매) 금액을 읽어온다.
    양식 단위는 천원이므로 원 단위로 환산한다."""
    wb = load_workbook(io.BytesIO(file_bytes), data_only=True)
    sheet_name = next((n for n in wb.sheetnames if n.strip().startswith("고온부품")), None)
    if sheet_name is None:
        return pd.DataFrame(columns=["사업장", "연도", "항목", "금액"])
    ws = wb[sheet_name]

    header_row, year_by_col = None, {}
    for r in range(1, 8):
        found = {}
        for c in range(1, ws.max_column + 1):
            v = ws.cell(row=r, column=c).value
            if v is None:
                continue
            m = re.match(r"^(\d{2})년", str(v).strip())
            if m:
                found[c] = 2000 + int(m.group(1))
        if found:
            header_row, year_by_col = r, found
            break
    if header_row is None:
        return pd.DataFrame(columns=["사업장", "연도", "항목", "금액"])

    short_to_full = std._site_sheet_name_map()
    rows = []
    current_site = None
    r = header_row + 1
    blank_run = 0
    while r <= ws.max_row:
        site_label = ws.cell(row=r, column=1).value
        item = ws.cell(row=r, column=5).value
        if site_label:
            current_site = short_to_full.get(str(site_label).strip())
        if item is None or current_site is None:
            blank_run += 1
            if blank_run >= 3:
                break
            r += 1
            continue
        blank_run = 0
        item = str(item).strip()
        for col, year in year_by_col.items():
            amount = ws.cell(row=r, column=col).value
            if not amount:
                continue
            rows.append({"사업장": current_site, "연도": year, "항목": item, "금액": float(amount) * 1000})
        r += 1

    return pd.DataFrame(rows, columns=["사업장", "연도", "항목", "금액"])


# ---------------------------------------------------------------- 투자비
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


# ---------------------------------------------------------------- 본사 원가분배
def load_hq_master() -> pd.DataFrame:
    if os.path.exists(HQ_MASTER_PATH):
        return pd.read_csv(HQ_MASTER_PATH)
    return pd.DataFrame(columns=["대분류", "중분류", "세부내역", "26년예산"])


def save_hq_master(df: pd.DataFrame):
    df.to_csv(HQ_MASTER_PATH, index=False)


def load_hq_ratio() -> pd.DataFrame:
    if os.path.exists(HQ_RATIO_PATH):
        return pd.read_csv(HQ_RATIO_PATH, dtype={"사업장": str})
    return pd.DataFrame(columns=["사업장", "계약체결금액"])


def save_hq_ratio(df: pd.DataFrame):
    df.to_csv(HQ_RATIO_PATH, index=False)


def import_hq_master_from_workbook(file_bytes) -> tuple:
    """'26년 본사 원가분배' 시트 전체를 그대로 읽어 (마스터표, 배분비율표)를 반환한다.
    라벨을 스캔해서 위치를 찾으므로 같은 형식의 수정본을 다시 올려도 그대로 갱신된다."""
    wb = load_workbook(io.BytesIO(file_bytes), data_only=True)
    sheet_name = next((n for n in wb.sheetnames if "본사 원가분배" in n), None)
    empty_master = pd.DataFrame(columns=["대분류", "중분류", "세부내역", "26년예산"])
    empty_ratio = pd.DataFrame(columns=["사업장", "계약체결금액"])
    if sheet_name is None:
        return empty_master, empty_ratio
    ws = wb[sheet_name]

    header_row, budget_col = None, None
    for r in range(1, 10):
        for c in range(1, ws.max_column + 1):
            if str(ws.cell(row=r, column=c).value or "").strip() == "26년 예산":
                header_row, budget_col = r, c
                break
        if header_row:
            break
    if header_row is None:
        return empty_master, empty_ratio

    short_to_full = std._site_sheet_name_map()
    site_col = {}
    for c in range(budget_col + 1, ws.max_column + 1):
        v = ws.cell(row=header_row, column=c).value
        if v is None:
            continue
        name = short_to_full.get(str(v).strip())
        if name:
            site_col[c] = name
    site_order = [site_col[c] for c in sorted(site_col)]

    rows = []
    major = minor = None
    r = header_row + 1
    while r <= ws.max_row:
        c1 = ws.cell(row=r, column=1).value
        c2 = ws.cell(row=r, column=2).value
        c3 = ws.cell(row=r, column=3).value
        budget = ws.cell(row=r, column=budget_col).value
        label1 = str(c1).strip() if c1 else ""
        if label1 in ("합계", "경상정비 원가배부기준"):
            break
        if c1:
            major = label1
        if c2:
            minor = str(c2).strip()
        detail = str(c3).strip() if c3 else ""
        if detail == "합계":  # 중분류 소계 행 - 개별 라인 합과 중복되므로 제외
            r += 1
            continue
        if budget not in (None, ""):
            row = {"대분류": major or "", "중분류": minor or "", "세부내역": detail, "26년예산": budget}
            for col, site in site_col.items():
                row[site] = ws.cell(row=r, column=col).value or 0
            rows.append(row)
        r += 1

    master_cols = ["대분류", "중분류", "세부내역", "26년예산"] + site_order
    master_df = pd.DataFrame(rows, columns=master_cols) if rows else empty_master

    ratio_rows = []
    while r <= ws.max_row:
        c3 = ws.cell(row=r, column=3).value
        if c3 and str(c3).strip() == "합계":
            for col, site in site_col.items():
                val = ws.cell(row=r, column=col).value
                if val not in (None, ""):
                    ratio_rows.append({"사업장": site, "계약체결금액": float(val)})
            break
        r += 1
    ratio_df = pd.DataFrame(ratio_rows, columns=["사업장", "계약체결금액"]) if ratio_rows else empty_ratio

    return master_df, ratio_df


def _hq_row_account_label(major: str, minor: str) -> str | None:
    key = minor if major in ("기타본사", "미래개발원", "플랜트") else major
    return HQ_CATEGORY_TO_ACCOUNT.get(key)


def hq_amount_by_site_account(hq_master_df: pd.DataFrame) -> dict:
    """{(사업장, 예산과목라벨): 금액} - 마스터 표를 계정과목 라벨 기준으로 합산."""
    result = {}
    if hq_master_df.empty:
        return result
    site_cols = [c for c in hq_master_df.columns if c not in ("대분류", "중분류", "세부내역", "26년예산")]
    for _, row in hq_master_df.iterrows():
        label = _hq_row_account_label(row.get("대분류", ""), row.get("중분류", ""))
        if label is None:
            continue
        for site in site_cols:
            amount = row.get(site) or 0
            key = (site, label)
            result[key] = result.get(key, 0) + float(amount)
    return result


# ---------------------------------------------------------------- 본사 일시적 사업
def load_hq_temp_projects() -> pd.DataFrame:
    if os.path.exists(HQ_TEMP_PROJECTS_PATH):
        return pd.read_csv(HQ_TEMP_PROJECTS_PATH)
    return pd.DataFrame(columns=["사업명", "예산과목", "연도", "금액"])


def save_hq_temp_projects(df: pd.DataFrame):
    df.to_csv(HQ_TEMP_PROJECTS_PATH, index=False)


def append_hq_temp_project(사업명: str, 예산과목: str, 연도: int, 금액: float):
    df = load_hq_temp_projects()
    new_row = pd.DataFrame([{"사업명": 사업명, "예산과목": 예산과목, "연도": 연도, "금액": 금액}])
    save_hq_temp_projects(pd.concat([df, new_row], ignore_index=True))


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


# ---------------------------------------------------------------- Test 모드 백데이터
def load_test_actuals() -> pd.DataFrame:
    if os.path.exists(TEST_ACTUALS_PATH):
        return pd.read_csv(TEST_ACTUALS_PATH, dtype={"사업장": str})
    return pd.DataFrame(columns=["사업장", "연도", "예산과목", "금액"])


def save_test_actuals(df: pd.DataFrame):
    os.makedirs(TEST_DATA_DIR, exist_ok=True)
    df.to_csv(TEST_ACTUALS_PATH, index=False)


def test_budget_plan_path(year: int) -> str:
    return os.path.join(TEST_DATA_DIR, f"longterm_test_budget_plan_{year}.csv")


def load_test_budget_plan(year: int = BASE_YEAR) -> pd.DataFrame:
    """Test 모드에서 업로드한 예산계획(연도별 확정 예산). 실제 budget_{연도}.csv와 같은 컬럼 구조.

    연도별 파일(test_budget_plan_path)이 없고, 연도 구분 없이 쓰던 예전 단일 파일
    (TEST_BUDGET_PLAN_PATH)이 남아있으면 - 그 파일은 원래 "당해년도(BASE_YEAR)" 예산 용도로만
    쓰였으므로 - BASE_YEAR 파일로 1회 옮겨써서 기존 백데이터를 잃지 않는다."""
    path = test_budget_plan_path(year)
    if not os.path.exists(path) and year == BASE_YEAR and os.path.exists(TEST_BUDGET_PLAN_PATH):
        legacy = pd.read_csv(TEST_BUDGET_PLAN_PATH)
        os.makedirs(TEST_DATA_DIR, exist_ok=True)
        legacy.to_csv(path, index=False)
        return legacy
    if os.path.exists(path):
        return pd.read_csv(path)
    return pd.DataFrame()


def save_test_budget_plan(df: pd.DataFrame, year: int = BASE_YEAR):
    os.makedirs(TEST_DATA_DIR, exist_ok=True)
    df.to_csv(test_budget_plan_path(year), index=False)


def load_test_budget_plan_years() -> list:
    """저장된 Test 예산계획 연도 목록(연도별 파일명에서 추출, 오름차순)."""
    years = []
    for path in glob.glob(os.path.join(TEST_DATA_DIR, "longterm_test_budget_plan_*.csv")):
        m = re.search(r"longterm_test_budget_plan_(\d+)\.csv$", path)
        if m:
            years.append(int(m.group(1)))
    return sorted(set(years))


def load_test_budget_plan_multi(years: list) -> pd.DataFrame:
    """선택한 여러 연도의 Test 예산계획을 합친다(정식 모드가 budget_{y}.csv 여러 개를 합치는 것과 동일 패턴)."""
    frames = [load_test_budget_plan(y) for y in years]
    frames = [f for f in frames if not f.empty]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


# ---------------------------------------------------------------- 지사별 돌발사업
def load_surprise_projects() -> pd.DataFrame:
    if os.path.exists(SURPRISE_PATH):
        return pd.read_csv(SURPRISE_PATH, dtype={"사업장": str})
    return pd.DataFrame(columns=["사업장", "연도", "예산과목", "금액", "사유"])


def save_surprise_projects(df: pd.DataFrame):
    df.to_csv(SURPRISE_PATH, index=False)


def append_surprise_project(사업장: str, 연도: int, 예산과목: str, 금액: float, 사유: str):
    df = load_surprise_projects()
    new_row = pd.DataFrame([{"사업장": 사업장, "연도": 연도, "예산과목": 예산과목, "금액": 금액, "사유": 사유}])
    save_surprise_projects(pd.concat([df, new_row], ignore_index=True))


# ---------------------------------------------------------------- 지사별 표 계산
def _standard_lookup(standard_df: pd.DataFrame) -> dict:
    """{(사업장,예산과목,등급): 표준금액}"""
    if standard_df.empty:
        return {}
    return {(r["사업장"], r["예산과목"], r["등급"]): r["표준금액"] for _, r in standard_df.iterrows()}


def compute_site_table(site: str, grade_hist: pd.DataFrame, standard_df: pd.DataFrame,
                        hot_parts_df: pd.DataFrame, hq_amount_by_site_acct: dict,
                        hq_temp_alloc: pd.DataFrame, factors_df: pd.DataFrame,
                        surprise_df: pd.DataFrame, investment_df: pd.DataFrame,
                        budget_lookup: dict = None) -> pd.DataFrame:
    """한 지사의 2026~2035년 예산과목별 금액 표. 반환: 라벨(행) × 연도(열)

    표준화 대상 계정과목(SITE_TABLE_LINES의 "표준화:" 항목)의 당해년도(BASE_YEAR) 금액은
    "지사 자체 몫 + 본사 원가분배 몫"의 합이다("총원가배분(전체) = 본사 + 지사" 원본 양식과 동일한
    구조). 지사 자체 몫은 예산계획(budget_lookup) 확정 금액이 있으면 그 값, 없으면 표준화 금액이다.
    본사 원가분배 몫은 경상정비/정기유지보수/정기점검/지급수수료/열원보완및개선처럼
    HQ_CATEGORY_TO_ACCOUNT에 있는 계정만 값이 있고(hq_amount_by_site_acct), 나머지 계정은 0이라
    그대로 더해도 무해하다. 다음년도부터는 종전대로 표준화 금액에 팩터를 복리로 곱해 예측한다."""
    site_grades = grade_hist[grade_hist["사업장"] == site]
    grade_by_year = dict(zip(site_grades["연도"], site_grades["등급"]))
    latest_known_grade = std.get_current_grade(site, grade_hist)

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
        for year in FORECAST_YEARS:
            mult = year_multiplier(year, factors_df)
            grade = grade_by_year.get(year, latest_known_grade)

            if source.startswith("표준화:"):
                account = source.split(":", 1)[1]
                budget_amount = budget_lookup.get((site, account)) if year == BASE_YEAR else None
                if budget_amount is not None:
                    site_amount = budget_amount
                else:
                    base = std_lookup.get((site, account, grade), 0.0) if grade else 0.0
                    site_amount = base * mult
                # 26년은 지사 자체 예산(예산계획/표준화)에 본사 원가분배 마스터 표의 배분액을 더한다 -
                # "총원가배분(전체) = 본사 + 지사"라 두 금액은 서로 다른 부서코드에 잡힌 별도 예산이며
                # 합쳐야 그 지사의 26년 총액이 된다(경상정비/정기유지보수/정기점검/지급수수료/
                # 열원보완및개선처럼 HQ_CATEGORY_TO_ACCOUNT에 없는 계정은 본사 배분이 0이라 그대로 더해도 무해).
                hq_lookup_account = STANDARDIZED_ACCOUNT_TO_HQ_LABEL.get(account, account)
                hq_part = hq_amount_by_site_acct.get((site, hq_lookup_account), 0.0) if year == BASE_YEAR else 0.0
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
    for year in FORECAST_YEARS:
        invest_row[year] = site_investment * year_multiplier(year, factors_df)
    rows.append(invest_row)

    return pd.DataFrame(rows)


def compute_all_sites(sites: list, grade_hist: pd.DataFrame, standard_df: pd.DataFrame,
                       hot_parts_df: pd.DataFrame, hq_master_df: pd.DataFrame,
                       hq_temp_df: pd.DataFrame, hq_ratio_df: pd.DataFrame,
                       factors_df: pd.DataFrame, surprise_df: pd.DataFrame,
                       investment_df: pd.DataFrame, budget_df: pd.DataFrame = None) -> dict:
    """지사별 표를 한 번에 계산. 반환: {사업장: DataFrame}"""
    hq_amount = hq_amount_by_site_account(hq_master_df)
    hq_temp_alloc = allocate_hq_temp_projects(hq_temp_df, hq_ratio_df)
    budget_lookup = budget_amount_by_site_account(budget_df) if budget_df is not None else {}
    return {
        site: compute_site_table(site, grade_hist, standard_df, hot_parts_df, hq_amount,
                                  hq_temp_alloc, factors_df, surprise_df, investment_df, budget_lookup)
        for site in sites
    }
