"""예산계획(배정)과 실적을 지사유형×계정과목 기준으로 합쳐 '배정/실적/잔액/실적률' 표를 만든다.
손익예산실적집계표(양식2)/자본예산실적집계표(양식3)의 요약 형태를 참고한다.

사업명 매칭(plan_vs_actual.py)과 달리 지사유형·계정과목 단위로만 집계하므로, '사업 매칭' 단계를
거치지 않은 실적(예: Test 모드의 투자유형 예측 테스트 결과)에도 그대로 쓸 수 있다.
"""
import pandas as pd
from builtin_categories import normalize_account_name, get_category_for_account
from mapping_config import get_site_display_name, get_current_site_type

SUMMARY_COLS = ["지사유형", "계정과목", "손익자본구분"]


def budget_by_site_type_account(budget_df: pd.DataFrame) -> pd.DataFrame:
    """예산계획 원본(budget_{연도}.csv과 동일 구조)을 지사유형×계정과목별 배정액으로 집계.
    반환: 지사유형, 계정과목, 손익자본구분, 배정"""
    cols = SUMMARY_COLS + ["배정"]
    if budget_df.empty:
        return pd.DataFrame(columns=cols)

    df = budget_df.copy()
    df["계정과목"] = df["예산과목"].apply(normalize_account_name)
    dept_col = "예산귀속 \n부서코드"
    df["사업장"] = df[dept_col].apply(get_site_display_name)
    df["지사유형"] = df["사업장"].apply(get_current_site_type)
    df["손익자본구분"] = df["계정과목"].apply(get_category_for_account)

    grouped = df.groupby(SUMMARY_COLS)["연예산 합계"].sum().reset_index()
    return grouped.rename(columns={"연예산 합계": "배정"})


def actual_by_site_type_account(actual_df: pd.DataFrame) -> pd.DataFrame:
    """실적 데이터(사업장명·지사유형·계정과목·금액 컬럼 필요)를 지사유형×계정과목별로 집계.
    반환: 지사유형, 계정과목, 손익자본구분, 실적"""
    cols = SUMMARY_COLS + ["실적"]
    if actual_df.empty:
        return pd.DataFrame(columns=cols)

    df = actual_df.copy()
    df["계정과목"] = df["계정과목"].apply(normalize_account_name)
    df["손익자본구분"] = df["계정과목"].apply(get_category_for_account)

    grouped = df.groupby(SUMMARY_COLS)["금액"].sum().reset_index()
    return grouped.rename(columns={"금액": "실적"})


def merge_budget_actual(budget_summary: pd.DataFrame, actual_summary: pd.DataFrame) -> pd.DataFrame:
    """배정·실적을 (지사유형,계정과목,손익자본구분) 기준으로 합쳐 잔액·실적률까지 계산.
    반환: 지사유형, 계정과목, 손익자본구분, 배정, 실적, 잔액, 실적률(%)"""
    merged = pd.merge(budget_summary, actual_summary, on=SUMMARY_COLS, how="outer")
    merged["배정"] = merged["배정"].fillna(0.0)
    merged["실적"] = merged["실적"].fillna(0.0)
    merged["잔액"] = merged["배정"] - merged["실적"]
    merged["실적률(%)"] = merged.apply(
        lambda r: round(r["실적"] / r["배정"] * 100, 1) if r["배정"] else None, axis=1
    )
    return merged


def site_type_summary_table(merged: pd.DataFrame) -> pd.DataFrame:
    """지사유형별 배정/실적/잔액/실적률 표(손익예산·자본예산 구분, 지사유형별 열 + 합계열).
    반환 인덱스: (손익자본구분, 항목), 컬럼: 지사유형... + 합계"""
    if merged.empty:
        return pd.DataFrame()

    site_types = sorted(t for t in merged["지사유형"].unique() if pd.notna(t))
    rows, index = [], []
    for category in ["손익", "자본"]:
        sub = merged[merged["손익자본구분"] == category]
        budget_by_type = sub.groupby("지사유형")["배정"].sum()
        actual_by_type = sub.groupby("지사유형")["실적"].sum()
        budget = {t: float(budget_by_type.get(t, 0.0)) for t in site_types}
        actual = {t: float(actual_by_type.get(t, 0.0)) for t in site_types}
        budget["합계"] = sum(budget.values())
        actual["합계"] = sum(actual.values())
        remain = {k: budget[k] - actual[k] for k in budget}
        rate = {k: (round(actual[k] / budget[k] * 100, 1) if budget[k] else None) for k in budget}

        for label, values in (("배정", budget), ("실적", actual), ("잔액", remain), ("실적률(%)", rate)):
            index.append((category + "예산", label))
            rows.append(values)

    table = pd.DataFrame(rows, index=pd.MultiIndex.from_tuples(index, names=["구분", "항목"]))
    money_rows = [label != "실적률(%)" for _, label in table.index]
    table.loc[money_rows] = (table.loc[money_rows] / 1e8).round(1)
    return table[site_types + ["합계"]]


def account_detail_table(merged: pd.DataFrame, category: str) -> pd.DataFrame:
    """계정과목별 배정/실적/잔액/실적률 표(손익 또는 자본 계열, 지사유형 구분 없이 전체 합계).
    반환: 계정과목을 인덱스로 하는 배정/실적/잔액/실적률(%) 표(배정 내림차순)"""
    sub = merged[merged["손익자본구분"] == category]
    if sub.empty:
        return pd.DataFrame(columns=["배정", "실적", "잔액", "실적률(%)"])

    by_account = sub.groupby("계정과목")[["배정", "실적"]].sum()
    by_account["잔액"] = by_account["배정"] - by_account["실적"]
    by_account["실적률(%)"] = by_account.apply(
        lambda r: round(r["실적"] / r["배정"] * 100, 1) if r["배정"] else None, axis=1
    )
    by_account[["배정", "실적", "잔액"]] = (by_account[["배정", "실적", "잔액"]] / 1e8).round(1)
    return by_account.sort_values("배정", ascending=False)
