"""app.py의 사이드바 메뉴 구성(이름/순서)을 AppTest로 검증한다."""
from pathlib import Path
import pytest
from streamlit.testing.v1 import AppTest

APP_PATH = str(Path(__file__).resolve().parent.parent / "app.py")


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    yield tmp_path


def test_dashboard_renamed_and_positioned_in_prod_category(isolated):
    """'예산 실적 분석' 카테고리: 이름만 '실적집계 대시보드'로 바뀌고 위치(3번째)는 그대로."""
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()
    assert not at.exception

    category_radio = at.sidebar.radio[0]
    category_radio.set_value("예산 실적 분석").run()
    assert not at.exception

    sub_radio = at.sidebar.radio[1]
    assert "집계 & 대시보드" not in sub_radio.options
    assert sub_radio.options[2] == "실적집계 대시보드"


def test_dashboard_renamed_and_moved_right_after_upload_in_test_mode(isolated):
    """'Test 모드' 카테고리: '계획 및 실적 업로드' 바로 다음으로 이동."""
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()
    assert not at.exception

    category_radio = at.sidebar.radio[0]
    category_radio.set_value("Test 모드").run()
    assert not at.exception

    sub_radio = at.sidebar.radio[1]
    assert "집계 & 대시보드" not in sub_radio.options
    idx = sub_radio.options.index("계획 및 실적 업로드")
    assert sub_radio.options[idx + 1] == "실적집계 대시보드"
