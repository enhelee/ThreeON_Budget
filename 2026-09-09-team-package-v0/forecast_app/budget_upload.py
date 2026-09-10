"""
예산 계획 업로드 파서.
한 워크북 안에 3개 시트가 함께 들어있는 실제 양식을 그대로 처리한다:
  - 양식1(월별): 실제 예산 계획 라인아이템 (헤더는 3번째 행부터)
  - 예산코드:   계정코드 -> 이름/주관부서코드/속성 마스터
  - 부서코드:   부서코드 -> 부서명/처.지사 마스터
"""
import pandas as pd
import re

SHEET_FORM = "양식1(월별)"
SHEET_ACCOUNT = "예산코드"
SHEET_DEPT = "부서코드"

MONTH_COLS = [f"{m}월" for m in range(1, 13)]

FORM_REQUIRED = ["예산귀속 \n부서코드", "예산코드", "예산과목", "연예산 합계"]

# 양식 상단에 '[단위 : 천원, 부가세 별도]'라고 명시되어 있어, 원본 값은 천원 단위다.
# 실적데이터(zrfm2/fbl3n)는 원(원) 단위로 그대로 들어오므로, 저장 시점에 미리 원 단위로 환산해
# 시스템 내부에서는 항상 같은 단위(원)를 쓰도록 통일한다.
UNIT_SCALE = 1000
AMOUNT_COLS_TO_SCALE = ["연예산 합계"] + MONTH_COLS


def _normalize_code(x) -> str:
    """
    코드를 비교 가능한 형태로 정규화한다.
    - 엑셀이 숫자로 읽어 '60909007.0'처럼 된 것을 '60909007'로 되돌림
    - 하이픈(-), 점(.), 공백 등 구분기호를 제거해 표기 차이를 무시하고 비교
    """
    if pd.isna(x):
        return ""
    s = str(x).strip()
    if re.fullmatch(r"\d+\.0+", s):  # 60909007.0 -> 60909007
        s = s.split(".")[0]
    s = re.sub(r"[\s\-\._]", "", s)  # 구분기호 제거
    return s.upper()


def _dedupe_columns(cols):
    """양식에 '12월'이 중복 등으로 두 번 나오는 경우 등을 안전하게 처리"""
    seen = {}
    out = []
    for c in cols:
        c = str(c).strip()
        if c in seen:
            seen[c] += 1
            out.append(f"{c}_{seen[c]}")
        else:
            seen[c] = 0
            out.append(c)
    return out


def parse_budget_workbook(file_path: str) -> dict:
    """세 시트를 모두 읽어 dict로 반환: {'form':.., 'account_master':.., 'dept_master':..}"""
    # ExcelFile을 명시적으로 닫아야 한다 - 안 닫으면 Windows에서 파일 핸들이 남아있어
    # 곧바로 임시파일을 지우려 할 때 PermissionError(WinError 32)가 날 수 있다.
    with pd.ExcelFile(file_path) as xls:
        missing_sheets = [s for s in [SHEET_FORM, SHEET_ACCOUNT, SHEET_DEPT] if s not in xls.sheet_names]
    if missing_sheets:
        raise ValueError(f"다음 시트를 찾을 수 없습니다: {', '.join(missing_sheets)}")

    form = pd.read_excel(file_path, sheet_name=SHEET_FORM, header=2)
    form.columns = _dedupe_columns(form.columns)
    form = form.dropna(how="all").reset_index(drop=True)
    # '사업명'이 비어있는 행은 실제 예산 라인이 아니라 빈 템플릿 행으로 간주하고 제외한다.
    if "사업명" in form.columns:
        form = form[form["사업명"].notna() & (form["사업명"].astype(str).str.strip() != "")].reset_index(drop=True)

    account_master = pd.read_excel(file_path, sheet_name=SHEET_ACCOUNT, header=0)
    account_master = account_master.dropna(how="all").reset_index(drop=True)

    dept_master = pd.read_excel(file_path, sheet_name=SHEET_DEPT, header=0)
    dept_master = dept_master.dropna(how="all").reset_index(drop=True)

    return {"form": form, "account_master": account_master, "dept_master": dept_master}


def validate_budget_form(form: pd.DataFrame, account_master: pd.DataFrame, dept_master: pd.DataFrame) -> dict:
    errors = []

    missing_cols = [c for c in FORM_REQUIRED if c not in form.columns]
    if missing_cols:
        return {
            "row_count": len(form), "error_count": len(form),
            "errors": [{"row": 0, "level": "critical", "type": "필수 컬럼 없음",
                        "detail": f"다음 컬럼을 찾을 수 없습니다: {', '.join(missing_cols)}"}],
            "data": pd.DataFrame(),
        }

    known_accounts = {_normalize_code(x) for x in account_master.iloc[:, 0]} if not account_master.empty else set()
    known_depts = {_normalize_code(x) for x in dept_master.iloc[:, 0]} if not dept_master.empty else set()

    for i, row in form.iterrows():
        excel_row_no = i + 4  # 헤더가 3행(0-index 2)이므로 데이터는 4행부터
        budget_sum = row.get("연예산 합계")
        acct_code = row.get("예산코드")
        dept_code = row.get("예산귀속 \n부서코드")

        if pd.isna(budget_sum):
            errors.append({"row": excel_row_no, "level": "critical", "type": "연예산 합계 없음", "detail": "금액이 비어있음"})
            continue

        if pd.notna(acct_code) and known_accounts and _normalize_code(acct_code) not in known_accounts:
            errors.append({"row": excel_row_no, "level": "warning", "type": "예산코드 미등록",
                           "detail": f"'예산코드' 시트에 없는 코드: {acct_code}"})

        if pd.notna(dept_code) and known_depts and _normalize_code(dept_code) not in known_depts:
            errors.append({"row": excel_row_no, "level": "warning", "type": "부서코드 미등록",
                           "detail": f"'부서코드' 시트에 없는 코드: {dept_code}"})

    critical = sum(1 for e in errors if e["level"] == "critical")
    warning = sum(1 for e in errors if e["level"] == "warning")

    # 양식 단위(천원)를 시스템 내부 저장 단위(원)로 환산 - 실적데이터(원 단위)와 맞추기 위함
    data_out = form.copy()
    for col in AMOUNT_COLS_TO_SCALE:
        if col in data_out.columns:
            data_out[col] = pd.to_numeric(data_out[col], errors="coerce") * UNIT_SCALE

    # 예산과목명 표기 차이(별칭)를 정식 명칭으로 통일 (예: '...보완개선및기타' -> '...보완및개선')
    if "예산과목" in data_out.columns:
        from builtin_categories import normalize_account_name
        data_out["예산과목"] = data_out["예산과목"].apply(normalize_account_name)

    return {
        "row_count": len(form),
        "critical_count": critical,
        "warning_count": warning,
        "error_count": critical + warning,
        "errors": errors,
        "data": data_out,
    }
