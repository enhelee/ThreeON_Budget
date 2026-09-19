# -*- coding: utf-8 -*-
"""재무팀 참고 양식 내보내기 — v2 `standardization_template.py`·`longterm_forecast_template.py` 승계.

Phase 6-7. 두 내장 양식(`app/templates/builtin_template_표준화.xlsx` 25시트 ·
`builtin_template_중장기예산.xlsx` 35시트)에 계산 결과를 채워 bytes 로 돌려준다.
셀 좌표를 박지 않고 시트 안의 라벨(예산과목명·'손익소계'·'Standization'·'정비등급'…)을
스캔해 위치를 찾는다 — 같은 형식의 수정본 양식을 넣어도 그대로 동작하게.

**단위** — 이 앱은 천원이다(v2 는 원). 양식 라벨을 따른다.
  표준화 지사 시트 «단위: 천원»       → 그대로
  고온부품(NN) «(단위: 천원)»          → 그대로
  NN년 총원가 배분 «본사(단위: 천원)»   → 그대로  (v2 는 백만원으로 나눴는데 라벨과 어긋났다 — 동료 확인 항목)
  중장기 지사탭 · 총괄표 «단위: 백만원» → /1,000
  NN년 본사 원가분배                     → 마스터 표 값 그대로(양식에서 왔던 값)

**기준연도** — 양식은 «26년» 라벨이 박힌 2026년 기준 양식이다. 시트명·헤더는 base_year 로 만들어
(«27년 본사 원가분배» 등) 찾으므로, 다른 기준연도용 양식을 같은 형식으로 넣으면 그대로 쓰인다.
2026 양식에 2027 기준 결과를 채우면 시트명이 맞는 부분(지사탭·총괄표·일정)만 채워진다.

시트명 → 지사명 매핑은 `forecast_import.site_sheet_map(site_names)`(dept_config 지사명).
"""
import io
import os
import re

import pandas as pd
from openpyxl import load_workbook
from openpyxl.cell.cell import MergedCell

from . import benchmark, forecast_calc
from .forecast_import import site_sheet_map

APP_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TEMPLATE_DIR = os.path.join(APP_DIR, "templates")
STD_TEMPLATE = os.path.join(TEMPLATE_DIR, "builtin_template_표준화.xlsx")
LT_TEMPLATE = os.path.join(TEMPLATE_DIR, "builtin_template_중장기예산.xlsx")

MILLION = 1000.0          # 천원 → 백만원


def _yy(base_year) -> str:
    return f"{int(base_year) % 100:02d}"


def set_cell(ws, row: int, col: int, value):
    """병합 셀이면 병합을 풀고 쓴다. 일부 지사 시트에 빈 장식용 병합(예: 삼송 D34:D39)이 남아 있어
    그 자리에 쓰면 MergedCell 이 read-only 라 오류가 난다."""
    cell = ws.cell(row=row, column=col)
    if isinstance(cell, MergedCell):
        for rng in list(ws.merged_cells.ranges):
            if rng.min_row <= row <= rng.max_row and rng.min_col <= col <= rng.max_col:
                ws.unmerge_cells(str(rng))
                break
        cell = ws.cell(row=row, column=col)
    cell.value = value


def _bytes(wb) -> bytes:
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ═══════════════════════════════════════════════════════════ 기준연도 재기준화
# 내장 양식은 «26년» 라벨이 박힌 2026년 기준 양식이다. 참조용 양식이므로 기준연도가 바뀌면
# 시트명(«26년 본사 원가분배»·«고온부품(26)»·«26년»~«35년»)·헤더 영역의 연도 값과 라벨·
# 그 시트명을 가리키는 수식 참조를 기준연도만큼 옮긴 뒤 채운다(사용자 요청 2026-09-20).
# 헤더 영역(1~6행) 밖의 숫자·문구는 건드리지 않는다 — 금액 26 이나 참고 블록 «(2025중장기)» 같은 것.

TEMPLATE_BASE_YEAR = 2026
_HEADER_ROWS = 6
_YY = re.compile(r"(?<!\d)(\d{2})년")            # 26년 · 26년 예산 · 26년 본사 원가분배
_PAREN_YY = re.compile(r"\((\d{2})\)")           # 고온부품(26)
_YYYY = re.compile(r"(?<!\d)(20\d{2})(?!\d)")    # (2026~2041)


def _shift_label(s: str, delta: int) -> str:
    def yy(m):
        v = int(m.group(1))
        return f"{(v + delta) % 100:02d}년" if 20 <= v <= 45 else m.group(0)

    def paren(m):
        v = int(m.group(1))
        return f"({(v + delta) % 100:02d})" if 20 <= v <= 45 else m.group(0)

    def yyyy(m):
        v = int(m.group(1))
        return str(v + delta) if 2020 <= v <= 2050 else m.group(0)

    return _YYYY.sub(yyyy, _PAREN_YY.sub(paren, _YY.sub(yy, s)))


def rebase_workbook_years(wb, base_year: int, template_base: int = TEMPLATE_BASE_YEAR) -> dict:
    """양식의 연도 라벨을 template_base → base_year 로 옮긴다. 반환 {옛 시트명: 새 시트명}."""
    delta = int(base_year) - int(template_base)
    if delta == 0:
        return {}
    renames = {}
    for ws in wb.worksheets:
        new = _shift_label(ws.title, delta)
        if new != ws.title:
            renames[ws.title] = new
    # «26년»→«27년» 을 바로 하면 아직 남아 있는 «27년» 과 충돌해 openpyxl 이 «27년1» 을 만든다(실측).
    # 임시 이름을 거쳐 두 단계로 바꾼다.
    targets = [ws for ws in wb.worksheets if ws.title in renames]
    finals = [renames[ws.title] for ws in targets]
    for i, ws in enumerate(targets):
        ws.title = f"__rebase_{i}__"
    for ws, final in zip(targets, finals):
        ws.title = final
    # 수식의 시트 참조 — openpyxl 은 시트를 바꿔도 수식을 고쳐 주지 않는다. 그대로 두면 #REF!.
    # 한 번에 치환한다: 순서대로 적용하면 '26년'→'27년'→'28년' 으로 연쇄된다.
    if renames:
        alt = "|".join(re.escape(old) for old in sorted(renames, key=len, reverse=True))
        quoted = re.compile(r"'(" + alt + r")'!")
        bare = re.compile(r"(?<![\w'])(" + alt + r")!")
        for ws in wb.worksheets:
            for row in ws.iter_rows():
                for cell in row:
                    v = cell.value
                    if isinstance(v, str) and v.startswith("="):
                        v = quoted.sub(lambda m: f"'{renames[m.group(1)]}'!", v)
                        v = bare.sub(lambda m: f"{renames[m.group(1)]}!", v)
                        if v != cell.value:
                            cell.value = v
    # 헤더 영역(모든 시트): 네 자리 연도 · «NN년» 라벨 · 두 자리 연도 행(5개 이상 나열된 행만)
    for ws in wb.worksheets:
        for r in range(1, min(_HEADER_ROWS, ws.max_row) + 1):
            cells = [ws.cell(row=r, column=c) for c in range(1, ws.max_column + 1)]
            bare_years = [c for c in cells if isinstance(c.value, (int, float)) and not isinstance(c.value, bool)
                          and 20 <= c.value <= 45]
            shift_bare = len(bare_years) >= 5
            for c in cells:
                if isinstance(c, MergedCell):
                    continue
                v = c.value
                if isinstance(v, bool):
                    continue
                if isinstance(v, (int, float)):
                    if 2020 <= v <= 2050:
                        c.value = int(v) + delta
                    elif shift_bare and 20 <= v <= 45:
                        c.value = int(v) + delta
                elif isinstance(v, str) and not v.startswith("="):
                    new = _shift_label(v, delta)
                    if new != v:
                        c.value = new
    return renames


# ═══════════════════════════════════════════════════════════ 표준화 양식 (25시트)
def _find_year_row(ws) -> dict:
    """연도 헤더 행 → {열: 연도}. 표준화 지사 시트는 2025, 2024, … 네 자리 정수."""
    for r in range(1, min(ws.max_row, 10) + 1):
        found = {c: int(ws.cell(row=r, column=c).value) for c in range(2, ws.max_column + 1)
                 if isinstance(ws.cell(row=r, column=c).value, (int, float))
                 and 2000 < ws.cell(row=r, column=c).value < 2100}
        if found:
            return found
    return {}


def _find_row_by_exact_label(ws, label: str, max_row: int = None):
    for r in range(1, (max_row or ws.max_row) + 1):
        if str(ws.cell(row=r, column=1).value or "").strip() == label:
            return r
    return None


def _match_history_account(label):
    normalized = forecast_calc.normalize_account_name(label)
    return normalized if normalized in benchmark.ALL_ACCOUNTS else None


def _match_standization_account(label):
    """'Standization' 표의 라벨 → 정식 계정과목. 그룹 헤더·장식 문구는 None."""
    label = (label or "").strip()
    if not label or label == "기계장치":
        return None                      # 자본 블록의 그룹 헤더 — 값은 '기타기계장치' 행에
    if "기타기계장치" in label:
        return "기계장치"
    if "외주비-열원정기점검" in label:
        return "외주비-열원정기점검"
    if label.startswith("공구와기구"):
        return "공구와기구-열원시설공기구"
    normalized = forecast_calc.normalize_account_name(label)
    if normalized in benchmark.ALL_ACCOUNTS:
        return normalized
    for acct in benchmark.ALL_ACCOUNTS:
        if label.startswith(acct):
            return acct
    return None


def _fill_history_section(ws, year_by_col, yearly_by_account):
    subtotal_row = _find_row_by_exact_label(ws, "손익소계")
    last_row = subtotal_row if subtotal_row else ws.max_row
    for r in range(1, last_row + 1):
        account = _match_history_account(ws.cell(row=r, column=1).value)
        if account is None or account not in yearly_by_account:
            continue
        for col, year in year_by_col.items():
            amount = yearly_by_account[account].get(year)
            if amount is not None:
                set_cell(ws, r, col, round(float(amount), 2))          # 천원 그대로


def _fill_grade_history_rows(ws, grade_by_year):
    subtotal_row = _find_row_by_exact_label(ws, "손익소계")
    if subtotal_row is None or not grade_by_year:
        return
    year_by_col = _find_year_row(ws)
    r = subtotal_row + 2                       # 손익소계 다음(보조소계)은 건너뛴다
    while r <= ws.max_row:
        label = ws.cell(row=r, column=1).value
        if label is None or str(label).strip() == "":
            break
        for col, year in year_by_col.items():
            grade = grade_by_year.get(year)
            if grade is not None:
                set_cell(ws, r, col, grade)
        r += 1


def _fill_standization_block(ws, block_label, grades, lookup):
    header_row = _find_row_by_exact_label(ws, block_label)
    if header_row is None:
        return
    start = 4                                  # D열부터 — 참고 양식 레이아웃
    for i, grade in enumerate(grades):
        set_cell(ws, header_row, start + i, grade)
    note_col = start + len(grades)
    set_cell(ws, header_row, note_col, "비고")
    r = header_row + 1
    while r <= ws.max_row:
        label = ws.cell(row=r, column=1).value
        if label is None or str(label).strip() == "":
            break
        account = _match_standization_account(label)
        if account is not None:
            notable = []
            for i, grade in enumerate(grades):
                entry = lookup.get((account, grade))
                if entry is not None:
                    amount, note = entry
                    set_cell(ws, r, start + i, round(float(amount), 2))
                    if note and note not in benchmark.METHOD_OPTIONS:
                        notable.append(f"{grade}:{note}")
            if notable:
                set_cell(ws, r, note_col, "; ".join(dict.fromkeys(notable)))
        r += 1


def fill_standardization_workbook(actuals_df, grade_history_df, standard_df, site_names,
                                  template_path: str = STD_TEMPLATE) -> bytes:
    """지사 시트만 채운다 — '합계'·'중대형chp'·'DH'·'소형CHP' 시트는 지사 시트를 더하는 수식이 이미 있다."""
    wb = load_workbook(template_path)
    site_to_sheet = {v: k for k, v in site_sheet_map(site_names).items()}
    actuals_df = actuals_df.copy()
    if not actuals_df.empty:
        actuals_df["예산과목"] = actuals_df["예산과목"].apply(forecast_calc.normalize_account_name)
    for site, sheet_name in site_to_sheet.items():
        if sheet_name not in wb.sheetnames:
            continue
        ws = wb[sheet_name]
        site_actuals = actuals_df[actuals_df["사업장"] == site] if not actuals_df.empty else actuals_df
        yearly_by_account = ({acct: g.groupby("연도")["금액"].sum().to_dict()
                              for acct, g in site_actuals.groupby("예산과목")} if not site_actuals.empty else {})
        _fill_history_section(ws, _find_year_row(ws), yearly_by_account)

        hist = grade_history_df[grade_history_df["사업장"] == site]
        _fill_grade_history_rows(ws, dict(zip(hist["연도"], hist["등급"])))

        site_std = standard_df[standard_df["사업장"] == site] if not standard_df.empty else standard_df
        if site_std.empty:
            continue
        grades = sorted(site_std["등급"].unique())
        for block_label, category in (("손익예산 Standization", "손익"), ("자본예산 Standization", "자본")):
            cat = site_std[site_std["구분"] == category]
            lookup = {(r["예산과목"], r["등급"]): (r["표준금액"], r["비고"]) for _, r in cat.iterrows()}
            _fill_standization_block(ws, block_label, grades, lookup)
    return _bytes(wb)


# ═══════════════════════════════════════════════════════════ 중장기예산 양식 (35시트)
def _find_bare_year_row(ws, max_scan_row: int = 6) -> dict:
    """지사별 탭은 연도를 26~35 두 자리 정수로 쓴다 → {열: 2026~2035}."""
    for r in range(1, max_scan_row + 1):
        found = {c: 2000 + int(ws.cell(row=r, column=c).value) for c in range(1, ws.max_column + 1)
                 if isinstance(ws.cell(row=r, column=c).value, (int, float))
                 and 20 <= ws.cell(row=r, column=c).value <= 45}
        if len(found) >= 5:
            return found
    return {}


def _find_label_header(ws, label: str, max_row: int = 10):
    """헤더 문구(예: '26년 예산')가 있는 (행, 열). 없으면 (None, None)."""
    for r in range(1, max_row + 1):
        for c in range(1, ws.max_column + 1):
            if str(ws.cell(row=r, column=c).value or "").strip() == label:
                return r, c
    return None, None


def _site_cols(ws, header_row, from_col, site_names) -> dict:
    short_to_full = site_sheet_map(site_names)
    out = {}
    for c in range(from_col + 1, ws.max_column + 1):
        v = ws.cell(row=header_row, column=c).value
        if v is None:
            continue
        full = short_to_full.get(str(v).strip())
        if full:
            out[c] = full
    return out


def _schedule_layout(ws, site_names):
    """'정기점검보수공사 일정' 시트의 (연도→GT열, 지사→행들). import 파서와 같은 규칙."""
    year_row = None
    for r in range(1, 6):
        if any(isinstance(ws.cell(row=r, column=c).value, (int, float)) and 2020 < ws.cell(row=r, column=c).value < 2050
               for c in range(1, ws.max_column + 1)):
            year_row = r
            break
    if year_row is None:
        return {}, {}
    year_by_gt_col = {c: int(ws.cell(row=year_row, column=c).value) for c in range(1, ws.max_column + 1)
                      if isinstance(ws.cell(row=year_row, column=c).value, (int, float))
                      and 2020 < ws.cell(row=year_row, column=c).value < 2050}
    short_to_full = site_sheet_map(site_names)
    shorts = sorted(short_to_full, key=len, reverse=True)
    site_rows, current, blank = {}, None, 0
    r = year_row + 3
    while r <= ws.max_row:
        vals = [ws.cell(row=r, column=c).value for c in range(1, ws.max_column + 1)]
        if all(v in (None, "") for v in vals):
            blank += 1
            if blank >= 3:
                break
            r += 1
            continue
        blank = 0
        label = ws.cell(row=r, column=1).value
        if label is not None and str(label).strip():
            raw = str(label).replace(" ", "").strip()
            m = next((s for s in shorts if raw.startswith(s)), None)
            current = short_to_full.get(m) if m else None
        if current:
            site_rows.setdefault(current, []).append(r)
        r += 1
    return year_by_gt_col, site_rows


def fill_schedule_sheet(ws, grade_hist, site_names, base_year: int = forecast_calc.BASE_YEAR):
    """GT열에 현재 저장된 미래(기준연도~) 정비등급을 되돌려 쓴다 — GT 어휘 행(없으면 첫 행)에."""
    year_by_gt_col, site_rows = _schedule_layout(ws, site_names)
    for site, rows in site_rows.items():
        g = grade_hist[(grade_hist["사업장"] == site) & (grade_hist["연도"].astype(int) >= int(base_year))]
        grade_by_year = dict(zip(g["연도"].astype(int), g["등급"]))
        if not grade_by_year:
            continue
        gt_rows = [ri for ri in rows if forecast_calc._classify_grade_row(
            {y: ws.cell(row=ri, column=c).value for c, y in year_by_gt_col.items()}) == "GT"]
        target = gt_rows[0] if gt_rows else rows[0]
        for col, year in year_by_gt_col.items():
            grade = grade_by_year.get(year)
            if grade:
                set_cell(ws, target, col, grade)


def fill_hot_parts_sheet(ws, hot_parts_df, site_names):
    """'고온부품(NN)' 시트에 현재 계획을 되돌려 쓴다. 천원 그대로."""
    header_row, year_by_col = None, {}
    for r in range(1, 8):
        found = {}
        for c in range(1, ws.max_column + 1):
            v = ws.cell(row=r, column=c).value
            m = re.match(r"^(\d{2})년", str(v).strip()) if v is not None else None
            if m:
                found[c] = 2000 + int(m.group(1))
        if found:
            header_row, year_by_col = r, found
            break
    if header_row is None:
        return
    short_to_full = site_sheet_map(site_names)
    lookup = {(r["사업장"], int(r["연도"]), r["항목"]): float(r["금액"]) for _, r in hot_parts_df.iterrows()}
    current, blank = None, 0
    r = header_row + 1
    while r <= ws.max_row:
        site_label = ws.cell(row=r, column=1).value
        item = ws.cell(row=r, column=5).value
        if site_label:
            current = short_to_full.get(str(site_label).strip())
        if item is None or current is None:
            blank += 1
            if blank >= 3:
                break
            r += 1
            continue
        blank = 0
        for col, year in year_by_col.items():
            amount = lookup.get((current, year, str(item).strip()))
            if amount is not None:
                set_cell(ws, r, col, round(amount, 3))
        r += 1


def fill_hq_master_sheet(ws, hq_master_df, site_names, base_year: int = forecast_calc.BASE_YEAR):
    """'NN년 본사 원가분배' 시트에 마스터 표를 그대로 되돌려 쓴다(라벨 순서로 대응)."""
    if hq_master_df is None or hq_master_df.empty:
        return
    header_row, budget_col = _find_label_header(ws, f"{_yy(base_year)}년 예산")
    if header_row is None:
        return
    site_col = _site_cols(ws, header_row, budget_col, site_names)
    rows = hq_master_df.reset_index(drop=True)
    major = minor = None
    r, idx = header_row + 1, 0
    while r <= ws.max_row and idx < len(rows):
        c1, c2, c3 = (ws.cell(row=r, column=k).value for k in (1, 2, 3))
        label1 = str(c1).strip() if c1 else ""
        if label1 in ("합계", "경상정비 원가배부기준"):
            break
        if c1:
            major = label1
        if c2:
            minor = str(c2).strip()
        detail = str(c3).strip() if c3 else ""
        if detail == "합계":
            r += 1
            continue
        src = rows.iloc[idx]
        if (str(src["대분류"]) == (major or "") and str(src["중분류"]) == (minor or "")
                and str(src["세부내역"]) == detail):
            for col, site in site_col.items():
                if site in rows.columns:
                    set_cell(ws, r, col, float(src[site]))
            idx += 1
        r += 1


# 지사별 탭 (대분류, 세부) 라벨 → SITE_TABLE_LINES 라벨
_SITE_ROW_LABELS = {
    ("수선유지비", "건물/구축물"): "수선유지비-건물/구축물",
    ("", "열원정기점검"): "수선유지비-열원정기점검",
    ("", "열원경상정비"): "수선유지비-열원경상정비",
    ("", "열원정기유지보수"): "수선유지비-열원정기유지보수",
    ("", "열원보완및개선"): "수선유지비-열원보완및개선",
    ("", "비저장품(보수자재)"): "비저장품(보수자재)",
    ("", "소모품(자재공기구)"): "소모품(자재공기구)",
    ("지급수수료", "지급수수료 열원"): "지급수수료-열원점검수수료",
    ("기계장치", "고온부품재생"): "기계장치_고온부품재생",
    ("", "기타기계장치"): "기계장치_기타기계장치",
    ("건가-외주비", "MI 및 A급 정비"): "외주비-열원정기점검",
    ("공구와기구", ""): "공구와기구-열원시설공기구",
    ("건설중인자산", "재생고온부품"): "건설중인자산_재생고온부품",
    ("", "자산화예비품"): "건설중인자산-자산화예비품",
    ("자산", "저장품"): "저장품-열원(보수)",
    ("투자비", "열원공사비 등"): "투자비",
}


def fill_site_sheet(ws, site_table, grade_hist, site):
    """지사 탭 — 정비등급 행 + 예산과목 라인(백만원)."""
    year_by_col = _find_bare_year_row(ws)
    if not year_by_col:
        return
    values_by_label = {row["예산과목"]: row for _, row in site_table.iterrows()}
    grade_row = next((r for r in range(1, ws.max_row + 1)
                      if str(ws.cell(row=r, column=1).value or "").strip() == "정비등급"), None)
    if grade_row:
        g = grade_hist[grade_hist["사업장"] == site]
        grade_by_year = dict(zip(g["연도"].astype(int), g["등급"]))
        latest = benchmark.get_current_grade(site, grade_hist)
        for col, year in year_by_col.items():
            gr = grade_by_year.get(year, latest)
            if gr:
                set_cell(ws, grade_row, col, gr)
    major = ""
    for r in range(1, ws.max_row + 1):
        c1, c2 = ws.cell(row=r, column=1).value, ws.cell(row=r, column=2).value
        if c1:
            major = str(c1).strip()
        label2 = str(c2).strip() if c2 else ""
        key = (major, label2) if (major, label2) in _SITE_ROW_LABELS else ("", label2)
        canonical = _SITE_ROW_LABELS.get(key)
        if canonical is None and label2 == "" and major:
            canonical = _SITE_ROW_LABELS.get((major, ""))
        if canonical is None:
            continue
        row_vals = values_by_label.get(canonical)
        if row_vals is None:
            continue
        for col, year in year_by_col.items():
            amount = row_vals.get(year)
            if amount is not None:
                set_cell(ws, r, col, round(float(amount) / MILLION, 3))


# 'NN년 총원가 배분' 의 (col2 대분류, col3 세부) 라벨 → SITE_TABLE_LINES 라벨. 대분류는 이전 값을 이어받는다.
_TOTAL_COST_ROW_LABELS = {
    ("", "건물구축물"): "수선유지비-건물/구축물",
    ("", "열원정기점검"): "수선유지비-열원정기점검",
    ("", "열원경상정비"): "수선유지비-열원경상정비",
    ("", "열원정기유지보수"): "수선유지비-열원정기유지보수",
    ("", "열원보완및개선"): "수선유지비-열원보완및개선",
    ("", "비저장품(보수자재)"): "비저장품(보수자재)",
    ("", "소모품(자재공기구)"): "소모품(자재공기구)",
    ("", "지급수수료"): "지급수수료-열원점검수수료",
    ("기계장치", "고온부품재생+LTSA"): "기계장치_고온부품재생",
    ("기계장치", "기타기계장치"): "기계장치_기타기계장치",
    ("건가-외주비", "MI 및 A급 정비"): "외주비-열원정기점검",
    ("공구와기구", ""): "공구와기구-열원시설공기구",
    ("건설중인자산", "재생고온부품"): "건설중인자산_재생고온부품",
    ("건설중인자산", "자산화예비품"): "건설중인자산-자산화예비품",
    ("자산", "저장품"): "저장품-열원(보수)",
    ("투자비", "열원공사비 등"): "투자비",
}


def fill_total_cost_sheet(ws, site_tables, site_names, base_year: int = forecast_calc.BASE_YEAR,
                          hq_master_df=None):
    """'NN년 총원가 배분' — **지사(단위: 천원) 블록만** 채운다.

    이 시트는 블록 3쌍이다: 본사(천원, «NN년 본사 원가분배» 참조 수식) · 지사(천원, 값) ·
    전체(백만원, =(본사+지사)/1000 수식). 값을 넣을 자리는 지사 블록뿐이고, 거기 들어갈 값은
    지사 탭 기준연도 금액(본사배분 포함)에서 **본사배분 몫을 뺀 지사 자체 몫**이다. v2 는 여섯 블록
    모두에 합산값을 덮어써 수식을 지웠다(6-7 실측).
    """
    header_row, budget_col = _find_label_header(ws, f"{_yy(base_year)}년 예산")
    if header_row is None:
        return
    site_col = _site_cols(ws, header_row, budget_col, site_names)
    hq_amount = forecast_calc.hq_amount_by_site_account(hq_master_df) if hq_master_df is not None else {}
    by = int(base_year)
    in_site_block, major = False, ""
    for r in range(header_row, ws.max_row + 1):
        c1, c2, c3 = (ws.cell(row=r, column=k).value for k in (1, 2, 3))
        label1 = str(c1).strip() if c1 else ""
        if "(단위" in label1:                          # 블록 헤더: 본사(단위 : 천원) / 지사(…) / 전체(…)
            in_site_block = label1.startswith("지사")
            major = ""
            continue
        if not in_site_block:
            continue
        if c2:
            major = str(c2).strip()
        minor = str(c3).strip() if c3 else ""
        canonical = _TOTAL_COST_ROW_LABELS.get((major, minor)) or _TOTAL_COST_ROW_LABELS.get(("", minor))
        if canonical is None and minor == "" and major:
            canonical = _TOTAL_COST_ROW_LABELS.get((major, ""))
        if canonical is None:
            continue
        hq_label = forecast_calc.STANDARDIZED_ACCOUNT_TO_HQ_LABEL.get(canonical, canonical)
        for col, site in site_col.items():
            table = site_tables.get(site)
            if table is None:
                continue
            match = table[table["예산과목"] == canonical]
            if match.empty or by not in match.columns:
                continue
            own = float(match.iloc[0][by]) - float(hq_amount.get((site, hq_label), 0.0))
            set_cell(ws, r, col, round(own, 3))


_SUMMARY_ROW_LABELS = {
    ("수선유지비", "건물/구축물"): "수선유지비-건물/구축물",
    ("", "열원정기점검"): "수선유지비-열원정기점검",
    ("", "열원경상정비"): "수선유지비-열원경상정비",
    ("", "열원정기유지보수"): "수선유지비-열원정기유지보수",
    ("", "열원보완및개선"): "수선유지비-열원보완및개선",
    ("", "비저장품(보수자재)"): "비저장품(보수자재)",
    ("", "소모품(자재공기구)"): "소모품(자재공기구)",
    ("지급수수료", "지급수수료 열원"): "지급수수료-열원점검수수료",
    ("기계장치", "고온부품재생+LTSA"): "기계장치_고온부품재생",
    ("", "기타기계장치"): "기계장치_기타기계장치",
    ("공구와기구", ""): "공구와기구-열원시설공기구",
    ("예비품", "재생고온부품"): "건설중인자산_재생고온부품",
    ("", "자산화예비품"): "건설중인자산-자산화예비품",
    ("", "저장품"): "저장품-열원(보수)",
    ("투자비", "열원공사비 등"): "투자비",
}


def fill_summary_sheet(ws, site_tables):
    """'총괄표' — 전 지사 합계를 연도별로(백만원). 헤더는 '26년' 같은 문자열."""
    def _yr(v):
        s = str(v).strip() if isinstance(v, str) else ""
        return 2000 + int(s[:-1]) if s.endswith("년") and s[:-1].isdigit() else None
    year_row = next((r for r in range(1, 6)
                     if any(_yr(ws.cell(row=r, column=c).value) for c in range(1, ws.max_column + 1))), None)
    if year_row is None:
        return
    year_by_col = {c: _yr(ws.cell(row=year_row, column=c).value) for c in range(1, ws.max_column + 1)
                   if _yr(ws.cell(row=year_row, column=c).value)}
    major = ""
    r = year_row + 1
    while r <= ws.max_row:
        c1, c2 = ws.cell(row=r, column=1).value, ws.cell(row=r, column=2).value
        # 본 블록은 첫 빈 행에서 끝난다. 그 아래에는 «손익예산(2025중장기)» 같은 참고 블록이 있고
        # (전년 실측치·수식), v2 는 거기까지 라벨을 매칭해 덮어썼다 — 총괄표 합계가 부풀고 전년 비교치가
        # 사라졌다(6-7 실측: 16행 자리에 22행이 채워짐).
        if c1 in (None, "") and c2 in (None, ""):
            break
        if c1:
            major = str(c1).strip()
        minor = str(c2).strip() if c2 else ""
        if minor in ("계", "합계"):
            r += 1
            continue
        key = (major, minor) if (major, minor) in _SUMMARY_ROW_LABELS else ("", minor)
        canonical = _SUMMARY_ROW_LABELS.get(key)
        if canonical is None and minor == "" and major:
            canonical = _SUMMARY_ROW_LABELS.get((major, ""))
        if canonical is None and major == "건가-외주비":
            canonical = "외주비-열원정기점검"
        if canonical:
            for col, year in year_by_col.items():
                total = 0.0
                for table in site_tables.values():
                    match = table[table["예산과목"] == canonical]
                    if not match.empty and year in match.columns:
                        total += float(match.iloc[0][year])
                set_cell(ws, r, col, round(total / MILLION, 3))
        r += 1


def _sheet_like(wb, pred):
    return next((n for n in wb.sheetnames if pred(n)), None)


def build_schedule_download(grade_hist, site_names, base_year: int = forecast_calc.BASE_YEAR,
                            template_path: str = LT_TEMPLATE) -> bytes:
    wb = load_workbook(template_path)
    rebase_workbook_years(wb, base_year)
    name = _sheet_like(wb, lambda n: "정기점검보수공사" in n)
    if name:
        fill_schedule_sheet(wb[name], grade_hist, site_names, base_year)
    return _bytes(wb)


def build_hot_parts_download(hot_parts_df, site_names, base_year: int = forecast_calc.BASE_YEAR,
                             template_path: str = LT_TEMPLATE) -> bytes:
    wb = load_workbook(template_path)
    rebase_workbook_years(wb, base_year)
    name = _sheet_like(wb, lambda n: n.strip().startswith("고온부품"))
    if name:
        fill_hot_parts_sheet(wb[name], hot_parts_df, site_names)
    return _bytes(wb)


def build_hq_master_download(hq_master_df, site_names, base_year: int = forecast_calc.BASE_YEAR,
                             template_path: str = LT_TEMPLATE) -> bytes:
    wb = load_workbook(template_path)
    rebase_workbook_years(wb, base_year)
    name = f"{_yy(base_year)}년 본사 원가분배"
    if name in wb.sheetnames:
        fill_hq_master_sheet(wb[name], hq_master_df, site_names, base_year)
    return _bytes(wb)


def fill_longterm_workbook(site_tables, grade_hist, hq_master_df, site_names,
                           base_year: int = forecast_calc.BASE_YEAR, template_path: str = LT_TEMPLATE) -> bytes:
    """지사 탭 + NN년 본사 원가분배 + NN년 총원가 배분 + 총괄표. 27~35년 개별 시트·원본 일정/고온부품 시트는
    건드리지 않는다(v2 정책 그대로 — 기준연도만 상세, 이후는 지사 탭으로 충분)."""
    wb = load_workbook(template_path)
    rebase_workbook_years(wb, base_year)
    short_to_full = site_sheet_map(site_names)
    for sheet_name in wb.sheetnames:
        site = short_to_full.get(sheet_name.strip())
        if site is not None and site in site_tables:
            fill_site_sheet(wb[sheet_name], site_tables[site], grade_hist, site)
    yy = _yy(base_year)
    if f"{yy}년 본사 원가분배" in wb.sheetnames:
        fill_hq_master_sheet(wb[f"{yy}년 본사 원가분배"], hq_master_df, site_names, base_year)
    if f"{yy}년 총원가 배분" in wb.sheetnames:
        fill_total_cost_sheet(wb[f"{yy}년 총원가 배분"], site_tables, site_names, base_year, hq_master_df)
    if "총괄표" in wb.sheetnames:
        fill_summary_sheet(wb["총괄표"], site_tables)
    return _bytes(wb)
