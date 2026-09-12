"""views/custom_report_page.py의 Test 모드(render_test())를 AppTest로 검증한다.
정식 render()는 실제 classified_*.csv 파이프라인 전체가 필요해 여기서는 다루지 않는다."""
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    yield tmp_path


def _run_render_test():
    import views.custom_report_page as page
    page.render_test()


def _click_build_button(at):
    build_button = next(b for b in at.button if b.key == "report_test_build_btn")
    build_button.click().run()
    assert not at.exception
    return at


def test_shows_status_before_building(isolated):
    """만들기 버튼을 누르기 전에는 현재 상태만 보이고 리포트는 계산되지 않는다."""
    shared_df = pd.DataFrame([
        {"사업명": "테스트사업", "예산과목": "기계장치", "사업장": "700001",
         "금액": 100.0, "투자유형_확정": "기타기계장치", "투자유형세부_확정": "", "연도": 2025},
    ])
    at = AppTest.from_function(_run_render_test, default_timeout=30)
    at.session_state["ptest_shared_df"] = shared_df
    at.run()
    assert not at.exception
    assert any("실적 업로드 완료" in i.value and "리포트 미작성" in i.value for i in at.info)
    assert any(b.key == "report_test_build_btn" for b in at.button)
    assert not any(s.value == "직접 조합하기" for s in at.subheader)


def test_build_shows_pivot_filtered_by_selected_year(isolated):
    """연도별로 태그된 실적 중 선택한 연도만 피벗에 반영되어야 한다."""
    shared_df = pd.DataFrame([
        {"사업명": "2025사업", "예산과목": "기계장치", "사업장": "700001",
         "금액": 100_000_000.0, "투자유형_확정": "기타기계장치", "투자유형세부_확정": "", "연도": 2025},
        {"사업명": "2026사업", "예산과목": "기계장치", "사업장": "700001",
         "금액": 900_000_000.0, "투자유형_확정": "기타기계장치", "투자유형세부_확정": "", "연도": 2026},
    ])
    at = AppTest.from_function(_run_render_test, default_timeout=30)
    at.session_state["ptest_shared_df"] = shared_df
    at.run()
    _click_build_button(at)

    assert any(s.value == "직접 조합하기" for s in at.subheader)
    prep_status = next(s for s in at.status if s.label == "실적 데이터 준비 완료")
    assert prep_status.state == "complete"
    calc_status = next(s for s in at.status if s.label == "리포트 계산 완료")
    assert calc_status.state == "complete"

    year_select = next(m for m in at.multiselect if m.key == "report_test_years")
    assert set(year_select.value) == {2025, 2026}

    year_select.set_value([2025]).run()
    assert not at.exception

    pivot = next(d.value for d in at.dataframe)
    assert pivot.loc["700001"].sum() == pytest.approx(1.0)  # 2025년 1억원만

    # 실제 버그 재현: site_type_map.csv가 없던 상태에서 처음 만들면 그 자리에서 기본값으로
    # seed되는데(위 회귀), 그 "파일이 새로 생김" 자체가 지문에 잡혀서 아무것도 안 바꿨는데도
    # 다음 rerun에서 "데이터가 변경되었습니다"로 잘못 뜨면 안 된다.
    assert not any("데이터가 변경되었습니다" in i.value for i in at.info)


def test_build_persists_across_fresh_app_runs_without_false_change_detection(isolated):
    """앱을 재시작해도(=새 AppTest 인스턴스) 이전에 만든 리포트가 다시 계산할 필요 없이
    '작성됨'으로 남아있어야 하고, site_type_map.csv가 처음 생성되는 것만으로 '데이터가 변경되었다'고
    오판하면 안 된다."""
    import views.project_type_test_page as ptest_page

    shared_df = pd.DataFrame([
        {"사업명": "테스트사업", "예산과목": "기계장치", "사업장": "700001",
         "금액": 100_000_000.0, "투자유형_확정": "기타기계장치", "투자유형세부_확정": "", "연도": 2025},
    ])
    ptest_page.save_shared_actual_df(shared_df)  # session_state가 아니라 파일로 저장 - 재시작을 흉내낸다

    at1 = AppTest.from_function(_run_render_test, default_timeout=30)
    at1.run()
    _click_build_button(at1)
    assert any(s.value == "직접 조합하기" for s in at1.subheader)

    at2 = AppTest.from_function(_run_render_test, default_timeout=30)
    at2.run()
    assert not at2.exception
    assert any("리포트 작성됨" in i.value for i in at2.info)
    assert not any("데이터가 변경되었습니다" in i.value for i in at2.info)
    assert any(s.value == "직접 조합하기" for s in at2.subheader)
    # 진짜로 다시 계산하지 않았어야 한다 - 준비 상태 블록 자체가 나타나면 안 된다.
    assert not any(s.label == "실적 데이터 준비 완료" for s in at2.status)
    assert any("다시 계산하지 않음" in c.value for c in at2.caption)
