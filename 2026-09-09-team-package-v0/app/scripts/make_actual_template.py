# -*- coding: utf-8 -*-
"""실적 집계표 양식(양식2 손익·양식3 자본) → 앱에 넣을 빈 양식.

    python scripts/make_actual_template.py 손익 "<(양식2) …손익예산 실적 집계표….xlsx>" templates/actual_template_손익.xlsx
    python scripts/make_actual_template.py 자본 "<(양식3) …자본예산 실적 집계표….xlsx>" templates/actual_template_자본.xlsx

남기는 것: 시트 이름·머리글·열 폭·칸 모양(첫 데이터 행 4행의 서식만, 값은 비움)·예시 행(3행)·종합표 배치와 수식.
지우는 것: 사업 행(4행~)·종합표에 손으로 넣은 숫자(→ SUMIFS 수식으로)·메모·데이터 유효성·작성자.
수식의 캐시 값은 openpyxl 이 저장하지 않으므로 숫자가 남지 않는다 — 마지막에 숫자 칸이 0개인지 확인한다.
"""
import sys

import openpyxl
from openpyxl.utils import get_column_letter

FIRST_DATA_ROW = 4


def sumifs(data_title, summary_title, item_ref, dept_ref):
    d, s = f"'{data_title}'", f"'{summary_title}'"
    return f"=SUMIFS({d}!$I:$I,{d}!$B:$B,{s}!{item_ref},{d}!$E:$E,{s}!{dept_ref})"


def main(budget, src, dst):
    wb = openpyxl.load_workbook(src)
    data, summary = wb.worksheets[0], wb.worksheets[1]

    # 1) 계획 대비 실적 — 사업 행을 지우고 4행은 서식만 남긴다(채울 때 이 행의 모양을 복사)
    if data.max_row > FIRST_DATA_ROW:
        data.delete_rows(FIRST_DATA_ROW + 1, data.max_row - FIRST_DATA_ROW)
    for c in range(1, data.max_column + 1):
        data.cell(FIRST_DATA_ROW, c).value = None
    data.data_validations.dataValidation = []
    data.conditional_formatting = type(data.conditional_formatting)()
    data.auto_filter.ref = None
    data.print_area = None

    # 2) 종합표 — 머리글(처·지사 이름) 줄과 과목 줄을 찾아, 과목×처지사 칸을 모두 같은 SUMIFS 로
    name_row = next(r for r in range(1, 10) if any(summary.cell(r, c).value == "소계"
                                                    for c in range(1, summary.max_column + 1)))
    dept_cols = [c for c in range(3, summary.max_column + 1)
                 if summary.cell(name_row, c).value not in (None, "소계")]
    item_rows = [r for r in range(name_row + 1, summary.max_row + 1)
                 if summary.cell(r, 2).value not in (None, "계")]
    for r in item_rows:
        for c in dept_cols:
            summary.cell(r, c).value = sumifs(data.title, summary.title, f"$B{r}",
                                              f"{get_column_letter(c)}${name_row}")
    # 자본 양식의 합계 줄 일부(C~E)가 SUM(…8:…16) — 건물·구축물 줄이 빠져 있었다. 다른 열처럼 첫 과목 줄부터.
    first, last = item_rows[0], item_rows[-1]
    for r in range(name_row + 1, summary.max_row + 1):
        for c in range(3, summary.max_column + 1):
            v = summary.cell(r, c).value
            col = get_column_letter(c)
            if isinstance(v, str) and v.startswith(f"=SUM({col}") and summary.cell(r, 1).value \
                    and "합계" in str(summary.cell(r, 1).value):
                summary.cell(r, c).value = f"=SUM({col}{first}:{col}{last})"

    # 3) 메모·작성자 지우기
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for cell in row:
                if getattr(cell, "comment", None) is not None:
                    cell.comment = None
    wb.properties.creator = wb.properties.lastModifiedBy = None
    wb.calculation.fullCalcOnLoad = True

    # 4) 숫자가 하나도 남지 않았는지 — 남아 있으면 실제 자료가 레포에 들어간다
    left = [(ws.title, cell.coordinate) for ws in wb.worksheets for row in ws.iter_rows()
            for cell in row if isinstance(cell.value, (int, float)) and not isinstance(cell.value, bool)
            and not (ws is data and cell.row == 3)]          # 3행 = 양식의 «예시)» 행(예시 금액)
    hm = [ws.title for ws in wb.worksheets if ws.max_row > 40]
    assert not left, f"숫자 칸이 남았습니다: {left[:10]}"
    assert not hm, f"행이 많이 남았습니다: {hm}"
    wb.save(dst)
    print(f"{budget}: {data.title} / {summary.title} — 과목 {len(item_rows)}줄 × 처지사 {len(dept_cols)}칸 → {dst}")


if __name__ == "__main__":
    main(*sys.argv[1:4])
