# -*- coding: utf-8 -*-
"""실적 산출물 작성: {연도}년 {손익|자본}예산_실적.xlsx + zrfm2_V1.

- 양식1(월별): 계획행(실적금액·구분 태깅) + 신규행 하단 추가.
- 종합표: 계획본과 동일 레이아웃, SUMIFS로 실적금액(K열)을 지사별 집계.
- 검토리포트: 미매핑 처지사, 미분류 과목, 연도 불일치 등.
- zrfm2_V1: 원본 유지 + R열에 매칭된 계획/신규 사업명.
"""
import openpyxl
import pandas as pd
from openpyxl.styles import Font, PatternFill

from . import loaders
from .config_store import SIMUI_THRESHOLD_THOUSAND
from . import excel_plan_writer as epw

# 양식3_R1 '25년 계획 대비 실적' 시트 포맷(9열) + 우리 분석열(4열).
ACTUAL_HEADER = [
    "연번", "예산과목", "속성", "주관부서명", "예산귀속 부서명(처.지사)",
    "예산귀속 부서명(부)", "사업명", "연예산(A)", "최종 실적금액(B)",
    "심의플래그", "구분", "비고", "매칭확신도",
]
NCOL = len(ACTUAL_HEADER)                 # 13
VALUE_COL_LETTER = "I"    # 9번 = 최종 실적금액(B)
ITEM_COL_LETTER = "B"     # 2번 = 예산과목
DEPT_COL_LETTER = "E"     # 5번 = 예산귀속 부서명(처.지사)
FLAG_COL_LETTER = "J"     # 10번 = 심의플래그
NEW_FILL = PatternFill(start_color="FFF2CC", end_color="FFF2CC", fill_type="solid")   # 신규(노랑)
MISSING_EXEC_FILL = PatternFill(start_color="F4CCCC", end_color="F4CCCC", fill_type="solid")  # 미시행(연빨강)

HEADER_ROW = epw.HEADER_ROW  # 3
DATA_START = 4


def _simui_flag(item_flags, item, base_amount):
    return "O" if item_flags.get(item) and base_amount is not None \
        and base_amount >= SIMUI_THRESHOLD_THOUSAND else ""


def _clean(val):
    return None if (val is None or (isinstance(val, float) and pd.isna(val))) else val


def write_actual_datasheet(ws, plan_rows, new_rows, budget, year, item_flags):
    ws.cell(1, 1, f"{year}년 {budget}예산 실적 (단위: 천원, 부가세 별도)")
    for i, h in enumerate(ACTUAL_HEADER, 1):
        c = ws.cell(HEADER_ROW, i, h)
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = epw.HEADER_FILL

    r = DATA_START
    seq = 0
    # 계획행: 1연번 2예산과목 3속성 4주관부서명 5처지사 6부서(팀) 7사업명 8연예산 9실적 10심의 11구분 12비고 13확신도
    for row in plan_rows:
        seq += 1
        ws.cell(r, 1, seq)
        ws.cell(r, 2, _clean(row.get("예산과목")))
        ws.cell(r, 3, _clean(row.get("속성")))
        ws.cell(r, 4, _clean(row.get("주관부서명")))
        ws.cell(r, 5, _clean(row.get("처지사")))
        ws.cell(r, 6, _clean(row.get("부서부")))
        ws.cell(r, 7, _clean(row.get("사업명")))
        ws.cell(r, 8, _clean(row.get("연예산")))
        ws.cell(r, 9, round(row.get("실적금액", 0.0)))
        ws.cell(r, 10, _simui_flag(item_flags, row.get("예산과목"), row.get("연예산")))
        ws.cell(r, 11, row.get("구분"))
        if row.get("구분") == "계획집행":
            note = f"매칭전표 {row.get('매칭전표수', 0)}건"
            low = row.get("저유사전표수", 0)
            if low:
                note += f" (저유사 {low}건)"
        elif row.get("구분") == "미시행":
            note = "계획O·실적X (실적 없음)"
        else:
            note = ""
        ws.cell(r, 12, note)
        conf = row.get("매칭확신도")
        ws.cell(r, 13, conf if conf is not None else None)
        if row.get("구분") == "미시행":
            for c in range(1, NCOL + 1):
                ws.cell(r, c).fill = MISSING_EXEC_FILL
        r += 1

    # 신규행
    for nr in new_rows:
        seq += 1
        ws.cell(r, 1, seq)
        ws.cell(r, 2, nr["예산과목"])
        ws.cell(r, 5, nr["처지사"])
        ws.cell(r, 7, nr["사업명"])
        ws.cell(r, 8, None)
        ws.cell(r, 9, round(nr["실적금액"]))
        ws.cell(r, 10, _simui_flag(item_flags, nr["예산과목"], nr["실적금액"]))
        ws.cell(r, 11, nr.get("구분", "신규"))
        ws.cell(r, 12, nr.get("비고", ""))
        for c in range(1, NCOL + 1):
            ws.cell(r, c).fill = NEW_FILL
        r += 1

    return {"written_rows": r - DATA_START}


def write_review_sheet(wb, review):
    ws = wb.create_sheet("검토리포트")
    ws.append(["■ 실적분석 검토리포트"])
    ws.append([])
    ws.append(["대상연도", review.get("year")])
    ws.append(["ERP 연도분포", str(review.get("year_dist"))])
    if review.get("year_mismatch"):
        ws.append(["⚠ 연도 불일치", review["year_mismatch"]])
    ws.append([])
    ws.append([f"■ 미매핑 처지사 (종합표 집계 누락 {review.get('unmatched_dept_amt', 0):,}천원 — 처지사_별칭.json 보강 필요)"])
    for d in review.get("unmatched_dept", []):
        ws.append([d])
    ws.append([])
    ws.append([f"■ 미분류(결측) 예산과목 — 사용자 예산과목 구성에 없음 ({review.get('unclassified_item_amt', 0):,}천원, 종합표 미반영)"])
    for it in review.get("unclassified_item", []):
        ws.append([it])
    ws.append([])
    ws.append([f"■ 미반영 전표 — 선택 안 된 예산과목·지사(구성 미포함/미분류/미매핑) ({review.get('unreflected_amt', 0):,}천원, 종합표·양식1 미포함)"])
    ws.append(["구분(과목/지사)", "금액(천원)", "전표수"])
    for row in review.get("unreflected_top", []):
        ws.append(list(row))
    ws.append([])
    ws.append(["■ 요약"])
    for k, v in review.get("summary", {}).items():
        ws.append([k, v])


def write_actual_workbook(out_path, plan_rows, new_rows, dept_columns, item_rows,
                          budget, year, review):
    item_flags = {it["과목"]: it["심의대상"] for cat in item_rows for it in cat["과목들"]}
    wb = openpyxl.Workbook()
    ds = wb.active
    ds.title = "양식1(월별)"
    write_actual_datasheet(ds, plan_rows, new_rows, budget, year, item_flags)
    sm = wb.create_sheet("종합표")
    layout = epw.build_summary_layout(sm, dept_columns, item_rows, budget, year, kind="실적")
    epw.write_summary_formulas(
        sm, layout, value_col=VALUE_COL_LETTER,
        item_col=ITEM_COL_LETTER, dept_col=DEPT_COL_LETTER, flag_col=FLAG_COL_LETTER,
    )
    write_review_sheet(wb, review)
    wb.save(out_path)
    wb.close()


UNREFLECTED_FILL = PatternFill(start_color="E2E2E2", end_color="E2E2E2", fill_type="solid")  # 미반영(연회색)


def write_zrfm2_v1(src_path, out_path, erp_annotated):
    """원본 zrfm2 + R열(18) 매칭 사업명 + S열(19) 매칭확신도 + T열(20) 반영구분.

    반영구분: 계획집행 / 신규 / 신규(소액집행) / 미반영 / (공란=타예산).
    '미반영' = 선택 안 된 예산과목·지사, 미분류, 미매핑 처지사 전표(종합표 미포함).
    """
    label_by_row = {int(r): lab for r, lab in
                    zip(erp_annotated["_erp_row"], erp_annotated["매칭사업명"])}
    conf_by_row = {int(r): c for r, c in
                   zip(erp_annotated["_erp_row"], erp_annotated["매칭확신도"])}
    gubun_by_row = {int(r): g for r, g in
                    zip(erp_annotated["_erp_row"], erp_annotated["구분"])}
    wb = openpyxl.load_workbook(src_path)
    ws = wb[wb.sheetnames[0]]
    ws.cell(1, 18, "사업명(매칭)")
    ws.cell(1, 19, "매칭확신도")
    ws.cell(1, 20, "반영구분")
    for r in range(2, ws.max_row + 1):
        lab = label_by_row.get(r)
        if lab:
            ws.cell(r, 18, lab)
        c = conf_by_row.get(r)
        if c is not None:
            ws.cell(r, 19, c)
        g = gubun_by_row.get(r)
        if g:
            ws.cell(r, 20, g)
            if g == "미반영":
                ws.cell(r, 20).fill = UNREFLECTED_FILL
    wb.save(out_path)
    wb.close()


# matched_{year}.csv 컬럼(데이터 계약 §08). ERP 전표 + 매칭 결과.
MATCHED_CSV_COLUMNS = [
    "_erp_row", "계정코드", "예산과목원문", "과목정규", "지사원문", "처지사정규",
    "연도", "전표번호", "사업명", "금액원", "금액천원",
    "매칭사업명", "매칭확신도", "구분",
]


def write_matched_csv(out_path, erp_annotated):
    """전표-사업 매칭 결과를 CSV로 저장(데이터 계약: matched_{year}.csv).
    3·4단계 파이프라인/외부 도구가 소비. Excel 한글 호환 위해 utf-8-sig."""
    cols = [c for c in MATCHED_CSV_COLUMNS if c in erp_annotated.columns]
    erp_annotated.to_csv(out_path, columns=cols, index=False, encoding="utf-8-sig")
