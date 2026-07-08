"""
업로드된 엑셀을 검증한다.
- 컬럼은 이름이 아니라 위치(E,G,L,N,O)로 읽는다.
- 행 단위로 문제를 찾아 '치명적' / '경고' 로 구분한다.
"""
import pandas as pd

COL_IDX = {"거래처명": 4, "사업장": 6, "전기일": 11, "전표헤더텍스트": 13, "금액": 14}
VALID_SITE_CODES = {1, 2, 3, 4, 5}  # 등록된 사업장 코드 (추후 실제 매핑표로 교체)


def validate_upload(file_path: str, year: int):
    raw = pd.read_excel(file_path, header=0)

    errors = []
    parsed_rows = []

    for i, row in raw.iterrows():
        excel_row_no = i + 2  # 헤더(1행) + 0-based index 보정
        amt = row.iloc[COL_IDX["금액"]]
        site = row.iloc[COL_IDX["사업장"]]
        date_val = row.iloc[COL_IDX["전기일"]]
        text = row.iloc[COL_IDX["전표헤더텍스트"]]
        vendor = row.iloc[COL_IDX["거래처명"]]

        # 치명적 오류: 금액 없음
        if pd.isna(amt):
            errors.append({"row": excel_row_no, "level": "critical", "type": "금액 없음", "detail": "O열 값이 비어있음"})
            continue

        # 치명적 오류: 날짜 파싱 불가
        try:
            parsed_date = pd.to_datetime(date_val)
        except Exception:
            errors.append({"row": excel_row_no, "level": "critical", "type": "날짜 형식 오류", "detail": f"L열 '{date_val}'"})
            continue

        # 경고: 사업장 코드가 등록되지 않음
        if pd.notna(site) and int(site) not in VALID_SITE_CODES:
            errors.append({"row": excel_row_no, "level": "warning", "type": "사업장 코드 이상", "detail": f"G열 값 '{int(site)}' (미등록 코드)"})

        # 경고: 전기일 연도가 선택한 연도와 다름 (업로드 실수 감지)
        if parsed_date.year != year:
            errors.append({"row": excel_row_no, "level": "warning", "type": "연도 불일치", "detail": f"선택연도 {year}, 실제 {parsed_date.year}"})

        parsed_rows.append({
            "거래처명": vendor, "사업장": site, "전기일": parsed_date, "전표헤더텍스트": text, "금액": amt,
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
    }
