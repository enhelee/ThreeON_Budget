import json
import os

import openpyxl
import pytest

from budget import pipeline_plan, pipeline_actual
from budget.excel_actual_writer import ACTUAL_HEADER

ROOT = r"C:\Users\User\Desktop\중장기 예산 소요 전망"
REAL_PLAN = os.path.join(ROOT, "양식1_월별_템플릿(25년 계획분)_R1.xlsx")
ZRFM2 = os.path.join(ROOT, "zrfm2.XLSX")
MASTER = os.path.join(ROOT, "(20251202) 손익예산26_최종본.xlsx")

pytestmark = pytest.mark.skipif(
    not (os.path.exists(REAL_PLAN) and os.path.exists(ZRFM2)),
    reason="실제 데이터 파일 없음",
)


def _make_plan(tmp_path, budget):
    cfg = str(tmp_path / "config")
    out = str(tmp_path / "output")
    res = pipeline_plan.run_plan(REAL_PLAN, cfg, out, "2025", budget)
    return res["output_path"], cfg, out


def test_actual_total_equals_full_erp(tmp_path):
    """'열원보완및개선' 통일 후 종합표 총 실적 = ERP 전체(누락 0). 미분류·미매핑 0."""
    for budget, expected in [("손익", 98554801), ("자본", 49709178)]:
        plan_path, cfg, out = _make_plan(tmp_path, budget)
        res = pipeline_actual.run_actual(
            plan_path, ZRFM2, MASTER, cfg, out, "2025", budget, new_policy="group",
        )
        assert os.path.exists(res["output_path"])
        assert os.path.exists(res["zrfm2_v1_path"])
        assert abs(res["요약"]["총 실적(천원)"] - expected) <= 1
        assert abs((res["요약"]["계획집행 실적(천원)"] + res["요약"]["신규 실적(천원)"]) - expected) <= 2
        assert res["미매핑처지사"] == []
        # 계정코드 동일 개명 통일로 '열원보완및개선'은 더 이상 미분류가 아님
        assert res["미분류과목"] == []
        # 전체 선택(기본 시드)에선 미반영 0 (미매핑·미분류 0, 모든 과목 포함)
        assert res["요약"]["미반영(천원)"] == 0


def test_actual_sheet_layout_matches_form3(tmp_path):
    """양식1(월별) 헤더가 양식3 포맷(연번·예산과목···실적) + 분석열이고,
    실적금액은 I열(9), 구분은 K열(11)이며 zrfm2_V1에 반영구분(20열)이 있다."""
    plan_path, cfg, out = _make_plan(tmp_path, "자본")
    res = pipeline_actual.run_actual(
        plan_path, ZRFM2, MASTER, cfg, out, "2025", "자본", new_policy="group",
    )
    wb = openpyxl.load_workbook(res["output_path"])
    ws = wb["양식1(월별)"]
    header = [ws.cell(3, c).value for c in range(1, len(ACTUAL_HEADER) + 1)]
    assert header == ACTUAL_HEADER
    assert header[8] == "최종 실적금액(B)"   # I열(9)
    assert header[10] == "구분"              # K열(11)
    # 데이터 첫 행 연번=1, 실적금액 숫자
    assert ws.cell(4, 1).value == 1
    assert isinstance(ws.cell(4, 9).value, (int, float))
    wb.close()

    v1 = openpyxl.load_workbook(res["zrfm2_v1_path"])
    vs = v1[v1.sheetnames[0]]
    assert vs.cell(1, 20).value == "반영구분"
    v1.close()


def test_deselect_item_becomes_unreflected(tmp_path):
    """예산과목 하나(기계장치)를 포함 해제하면 그 실적이 종합표에서 빠지고
    동일 금액이 미반영으로 이동한다(총액=ERP 자본유니버스 보존)."""
    plan_path, cfg, out = _make_plan(tmp_path, "자본")
    base = pipeline_actual.run_actual(
        plan_path, ZRFM2, MASTER, cfg, out, "2025", "자본", new_policy="group",
    )
    base_total = base["요약"]["총 실적(천원)"]
    base_unref = base["요약"]["미반영(천원)"]

    # 과목구성에서 '기계장치' 포함 해제
    item_path = os.path.join(cfg, "과목구성_2025_자본.json")
    with open(item_path, "r", encoding="utf-8") as f:
        items = json.load(f)
    for it in items:
        if it["과목"] == "기계장치":
            it["포함"] = False
    with open(item_path, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)

    res = pipeline_actual.run_actual(
        plan_path, ZRFM2, MASTER, cfg, out, "2025", "자본", new_policy="group",
    )
    moved = base_total - res["요약"]["총 실적(천원)"]
    assert moved > 0                                   # 기계장치 실적이 종합표에서 빠짐
    # 빠진 만큼 미반영으로 이동 (반영+미반영 = 자본 유니버스 보존)
    assert abs((res["요약"]["미반영(천원)"] - base_unref) - moved) <= 2
    assert base_total + base_unref == pytest.approx(
        res["요약"]["총 실적(천원)"] + res["요약"]["미반영(천원)"], abs=2)

    # 양식1(월별)·종합표에 '기계장치'가 남지 않아야 함(선택된 항목만 포함)
    wb = openpyxl.load_workbook(res["output_path"], data_only=True)
    items_in_sheet = {wb["양식1(월별)"].cell(r, 2).value
                      for r in range(4, wb["양식1(월별)"].max_row + 1)}
    assert "기계장치" not in items_in_sheet
    summary_items = {wb["종합표"].cell(r, 2).value
                     for r in range(5, wb["종합표"].max_row + 1)}
    assert "기계장치" not in summary_items
    wb.close()
    # 그 전표들은 zrfm2_V1에서 '미반영'으로 표기
    v1 = openpyxl.load_workbook(res["zrfm2_v1_path"], data_only=True)
    vs = v1[v1.sheetnames[0]]
    assert any(vs.cell(r, 20).value == "미반영" for r in range(2, vs.max_row + 1))
    v1.close()


def test_strict_policy_more_new(tmp_path):
    plan_path, cfg, out = _make_plan(tmp_path, "손익")
    grp = pipeline_actual.run_actual(plan_path, ZRFM2, MASTER, cfg, out, "2025", "손익", new_policy="group")
    strt = pipeline_actual.run_actual(plan_path, ZRFM2, MASTER, cfg, out, "2025", "손익", new_policy="strict_name")
    # 총액은 정책 무관 동일
    assert grp["요약"]["총 실적(천원)"] == strt["요약"]["총 실적(천원)"]
    # 엄격정책은 신규 실적이 더 큼
    assert strt["요약"]["신규 실적(천원)"] > grp["요약"]["신규 실적(천원)"]
