import os
import pytest
from budget import pipeline_plan, pipeline_actual

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
    """종합표에 반영되는 총 실적 = ERP 전체 해당예산 실적(누락 0)."""
    for budget, expected in [("손익", 98554801), ("자본", 49709178)]:
        plan_path, cfg, out = _make_plan(tmp_path, budget)
        res = pipeline_actual.run_actual(
            plan_path, ZRFM2, MASTER, cfg, out, "2025", budget, new_policy="group",
        )
        assert os.path.exists(res["output_path"])
        assert os.path.exists(res["zrfm2_v1_path"])
        # 데이터 총액은 전액 보존(계획집행+신규 = ERP 전체). 미매핑 처지사분도
        # 신규((미매핑))로 남아 총액에는 포함되며, 검토리포트로 보고된다.
        assert abs(res["요약"]["총 실적(천원)"] - expected) <= 1
        assert abs((res["요약"]["계획집행 실적(천원)"] + res["요약"]["신규 실적(천원)"]) - expected) <= 2
        # 미분류 예산과목은 없어야 함(빈문자열 제외)
        assert res["미분류과목"] == []
        # 미매핑 처지사가 있으면 금액이 함께 보고돼야 함
        if res["미매핑처지사"]:
            assert res["미매핑처지사금액"] > 0


def test_strict_policy_more_new(tmp_path):
    plan_path, cfg, out = _make_plan(tmp_path, "손익")
    grp = pipeline_actual.run_actual(plan_path, ZRFM2, MASTER, cfg, out, "2025", "손익", new_policy="group")
    strt = pipeline_actual.run_actual(plan_path, ZRFM2, MASTER, cfg, out, "2025", "손익", new_policy="strict_name")
    # 총액은 정책 무관 동일
    assert grp["요약"]["총 실적(천원)"] == strt["요약"]["총 실적(천원)"]
    # 엄격정책은 신규 실적이 더 큼
    assert strt["요약"]["신규 실적(천원)"] > grp["요약"]["신규 실적(천원)"]
