"""
전표헤더텍스트를 '사업' 마스터 목록(사업코드, 사업명)과 매칭한다.
투자유형처럼 고정된 8개 카테고리가 아니라, 수십~수백 개의 구체적인 사업명 중
가장 유사한 것을 찾는 문제라서 텍스트 유사도(rapidfuzz) 기반으로 매칭한다.
rapidfuzz는 C로 구현되어 순수 파이썬(difflib) 대비 수백 배 빠르며, 인터넷 연결 없이도 동작한다.
(개발 시 한 번 설치 필요: pip install rapidfuzz)
"""
import os
import pandas as pd
from rapidfuzz import fuzz, process

MASTER_PATH = "project_master.csv"  # 컬럼: 사업코드, 사업명


def load_project_master() -> pd.DataFrame:
    if os.path.exists(MASTER_PATH):
        return pd.read_csv(MASTER_PATH)
    return pd.DataFrame(columns=["사업코드", "사업명"])


def build_master_from_budget(year: int) -> pd.DataFrame:
    """예산계획(budget_{year}.csv)의 '사업명'과 '예산과목'을 함께 뽑아 매칭용 마스터를 만든다."""
    path = f"budget_{year}.csv"
    empty = pd.DataFrame(columns=["사업코드", "사업명", "예산과목"])
    if not os.path.exists(path):
        return empty
    budget = pd.read_csv(path)
    if "사업명" not in budget.columns:
        return empty
    cols = ["사업명"] + (["예산과목"] if "예산과목" in budget.columns else [])
    sub = budget[cols].dropna(subset=["사업명"]).drop_duplicates().reset_index(drop=True)
    sub["사업코드"] = None
    if "예산과목" not in sub.columns:
        sub["예산과목"] = None
    return sub[["사업코드", "사업명", "예산과목"]]


EXTRA_PROJECTS_PATH = "extra_projects.csv"  # 예산계획엔 없지만 사용자가 '신규 사업'으로 확인한 것들


def load_extra_projects() -> pd.DataFrame:
    if os.path.exists(EXTRA_PROJECTS_PATH):
        df = pd.read_csv(EXTRA_PROJECTS_PATH)
        if "예산과목" not in df.columns:
            df["예산과목"] = None
        return df
    return pd.DataFrame(columns=["사업코드", "사업명", "예산과목"])


def add_extra_project(name: str, category: str = None):
    """신규 사업명을 (해당 예산과목과 함께) 추가 등록한다. 이후 같은 예산과목 안에서 매칭 후보로 재사용된다."""
    existing = load_extra_projects()
    if name in existing["사업명"].values:
        return existing
    updated = pd.concat(
        [existing, pd.DataFrame([{"사업코드": None, "사업명": name, "예산과목": category}])],
        ignore_index=True,
    )
    updated.to_csv(EXTRA_PROJECTS_PATH, index=False)
    return updated


def build_full_master(year: int) -> pd.DataFrame:
    """예산계획 기반 마스터 + 사용자가 등록한 신규 사업 목록을 합쳐서 반환한다."""
    budget_master = build_master_from_budget(year)
    extra = load_extra_projects()
    combined = pd.concat([budget_master, extra], ignore_index=True).drop_duplicates(subset="사업명")
    return combined.reset_index(drop=True)


def save_project_master(df: pd.DataFrame):
    df.to_csv(MASTER_PATH, index=False)


def match_text(text: str, master: pd.DataFrame, top_n: int = 3) -> list:
    """텍스트 하나에 대해 사업명 후보 top_n개를 유사도 순으로 반환"""
    names = master["사업명"].astype(str).tolist()
    codes = master["사업코드"].tolist()
    results = process.extract(str(text), names, scorer=fuzz.ratio, limit=top_n)
    return [(codes[idx], name, score / 100) for name, score, idx in results]


def match_dataframe(df: pd.DataFrame, master: pd.DataFrame, text_col: str = "전표헤더텍스트", progress_callback=None) -> pd.DataFrame:
    """
    df의 각 행에 가장 유사한 사업을 매칭해서 사업코드/사업명/매칭확신도 컬럼을 추가한다.
    확신도가 낮은 순으로 정렬해서 검토가 필요한 것을 위로 올린다.
    progress_callback(fraction: float)이 주어지면 계산 도중 진행률(0~1)을 알려준다 (전표 건수가 많을 때 유용).
    """
    total = len(df)
    if master.empty:
        out = df.copy()
        out["사업코드"] = None
        out["사업명"] = "미매칭(마스터 없음)"
        out["매칭확신도"] = 0.0
        return out

    names = master["사업명"].astype(str).tolist()
    codes = master["사업코드"].tolist()
    texts = df[text_col].astype(str).tolist()

    best_names, best_codes, best_scores = [], [], []
    step = max(1, total // 50)

    for i, text in enumerate(texts):
        match_name, score, idx = process.extractOne(text, names, scorer=fuzz.ratio)
        best_names.append(match_name)
        best_codes.append(codes[idx])
        best_scores.append(round(score / 100, 2))
        if progress_callback and (i % step == 0 or i == total - 1):
            progress_callback((i + 1) / total)

    out = df.copy()
    out["사업코드"] = best_codes
    out["사업명"] = best_names
    out["매칭확신도"] = best_scores
    return out.sort_values("매칭확신도").reset_index(drop=True)


def match_dataframe_by_category(
    df: pd.DataFrame,
    master: pd.DataFrame,
    category_col: str = "계정과목",
    master_category_col: str = "예산과목",
    text_col: str = "전표헤더텍스트",
    progress_callback=None,
) -> pd.DataFrame:
    """
    전표의 계정과목(예산과목)이 같은 사업명 후보끼리만 유사도 매칭한다.
    예) '수선유지비-건물/구축물' 전표는 같은 예산과목의 사업명 중에서만 후보를 찾는다.
    이렇게 하면 서로 다른 예산과목끼리 잘못 매칭되는 걸 막고, 계산량도 줄어든다.

    이미 저장된 데이터는 예산과목명이 정규화되기 전 표기(별칭)로 남아있을 수 있으므로,
    비교 직전에 양쪽 다 정규화해서 표기가 달라도 같은 예산과목으로 인식하게 한다.
    """
    from builtin_categories import normalize_account_name

    if master.empty or master_category_col not in master.columns or category_col not in df.columns:
        return match_dataframe(df, master, text_col=text_col, progress_callback=progress_callback)

    df = df.copy()
    master = master.copy()
    df[category_col] = df[category_col].apply(normalize_account_name)
    master[master_category_col] = master[master_category_col].apply(normalize_account_name)

    total = len(df)
    processed = 0
    out_frames = []

    for category, sub_df in df.groupby(category_col, dropna=False):
        sub_master = master[master[master_category_col] == category]
        if sub_master.empty:
            r = sub_df.copy()
            r["사업코드"] = None
            r["사업명"] = f"미매칭(예산과목 '{category}'에 등록된 사업 없음)"
            r["매칭확신도"] = 0.0
        else:
            r = match_dataframe(sub_df, sub_master[["사업코드", "사업명"]].reset_index(drop=True), text_col=text_col)
        out_frames.append(r)
        processed += len(sub_df)
        if progress_callback:
            progress_callback(min(processed / total, 1.0))

    result = pd.concat(out_frames, ignore_index=True)
    return result.sort_values("매칭확신도").reset_index(drop=True)


# 이 확신도 미만이면 화면에서 '검토 필요' 항목으로 분류한다 (사업 매칭).
MATCH_CONFIDENCE_THRESHOLD = 0.6

SMALL_AMOUNT_THRESHOLD = 2_000_000  # 이 금액 이하는 개별 매칭 대신 자동으로 묶어서 확정
SMALL_VALUE_ELIGIBLE_KEYWORD = "열원보완및개선"  # 이 예산과목(계정과목)에 한해서만 소액 자동분류 적용

SMALL_VALUE_LABEL = "설비개선, 보완 및 소액구매"


def suggest_low_value_buckets(
    df: pd.DataFrame,
    amount_col: str = "금액",
    site_col: str = "사업장",
    text_col: str = "전표헤더텍스트",
    category_col: str = "계정과목",
    threshold: float = SMALL_AMOUNT_THRESHOLD,
) -> pd.DataFrame:
    """
    금액이 threshold 이하이면서, 예산과목(계정과목)이 '열원보완개선및기타'인 건들만
    지사별로 묶어 '{지사} 설비개선, 보완 및 소액구매'로 자동 분류 대상을 만든다.
    다른 예산과목의 소액 건은 이 자동분류 대상에서 제외되고 개별 검토로 남는다.
    추천 사업명, 건수, 합계금액, 해당 행 인덱스 목록을 반환한다.
    """
    from mapping_config import get_site_display_name
    from builtin_categories import normalize_account_name

    if category_col in df.columns:
        normalized_cat = df[category_col].apply(normalize_account_name).astype(str)
        eligible_mask = normalized_cat.str.contains(SMALL_VALUE_ELIGIBLE_KEYWORD, na=False)
    else:
        eligible_mask = pd.Series(False, index=df.index)  # 계정과목 정보가 없으면 안전하게 자동분류 대상 없음

    small = df[(df[amount_col] <= threshold) & eligible_mask].copy()
    empty_result = pd.DataFrame(columns=["사업장", "추천사업명", "건수", "합계금액", "행인덱스"])
    if small.empty:
        return empty_result

    small[site_col] = small[site_col].fillna("미지정")

    rows = []
    for site, group in small.groupby(site_col, dropna=False):
        display_site = get_site_display_name(site)
        rows.append({
            "사업장": site,
            "사업장표시명": display_site,
            "추천사업명": f"{display_site} {SMALL_VALUE_LABEL}",
            "건수": len(group),
            "합계금액": group[amount_col].sum(),
            "행인덱스": group.index.tolist(),
        })
    if not rows:
        return empty_result
    return pd.DataFrame(rows).sort_values("합계금액", ascending=False).reset_index(drop=True)


# 예산과목당 사업이 정확히 1개뿐이라, 개별 매칭 없이 전부 그 사업으로 합쳐도 되는 예산과목 목록
SINGLE_PROJECT_CATEGORIES = ["외주비-열원정기점검"]


def apply_single_project_override(matched: pd.DataFrame, master: pd.DataFrame,
                                   categories: list = None, category_col: str = "계정과목") -> pd.DataFrame:
    """
    지정된 예산과목에 대해, 예산계획(master)에 사업이 정확히 1개만 있으면
    그 예산과목의 모든 행을 그 사업 하나로 강제 배정한다(확신도 100%로 처리).
    사업이 0개나 2개 이상이면 안전하게 건너뛰고 기존 매칭 결과를 그대로 둔다.
    예산과목명 표기가 서로 다를 수 있어(별칭), 비교 전 정규화한다.
    """
    from builtin_categories import normalize_account_name

    if categories is None:
        categories = SINGLE_PROJECT_CATEGORIES
    if category_col not in matched.columns or "예산과목" not in master.columns:
        return matched

    matched = matched.copy()
    master = master.copy()
    matched[category_col] = matched[category_col].apply(normalize_account_name)
    master["예산과목"] = master["예산과목"].apply(normalize_account_name)

    for cat in categories:
        cat = normalize_account_name(cat)
        candidates = master[master["예산과목"] == cat]["사업명"].dropna().unique()
        if len(candidates) != 1:
            continue  # 사업이 없거나 여러 개면 자동배정하지 않음(개별 검토로 남김)
        project_name = candidates[0]
        mask = matched[category_col] == cat
        if not mask.any():
            continue
        match_row = master[master["사업명"] == project_name]
        project_code = match_row["사업코드"].iloc[0] if not match_row.empty else None

        matched.loc[mask, "사업명"] = project_name
        matched.loc[mask, "사업코드"] = project_code
        matched.loc[mask, "매칭확신도"] = 1.0

    return matched


UNCATEGORIZED_SUFFIX = "_미분류"


def suggest_uncategorized_buckets(
    df: pd.DataFrame,
    category_col: str = "계정과목",
    amount_col: str = "금액",
) -> pd.DataFrame:
    """
    남은 항목들을 예산과목별로 묶어 '{예산과목}_미분류' 후보를 만든다.
    다른 규칙(소액 자동확정, 단일사업 강제배정)으로 처리되지 않고 남은 항목들의 최종 받침 그룹이다.
    확정 여부는 화면에서 사람이 직접 눌러야 반영된다(자동확정 아님).
    """
    empty_result = pd.DataFrame(columns=["예산과목", "추천사업명", "건수", "합계금액", "행인덱스"])
    if category_col not in df.columns or df.empty:
        return empty_result

    rows = []
    for cat, group in df.groupby(category_col, dropna=False):
        cat_label = str(cat) if pd.notna(cat) else "미지정"
        rows.append({
            "예산과목": cat,
            "추천사업명": f"{cat_label}{UNCATEGORIZED_SUFFIX}",
            "건수": len(group),
            "합계금액": group[amount_col].sum() if amount_col in group.columns else 0,
            "행인덱스": group.index.tolist(),
        })
    if not rows:
        return empty_result
    return pd.DataFrame(rows).sort_values("합계금액", ascending=False).reset_index(drop=True)