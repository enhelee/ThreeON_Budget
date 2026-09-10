"""'실적집계 대시보드'(정식/Test 모드 공통) '배정 대비 실적' 결과를 손익예산실적집계표/
자본예산실적집계표 스타일의 엑셀 리포트 한 장으로 내보낸다.

budget_actual_summary.py가 이미 계산한 merged(지사유형×계정과목×손익자본구분×배정×실적)를
입력으로 받아, 회사 보고서 형태(계정과목 대분류 그룹핑, 연도별 추이, 지사유형별 점유율)로
재배열만 한다 - 집계 로직 자체(배정/실적/잔액/실적률 계산)는 budget_actual_summary.py가
단일 소스다.
"""
import io
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font, Border, Side, Alignment
import budget_actual_summary as bas
from longterm_forecast import INVESTMENT_ACCOUNTS

INVESTMENT_LABEL = "__투자비__"  # 실제 계정과목이 아니라 INVESTMENT_ACCOUNTS 합산을 나타내는 표식

# (대분류, [세부 계정과목 또는 INVESTMENT_LABEL, ...]) - 순서 그대로 리포트에 표시된다.
PROFIT_LOSS_REPORT_GROUPS = [
    ("수선유지비", [
        "수선유지비-건물/구축물", "수선유지비-열원경상정비", "수선유지비-열원보완및개선",
        "수선유지비-열원정기유지보수", "수선유지비-열원정기점검",
    ]),
    ("지급수수료", ["지급수수료-열원점검수수료"]),
]

CAPITAL_REPORT_GROUPS = [
    ("자산", ["건물", "구축물", "기계장치", "공구와기구-열원시설공기구"]),
    ("예비품", ["저장품-열원(보수)", "건설중인자산-재생고온부품", "건설중인자산-자산화예비품"]),
    ("건가", ["외주비-열원정기점검", INVESTMENT_LABEL]),
]

_MONEY_COLS = ["배정", "실적", "잔액"]
_DETAIL_COLS = ["배정", "실적", "잔액", "실적률(%)"]


def _account_totals(merged: pd.DataFrame, account: str) -> tuple:
    """merged에서 계정과목 하나의 배정·실적 합(원 단위)을 구한다. 데이터가 없으면 (0.0, 0.0)."""
    sub = merged[merged["계정과목"] == account]
    return float(sub["배정"].sum()), float(sub["실적"].sum())


def _investment_totals(merged: pd.DataFrame) -> tuple:
    """INVESTMENT_ACCOUNTS(외주비-열원공사비/외주비-열원기술용역비/재료비-열원자재비/외주비-기타)
    합계 - longterm_forecast.py가 '투자비' 한 줄로 다루는 것과 동일한 기준."""
    sub = merged[merged["계정과목"].isin(INVESTMENT_ACCOUNTS)]
    return float(sub["배정"].sum()), float(sub["실적"].sum())


def grouped_account_detail_table(merged: pd.DataFrame, groups: list) -> pd.DataFrame:
    """groups(대분류→세부 목록) 순서대로 배정/실적/잔액/실적률(%)을 계산해 (대분류,세부) 2단
    인덱스 표로 반환한다(억원 단위). 마지막에 전체 '합계' 행을 더한다. 데이터가 없는 계정과목도
    0으로 행 자체는 항상 표시한다(원본 보고서 양식과 동일)."""
    rows, index = [], []
    total_budget = total_actual = 0.0
    for major, items in groups:
        for item in items:
            label = "투자비" if item == INVESTMENT_LABEL else item
            budget, actual = _investment_totals(merged) if item == INVESTMENT_LABEL else _account_totals(merged, item)
            total_budget += budget
            total_actual += actual
            index.append((major, label))
            rows.append({"배정": budget, "실적": actual})

    table = pd.DataFrame(rows, index=pd.MultiIndex.from_tuples(index, names=["대분류", "세부"]))
    table["잔액"] = table["배정"] - table["실적"]
    table["실적률(%)"] = table.apply(
        lambda r: round(r["실적"] / r["배정"] * 100, 1) if r["배정"] else None, axis=1
    )
    table[_MONEY_COLS] = (table[_MONEY_COLS] / 1e8).round(1)

    total_row = pd.DataFrame(
        [{"배정": round(total_budget / 1e8, 1), "실적": round(total_actual / 1e8, 1),
          "잔액": round((total_budget - total_actual) / 1e8, 1),
          "실적률(%)": round(total_actual / total_budget * 100, 1) if total_budget else None}],
        index=pd.MultiIndex.from_tuples([("합계", "")], names=["대분류", "세부"]),
    )
    return pd.concat([table, total_row])[_DETAIL_COLS]


def site_type_share_table(merged: pd.DataFrame, site_counts: dict) -> pd.DataFrame:
    """지사유형별 실적 점유율(%) 표(표2). 값은 억원 단위 실적, 점유율은 build_report_workbook이
    셀에 쓸 때 같은 행의 '합계' 열 대비 비율로 계산한다(여기서는 raw 실적 값만 반환).
    site_counts: {"중대형CHP": n, "소형CHP": n, "DH": n} - 본사는 지사가 아니므로 표시하지 않는다."""
    if merged.empty:
        return pd.DataFrame()

    summary = bas.site_type_summary_table(merged)
    site_types = [c for c in summary.columns if c != "합계"]

    def _actual_row(category):
        return summary.loc[(category + "예산", "실적")] if (category + "예산", "실적") in summary.index else \
            pd.Series(0.0, index=summary.columns)

    pl_row, cap_row = _actual_row("손익"), _actual_row("자본")
    total_row = pl_row + cap_row

    table = pd.DataFrame([pl_row, cap_row, total_row], index=["손익", "자본", "합계"])
    table.attrs["site_counts"] = site_counts
    return table[site_types + ["합계"]]


def yearly_trend_table(year_to_merged: dict) -> pd.DataFrame:
    """연도별(합산하지 않고 나란히) 손익/자본/합계 배정·실적·실적률(%) 추이(표1).
    반환: 행=[손익,자본,합계], 열=MultiIndex(연도, [배정,실적,실적률(%)]) - 연도 오름차순."""
    years = sorted(year_to_merged.keys())
    data = {}
    totals = {y: {"배정": 0.0, "실적": 0.0} for y in years}

    for category in ["손익", "자본"]:
        for y in years:
            merged = year_to_merged[y]
            sub = merged[merged["손익자본구분"] == category] if not merged.empty else merged
            budget = float(sub["배정"].sum()) if not sub.empty else 0.0
            actual = float(sub["실적"].sum()) if not sub.empty else 0.0
            totals[y]["배정"] += budget
            totals[y]["실적"] += actual
            data[(y, "배정")] = data.get((y, "배정"), {})
            data[(y, "배정")][category] = round(budget / 1e8, 1)
            data[(y, "실적")] = data.get((y, "실적"), {})
            data[(y, "실적")][category] = round(actual / 1e8, 1)
            data[(y, "실적률(%)")] = data.get((y, "실적률(%)"), {})
            data[(y, "실적률(%)")][category] = round(actual / budget * 100, 1) if budget else None

    for y in years:
        b, a = totals[y]["배정"], totals[y]["실적"]
        data[(y, "배정")]["합계"] = round(b / 1e8, 1)
        data[(y, "실적")]["합계"] = round(a / 1e8, 1)
        data[(y, "실적률(%)")]["합계"] = round(a / b * 100, 1) if b else None

    columns = pd.MultiIndex.from_tuples(
        [(y, m) for y in years for m in ("배정", "실적", "실적률(%)")], names=["연도", "항목"]
    )
    table = pd.DataFrame(index=["손익", "자본", "합계"], columns=columns, dtype=float)
    for col, values in data.items():
        for row, val in values.items():
            table.loc[row, col] = val
    return table


# ---------------------------------------------------------------- 엑셀 작성
_THIN = Side(style="thin")
_BOX = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)
_BOLD = Font(bold=True)
_CENTER = Alignment(horizontal="center", vertical="center")


def _write_title(ws, row: int, text: str) -> int:
    ws.cell(row=row, column=1, value=text).font = _BOLD
    return row + 1


def _write_trend_table(ws, row: int, trend: pd.DataFrame) -> int:
    years = sorted({y for y, _ in trend.columns})
    ws.cell(row=row, column=1, value="구 분")
    col = 2
    for y in years:
        ws.merge_cells(start_row=row, start_column=col, end_row=row, end_column=col + 1)
        c = ws.cell(row=row, column=col, value=f"{y}년")
        c.font = _BOLD
        c.alignment = _CENTER
        col += 2
    row += 1

    ws.cell(row=row, column=1)
    col = 2
    for _ in years:
        ws.cell(row=row, column=col, value="배정")
        ws.cell(row=row, column=col + 1, value="실적")
        col += 2
    row += 1

    for label in ["손익", "자본", "합계"]:
        ws.cell(row=row, column=1, value=label)
        col = 2
        for y in years:
            ws.cell(row=row, column=col, value=trend.loc[label, (y, "배정")])
            ws.cell(row=row, column=col + 1, value=trend.loc[label, (y, "실적")])
            col += 2
        row += 1

        rate_row = row
        ws.cell(row=rate_row, column=1, value="실적률")
        col = 2
        for y in years:
            ws.merge_cells(start_row=rate_row, start_column=col, end_row=rate_row, end_column=col + 1)
            rate = trend.loc[label, (y, "실적률(%)")]
            ws.cell(row=rate_row, column=col, value=f"{rate}%" if rate is not None else "-")
            col += 2
        row += 1

    if years:
        latest_col_start = 2 + 2 * (len(years) - 1)
        for r in range(row - 2 * len(["손익", "자본", "합계"]), row):
            for c in range(latest_col_start, latest_col_start + 2):
                ws.cell(row=r, column=c).border = _BOX
    return row + 1


def _write_share_table(ws, row: int, share: pd.DataFrame) -> int:
    if share.empty:
        return row
    site_counts = share.attrs.get("site_counts", {})
    ws.cell(row=row, column=1, value="구분")
    for i, col_name in enumerate(share.columns, start=2):
        label = col_name
        if col_name in site_counts:
            label = f"{col_name}({site_counts[col_name]})"
        ws.cell(row=row, column=i, value=label).font = _BOLD
    row += 1

    for idx in share.index:
        ws.cell(row=row, column=1, value=idx)
        row_total = share.loc[idx, "합계"]
        for i, col_name in enumerate(share.columns, start=2):
            value = share.loc[idx, col_name]
            pct = round(value / row_total * 100) if row_total else 0
            ws.cell(row=row, column=i, value=f"{value}({pct}%)")
        row += 1
    return row + 1


def _write_summary_table(ws, row: int, summary: pd.DataFrame) -> int:
    if summary.empty:
        return row
    ws.cell(row=row, column=1, value="구분")
    for i, col_name in enumerate(summary.columns, start=2):
        ws.cell(row=row, column=i, value=col_name).font = _BOLD
    row += 1

    for (category, label) in summary.index:
        ws.cell(row=row, column=1, value=f"{category} {label}")
        for i, col_name in enumerate(summary.columns, start=2):
            value = summary.loc[(category, label), col_name]
            ws.cell(row=row, column=i, value=value if pd.notna(value) else None)
        row += 1
    return row + 1


def _write_detail_table(ws, row: int, detail: pd.DataFrame) -> int:
    if detail.empty:
        return row
    ws.cell(row=row, column=1, value="구분")
    for i, col_name in enumerate(detail.columns, start=3):
        ws.cell(row=row, column=i, value=col_name).font = _BOLD
    row += 1

    merge_start = None
    prev_major = None
    for (major, minor) in detail.index:
        is_total = major == "합계"
        if not is_total and major != prev_major:
            if merge_start is not None and row - 1 > merge_start:
                ws.merge_cells(start_row=merge_start, start_column=1, end_row=row - 1, end_column=1)
            ws.cell(row=row, column=1, value=major)
            merge_start = row
            prev_major = major
        ws.cell(row=row, column=2, value=minor if not is_total else major)
        if is_total:
            ws.cell(row=row, column=1, value=major).font = _BOLD
            ws.cell(row=row, column=2).font = _BOLD
        for i, col_name in enumerate(detail.columns, start=3):
            value = detail.loc[(major, minor), col_name]
            cell = ws.cell(row=row, column=i, value=value if pd.notna(value) else None)
            if is_total:
                cell.font = _BOLD
        row += 1

    if merge_start is not None and row - 2 > merge_start:
        ws.merge_cells(start_row=merge_start, start_column=1, end_row=row - 2, end_column=1)
    return row + 1


def build_report_workbook(trend: pd.DataFrame, share: pd.DataFrame, summary: pd.DataFrame,
                           pl_detail: pd.DataFrame, capital_detail: pd.DataFrame) -> bytes:
    """5개 표(연도별 추이/지사유형 점유율/지사유형 배정·실적/손익 상세/자본 상세)를 한 시트에
    위아래로 쌓아 엑셀 파일 bytes로 반환한다. 금액 단위는 억원."""
    wb = Workbook()
    ws = wb.active
    ws.title = "실적집계표"

    row = 1
    row = _write_title(ws, row, "연도별 배정·실적 추이 (억원)")
    row = _write_trend_table(ws, row, trend)

    row = _write_title(ws, row, "지사유형별 실적 점유율 (억원, 지사수)")
    row = _write_share_table(ws, row, share)

    row = _write_title(ws, row, "지사유형별 배정 대비 실적 (억원)")
    row = _write_summary_table(ws, row, summary)

    row = _write_title(ws, row, "손익 계정과목별 상세 (억원)")
    row = _write_detail_table(ws, row, pl_detail)

    row = _write_title(ws, row, "자본 계정과목별 상세 (억원)")
    row = _write_detail_table(ws, row, capital_detail)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
