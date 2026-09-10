import pandas as pd
import pytest
import streamlit as st
from views.project_type_test_page import (
    _dedupe_columns as dedupe_in_test_page,
    _read_uploaded as read_in_test_page,
    save_shared_actual_df,
    load_shared_actual_df,
    get_shared_actual_df,
)
from views.project_type_learning_page import _dedupe_columns as dedupe_in_learning_page


class _FakeFile:
    def __init__(self, name, data_bytes):
        self.name = name
        self._data = data_bytes

    def getvalue(self):
        return self._data


def test_dedupe_columns_numbers_repeats():
    cols = ["사업명", "금액", "금액", "금액"]
    assert dedupe_in_test_page(cols) == ["사업명", "금액", "금액_1", "금액_2"]
    assert dedupe_in_learning_page(cols) == ["사업명", "금액", "금액_1", "금액_2"]


def test_dedupe_columns_no_repeats_unchanged():
    cols = ["사업명", "예산과목", "금액"]
    assert dedupe_in_test_page(cols) == cols


def test_read_uploaded_with_duplicate_headers_does_not_crash_on_concat():
    """실제 버그 재현: 컬럼명이 중복된 파일을 여러 개 합칠 때 InvalidIndexError가 나면 안 된다."""
    csv_text = "전표헤더텍스트,계정과목,금액,금액\n부품구매 A,수선유지비,100,100\n공사대금 B,수선유지비,200,200\n"
    f = _FakeFile("dup.csv", csv_text.encode("utf-8-sig"))

    df = read_in_test_page(f)
    assert list(df.columns) == ["전표헤더텍스트", "계정과목", "금액", "금액_1"]

    combined = pd.concat([df, df.copy()], ignore_index=True)  # 예전엔 여기서 InvalidIndexError
    assert combined.shape == (4, 4)


def test_read_uploaded_drops_blank_header_columns():
    """실제 버그 재현: 이름 없는 빈 컬럼('nan', 'nan_1'...)이 결과/다운로드에 남으면 안 된다."""
    csv_text = "사업명,예산과목,,\n부품구매 A,기계장치,,\n공사대금 B,외주비,,\n"
    f = _FakeFile("blank_cols.csv", csv_text.encode("utf-8-sig"))

    df = read_in_test_page(f)
    assert list(df.columns) == ["사업명", "예산과목"]
    assert not any(str(c).startswith("nan") for c in df.columns)


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    yield tmp_path


def _sample_shared_df():
    return pd.DataFrame([
        {"사업명": "테스트사업", "예산과목": "기계장치", "사업장": "700001",
         "금액": 1_000_000.0, "투자유형_확정": "기타기계장치", "투자유형세부_확정": ""},
    ])


def test_save_and_load_shared_actual_df_round_trips_to_test_data_folder(isolated):
    """저장하면 test_data/ 폴더(longterm_forecast.TEST_DATA_DIR)에 저장되고, 다시 불러오면 그대로 읽힌다."""
    df = _sample_shared_df()
    save_shared_actual_df(df)

    saved_path = isolated / "test_data" / "project_type_test_actual.csv"
    assert saved_path.exists()

    loaded = load_shared_actual_df()
    assert len(loaded) == 1
    assert loaded.iloc[0]["사업명"] == "테스트사업"
    assert loaded.iloc[0]["사업장"] == "700001"  # dtype=str로 읽어 부서코드 앞자리가 안 깨진다


def test_load_shared_actual_df_missing_file_returns_empty_with_expected_columns(isolated):
    loaded = load_shared_actual_df()
    assert loaded.empty
    assert list(loaded.columns) == ["사업명", "예산과목", "사업장", "금액", "투자유형_확정", "투자유형세부_확정", "연도"]


def test_get_shared_actual_df_prefers_session_state_over_saved_file(isolated):
    """이번 세션에서 방금 확정한 결과가 있으면, 디스크에 저장된 이전 결과보다 그것을 우선한다."""
    save_shared_actual_df(_sample_shared_df())

    session_df = pd.DataFrame([
        {"사업명": "세션사업", "예산과목": "기계장치", "사업장": "700002",
         "금액": 2_000_000.0, "투자유형_확정": "기타기계장치", "투자유형세부_확정": ""},
    ])
    st.session_state["ptest_shared_df"] = session_df
    try:
        result = get_shared_actual_df()
        assert result.iloc[0]["사업명"] == "세션사업"
    finally:
        del st.session_state["ptest_shared_df"]


def test_get_shared_actual_df_falls_back_to_saved_file_when_session_empty(isolated):
    """세션에 아직 확정한 결과가 없으면(None이거나 빈 DataFrame) 저장해둔 파일로 대체한다."""
    save_shared_actual_df(_sample_shared_df())
    assert st.session_state.get("ptest_shared_df") is None

    result = get_shared_actual_df()
    assert len(result) == 1
    assert result.iloc[0]["사업명"] == "테스트사업"


def test_save_shared_actual_df_replaces_only_matching_year(isolated):
    """같은 연도로 다시 저장하면 그 연도만 교체되고, 다른 연도 데이터는 그대로 남는다 -
    '실적집계 대시보드'에서 여러 연도를 동시에 누적·비교하려면 이게 되어야 한다."""
    df_2025 = pd.DataFrame([
        {"사업명": "2025사업", "예산과목": "기계장치", "사업장": "700001",
         "금액": 1_000_000.0, "투자유형_확정": "기타기계장치", "투자유형세부_확정": "", "연도": 2025},
    ])
    df_2026 = pd.DataFrame([
        {"사업명": "2026사업", "예산과목": "기계장치", "사업장": "700001",
         "금액": 2_000_000.0, "투자유형_확정": "기타기계장치", "투자유형세부_확정": "", "연도": 2026},
    ])
    save_shared_actual_df(df_2025)
    save_shared_actual_df(df_2026)

    loaded = load_shared_actual_df()
    assert set(loaded["연도"]) == {2025, 2026}
    assert set(loaded["사업명"]) == {"2025사업", "2026사업"}

    # 2025년 데이터를 다시 올려 교체 - 2026년 데이터는 그대로 유지되어야 한다.
    df_2025_updated = pd.DataFrame([
        {"사업명": "2025사업_수정", "예산과목": "기계장치", "사업장": "700001",
         "금액": 1_500_000.0, "투자유형_확정": "기타기계장치", "투자유형세부_확정": "", "연도": 2025},
    ])
    save_shared_actual_df(df_2025_updated)

    loaded = load_shared_actual_df()
    assert set(loaded["연도"]) == {2025, 2026}
    assert set(loaded["사업명"]) == {"2025사업_수정", "2026사업"}


def test_load_shared_actual_df_migrates_legacy_data_without_year_column(isolated):
    """연도 태그 없이 저장된 예전 백데이터를 읽으면 기본 연도(2025)를 채워 넣고, 이후 다시 읽을 때도
    같은 값이 유지되도록 파일에도 저장한다."""
    legacy_path = isolated / "test_data" / "project_type_test_actual.csv"
    legacy_path.parent.mkdir(exist_ok=True)
    pd.DataFrame([
        {"사업명": "레거시사업", "예산과목": "기계장치", "사업장": "700001",
         "금액": 1_000_000.0, "투자유형_확정": "기타기계장치", "투자유형세부_확정": ""},
    ]).to_csv(legacy_path, index=False)

    loaded = load_shared_actual_df()
    assert loaded.iloc[0]["연도"] == 2025

    reloaded = pd.read_csv(legacy_path)
    assert "연도" in reloaded.columns
    assert reloaded.iloc[0]["연도"] == 2025
