"""
업로드된 엑셀을 검증한다.
- 실제 ERP(ZRFM2) export의 컬럼명으로 읽는다 (위치가 아니라 이름 기준 — 컬럼 순서가 바뀌어도 안전).
- 행 단위로 문제를 찾아 '치명적' / '경고' 로 구분한다.
"""
import pandas as pd
import re
from openpyxl import load_workbook
from builtin_categories import normalize_account_name

SUMMARY_KEYWORDS = ["합계", "총계", "소계", "합 계", "총 계", "Total", "TOTAL"]


def _is_yellow_fill(cell) -> bool:
    """
    셀 배경색이 노란색 계열인지 확인한다.
    RGB(ARGB) 값으로 저장된 채우기만 인식하며, 테마 색상(theme color) 인덱스로 저장된
    채우기는 판단하지 못한다 (그 경우 아래 키워드/구조적 특징 판단으로 대체된다).
    """
    fill = cell.fill
    if not fill or fill.fgColor is None:
        return False
    rgb = fill.fgColor.rgb
    if rgb and isinstance(rgb, str):
        rgb = rgb.upper()
        # FFFFFF00, FFFFFF33 등 - 노란색 계열(R,G 높고 B 낮음)
        if len(rgb) == 8:  # ARGB
            r, g, b = int(rgb[2:4], 16), int(rgb[4:6], 16), int(rgb[6:8], 16)
            if r > 200 and g > 200 and b < 120:
                return True
    return False


def _row_has_summary_keyword(values) -> bool:
    for v in values:
        if isinstance(v, str) and any(k in v for k in SUMMARY_KEYWORDS):
            return True
    return False


def detect_summary_row(file_path: str):
    """
    마지막 데이터 행이 '합계행'으로 추정되면 그 행의 엑셀 행 번호(1-based)를 반환, 아니면 None.
    다음 중 하나라도 해당하면 합계행으로 판단한다.
    - 노란색 배경
    - '합계/총계' 같은 단어 포함
    - 금액은 있는데 사업장·계정과목·전기일·거래처명이 전부 비어있음 (구조적 특징 - 색/텍스트가 안 잡혀도 감지)
    """
    wb = load_workbook(file_path, data_only=True)
    ws = wb.active
    last_row = ws.max_row
    if not last_row or last_row < 2:
        return None

    row_cells = list(ws[last_row])
    row_values = [c.value for c in row_cells]

    if all(v is None for v in row_values):
        return None  # 완전히 빈 행이면 별도 처리 불필요 (pandas가 이미 무시함)

    is_yellow = any(_is_yellow_fill(c) for c in row_cells)
    has_keyword = _row_has_summary_keyword(row_values)

    # 헤더에서 핵심 컬럼 위치를 찾아 구조적 특징도 함께 확인
    header_row = [c.value for c in ws[1]]
    col_idx = {name: header_row.index(col) for name, col in REQUIRED_COLUMNS.items() if col in header_row}

    def _get(field):
        idx = col_idx.get(field)
        return row_values[idx] if idx is not None and idx < len(row_values) else None

    amt = _get("금액")
    key_fields_blank = all(
        _get(f) is None or (isinstance(_get(f), str) and _get(f).strip() == "")
        for f in ["사업장", "계정과목", "전기일", "거래처명"]
    )
    is_structural_summary = amt is not None and key_fields_blank

    if is_yellow or has_keyword or is_structural_summary:
        return last_row
    return None


# 실제 FM(ZRFM2) export 컬럼명. 컬럼 순서가 바뀌어도 이름으로 찾으므로 안전하다.
REQUIRED_COLUMNS = {
    "거래처명": "공급업체",              # 협력업체/거래처
    "사업장": "손익 센터",                # 지사/사업소 구분
    "전기일": "FM 전기일",                # 실제 자금 집행일
    "전표헤더텍스트": "텍스트",           # 투자유형·사업 유추용 자유텍스트
    "금액": "FM 영역통화로 표시된 지급예산금액",  # 실적 금액
    "계정과목": "약정항목 텍스트",        # 예산과목 (예: 수선유지비-건물/구축물)
}
VALID_SITE_CODES = None  # 사업장은 이제 이름 문자열이라 코드 검증은 mapping_config에서 처리

TRANSACTION_CODE_COL = "트랜잭션 코드"
EXCLUDED_TRANSACTION_CODES = {"KSV5"}  # 이 코드가 있는 행은 분류 대상에서 제외

DOC_NO_COL = "전표 번호"
REVERSAL_COL = "역분개"


def _find_column(columns, target):
    """공백 표기 차이를 무시하고 컬럼을 찾는다"""
    def norm(s):
        return str(s).replace(" ", "").replace("\u3000", "").strip().upper()
    for col in columns:
        if norm(col) == norm(target):
            return col
    return None


def _normalize_doc_no(v) -> str:
    if pd.isna(v):
        return ""
    s = str(v).strip()
    if re.fullmatch(r"\d+\.0+", s):
        s = s.split(".")[0]
    return s


def _doc_key(v) -> str:
    """전표번호 비교용 키. 앞자리 0 차이(예: '0012345' vs '12345')도 같은 것으로 취급한다."""
    s = _normalize_doc_no(v)
    if not s:
        return ""
    stripped = s.lstrip("0")
    return stripped if stripped else "0"


def exclude_reversal_pairs(raw: pd.DataFrame, amount_col: str):
    """
    '역분개' 컬럼에 원본 전표번호가 적혀있고, 그 원본 전표와 금액을 더하면 0이 되는
    상쇄쌍(원본 + 역분개 취소전표)을 찾아 둘 다 제외한다.
    """
    doc_col = _find_column(raw.columns, DOC_NO_COL)
    rev_col = _find_column(raw.columns, REVERSAL_COL)
    if doc_col is None or rev_col is None:
        return raw, 0

    doc_to_indices = {}
    for idx, val in raw[doc_col].items():
        key = _doc_key(val)
        if key:
            doc_to_indices.setdefault(key, []).append(idx)

    amounts = pd.to_numeric(raw[amount_col], errors="coerce")
    to_exclude = set()

    for idx, rev_val in raw[rev_col].items():
        key = _doc_key(rev_val)
        if not key:
            continue
        for orig_idx in doc_to_indices.get(key, []):
            if orig_idx == idx:
                continue
            amt_sum = amounts.get(idx, float("nan")) + amounts.get(orig_idx, float("nan"))
            if pd.notna(amt_sum) and abs(amt_sum) < 1:
                to_exclude.add(idx)
                to_exclude.add(orig_idx)

    if not to_exclude:
        return raw, 0

    kept = raw.drop(index=list(to_exclude)).reset_index(drop=True)
    return kept, len(to_exclude)


REFERENCE_DOC_COL = "참조 전표 번호"
STAMP_TAX_KEYWORD = "인지세"


def merge_stamp_tax_rows(raw: pd.DataFrame, text_col: str, amount_col: str):
    """
    전표헤더텍스트에 '인지세'가 포함된 행을 찾아서, 같은 '참조 전표 번호'를 가진
    다른(인지세가 아닌) 행에 금액을 합치고, 인지세 행 자체는 제거한다.
    같은 참조번호의 다른 행을 못 찾으면 그대로 둔다(개별 검토 대상으로 남김).
    """
    ref_col = _find_column(raw.columns, REFERENCE_DOC_COL)
    if ref_col is None or text_col not in raw.columns or amount_col not in raw.columns:
        return raw, 0

    is_stamp = raw[text_col].astype(str).str.contains(STAMP_TAX_KEYWORD, na=False)
    if not is_stamp.any():
        return raw, 0

    raw = raw.copy()
    raw[amount_col] = pd.to_numeric(raw[amount_col], errors="coerce")
    ref_norm = raw[ref_col].apply(_doc_key)

    to_drop = []
    for idx in raw.index[is_stamp]:
        ref_val = ref_norm.loc[idx]
        if not ref_val:
            continue
        candidates = raw.index[(ref_norm == ref_val) & (~is_stamp) & (raw.index != idx)]
        if len(candidates) == 0:
            continue
        target_idx = candidates[0]
        current_target_amt = raw.at[target_idx, amount_col]
        current_stamp_amt = raw.at[idx, amount_col]
        raw.at[target_idx, amount_col] = (current_target_amt if pd.notna(current_target_amt) else 0) + \
                                          (current_stamp_amt if pd.notna(current_stamp_amt) else 0)
        to_drop.append(idx)

    if not to_drop:
        return raw, 0

    merged = raw.drop(index=to_drop).reset_index(drop=True)
    return merged, len(to_drop)


def exclude_offsetting_text_pairs(raw: pd.DataFrame, text_col: str, amount_col: str):
    """
    전표헤더텍스트가 동일한 행들 중에서, +금액 행과 -금액 행을 짝지어
    두 금액의 합이 0이 되는 쌍을 찾아 둘 다 제외한다. (전표번호/참조번호와 무관하게 텍스트 기준)
    한 텍스트 그룹 안에 여러 쌍이 있으면 가능한 만큼 모두 짝지어 제외한다.
    """
    if text_col not in raw.columns or amount_col not in raw.columns:
        return raw, 0

    amounts = pd.to_numeric(raw[amount_col], errors="coerce")
    texts = raw[text_col].astype(str)

    to_exclude = set()
    for _, group_idx in raw.groupby(texts).groups.items():
        idx_list = list(group_idx)
        if len(idx_list) < 2:
            continue
        used = set()
        for i in idx_list:
            if i in used:
                continue
            amt_i = amounts.get(i)
            if pd.isna(amt_i) or amt_i == 0:
                continue
            for j in idx_list:
                if j == i or j in used:
                    continue
                amt_j = amounts.get(j)
                if pd.notna(amt_j) and abs(amt_i + amt_j) < 1:
                    used.add(i)
                    used.add(j)
                    break
        to_exclude |= used

    if not to_exclude:
        return raw, 0

    kept = raw.drop(index=list(to_exclude)).reset_index(drop=True)
    return kept, len(to_exclude)


# 특정 예산과목에서 텍스트가 비어있을 때 자동으로 채워줄 규칙 (날짜 + 키워드 + " 구매")
AUTO_TEXT_RULES = {
    "건설중인자산-재생고온부품": "재생고온부품 구매",
    "건설중인자산-자산화예비품": "자산화예비품 구매",
    "저장품-열원(보수)": "저장품 구매",
}


def fill_missing_text_by_category(raw: pd.DataFrame, text_col: str, category_col: str, date_col: str):
    """
    category_col 값이 AUTO_TEXT_RULES에 해당하는 행은, 기존 텍스트가 있든 없든
    '{date_col 날짜}{키워드}' 형식으로 텍스트를 항상 덮어쓴다.
    (해당 예산과목이 아니면 손대지 않는다)
    """
    if text_col not in raw.columns or category_col not in raw.columns or date_col not in raw.columns:
        return raw, 0

    raw = raw.copy()
    filled_count = 0

    for idx, row in raw.iterrows():
        category_val = row[category_col]
        if pd.isna(category_val):
            continue
        suffix = AUTO_TEXT_RULES.get(str(category_val).strip())
        if suffix is None:
            continue  # 대상 예산과목이 아니면 기존 텍스트 그대로 둠

        date_val = row[date_col]
        try:
            date_str = pd.to_datetime(date_val).strftime("%Y-%m-%d")
        except Exception:
            date_str = str(date_val).strip() if pd.notna(date_val) else ""

        raw.at[idx, text_col] = f"{date_str}{suffix}"
        filled_count += 1

    return raw, filled_count


def validate_upload(file_path: str, year: int):
    raw = pd.read_excel(file_path, header=0)

    # 특정 예산과목의 빈 텍스트를 날짜+키워드로 자동 채움 (다른 필터보다 먼저 - 빈 텍스트끼리 잘못 묶이는 것 방지)
    filled_text_count = 0
    if REQUIRED_COLUMNS["전표헤더텍스트"] in raw.columns and REQUIRED_COLUMNS["계정과목"] in raw.columns \
            and REQUIRED_COLUMNS["전기일"] in raw.columns:
        raw, filled_text_count = fill_missing_text_by_category(
            raw, REQUIRED_COLUMNS["전표헤더텍스트"], REQUIRED_COLUMNS["계정과목"], REQUIRED_COLUMNS["전기일"]
        )

    summary_excluded = None
    amount_col = REQUIRED_COLUMNS["금액"]
    is_sum_match = False
    if amount_col in raw.columns and len(raw) >= 2:
        amounts = pd.to_numeric(raw[amount_col], errors="coerce")
        last_amt = amounts.iloc[-1]
        rest_sum = amounts.iloc[:-1].sum()
        if pd.notna(last_amt) and abs(last_amt - rest_sum) < 1:  # 반올림 오차 허용
            is_sum_match = True

    summary_row_no = None if is_sum_match else detect_summary_row(file_path)

    if is_sum_match or summary_row_no is not None:
        drop_idx = len(raw) - 1
        summary_excluded = raw.iloc[drop_idx].to_dict()
        raw = raw.iloc[:-1].reset_index(drop=True)

    # 트랜잭션 코드가 특정 값(예: KSV5)인 행은 분류 대상에서 제외
    # 컬럼명 표기가 살짝 다를 수 있어(공백 위치 등) 공백을 무시하고 컬럼을 찾는다.
    excluded_by_code_count = 0

    def _norm(s):
        return str(s).replace(" ", "").replace("\u3000", "").strip().upper()

    target_col = None
    for col in raw.columns:
        if _norm(col) == _norm(TRANSACTION_CODE_COL):
            target_col = col
            break

    if target_col is not None:
        code_series = raw[target_col].apply(_norm)
        exclude_mask = code_series.isin({_norm(c) for c in EXCLUDED_TRANSACTION_CODES})
        excluded_by_code_count = int(exclude_mask.sum())
        raw = raw[~exclude_mask].reset_index(drop=True)

    # 역분개(취소전표) - 원본전표 상쇄쌍 제외
    raw, excluded_by_reversal_count = exclude_reversal_pairs(raw, REQUIRED_COLUMNS["금액"])

    # 인지세 - 같은 참조전표번호의 다른 행에 금액 합치고 인지세 행은 제거
    merged_stamp_tax_count = 0
    if REQUIRED_COLUMNS["전표헤더텍스트"] in raw.columns and REQUIRED_COLUMNS["금액"] in raw.columns:
        raw, merged_stamp_tax_count = merge_stamp_tax_rows(
            raw, REQUIRED_COLUMNS["전표헤더텍스트"], REQUIRED_COLUMNS["금액"]
        )

    # 같은 텍스트를 가진 +전표/-전표가 상쇄되면 둘 다 제외
    excluded_by_text_offset_count = 0
    if REQUIRED_COLUMNS["전표헤더텍스트"] in raw.columns and REQUIRED_COLUMNS["금액"] in raw.columns:
        raw, excluded_by_text_offset_count = exclude_offsetting_text_pairs(
            raw, REQUIRED_COLUMNS["전표헤더텍스트"], REQUIRED_COLUMNS["금액"]
        )

    missing = [REQUIRED_COLUMNS[k] for k in REQUIRED_COLUMNS if REQUIRED_COLUMNS[k] not in raw.columns]
    if missing:
        return {
            "row_count": len(raw), "valid_row_count": 0, "critical_count": len(raw), "warning_count": 0,
            "error_count": len(raw),
            "errors": [{"row": 0, "level": "critical", "type": "필수 컬럼 없음",
                        "detail": f"엑셀에서 다음 컬럼을 찾을 수 없습니다: {', '.join(missing)}"}],
            "data": pd.DataFrame(),
            "summary_row_excluded": summary_excluded,
            "excluded_by_code_count": excluded_by_code_count,
            "excluded_by_reversal_count": excluded_by_reversal_count,
            "merged_stamp_tax_count": merged_stamp_tax_count,
            "excluded_by_text_offset_count": excluded_by_text_offset_count,
            "filled_text_count": filled_text_count,
        }

    errors = []
    parsed_rows = []

    for i, row in raw.iterrows():
        excel_row_no = i + 2  # 헤더(1행) + 0-based index 보정
        amt = row[REQUIRED_COLUMNS["금액"]]
        site = row[REQUIRED_COLUMNS["사업장"]]
        date_val = row[REQUIRED_COLUMNS["전기일"]]
        text = row[REQUIRED_COLUMNS["전표헤더텍스트"]]
        vendor = row[REQUIRED_COLUMNS["거래처명"]]
        account = row[REQUIRED_COLUMNS["계정과목"]]

        # 치명적 오류: 금액 없음
        if pd.isna(amt):
            errors.append({"row": excel_row_no, "level": "critical", "type": "금액 없음", "detail": "금액(현지 통화) 값이 비어있음"})
            continue

        # 치명적 오류: 날짜 파싱 불가
        try:
            parsed_date = pd.to_datetime(date_val)
        except Exception:
            errors.append({"row": excel_row_no, "level": "critical", "type": "날짜 형식 오류", "detail": f"전기일 '{date_val}'"})
            continue

        # 경고: 사업장 값이 비어있음
        if pd.isna(site) or str(site).strip() == "":
            errors.append({"row": excel_row_no, "level": "warning", "type": "사업장 비어있음", "detail": "사업장 값이 없음"})

        # 경고: 계정과목 비어있음
        if pd.isna(account) or str(account).strip() == "":
            errors.append({"row": excel_row_no, "level": "warning", "type": "계정과목 비어있음", "detail": "예산과목 매핑 불가"})

        # 경고: 전기일 연도가 선택한 연도와 다름 (업로드 실수 감지)
        if parsed_date.year != year:
            errors.append({"row": excel_row_no, "level": "warning", "type": "연도 불일치", "detail": f"선택연도 {year}, 실제 {parsed_date.year}"})

        parsed_rows.append({
            "거래처명": vendor, "사업장": site, "전기일": parsed_date,
            "전표헤더텍스트": text, "금액": amt, "계정과목": normalize_account_name(account),
        })

    critical_count = sum(1 for e in errors if e["level"] == "critical")
    warning_count = sum(1 for e in errors if e["level"] == "warning")

    return {
        "row_count": len(raw),
        "valid_row_count": len(parsed_rows),
        "critical_count": critical_count,
        "warning_count": warning_count,
        "error_count": critical_count + warning_count,
        "errors": errors,
        "data": pd.DataFrame(parsed_rows),
        "summary_row_excluded": summary_excluded,
        "excluded_by_code_count": excluded_by_code_count,
        "excluded_by_reversal_count": excluded_by_reversal_count,
        "merged_stamp_tax_count": merged_stamp_tax_count,
        "excluded_by_text_offset_count": excluded_by_text_offset_count,
        "filled_text_count": filled_text_count,
    }
