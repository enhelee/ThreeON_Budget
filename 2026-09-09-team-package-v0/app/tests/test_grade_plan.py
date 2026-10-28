# -*- coding: utf-8 -*-
"""전지사 정비등급 양식(2026-10-28 사용자 확정) — 가져오기·내려받기가 같은 양식을 오간다.

양식 = templates/builtin_template_정비등급.xlsx(사용자 파일 그대로). 한 해 «등급» 한 열, A열 묶음
(발전설비·DH), B열 지사, C열 설비. 대표 등급은 GT 어휘 줄 우선, 줄이 둘 이상인 지사는 설비별도.
"""
import io

import pandas as pd
from openpyxl import load_workbook

from budget import forecast_export as fe
from budget import forecast_import as fi

SITES = ["강남지사", "고양사업소", "광교지사", "광주전남지사", "김해사업소", "대구지사", "동탄지사", "분당사업소",
         "삼송지사", "세종지사", "수원사업소", "양산지사", "용인지사", "중앙지사", "청주지사", "파주지사",
         "판교지사", "평택지사", "화성지사"]


def _template_bytes():
    return open(fe.GRADE_TEMPLATE, "rb").read()


def _pivot(df):
    return {(s, int(y)): g for s, y, g in zip(df["사업장"], df["연도"], df["등급"])}


def test_reads_every_site_from_the_user_template():
    grades, units = fi.grade_plan_from_workbook(_template_bytes(), SITES)
    assert set(grades["사업장"]) == set(SITES)
    g = _pivot(grades)
    assert g[("화성지사", 2031)] == "MI"
    assert g[("중앙지사", 2026)] == "A"                    # DH 표(B열 «중앙 정비등급»)
    assert g[("광주전남지사", 2032)] == "A" and g[("광주전남지사", 2027)] == "C"
    assert g[("대구지사", 2030)] == "MI"                    # 우드칩(A)보다 신규CHP(GT 어휘) 줄
    assert g[("강남지사", 2034)] == "HGPI"                  # 동남권 GT 줄 — 일원·DH 의 A 가 아니라
    assert ("수원사업소", 2026) not in g and ("수원사업소", 2028) not in g   # «-»·«준공»은 등급 아님


def test_multi_unit_sites_keep_each_unit():
    _, units = fi.grade_plan_from_workbook(_template_bytes(), SITES)
    u = {(s, q, int(y)): g for s, q, y, g in zip(units["사업장"], units["설비"], units["연도"], units["등급"])}
    assert u[("동탄지사", "#2 Block", 2029)] == "MI"       # 대표(#1 Block) 줄만 보면 놓치는 MI
    assert u[("삼송지사", "#2 GT", 2031)] == "HGPI"
    assert u[("강남지사", "DH", 2026)] == "A"
    assert set(units["사업장"]) == {"강남지사", "대구지사", "동탄지사", "삼송지사"}


def test_schedule_importer_accepts_the_grade_plan_form():
    assert len(fi.schedule_from_workbook(_template_bytes(), SITES)) == len(fi.grade_plan_from_workbook(_template_bytes(), SITES)[0])


def test_download_round_trips_to_the_same_grades():
    grades, units = fi.grade_plan_from_workbook(_template_bytes(), SITES)
    out = fe.build_grade_plan_download(grades, SITES, 2026, units=units)
    g2, u2 = fi.grade_plan_from_workbook(out, SITES)
    assert _pivot(g2) == _pivot(grades)
    assert len(u2) == len(units)


def test_download_writes_changes_with_grade_colors_and_blanks_missing_years():
    grades, units = fi.grade_plan_from_workbook(_template_bytes(), SITES)
    grades = grades.copy()
    grades.loc[(grades["사업장"] == "화성지사") & (grades["연도"] == 2026), "등급"] = "MI"
    grades = grades[~((grades["사업장"] == "파주지사") & (grades["연도"] == 2027))]
    ws = load_workbook(io.BytesIO(fe.build_grade_plan_download(grades, SITES, 2026, units=units))).active
    assert ws["D4"].value == "MI" and ws["D4"].fill.fgColor.rgb == "FFFFFF00"     # 화성 2026
    assert ws["E6"].value is None                                                  # 파주 2027 — 저장값 없음
    assert ws["F16"].value == "준공"                                               # 수원 표시는 그대로
    assert ws["B4"].value == "화 성" and ws["A4"].value == "발전설비"              # 양식 글자 그대로


def test_download_for_next_base_year_shifts_year_headers():
    grades = pd.DataFrame([{"사업장": "화성지사", "연도": 2027, "등급": "TI"}])
    ws = load_workbook(io.BytesIO(fe.build_grade_plan_download(grades, SITES, 2027))).active
    assert ws["D1"].value == 2027 and ws["M1"].value == 2036 and ws["D21"].value == 2027
    assert ws["D4"].value == "TI" and ws["E4"].value is None


def test_screen_grid_has_every_excel_line_and_round_trips():
    """화면 표 = 엑셀 양식 줄 그대로(삼송 #1·#2 GT, 동탄 #1·#2 Block, 대구 우드칩·신규CHP, 강남 동남권·일원·DH …)."""
    grades, units = fi.grade_plan_from_workbook(_template_bytes(), SITES)
    grid = fe.grade_plan_grid(grades, SITES, 2026, units=units)
    assert grid["years"] == list(range(2026, 2036))
    lines = {(ln["site"], ln["unit"]) for ln in grid["lines"]}
    assert {("동탄지사", "#1 Block"), ("동탄지사", "#2 Block"), ("삼송지사", "#2 GT"),
            ("대구지사", "우드칩"), ("대구지사", "신규CHP"), ("강남지사", "일원"), ("중앙지사", "")} <= lines
    cells = [{"row": ln["row"], "year": int(y), "grade": v} for ln in grid["lines"] for y, v in ln["values"].items()]
    g2, u2, multi = fe.grade_plan_from_cells(cells, SITES, 2026)
    assert _pivot(g2) == _pivot(grades) and len(u2) == len(units)
    assert multi == {"강남지사", "대구지사", "동탄지사", "삼송지사"}


def test_screen_edit_of_second_unit_changes_only_that_unit():
    grades, units = fi.grade_plan_from_workbook(_template_bytes(), SITES)
    grid = fe.grade_plan_grid(grades, SITES, 2026, units=units)
    row2 = next(ln["row"] for ln in grid["lines"] if ln["site"] == "동탄지사" and ln["unit"] == "#2 Block")
    cells = [{"row": ln["row"], "year": int(y), "grade": ("HGPI" if ln["row"] == row2 and y == "2027" else v)}
             for ln in grid["lines"] for y, v in ln["values"].items()]
    g2, u2, _ = fe.grade_plan_from_cells(cells, SITES, 2026)
    u = {(q, int(y)): g for s, q, y, g in zip(u2["사업장"], u2["설비"], u2["연도"], u2["등급"]) if s == "동탄지사"}
    assert u[("#2 Block", 2027)] == "HGPI" and u[("#1 Block", 2027)] == "간이"
    assert _pivot(g2)[("동탄지사", 2027)] == "간이"            # 대표 = #1 Block 줄(GT 어휘 첫 줄)
