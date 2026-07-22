# -*- coding: utf-8 -*-
"""동적 종합표(SUMIFS)와 양식1(월별) 데이터시트를 작성 (원본 워크북 없이 신규 생성)."""
import pandas as pd
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from . import loaders
from . import missing as missing_mod
from .config_store import SIMUI_THRESHOLD_THOUSAND

DATA_HEADER = [
    "주관부서명", "예산귀속 부서코드", "예산귀속 부서명(처.지사)", "예산귀속 부서명(부)",
    "속성", "예산코드", "예산과목", "사업명", "산출내역", "연예산 합계",
]
MISSING_FILL = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")
HEADER_FILL = PatternFill(start_color="305496", end_color="305496", fill_type="solid")
SUBTOTAL_FILL = PatternFill(start_color="D9E1F2", end_color="D9E1F2", fill_type="solid")
THIN = Side(style="thin", color="B7B7B7")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)

HEADER_ROW = 3
NAME_ROW = 4

_MISSING_COL_INDEX = {"처지사": 3, "예산과목": 7, "연예산": 10, "사업명": 8}


def write_datasheet(ws, df, budget, year, item_flags):
    ws.cell(1, 1, f"{year}년 {budget}예산 계획 (단위: 천원)")
    for i, h in enumerate(DATA_HEADER, 1):
        c = ws.cell(HEADER_ROW, i, h)
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = HEADER_FILL
    for i, h in ((11, "검증"), (12, "심의플래그")):
        c = ws.cell(HEADER_ROW, i, h)
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = HEADER_FILL

    r = 4
    for _, row in df.iterrows():
        for i, key in enumerate(loaders.PLAN_COLUMNS, 1):
            val = row[key]
            ws.cell(r, i, None if pd.isna(val) else val)
        mf = missing_mod.missing_fields(row)
        for f in mf:
            ws.cell(r, _MISSING_COL_INDEX[f]).fill = MISSING_FILL
        ws.cell(r, 11, (", ".join(mf) + " 누락") if mf else "")
        item = row["예산과목"]
        amt = row["연예산"]
        flag = "O" if item_flags.get(item) and not pd.isna(amt) and amt >= SIMUI_THRESHOLD_THOUSAND else ""
        ws.cell(r, 12, flag)
        r += 1
    return {"written_rows": r - 4}
