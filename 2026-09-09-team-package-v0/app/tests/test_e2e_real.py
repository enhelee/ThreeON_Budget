import os
import pytest
from budget import pipeline_plan

ROOT = r"C:\Users\User\Desktop\중장기 예산 소요 전망"
REAL_PLAN = os.path.join(ROOT, "양식1_월별_템플릿(25년 계획분)_R1.xlsx")


@pytest.mark.skipif(not os.path.exists(REAL_PLAN), reason="실제 사업별 예산 파일 없음")
def test_real_data_classification_covers_all_items(tmp_path):
    config_dir = str(tmp_path / "config")
    out_dir = str(tmp_path / "output")

    res_pl = pipeline_plan.run_plan(REAL_PLAN, config_dir, out_dir, "2025", "손익")
    res_cap = pipeline_plan.run_plan(REAL_PLAN, config_dir, out_dir, "2025", "자본")

    assert os.path.exists(res_pl["output_path"])
    assert os.path.exists(res_cap["output_path"])

    # 시드 19개 과목이 실제 16종 예산과목을 모두 커버 -> 미분류 없어야 함
    assert res_pl["요약"]["미분류과목"] == []
    assert res_cap["요약"]["미분류과목"] == []

    # 손익+자본 필터된 행수 합계가 전체 유효 행수(1700)와 일치해야 함
    assert res_pl["요약"]["행수"] + res_cap["요약"]["행수"] == 1700
