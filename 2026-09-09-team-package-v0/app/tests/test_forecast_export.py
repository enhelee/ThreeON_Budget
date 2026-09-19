# -*- coding: utf-8 -*-
"""재무팀 양식 내보내기 — v2 `test_standardization_template.py`·`test_longterm_forecast_template.py` 승계 (Phase 6-7).

바뀐 것: 입력 단위가 **천원**이다(v2 는 원). 양식 라벨을 따라 표준화 지사 시트·고온부품·총원가 배분은
그대로, 중장기 지사탭·총괄표(«백만원»)만 /1,000. 시트명 → 지사명 매핑은 dept_config 지사명에서.
"""
import io
import os

import pandas as pd
import pytest
from openpyxl import Workbook, load_workbook

from budget import forecast_export as fe

SITES = ["화성지사", "동탄지사", "광주전남지사", "수원사업소"]


def _save(wb) -> bytes:
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _write(tmp_path, name, data):
    p = tmp_path / name
    p.write_bytes(data)
    return str(p)


# ---------------------------------------------------------------- set_cell (병합 셀 안전)
def test_set_cell_writes_normal_cell():
    ws = Workbook().active
    fe.set_cell(ws, 1, 1, "값")
    assert ws.cell(row=1, column=1).value == "값"


def test_set_cell_unmerges_and_writes_when_target_is_merged():
    """지사 시트에 남은 빈 병합 셀(예: 삼송 D34:D39)에 쓰면 MergedCell read-only 오류 — 병합을 풀고 쓴다."""
    ws = Workbook().active
    ws.merge_cells("D34:D39")
    fe.set_cell(ws, 34, 4, "값1")
    fe.set_cell(ws, 35, 4, "값2")
    assert len(ws.merged_cells.ranges) == 0
    assert ws.cell(row=34, column=4).value == "값1" and ws.cell(row=35, column=4).value == "값2"


def test_set_cell_only_unmerges_the_overlapping_range():
    ws = Workbook().active
    ws.merge_cells("D34:D39")
    ws.merge_cells("F1:F3")
    fe.set_cell(ws, 35, 4, "값")
    assert [str(r) for r in ws.merged_cells.ranges] == ["F1:F3"]


# ---------------------------------------------------------------- 정기점검 일정 (현재값 양식)
def _schedule_template():
    wb = Workbook()
    ws = wb.active
    ws.title = "정기점검보수공사 일정(2026~2041)"
    ws.cell(row=1, column=1, value="구 분")
    ws.cell(row=1, column=3, value=2026)
    ws.cell(row=1, column=6, value=2027)
    ws.cell(row=2, column=3, value="등급")
    ws.cell(row=2, column=6, value="등급")
    for c, v in ((3, "GT"), (4, "ST"), (5, "기간"), (6, "GT"), (7, "ST"), (8, "기간")):
        ws.cell(row=3, column=c, value=v)
    ws.cell(row=4, column=1, value="화 성")
    ws.cell(row=4, column=3, value="MI")
    ws.cell(row=4, column=6, value="MI")
    return _save(wb)


def test_schedule_download_overwrites_with_current_grade_history(tmp_path):
    tpl = _write(tmp_path, "sched.xlsx", _schedule_template())
    grade_hist = pd.DataFrame({"사업장": ["화성지사", "화성지사"], "연도": [2026, 2027], "등급": ["간이", "TI"]})
    ws = load_workbook(io.BytesIO(fe.build_schedule_download(grade_hist, SITES, template_path=tpl)), data_only=True).active
    assert ws.cell(row=4, column=3).value == "간이"
    assert ws.cell(row=4, column=6).value == "TI"


def test_schedule_download_ignores_years_without_history(tmp_path):
    tpl = _write(tmp_path, "sched.xlsx", _schedule_template())
    grade_hist = pd.DataFrame({"사업장": ["화성지사"], "연도": [2026], "등급": ["간이"]})
    ws = load_workbook(io.BytesIO(fe.build_schedule_download(grade_hist, SITES, template_path=tpl)), data_only=True).active
    assert ws.cell(row=4, column=3).value == "간이"
    assert ws.cell(row=4, column=6).value == "MI"          # 이력 없는 해는 원본 그대로


def test_schedule_download_skips_past_years_before_base_year(tmp_path):
    """일정 양식은 미래(기준연도~)만 담는다 — 과거 등급 이력은 쓰지 않는다."""
    tpl = _write(tmp_path, "sched.xlsx", _schedule_template())
    grade_hist = pd.DataFrame({"사업장": ["화성지사", "화성지사"], "연도": [2026, 2027], "등급": ["간이", "TI"]})
    ws = load_workbook(io.BytesIO(fe.build_schedule_download(grade_hist, SITES, base_year=2027, template_path=tpl)),
                       data_only=True).active
    assert ws.cell(row=4, column=3).value == "MI"          # 2026 은 2027 기준에선 과거 → 원본
    assert ws.cell(row=4, column=6).value == "TI"


# ---------------------------------------------------------------- 고온부품 (천원 그대로)
def _hot_parts_template():
    wb = Workbook()
    ws = wb.active
    ws.title = "고온부품(26)"
    ws.cell(row=4, column=1, value="구  분")
    ws.cell(row=4, column=6, value="26년")
    ws.cell(row=4, column=7, value="27년")
    ws.cell(row=5, column=1, value="화성")
    ws.cell(row=5, column=4, value="기계장치")
    ws.cell(row=5, column=5, value="고온부품재생")
    ws.cell(row=5, column=6, value=999)
    ws.cell(row=5, column=7, value=0)
    return _save(wb)


def test_hot_parts_download_writes_thousand_won_as_is(tmp_path):
    tpl = _write(tmp_path, "hp.xlsx", _hot_parts_template())
    hot = pd.DataFrame([{"사업장": "화성지사", "연도": 2026, "항목": "고온부품재생", "금액": 1000.0}])
    ws = load_workbook(io.BytesIO(fe.build_hot_parts_download(hot, SITES, template_path=tpl)), data_only=True).active
    assert ws.cell(row=5, column=6).value == 1000          # v2 는 1,000,000원 → 1000 이었다
    assert ws.cell(row=5, column=7).value == 0


# ---------------------------------------------------------------- 본사 원가분배 (그대로)
def _hq_template():
    wb = Workbook()
    ws = wb.active
    ws.title = "26년 본사 원가분배"
    ws.cell(row=5, column=1, value="총계")
    ws.cell(row=5, column=4, value="26년 예산")
    ws.cell(row=5, column=5, value="화성")
    ws.cell(row=5, column=6, value="동탄")
    ws.cell(row=6, column=1, value="플랜트")
    ws.cell(row=6, column=2, value="경상정비")
    ws.cell(row=6, column=3, value="중대형")
    ws.cell(row=6, column=4, value=1000)
    ws.cell(row=6, column=5, value=1)
    ws.cell(row=6, column=6, value=1)
    ws.cell(row=7, column=1, value="합계")
    return _save(wb)


def test_hq_master_download_overwrites_with_current_master(tmp_path):
    tpl = _write(tmp_path, "hq.xlsx", _hq_template())
    master = pd.DataFrame([{"대분류": "플랜트", "중분류": "경상정비", "세부내역": "중대형", "26년예산": 1000,
                            "화성지사": 600, "동탄지사": 400}])
    ws = load_workbook(io.BytesIO(fe.build_hq_master_download(master, SITES, template_path=tpl)), data_only=True).active
    assert ws.cell(row=6, column=5).value == 600 and ws.cell(row=6, column=6).value == 400


# ---------------------------------------------------------------- 총괄표 (백만원)
def test_fill_summary_sheet_resolves_profit_loss_account_not_orphaned_hq_line():
    """'수선유지비-건물/구축물'(표준화)과 orphan 라벨 '건물/구축물'(본사배분)이 총괄표에서는 같은 셀 텍스트로
    보인다 — 값이 있는 표준화 계정으로 매칭되어야 한다. 천원 → 백만원."""
    wb = Workbook()
    ws = wb.active
    ws.title = "총괄표"
    ws.cell(row=3, column=1, value="총괄표")
    ws.cell(row=3, column=3, value="26년")
    ws.cell(row=4, column=1, value="수선유지비")
    ws.cell(row=4, column=2, value="건물/구축물")
    ws.cell(row=5, column=2, value="열원정기점검")
    ws.cell(row=6, column=1, value="건물")
    site_table = pd.DataFrame([
        {"예산과목": "수선유지비-건물/구축물", 2026: 5_000.0},
        {"예산과목": "건물/구축물", 2026: 1.0},
        {"예산과목": "수선유지비-열원정기점검", 2026: 2_000.0},
    ])
    fe.fill_summary_sheet(ws, {"화성지사": site_table})
    assert ws.cell(row=4, column=3).value == 5.0
    assert ws.cell(row=5, column=3).value == 2.0
    assert ws.cell(row=6, column=3).value is None


# ---------------------------------------------------------------- 실제 내장 양식 스모크
@pytest.mark.skipif(not os.path.exists(fe.STD_TEMPLATE), reason="내장 표준화 양식 없음")
def test_standardization_workbook_fills_real_template_in_thousand_won():
    actuals = pd.DataFrame([{"사업장": "화성지사", "연도": 2025, "예산과목": "수선유지비-열원경상정비", "금액": 6074554.26},
                            {"사업장": "화성지사", "연도": 2024, "예산과목": "수선유지비-열원경상정비", "금액": 5000000.0}])
    grade = pd.DataFrame([{"사업장": "화성지사", "연도": 2025, "등급": "TI"}])
    std = pd.DataFrame([{"사업장": "화성지사", "구분": "손익", "예산과목": "수선유지비-열원경상정비", "등급": "TI",
                         "표준금액": 5537277.13, "산출방식": "3개년 평균", "방식출처": "자동추천", "추천사유": "", "비고": "3개년 평균"}])
    data = fe.fill_standardization_workbook(actuals, grade, std, SITES)
    wb = load_workbook(io.BytesIO(data))
    ws = wb["화성"]
    years = fe._find_year_row(ws)
    col_2025 = next(c for c, y in years.items() if y == 2025)
    row = fe._find_row_by_exact_label(ws, "수선유지비-열원경상정비")
    assert ws.cell(row=row, column=col_2025).value == round(6074554.26, 2)     # 천원 그대로
    assert wb["표준화방향"] is not None and len(wb.sheetnames) == 25


@pytest.mark.skipif(not os.path.exists(fe.LT_TEMPLATE), reason="내장 중장기 양식 없음")
def test_longterm_workbook_fills_real_template_site_tab_in_million_won():
    years = list(range(2026, 2036))
    table = pd.DataFrame([{"예산과목": "수선유지비-열원경상정비", **{y: 1_234_567.0 for y in years}},
                          {"예산과목": "투자비", **{y: 0.0 for y in years}}])
    grade = pd.DataFrame([{"사업장": "화성지사", "연도": 2027, "등급": "TI"}])
    data = fe.fill_longterm_workbook({"화성지사": table}, grade, pd.DataFrame(), SITES)
    ws = load_workbook(io.BytesIO(data))["화성"]
    year_by_col = fe._find_bare_year_row(ws)
    col_2026 = next(c for c, y in year_by_col.items() if y == 2026)
    row = next(r for r in range(1, ws.max_row + 1)
               if str(ws.cell(row=r, column=2).value or "").strip() == "열원경상정비")
    assert ws.cell(row=row, column=col_2026).value == round(1_234_567.0 / 1000, 3)   # 천원 → 백만원
    grade_row = next(r for r in range(1, ws.max_row + 1) if str(ws.cell(row=r, column=1).value or "").strip() == "정비등급")
    col_2027 = next(c for c, y in year_by_col.items() if y == 2027)
    assert ws.cell(row=grade_row, column=col_2027).value == "TI"


def test_fill_summary_sheet_stops_at_main_block_and_keeps_reference_blocks():
    """총괄표 아래의 참고 블록(«손익예산(2025중장기)» 전년 실측치·수식)은 건드리지 않는다.
    v2 는 시트 끝까지 라벨을 매칭해 이 블록까지 덮어썼다(6-7 실측)."""
    wb = Workbook()
    ws = wb.active
    ws.title = "총괄표"
    ws.cell(row=3, column=1, value="총괄표")
    ws.cell(row=3, column=3, value="26년")
    ws.cell(row=4, column=1, value="수선유지비")
    ws.cell(row=4, column=2, value="열원경상정비")
    ws.cell(row=5, column=1, value="투자비")
    ws.cell(row=5, column=2, value="열원공사비 등")
    # 빈 행 6~7 뒤의 참고 블록
    ws.cell(row=8, column=1, value="손익예산(2025중장기)")
    ws.cell(row=8, column=3, value="25년")
    ws.cell(row=9, column=1, value="수선유지비")
    ws.cell(row=9, column=2, value="열원경상정비")
    ws.cell(row=9, column=3, value=42214000)          # 전년 실측치 — 남아 있어야 한다
    table = pd.DataFrame([{"예산과목": "수선유지비-열원경상정비", 2026: 3_000.0}, {"예산과목": "투자비", 2026: 500.0}])
    fe.fill_summary_sheet(ws, {"화성지사": table})
    assert ws.cell(row=4, column=3).value == 3.0
    assert ws.cell(row=5, column=3).value == 0.5
    assert ws.cell(row=9, column=3).value == 42214000


# ---------------------------------------------------------------- 총원가 배분 (지사 블록만, 천원)
def test_fill_total_cost_sheet_writes_only_site_block_with_own_share():
    """본사 블록(원가분배 참조 수식)·전체 블록((본사+지사)/1000 수식)은 보존, 지사 블록에는
    지사 탭 값 − 본사배분 몫. v2 는 여섯 블록을 다 덮어써 수식을 지웠다."""
    wb = Workbook()
    ws = wb.active
    ws.title = "26년 총원가 배분"
    ws.cell(row=3, column=1, value="본사(단위 : 천원)")
    ws.cell(row=3, column=4, value="26년 예산")
    ws.cell(row=3, column=5, value="화성")
    ws.cell(row=4, column=1, value="손익예산 전체")
    ws.cell(row=4, column=3, value="열원경상정비")
    ws.cell(row=4, column=5, value="='26년 본사 원가분배'!E50")
    ws.cell(row=6, column=1, value="지사(단위 : 천원)")
    ws.cell(row=7, column=1, value="손익예산 전체")
    ws.cell(row=7, column=3, value="열원경상정비")
    ws.cell(row=7, column=5, value=1)
    ws.cell(row=8, column=2, value="투자비")
    ws.cell(row=8, column=3, value="열원공사비 등")
    ws.cell(row=8, column=5, value=1)
    ws.cell(row=10, column=1, value="전체(단위 : 백만원)")
    ws.cell(row=11, column=1, value="손익예산 전체")
    ws.cell(row=11, column=3, value="열원경상정비")
    ws.cell(row=11, column=5, value="=ROUND((E4+E7)/1000,0)")
    table = pd.DataFrame([{"예산과목": "수선유지비-열원경상정비", 2026: 5_000.0}, {"예산과목": "투자비", 2026: 300.0}])
    hq_master = pd.DataFrame([{"대분류": "플랜트", "중분류": "경상정비", "세부내역": "", "26년예산": 800, "화성지사": 800}])
    fe.fill_total_cost_sheet(ws, {"화성지사": table}, SITES, 2026, hq_master)
    assert ws.cell(row=4, column=5).value == "='26년 본사 원가분배'!E50"      # 본사 블록 보존
    assert ws.cell(row=7, column=5).value == 4_200.0                         # 5,000 − 본사배분 800
    assert ws.cell(row=8, column=5).value == 300.0
    assert ws.cell(row=11, column=5).value == "=ROUND((E4+E7)/1000,0)"      # 전체 블록 보존
