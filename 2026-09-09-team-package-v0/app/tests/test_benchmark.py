# -*- coding: utf-8 -*-
"""예산 표준화(3단계) 계산 — 전망 앱 v2 `tests/test_standardization.py` 승계.

Phase 6-2. v2 구현을 옮겨오면서 «같은 계산인가»를 말이 아니라 실행으로 증명한다.
그래서 본문을 손대지 않고, 모듈 별칭 `std` 도 v2 그대로 둔다 — 두 파일을 나란히
놓고 비교할 수 있어야 포팅이 옳았는지 나중에도 확인된다.

옮기지 않은 것(원본에 남아 있다):
  - 파일 IO 왕복 2건 — 상태는 6-5 에서 DB 표로 간다
  - 엑셀 import 4건 — 지사 표시명 매핑(mapping_config)이 dept_config 로 바뀐 뒤에 옮긴다
"""
import pandas as pd
import pytest

from budget import benchmark as std

def _force_method(site, account, method):
    """recommend_method()의 자동 추천과 무관하게 특정 방식을 강제하는 method_map."""
    return pd.DataFrame({"사업장": [site], "예산과목": [account], "방식": [method]})

def test_compute_grade_conditional_average():
    actuals = pd.DataFrame({
        "사업장": ["화성지사"] * 4,
        "연도": [2022, 2023, 2024, 2025],
        "예산과목": ["수선유지비-열원경상정비"] * 4,
        "금액": [100, 200, 300, 400],
    })
    grades = pd.DataFrame({
        "사업장": ["화성지사"] * 4,
        "연도": [2022, 2023, 2024, 2025],
        "등급": ["MI", "TI", "MI", "TI"],
    })
    method_map = _force_method("화성지사", "수선유지비-열원경상정비", "등급별 평균")
    result = std.compute_standard_amounts(actuals, grades, method_map)
    mi_row = result[result["등급"] == "MI"].iloc[0]
    ti_row = result[result["등급"] == "TI"].iloc[0]
    assert mi_row["표준금액"] == pytest.approx((100 + 300) / 2)
    assert ti_row["표준금액"] == pytest.approx((200 + 400) / 2)
    assert mi_row["방식출처"] == "사용자지정"

def test_compute_falls_back_to_overall_average_when_grade_missing():
    actuals = pd.DataFrame({
        "사업장": ["화성지사"] * 2,
        "연도": [2024, 2025],
        "예산과목": ["기계장치"] * 2,
        "금액": [100, 300],
    })
    grades = pd.DataFrame({"사업장": ["화성지사"] * 2, "연도": [2024, 2025], "등급": ["MI", "MI"]})
    method_map = _force_method("화성지사", "기계장치", "등급별 평균")
    result = std.compute_standard_amounts(actuals, grades, method_map)
    ci_row = result[result["등급"] == "CI"]
    assert ci_row.empty  # 등급 이력에 CI가 아예 없으면 컬럼 자체가 안 생긴다

    # CI가 이력에 존재하지만 그 연도의 실적이 없는 경우
    grades2 = pd.DataFrame({"사업장": ["화성지사"] * 3, "연도": [2023, 2024, 2025], "등급": ["CI", "MI", "MI"]})
    result2 = std.compute_standard_amounts(actuals, grades2, method_map)
    ci_row2 = result2[result2["등급"] == "CI"].iloc[0]
    assert ci_row2["표준금액"] == pytest.approx((100 + 300) / 2)
    assert "전체평균" in ci_row2["비고"]

def test_recommend_method_prefers_grade_when_it_explains_variance():
    yearly = pd.Series({2021: 100, 2022: 100, 2023: 500, 2024: 500, 2025: 100})
    grade_by_year = {2021: "MI", 2022: "MI", 2023: "TI", 2024: "TI", 2025: "MI"}
    method, reason = std.recommend_method(yearly, grade_by_year)
    assert method == "등급별 평균"
    assert "편차" in reason

def test_recommend_method_prefers_recent_when_stable():
    yearly = pd.Series({2021: 100, 2022: 102, 2023: 99, 2024: 101, 2025: 100})
    grade_by_year = {y: "A" for y in yearly.index}
    method, reason = std.recommend_method(yearly, grade_by_year)
    assert method == "최근실적"
    assert "변동" in reason

def test_recommend_method_prefers_five_year_average_when_noisy_and_no_grade_pattern():
    yearly = pd.Series({2019: 80, 2020: 220, 2021: 60, 2022: 240, 2023: 90, 2024: 210, 2025: 70})
    grade_by_year = {y: "A" for y in yearly.index}
    method, _ = std.recommend_method(yearly, grade_by_year)
    assert method == "5개년 평균"

def test_recommend_method_prefers_three_year_average_when_sparse():
    yearly = pd.Series({2023: 80, 2024: 220, 2025: 60})
    grade_by_year = {2023: "A", 2024: "A", 2025: "A"}
    method, _ = std.recommend_method(yearly, grade_by_year)
    assert method == "3개년 평균"

def test_recommend_method_single_year_uses_recent_actual():
    yearly = pd.Series({2025: 500})
    method, reason = std.recommend_method(yearly, {2025: "A"})
    assert method == "최근실적"
    assert "1개년" in reason

def test_compute_uses_auto_recommendation_when_no_explicit_method():
    actuals = pd.DataFrame({
        "사업장": ["강남지사"] * 3,
        "연도": [2023, 2024, 2025],
        "예산과목": ["지급수수료-열원점검수수료"] * 3,
        "금액": [100, 102, 99],
    })
    grades = pd.DataFrame({"사업장": ["강남지사"] * 3, "연도": [2023, 2024, 2025], "등급": ["A", "A", "A"]})
    result = std.compute_standard_amounts(actuals, grades)  # method_map 없음
    row = result.iloc[0]
    assert row["방식출처"] == "자동추천"
    assert row["산출방식"] == "최근실적"
    assert row["추천사유"] != ""

def test_compute_recent_actual_method():
    actuals = pd.DataFrame({
        "사업장": ["강남지사"] * 3,
        "연도": [2023, 2024, 2025],
        "예산과목": ["지급수수료-열원점검수수료"] * 3,
        "금액": [10, 20, 30],
    })
    grades = pd.DataFrame({"사업장": ["강남지사"] * 3, "연도": [2023, 2024, 2025], "등급": ["A", "A", "A"]})
    method_map = pd.DataFrame({"사업장": ["강남지사"], "예산과목": ["지급수수료-열원점검수수료"], "방식": ["최근실적"]})
    result = std.compute_standard_amounts(actuals, grades, method_map)
    assert result.iloc[0]["표준금액"] == 30

def test_compute_n_year_average_methods():
    actuals = pd.DataFrame({
        "사업장": ["강남지사"] * 5,
        "연도": [2021, 2022, 2023, 2024, 2025],
        "예산과목": ["지급수수료-열원점검수수료"] * 5,
        "금액": [10, 20, 30, 40, 50],
    })
    grades = pd.DataFrame({"사업장": ["강남지사"] * 5, "연도": [2021, 2022, 2023, 2024, 2025], "등급": ["A"] * 5})
    method_map = pd.DataFrame({"사업장": ["강남지사"], "예산과목": ["지급수수료-열원점검수수료"], "방식": ["3개년 평균"]})
    result = std.compute_standard_amounts(actuals, grades, method_map)
    assert result.iloc[0]["표준금액"] == pytest.approx((30 + 40 + 50) / 3)

def test_ltsa_and_cri_excluded_when_detail_available():
    actuals = pd.DataFrame({
        "사업장": ["화성지사"] * 4,
        "연도": [2023, 2023, 2024, 2024],
        "예산과목": ["기계장치"] * 4,
        "금액": [1000, 500, 2000, 300],
        "투자유형세부_확정": ["LTSA", "기타", "CRI", "기타"],
    })
    grades = pd.DataFrame({"사업장": ["화성지사"] * 2, "연도": [2023, 2024], "등급": ["MI", "MI"]})
    result = std.compute_standard_amounts(actuals, grades)
    assert result.iloc[0]["표준금액"] == pytest.approx((500 + 300) / 2)

def test_machine_total_used_as_is_without_detail_column():
    actuals = pd.DataFrame({
        "사업장": ["화성지사"] * 2,
        "연도": [2023, 2024],
        "예산과목": ["기계장치"] * 2,
        "금액": [1500, 2300],
    })
    grades = pd.DataFrame({"사업장": ["화성지사"] * 2, "연도": [2023, 2024], "등급": ["MI", "MI"]})
    assert std.has_ltsa_detail(actuals) is False
    result = std.compute_standard_amounts(actuals, grades)
    assert result.iloc[0]["표준금액"] == pytest.approx((1500 + 2300) / 2)

def test_override_takes_precedence():
    actuals = pd.DataFrame({
        "사업장": ["화성지사"], "연도": [2025], "예산과목": ["기계장치"], "금액": [1000],
    })
    grades = pd.DataFrame({"사업장": ["화성지사"], "연도": [2025], "등급": ["MI"]})
    overrides = pd.DataFrame({"사업장": ["화성지사"], "예산과목": ["기계장치"], "등급": ["MI"], "표준금액": [9999]})
    result = std.compute_standard_amounts(actuals, grades, overrides=overrides)
    assert result.iloc[0]["표준금액"] == 9999
    assert result.iloc[0]["산출방식"] == "수동수정"

def test_get_current_grade_returns_latest_year():
    grades = pd.DataFrame({
        "사업장": ["화성지사", "화성지사", "화성지사"],
        "연도": [2023, 2024, 2025],
        "등급": ["TI", "간이", "MI"],
    })
    assert std.get_current_grade("화성지사", grades) == "MI"

def test_get_current_grade_no_history_returns_none():
    grades = pd.DataFrame(columns=["사업장", "연도", "등급"])
    assert std.get_current_grade("화성지사", grades) is None
