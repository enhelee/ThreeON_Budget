"""
사업명 기준으로 예산계획(연예산)과 사업매칭 결과(실적)를 합쳐
'계획 대비 실적' 표를 만든다. (손익예산실적집계표 양식2의 구조 그대로)
손익/자본 구분은 양식2/양식3의 종합표에서 뽑아낸 예산과목 목록(builtin_categories)으로 자동 판단한다.
"""
import os
import pandas as pd
from builtin_categories import get_category_for_account


def build_plan_vs_actual(year: int, category_filter: str = None) -> pd.DataFrame:
    """
    category_filter: "손익", "자본", 또는 None(전체)
    """
    budget_path = f"budget_{year}.csv"
    matched_path = f"matched_{year}.csv"
    dept_col = "예산귀속\n부서명(처.지사)"
    cols = ["사업명", "지사명", "예산과목", "손익자본구분", "연예산(A)", "최종실적금액(B)", "차이(B-A)", "집행률(%)"]

    if not os.path.exists(budget_path):
        return pd.DataFrame(columns=cols)

    budget = pd.read_csv(budget_path)
    meta_cols = [c for c in ["예산과목", dept_col] if c in budget.columns]
    plan_meta = budget.groupby("사업명", dropna=True)[meta_cols].first().reset_index() \
        if meta_cols else budget[["사업명"]].drop_duplicates()
    plan_sum = budget.groupby("사업명", dropna=True)["연예산 합계"].sum().reset_index()
    plan_sum = plan_sum.rename(columns={"연예산 합계": "연예산(A)"})
    plan = plan_meta.merge(plan_sum, on="사업명", how="outer")

    matched_raw = None
    if os.path.exists(matched_path):
        matched_raw = pd.read_csv(matched_path)
        actual_meta_cols = [c for c in ["계정과목", "사업장"] if c in matched_raw.columns]
        actual_meta = matched_raw.groupby("사업명", dropna=True)[actual_meta_cols].first().reset_index() \
            if actual_meta_cols else matched_raw[["사업명"]].drop_duplicates()
        actual_sum = matched_raw.groupby("사업명", dropna=True)["금액"].sum().reset_index()
        actual_sum = actual_sum.rename(columns={"금액": "최종실적금액(B)"})
        actual = actual_meta.merge(actual_sum, on="사업명", how="outer")
    else:
        actual = pd.DataFrame(columns=["사업명", "계정과목", "사업장", "최종실적금액(B)"])

    merged = pd.merge(plan, actual, on="사업명", how="outer", suffixes=("", "_실적"))
    merged["연예산(A)"] = merged["연예산(A)"].fillna(0)
    merged["최종실적금액(B)"] = merged["최종실적금액(B)"].fillna(0)

    # 예산과목이 없으면(신규사업 등) 실적 쪽 계정과목으로 대체
    if "계정과목" in merged.columns:
        merged["예산과목"] = merged["예산과목"].fillna(merged["계정과목"]) if "예산과목" in merged.columns else merged["계정과목"]
    if "예산과목" not in merged.columns:
        merged["예산과목"] = None

    # 지사명: 예산계획의 처.지사 필드 우선, 없으면 실적데이터의 사업장(코드->표시명 변환)으로 대체
    from mapping_config import get_site_display_name
    if dept_col not in merged.columns:
        merged[dept_col] = None
    if "사업장" in merged.columns:
        missing = merged[dept_col].isna()
        merged.loc[missing, dept_col] = merged.loc[missing, "사업장"].apply(
            lambda v: get_site_display_name(v) if pd.notna(v) else None
        )
    # 예산계획에 부서'코드'가 그대로 남아있는 경우(예: '2023.0')도 실제 지사명으로 정규화한다.
    # 등록되지 않은 코드라도 앞 3자리가 같은 코드가 있으면 같은 지사로 묶인다.
    merged[dept_col] = merged[dept_col].apply(lambda v: get_site_display_name(v) if pd.notna(v) else v)
    merged["지사명"] = merged[dept_col]

    merged["손익자본구분"] = merged["예산과목"].apply(get_category_for_account)

    merged["차이(B-A)"] = merged["최종실적금액(B)"] - merged["연예산(A)"]
    merged["집행률(%)"] = merged.apply(
        lambda r: round(r["최종실적금액(B)"] / r["연예산(A)"] * 100, 1) if r["연예산(A)"] else None, axis=1
    )

    if category_filter:
        merged = merged[merged["손익자본구분"] == category_filter]

    return merged[cols].sort_values("연예산(A)", ascending=False).reset_index(drop=True)