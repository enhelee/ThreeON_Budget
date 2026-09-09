import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest
from views.standardization_page import _pivot_grade_history, _unpivot_grade_history


def test_pivot_grade_history_rows_are_sites_columns_are_years_descending():
    long_df = pd.DataFrame({
        "사업장": ["화성지사", "화성지사", "중앙지사"],
        "연도": [2025, 2024, 2025],
        "등급": ["MI", "간이", "A"],
    })
    wide = _pivot_grade_history(long_df)
    assert wide.columns.tolist() == ["사업장", 2025, 2024]
    assert wide.set_index("사업장").loc["화성지사", 2025] == "MI"
    assert wide.set_index("사업장").loc["화성지사", 2024] == "간이"


def test_pivot_empty_history_returns_site_only_column():
    wide = _pivot_grade_history(pd.DataFrame(columns=["사업장", "연도", "등급"]))
    assert wide.columns.tolist() == ["사업장"]
    assert wide.empty


def test_unpivot_round_trips_back_to_long_format():
    long_df = pd.DataFrame({
        "사업장": ["화성지사", "화성지사", "중앙지사"],
        "연도": [2025, 2024, 2025],
        "등급": ["MI", "간이", "A"],
    })
    wide = _pivot_grade_history(long_df)
    back = _unpivot_grade_history(wide).sort_values(["사업장", "연도"], ascending=[True, False]).reset_index(drop=True)
    expected = long_df.sort_values(["사업장", "연도"], ascending=[True, False]).reset_index(drop=True)
    pd.testing.assert_frame_equal(back, expected)


def test_unpivot_drops_missing_cells_without_leaving_nan_string():
    """중앙지사는 2024년 이력이 없어(NaN) 셀이 빈칸이다 - 문자열 'nan'으로 새는 걸 방지하는 회귀 테스트."""
    long_df = pd.DataFrame({"사업장": ["화성지사", "중앙지사"], "연도": [2024, 2025], "등급": ["간이", "A"]})
    wide = _pivot_grade_history(long_df)
    back = _unpivot_grade_history(wide)
    assert "nan" not in back["등급"].values
    assert len(back) == 2


def test_unpivot_no_year_columns_returns_empty():
    wide = pd.DataFrame({"사업장": ["화성지사"]})
    back = _unpivot_grade_history(wide)
    assert back.empty
    assert list(back.columns) == ["사업장", "연도", "등급"]


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    yield tmp_path


def _run_render_test():
    import views.standardization_page as page
    page.render_test()


def _sample_shared_df():
    return pd.DataFrame([
        {"사업명": "테스트사업", "예산과목": "기계장치", "사업장": "700001",
         "금액": 100_000_000.0, "투자유형_확정": "기타기계장치", "투자유형세부_확정": ""},
    ])


def test_render_test_shows_status_before_building(isolated):
    """만들기 버튼을 누르기 전에는 현재 상태만 보이고 표준화는 계산되지 않는다."""
    at = AppTest.from_function(_run_render_test, default_timeout=30)
    at.session_state["ptest_shared_df"] = _sample_shared_df()
    at.run()
    assert not at.exception
    assert any("실적 업로드 완료" in i.value and "표준화 미작성" in i.value for i in at.info)
    assert any(b.key == "std_test_build_btn" for b in at.button)
    assert not any("표준 금액 계산 결과" in m.value for m in at.markdown)


def test_render_test_computes_after_build(isolated):
    """만들기 버튼을 누르면 상태 블록과 함께 표준화 계산 결과가 나온다."""
    at = AppTest.from_function(_run_render_test, default_timeout=30)
    at.session_state["ptest_shared_df"] = _sample_shared_df()
    at.run()

    build_button = next(b for b in at.button if b.key == "std_test_build_btn")
    build_button.click().run()
    assert not at.exception

    prep_status = next(s for s in at.status if s.label == "표준화 데이터 준비 완료")
    assert prep_status.state == "complete"
    assert any("표준 금액 계산 결과" in m.value for m in at.markdown)


def test_build_persists_across_fresh_app_runs_without_false_change_detection(isolated):
    """앱을 재시작해도(=새 AppTest 인스턴스) 이전에 만든 표준화 결과가 다시 계산할 필요 없이
    '작성됨'으로 남아있어야 하고, site_type_map.csv가 처음 생성되는 것만으로 '데이터가 변경되었다'고
    오판하면 안 된다."""
    import views.project_type_test_page as ptest_page
    ptest_page.save_shared_actual_df(_sample_shared_df())  # session_state가 아니라 파일로 - 재시작 흉내

    at1 = AppTest.from_function(_run_render_test, default_timeout=30)
    at1.run()
    build_button = next(b for b in at1.button if b.key == "std_test_build_btn")
    build_button.click().run()
    assert not at1.exception

    at2 = AppTest.from_function(_run_render_test, default_timeout=30)
    at2.run()
    assert not at2.exception
    assert any("표준화 작성됨" in i.value for i in at2.info)
    assert not any("데이터가 변경되었습니다" in i.value for i in at2.info)
    assert any("표준 금액 계산 결과" in m.value for m in at2.markdown)
    # 진짜로 다시 계산하지 않았어야 한다 - 준비 상태 블록 자체가 나타나면 안 된다.
    assert not any(s.label == "표준화 데이터 준비 완료" for s in at2.status)
    assert any("다시 계산하지 않음" in c.value for c in at2.caption)
