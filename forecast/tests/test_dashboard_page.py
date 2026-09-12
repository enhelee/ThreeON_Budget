"""views/dashboard_page.py의 '배정 대비 실적' 섹션(Test 모드)을 AppTest로 검증한다.
정식 render()는 실제 classified_*.csv 파이프라인 전체가 필요해 여기서는 다루지 않고,
budget_actual_summary.py 자체 단위 테스트(tests/test_budget_actual_summary.py)로 계산 로직을
이미 검증했으므로, 여기서는 render_test()가 그 결과를 화면에 올바르게 배선하는지만 확인한다."""
import os
import time
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest
import longterm_forecast as lf
import views.dashboard_page as dashboard_page


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    site_type_map = pd.DataFrame([
        {"사업장": "700001", "표시명": "화성지사", "지사유형": "중대형CHP", "적용시작연도": 1900},
        {"사업장": "화성지사", "표시명": "화성지사", "지사유형": "중대형CHP", "적용시작연도": 1900},
    ])
    site_type_map.to_csv(tmp_path / "site_type_map.csv", index=False)
    monkeypatch.chdir(tmp_path)
    yield tmp_path


def _run_render_test():
    import views.dashboard_page as page
    page.render_test()


def _click_build_button(at):
    """대시보드는 이제 진입 즉시 계산되지 않고 '대시보드 만들기' 버튼을 눌러야 계산된다."""
    build_button = next(b for b in at.button if b.key == "dash_test_build_btn")
    build_button.click().run()
    assert not at.exception
    return at


def test_render_test_shows_status_before_building(isolated):
    """대시보드 만들기 버튼을 누르기 전에는 현재 상태만 보이고 집계는 계산되지 않는다."""
    shared_df = pd.DataFrame([
        {"사업명": "테스트사업", "예산과목": "수선유지비-열원경상정비", "사업장": "700001",
         "금액": 80_000_000.0, "투자유형_확정": "기타기계장치", "투자유형세부_확정": ""},
    ])
    at = AppTest.from_function(_run_render_test, default_timeout=30)
    at.session_state["ptest_shared_df"] = shared_df
    at.run()
    assert not at.exception
    assert any("실적 업로드 완료" in i.value and "대시보드 미작성" in i.value for i in at.info)
    assert any(b.key == "dash_test_build_btn" for b in at.button)
    assert not any(s.value == "지사별 실적" for s in at.subheader)  # 본문은 아직 계산되지 않아야 함


def test_render_test_without_budget_shows_caption_no_crash(isolated):
    shared_df = pd.DataFrame([
        {"사업명": "테스트사업", "예산과목": "수선유지비-열원경상정비", "사업장": "700001",
         "금액": 80_000_000.0, "투자유형_확정": "기타기계장치", "투자유형세부_확정": ""},
    ])
    at = AppTest.from_function(_run_render_test, default_timeout=30)
    at.session_state["ptest_shared_df"] = shared_df
    at.run()
    _click_build_button(at)
    assert any("테스트 예산계획이 없어" in c.value for c in at.caption)


def test_render_test_shows_budget_vs_actual_when_both_present(isolated):
    budget_df = pd.DataFrame([
        {"예산귀속 \n부서코드": "700001", "예산과목": "수선유지비-열원경상정비", "연예산 합계": 100_000_000.0},
    ])
    lf.save_test_budget_plan(budget_df)

    shared_df = pd.DataFrame([
        {"사업명": "테스트사업", "예산과목": "수선유지비-열원경상정비", "사업장": "700001",
         "금액": 80_000_000.0, "투자유형_확정": "기타기계장치", "투자유형세부_확정": ""},
    ])

    at = AppTest.from_function(_run_render_test, default_timeout=30)
    at.session_state["ptest_shared_df"] = shared_df
    at.run()
    _click_build_button(at)

    assert any(s.value == "배정 대비 실적" for s in at.subheader)

    # render_test()는 이제 상태 블록이 2개다: "실적 데이터 준비"(사업장명·지사유형 매핑, 실제 병목이던
    # 부분)와 "대시보드 계산"(지표·차트 집계). 여기서는 후자를 확인한다.
    build_status = next(s for s in at.status if s.label == "대시보드 계산 완료")
    assert build_status.state == "complete"
    assert build_status.label == "대시보드 계산 완료"
    step_messages = [m.value for m in build_status.markdown]
    assert any("지사별 실적" in m for m in step_messages)
    assert not any("배정" in m for m in step_messages)  # 배정 대비 실적 자체는 상태 블록 밖에서 그려짐

    # 실제 병목이었던 사업장명·지사유형 매핑 단계도 별도 상태 블록으로 보여야 한다.
    prep_status = next(s for s in at.status if s.label == "실적 데이터 준비 완료")
    assert prep_status.state == "complete"

    summary_table = next(d.value for d in at.dataframe if "합계" in d.value.columns)
    assert summary_table.loc[("손익예산", "배정"), "중대형CHP"] == pytest.approx(1.0)  # 1억원
    assert summary_table.loc[("손익예산", "실적"), "중대형CHP"] == pytest.approx(0.8)  # 0.8억원
    assert summary_table.loc[("손익예산", "실적률(%)"), "중대형CHP"] == pytest.approx(80.0)

    detail_table = next(
        d.value for d in at.dataframe
        if list(d.value.columns) == ["배정", "실적", "잔액", "실적률(%)"] and not d.value.empty
    )
    row = detail_table.loc["수선유지비-열원경상정비"]
    assert row["배정"] == pytest.approx(1.0)
    assert row["실적"] == pytest.approx(0.8)
    assert row["잔액"] == pytest.approx(0.2)


def test_render_test_filters_by_selected_year(isolated):
    """실적/예산계획에 연도가 태그되어 있으면 연도 선택 멀티셀렉트가 나타나고, 선택한 연도만 집계된다."""
    lf.save_test_budget_plan(
        pd.DataFrame([{"예산귀속 \n부서코드": "700001", "예산과목": "수선유지비-열원경상정비", "연예산 합계": 100_000_000.0}]),
        year=2025,
    )
    lf.save_test_budget_plan(
        pd.DataFrame([{"예산귀속 \n부서코드": "700001", "예산과목": "수선유지비-열원경상정비", "연예산 합계": 500_000_000.0}]),
        year=2026,
    )

    shared_df = pd.DataFrame([
        {"사업명": "2025사업", "예산과목": "수선유지비-열원경상정비", "사업장": "700001",
         "금액": 80_000_000.0, "투자유형_확정": "기타기계장치", "투자유형세부_확정": "", "연도": 2025},
        {"사업명": "2026사업", "예산과목": "수선유지비-열원경상정비", "사업장": "700001",
         "금액": 400_000_000.0, "투자유형_확정": "기타기계장치", "투자유형세부_확정": "", "연도": 2026},
    ])

    at = AppTest.from_function(_run_render_test, default_timeout=30)
    at.session_state["ptest_shared_df"] = shared_df
    at.run()
    _click_build_button(at)

    year_select = next(m for m in at.multiselect if m.key == "dash_test_years")
    assert set(year_select.value) == {2025, 2026}

    year_select.set_value([2025]).run()
    assert not at.exception
    assert at.metric[0].value == "0.8억"  # 2025년 실적 0.8억만 집계

    summary_table = next(d.value for d in at.dataframe if "합계" in d.value.columns)
    assert summary_table.loc[("손익예산", "배정"), "중대형CHP"] == pytest.approx(1.0)  # 2025년 배정 1억만


def test_render_test_build_persists_across_fresh_app_runs_and_flags_data_changes(isolated):
    """앱을 재시작해도(=세션 상태 없이 새 AppTest 인스턴스) 이전에 만든 대시보드는 다시 계산할 필요 없이
    '작성됨'으로 남아있어야 하고, 데이터가 실제로 바뀌면 '데이터가 변경되었습니다'가 떠야 한다."""
    import views.project_type_test_page as ptest_page

    shared_df = pd.DataFrame([
        {"사업명": "테스트사업", "예산과목": "수선유지비-열원경상정비", "사업장": "700001",
         "금액": 80_000_000.0, "투자유형_확정": "기타기계장치", "투자유형세부_확정": "", "연도": 2025},
    ])
    ptest_page.save_shared_actual_df(shared_df)  # session_state가 아니라 파일로 저장 - 재시작을 흉내낸다

    at1 = AppTest.from_function(_run_render_test, default_timeout=30)
    at1.run()
    _click_build_button(at1)
    assert any(s.value == "배정 대비 실적" for s in at1.subheader)

    # st.cache_data는 프로세스 메모리에 남기 때문에, pytest는 실제로는 같은 프로세스 안에서 at1/at2를
    # 실행한다 - 진짜 "앱 재시작"을 흉내내려면 그 인메모리 캐시까지 강제로 비워야, 이후 결과가 정말
    # 저장해둔 artifact(파일)에서 온 것인지(재계산 캐시에 우연히 남아있던 게 아니라) 확인할 수 있다.
    dashboard_page._cached_test_actual_prep.clear()

    at2 = AppTest.from_function(_run_render_test, default_timeout=30)
    at2.run()
    assert not at2.exception
    assert any("대시보드 작성됨" in i.value for i in at2.info)
    # 버튼을 누르지 않아도(=클릭 이벤트 없이 첫 run()만으로) 이전에 만든 본문이 바로 보여야 한다.
    assert any(s.value == "배정 대비 실적" for s in at2.subheader)
    # 진짜로 다시 계산하지 않았어야 한다 - "실적 데이터 준비 중" 상태 블록 자체가 나타나면 안 된다.
    assert not any(s.label == "실적 데이터 준비 완료" for s in at2.status)
    assert any("다시 계산하지 않음" in c.value for c in at2.caption)

    # 실적 데이터를 바꿔서 다시 저장하면(=새로 업로드) 변경 감지가 떠야 한다.
    changed_df = shared_df.copy()
    changed_df.loc[0, "금액"] = 999_000_000.0
    ptest_page.save_shared_actual_df(changed_df)

    at3 = AppTest.from_function(_run_render_test, default_timeout=30)
    at3.run()
    assert not at3.exception
    assert any("데이터가 변경되었습니다" in i.value for i in at3.info)
    assert any(b.key == "dash_test_build_btn" for b in at3.button)  # 다시 만들어야 하니 버튼이 다시 보임
    assert not any(s.value == "배정 대비 실적" for s in at3.subheader)  # 재계산 전엔 옛 결과를 보여주지 않음


def test_build_does_not_false_flag_change_when_site_type_map_did_not_exist_yet(tmp_path, monkeypatch):
    """실제 버그 재현: site_type_map.csv가 아직 없는 상태(맨 처음 사용)에서 만들면, 지문을 계산하기 전에
    그 파일이 기본값으로 seed되어 mtime이 새로 생긴다 - 그 '파일이 없다가 생긴 것' 자체가 지문에
    잡혀서 아무것도 안 바꿨는데 다음 rerun에서 '데이터가 변경되었습니다'로 잘못 뜨면 안 된다."""
    monkeypatch.chdir(tmp_path)  # site_type_map.csv를 일부러 미리 만들지 않는다(공용 isolated 픽스처와 차이)
    import views.project_type_test_page as ptest_page

    shared_df = pd.DataFrame([
        {"사업명": "테스트사업", "예산과목": "수선유지비-열원경상정비", "사업장": "700001",
         "금액": 80_000_000.0, "투자유형_확정": "기타기계장치", "투자유형세부_확정": "", "연도": 2025},
    ])
    ptest_page.save_shared_actual_df(shared_df)
    assert not (tmp_path / "site_type_map.csv").exists()

    at1 = AppTest.from_function(_run_render_test, default_timeout=30)
    at1.run()
    _click_build_button(at1)
    assert (tmp_path / "site_type_map.csv").exists()  # 이번에 seed됨

    at2 = AppTest.from_function(_run_render_test, default_timeout=30)
    at2.run()
    assert not at2.exception
    assert not any("데이터가 변경되었습니다" in i.value for i in at2.info)
    assert any(s.value == "배정 대비 실적" for s in at2.subheader)


def test_cached_classified_df_refreshes_when_file_mtime_changes(isolated):
    """캐싱이 파일 내용을 영원히 고정해버리면 안 된다 - mtime이 바뀌면(=새로 업로드되면) 다시 읽어야 한다."""
    path = "classified_2025.csv"
    pd.DataFrame([
        {"사업장": "700001", "계정과목": "수선유지비-열원경상정비", "전기일": "2025-01-01", "금액": 100.0},
    ]).to_csv(path, index=False)

    sig1 = (os.path.getmtime(path),) + dashboard_page._mapping_sig()
    result1 = dashboard_page._cached_classified_df((2025,), sig1)
    assert result1["금액"].sum() == pytest.approx(100.0)

    time.sleep(0.05)
    pd.DataFrame([
        {"사업장": "700001", "계정과목": "수선유지비-열원경상정비", "전기일": "2025-01-01", "금액": 999.0},
    ]).to_csv(path, index=False)
    os.utime(path, (os.path.getmtime(path) + 1, os.path.getmtime(path) + 1))

    sig2 = (os.path.getmtime(path),) + dashboard_page._mapping_sig()
    result2 = dashboard_page._cached_classified_df((2025,), sig2)
    assert result2["금액"].sum() == pytest.approx(999.0)
