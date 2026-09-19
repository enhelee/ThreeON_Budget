# -*- coding: utf-8 -*-
"""중장기 전망(4단계) 계산 — 전망 앱 v2 `tests/test_longterm_forecast.py` 승계.

Phase 6-4. 6-2 와 같은 방식이다. 본문을 손대지 않고 모듈 별칭 `lf` 도 v2 그대로
두어, 두 파일을 나란히 놓고 비교할 수 있게 한다.

옮기지 않은 것(원본에 남아 있다):
  - 팩터·테스트예산 파일 IO 4건 — 상태는 6-5 에서 DB 표로 간다
  - 엑셀 파서 6건 — 지사 표시명 매핑(mapping_config)이 dept_config 로 바뀐 뒤에 옮긴다
"""
import pandas as pd
import pytest

from budget import forecast_calc as lf

def test_year_multiplier_single_factor_compounds():
    factors = pd.DataFrame([{"팩터명": "물가상승률", "연간비율": 0.1, "활성": True}])
    assert lf.year_multiplier(2026, factors) == pytest.approx(1.0)
    assert lf.year_multiplier(2027, factors) == pytest.approx(1.1)
    assert lf.year_multiplier(2028, factors) == pytest.approx(1.21)


def test_year_multiplier_multiplies_multiple_active_factors():
    factors = pd.DataFrame([
        {"팩터명": "물가상승률", "연간비율": 0.1, "활성": True},
        {"팩터명": "노후화", "연간비율": 0.05, "활성": True},
    ])
    assert lf.year_multiplier(2027, factors) == pytest.approx(1.1 * 1.05)


def test_year_multiplier_ignores_inactive_factor():
    factors = pd.DataFrame([
        {"팩터명": "물가상승률", "연간비율": 0.1, "활성": True},
        {"팩터명": "노후화", "연간비율": 0.5, "활성": False},
    ])
    assert lf.year_multiplier(2027, factors) == pytest.approx(1.1)


def test_year_multiplier_before_base_year_is_one():
    factors = pd.DataFrame([{"팩터명": "물가상승률", "연간비율": 0.1, "활성": True}])
    assert lf.year_multiplier(2020, factors) == 1.0


def test_allocate_hq_temp_projects_uses_ratio():
    temp_df = pd.DataFrame([{"사업명": "긴급공사", "예산과목": "기계장치", "연도": 2026, "금액": 1000.0}])
    ratio_df = pd.DataFrame([
        {"사업장": "화성지사", "계약체결금액": 600.0},
        {"사업장": "동탄지사", "계약체결금액": 400.0},
    ])
    result = lf.allocate_hq_temp_projects(temp_df, ratio_df)
    amounts = dict(zip(result["사업장"], result["금액"]))
    assert amounts["화성지사"] == pytest.approx(600.0)
    assert amounts["동탄지사"] == pytest.approx(400.0)


def test_allocate_hq_temp_projects_empty_inputs_return_empty():
    empty = pd.DataFrame(columns=["사업명", "예산과목", "연도", "금액"])
    ratio_df = pd.DataFrame(columns=["사업장", "계약체결금액"])
    result = lf.allocate_hq_temp_projects(empty, ratio_df)
    assert result.empty


def test_compute_site_table_applies_grade_specific_standard_and_inflation():
    grade_hist = pd.DataFrame({"사업장": ["화성지사"] * 2, "연도": [2026, 2027], "등급": ["간이", "TI"]})
    standard_df = pd.DataFrame([
        {"사업장": "화성지사", "구분": "손익", "예산과목": "수선유지비-열원경상정비", "등급": "간이", "표준금액": 100.0},
        {"사업장": "화성지사", "구분": "손익", "예산과목": "수선유지비-열원경상정비", "등급": "TI", "표준금액": 200.0},
    ])
    factors = pd.DataFrame([{"팩터명": "물가상승률", "연간비율": 0.1, "활성": True}])
    empty_hot = pd.DataFrame(columns=["사업장", "연도", "항목", "금액"])
    empty_temp_alloc = pd.DataFrame(columns=["사업장", "연도", "예산과목", "금액"])
    empty_surprise = pd.DataFrame(columns=["사업장", "연도", "예산과목", "금액", "사유"])
    empty_investment = pd.DataFrame(columns=["사업장", "지사유형", "금액"])

    table = lf.compute_site_table("화성지사", grade_hist, standard_df, empty_hot, {},
                                   empty_temp_alloc, factors, empty_surprise, empty_investment)
    row = table[table["예산과목"] == "수선유지비-열원경상정비"].iloc[0]
    assert row[2026] == pytest.approx(100.0)
    assert row[2027] == pytest.approx(200.0 * 1.1)


def test_compute_site_table_uses_latest_known_grade_for_unlisted_future_years():
    grade_hist = pd.DataFrame({"사업장": ["화성지사"], "연도": [2026], "등급": ["간이"]})
    standard_df = pd.DataFrame([
        {"사업장": "화성지사", "구분": "손익", "예산과목": "수선유지비-열원경상정비", "등급": "간이", "표준금액": 100.0},
    ])
    factors = pd.DataFrame([{"팩터명": "물가상승률", "연간비율": 0.0, "활성": True}])
    empty_hot = pd.DataFrame(columns=["사업장", "연도", "항목", "금액"])
    empty_temp_alloc = pd.DataFrame(columns=["사업장", "연도", "예산과목", "금액"])
    empty_surprise = pd.DataFrame(columns=["사업장", "연도", "예산과목", "금액", "사유"])
    empty_investment = pd.DataFrame(columns=["사업장", "지사유형", "금액"])

    table = lf.compute_site_table("화성지사", grade_hist, standard_df, empty_hot, {},
                                   empty_temp_alloc, factors, empty_surprise, empty_investment)
    row = table[table["예산과목"] == "수선유지비-열원경상정비"].iloc[0]
    assert row[2030] == pytest.approx(100.0)


def test_compute_site_table_hot_parts_passthrough_without_factor():
    grade_hist = pd.DataFrame(columns=["사업장", "연도", "등급"])
    standard_df = pd.DataFrame(columns=["사업장", "구분", "예산과목", "등급", "표준금액"])
    hot_parts = pd.DataFrame([{"사업장": "화성지사", "연도": 2027, "항목": "고온부품재생", "금액": 5000.0}])
    factors = pd.DataFrame([{"팩터명": "물가상승률", "연간비율": 0.5, "활성": True}])
    empty_temp_alloc = pd.DataFrame(columns=["사업장", "연도", "예산과목", "금액"])
    empty_surprise = pd.DataFrame(columns=["사업장", "연도", "예산과목", "금액", "사유"])
    empty_investment = pd.DataFrame(columns=["사업장", "지사유형", "금액"])

    table = lf.compute_site_table("화성지사", grade_hist, standard_df, hot_parts, {},
                                   empty_temp_alloc, factors, empty_surprise, empty_investment)
    row = table[table["예산과목"] == "기계장치_고온부품재생"].iloc[0]
    assert row[2027] == 5000.0


def test_budget_amount_by_site_account_aggregates_by_site_and_account(monkeypatch):
    budget_df = pd.DataFrame([
        {"예산귀속 \n부서코드": "H001", "예산과목": "수선유지비-열원경상정비", "연예산 합계": 100.0},
        {"예산귀속 \n부서코드": "H001", "예산과목": "수선유지비-열원경상정비", "연예산 합계": 50.0},
        {"예산귀속 \n부서코드": "H001", "예산과목": "기계장치", "연예산 합계": 30.0},
    ])
    monkeypatch.setattr(lf, "get_site_display_name", lambda code: "화성지사")
    lookup = lf.budget_amount_by_site_account(budget_df)
    assert lookup[("화성지사", "수선유지비-열원경상정비")] == 150.0
    assert lookup[("화성지사", "기계장치")] == 30.0


def test_budget_amount_by_site_account_empty_df_returns_empty_dict():
    assert lf.budget_amount_by_site_account(pd.DataFrame()) == {}


def test_compute_site_table_uses_budget_plan_for_base_year_when_available():
    grade_hist = pd.DataFrame({"사업장": ["화성지사"] * 2, "연도": [2026, 2027], "등급": ["간이", "간이"]})
    standard_df = pd.DataFrame([
        {"사업장": "화성지사", "구분": "손익", "예산과목": "수선유지비-열원경상정비", "등급": "간이", "표준금액": 100.0},
    ])
    factors = pd.DataFrame([{"팩터명": "물가상승률", "연간비율": 0.1, "활성": True}])
    empty_hot = pd.DataFrame(columns=["사업장", "연도", "항목", "금액"])
    empty_temp_alloc = pd.DataFrame(columns=["사업장", "연도", "예산과목", "금액"])
    empty_surprise = pd.DataFrame(columns=["사업장", "연도", "예산과목", "금액", "사유"])
    empty_investment = pd.DataFrame(columns=["사업장", "지사유형", "금액"])
    budget_lookup = {("화성지사", "수선유지비-열원경상정비"): 555.0}

    table = lf.compute_site_table("화성지사", grade_hist, standard_df, empty_hot, {},
                                   empty_temp_alloc, factors, empty_surprise, empty_investment,
                                   budget_lookup)
    row = table[table["예산과목"] == "수선유지비-열원경상정비"].iloc[0]
    assert row[2026] == pytest.approx(555.0)  # 당해년도 - 예산계획 확정값
    assert row[2027] == pytest.approx(100.0 * 1.1)


def test_compute_site_table_falls_back_to_standard_when_budget_plan_missing_entry():
    grade_hist = pd.DataFrame({"사업장": ["화성지사"], "연도": [2026], "등급": ["간이"]})
    standard_df = pd.DataFrame([
        {"사업장": "화성지사", "구분": "손익", "예산과목": "수선유지비-열원경상정비", "등급": "간이", "표준금액": 100.0},
    ])
    factors = pd.DataFrame([{"팩터명": "물가상승률", "연간비율": 0.0, "활성": True}])
    empty_hot = pd.DataFrame(columns=["사업장", "연도", "항목", "금액"])
    empty_temp_alloc = pd.DataFrame(columns=["사업장", "연도", "예산과목", "금액"])
    empty_surprise = pd.DataFrame(columns=["사업장", "연도", "예산과목", "금액", "사유"])
    empty_investment = pd.DataFrame(columns=["사업장", "지사유형", "금액"])
    budget_lookup = {("동탄지사", "수선유지비-열원경상정비"): 999.0}  # 다른 지사 - 화성지사엔 매칭 안 됨

    table = lf.compute_site_table("화성지사", grade_hist, standard_df, empty_hot, {},
                                   empty_temp_alloc, factors, empty_surprise, empty_investment,
                                   budget_lookup)
    row = table[table["예산과목"] == "수선유지비-열원경상정비"].iloc[0]
    assert row[2026] == pytest.approx(100.0)


def test_compute_site_table_adds_hq_master_allocation_on_top_of_budget_plan_for_base_year():
    """원본 양식의 "26년" 시트는 총원가배분(전체) = 본사 + 지사로 나뉜다 - 본사 원가분배 마스터 표
    (hq_amount_by_site_acct)가 이 계정을 다루면(경상정비 등 HQ_CATEGORY_TO_ACCOUNT에 있는 계정)
    그 배분값은 지사 자체 몫(예산계획)을 대체하는 게 아니라 더해진다. 서로 다른 부서코드에 잡힌
    별도 예산이라 합쳐야 그 지사의 26년 총액이 된다."""
    grade_hist = pd.DataFrame({"사업장": ["화성지사"] * 2, "연도": [2026, 2027], "등급": ["간이", "간이"]})
    standard_df = pd.DataFrame([
        {"사업장": "화성지사", "구분": "손익", "예산과목": "수선유지비-열원경상정비", "등급": "간이", "표준금액": 100.0},
    ])
    factors = pd.DataFrame([{"팩터명": "물가상승률", "연간비율": 0.1, "활성": True}])
    empty_hot = pd.DataFrame(columns=["사업장", "연도", "항목", "금액"])
    empty_temp_alloc = pd.DataFrame(columns=["사업장", "연도", "예산과목", "금액"])
    empty_surprise = pd.DataFrame(columns=["사업장", "연도", "예산과목", "금액", "사유"])
    empty_investment = pd.DataFrame(columns=["사업장", "지사유형", "금액"])
    hq_amount = {("화성지사", "수선유지비-열원경상정비"): 777.0}
    budget_lookup = {("화성지사", "수선유지비-열원경상정비"): 555.0}

    table = lf.compute_site_table("화성지사", grade_hist, standard_df, empty_hot, hq_amount,
                                   empty_temp_alloc, factors, empty_surprise, empty_investment,
                                   budget_lookup)
    row = table[table["예산과목"] == "수선유지비-열원경상정비"].iloc[0]
    assert row[2026] == pytest.approx(555.0 + 777.0)  # 지사 몫(예산계획) + 본사 배분 몫
    assert row[2027] == pytest.approx(100.0 * 1.1)


def test_compute_site_table_hq_master_zero_when_other_site_has_entry():
    """본사 원가분배 마스터 표에 이 지사·계정 배분이 없으면(예: 마스터 표에 없는 신규 지사) 본사 몫은
    0으로 더해져 예산계획 금액만 그대로 남는다."""
    grade_hist = pd.DataFrame({"사업장": ["화성지사"], "연도": [2026], "등급": ["간이"]})
    standard_df = pd.DataFrame([
        {"사업장": "화성지사", "구분": "손익", "예산과목": "수선유지비-열원경상정비", "등급": "간이", "표준금액": 100.0},
    ])
    factors = pd.DataFrame([{"팩터명": "물가상승률", "연간비율": 0.0, "활성": True}])
    empty_hot = pd.DataFrame(columns=["사업장", "연도", "항목", "금액"])
    empty_temp_alloc = pd.DataFrame(columns=["사업장", "연도", "예산과목", "금액"])
    empty_surprise = pd.DataFrame(columns=["사업장", "연도", "예산과목", "금액", "사유"])
    empty_investment = pd.DataFrame(columns=["사업장", "지사유형", "금액"])
    hq_amount = {("동탄지사", "수선유지비-열원경상정비"): 777.0}  # 다른 지사 - 화성지사엔 매칭 안 됨
    budget_lookup = {("화성지사", "수선유지비-열원경상정비"): 555.0}

    table = lf.compute_site_table("화성지사", grade_hist, standard_df, empty_hot, hq_amount,
                                   empty_temp_alloc, factors, empty_surprise, empty_investment,
                                   budget_lookup)
    row = table[table["예산과목"] == "수선유지비-열원경상정비"].iloc[0]
    assert row[2026] == pytest.approx(555.0)


def test_compute_site_table_building_line_adds_hq_master_via_label_alias():
    """"수선유지비-건물/구축물"(표준화 라인)의 본사 배분 몫은 본사 원가분배 마스터 표에서
    "건물/구축물"(접두어 없는 라벨, HQ_CATEGORY_TO_ACCOUNT["건물구축물"])로 저장돼 있어 표기가
    다르다 - STANDARDIZED_ACCOUNT_TO_HQ_LABEL 별칭으로 찾아서 더해야 한다."""
    grade_hist = pd.DataFrame({"사업장": ["화성지사"], "연도": [2026], "등급": ["간이"]})
    standard_df = pd.DataFrame([
        {"사업장": "화성지사", "구분": "손익", "예산과목": "수선유지비-건물/구축물", "등급": "간이", "표준금액": 100.0},
    ])
    factors = pd.DataFrame([{"팩터명": "물가상승률", "연간비율": 0.0, "활성": True}])
    empty_hot = pd.DataFrame(columns=["사업장", "연도", "항목", "금액"])
    empty_temp_alloc = pd.DataFrame(columns=["사업장", "연도", "예산과목", "금액"])
    empty_surprise = pd.DataFrame(columns=["사업장", "연도", "예산과목", "금액", "사유"])
    empty_investment = pd.DataFrame(columns=["사업장", "지사유형", "금액"])
    hq_amount = {("화성지사", "건물/구축물"): 242.0}  # 마스터 표 라벨은 "건물/구축물"(접두어 없음)

    table = lf.compute_site_table("화성지사", grade_hist, standard_df, empty_hot, hq_amount,
                                   empty_temp_alloc, factors, empty_surprise, empty_investment)
    row = table[table["예산과목"] == "수선유지비-건물/구축물"].iloc[0]
    assert row[2026] == pytest.approx(100.0 + 242.0)


def test_compute_site_table_without_budget_lookup_behaves_as_before():
    grade_hist = pd.DataFrame({"사업장": ["화성지사"], "연도": [2026], "등급": ["간이"]})
    standard_df = pd.DataFrame([
        {"사업장": "화성지사", "구분": "손익", "예산과목": "수선유지비-열원경상정비", "등급": "간이", "표준금액": 100.0},
    ])
    factors = pd.DataFrame([{"팩터명": "물가상승률", "연간비율": 0.0, "활성": True}])
    empty_hot = pd.DataFrame(columns=["사업장", "연도", "항목", "금액"])
    empty_temp_alloc = pd.DataFrame(columns=["사업장", "연도", "예산과목", "금액"])
    empty_surprise = pd.DataFrame(columns=["사업장", "연도", "예산과목", "금액", "사유"])
    empty_investment = pd.DataFrame(columns=["사업장", "지사유형", "금액"])

    table = lf.compute_site_table("화성지사", grade_hist, standard_df, empty_hot, {},
                                   empty_temp_alloc, factors, empty_surprise, empty_investment)
    row = table[table["예산과목"] == "수선유지비-열원경상정비"].iloc[0]
    assert row[2026] == pytest.approx(100.0)


def test_compute_site_table_adds_surprise_project():
    grade_hist = pd.DataFrame(columns=["사업장", "연도", "등급"])
    standard_df = pd.DataFrame(columns=["사업장", "구분", "예산과목", "등급", "표준금액"])
    empty_hot = pd.DataFrame(columns=["사업장", "연도", "항목", "금액"])
    factors = pd.DataFrame([{"팩터명": "물가상승률", "연간비율": 0.0, "활성": True}])
    empty_temp_alloc = pd.DataFrame(columns=["사업장", "연도", "예산과목", "금액"])
    surprise = pd.DataFrame([
        {"사업장": "화성지사", "연도": 2028, "예산과목": "공구와기구-열원시설공기구", "금액": 999.0, "사유": "돌발"},
    ])
    empty_investment = pd.DataFrame(columns=["사업장", "지사유형", "금액"])

    table = lf.compute_site_table("화성지사", grade_hist, standard_df, empty_hot, {},
                                   empty_temp_alloc, factors, surprise, empty_investment)
    row = table[table["예산과목"] == "공구와기구-열원시설공기구"].iloc[0]
    assert row[2028] == 999.0
    assert row[2027] == 0.0
