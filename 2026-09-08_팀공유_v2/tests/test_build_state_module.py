import os
import time
import pandas as pd
import pytest
import build_state as bstate


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    yield tmp_path


def test_fingerprint_changes_when_df_content_changes():
    df1 = pd.DataFrame([{"a": 1, "b": 2}])
    df2 = pd.DataFrame([{"a": 1, "b": 3}])
    assert bstate.fingerprint(df=df1) != bstate.fingerprint(df=df2)


def test_fingerprint_stable_for_same_df_content():
    df1 = pd.DataFrame([{"a": 1, "b": 2}])
    df2 = pd.DataFrame([{"a": 1, "b": 2}])
    assert bstate.fingerprint(df=df1) == bstate.fingerprint(df=df2)


def test_fingerprint_changes_when_file_mtime_changes(isolated):
    path = "some_input.csv"
    pd.DataFrame([{"x": 1}]).to_csv(path, index=False)
    fp1 = bstate.fingerprint(paths=(path,))

    time.sleep(0.05)
    pd.DataFrame([{"x": 2}]).to_csv(path, index=False)
    os.utime(path, (os.path.getmtime(path) + 1, os.path.getmtime(path) + 1))
    fp2 = bstate.fingerprint(paths=(path,))

    assert fp1 != fp2


def test_fingerprint_handles_missing_file_without_crashing(isolated):
    fp = bstate.fingerprint(paths=("does_not_exist.csv",))
    assert "missing" in fp


def test_save_and_load_build_fingerprint_round_trips(isolated):
    assert bstate.load_build_fingerprint("dashboard_test") is None
    bstate.save_build_fingerprint("dashboard_test", "abc123")
    assert bstate.load_build_fingerprint("dashboard_test") == "abc123"
    assert os.path.exists(os.path.join("test_data", "dashboard_test_build_state.json"))


def test_save_and_load_artifact_round_trips_dataframe(isolated):
    assert bstate.load_artifact("dashboard_test_prepared") is None
    df = pd.DataFrame([{"a": 1, "b": "x"}])
    bstate.save_artifact("dashboard_test_prepared", df)
    loaded = bstate.load_artifact("dashboard_test_prepared")
    pd.testing.assert_frame_equal(loaded, df)


def test_save_and_load_artifact_round_trips_dict_of_dataframes(isolated):
    """longterm_forecast_page의 site_tables(지사명 -> DataFrame 딕셔너리)처럼 중첩 구조도 그대로 저장/복원돼야 한다."""
    obj = {"화성지사": pd.DataFrame([{"연도": 2026, "금액": 1.0}])}
    bstate.save_artifact("longterm_test", obj)
    loaded = bstate.load_artifact("longterm_test")
    pd.testing.assert_frame_equal(loaded["화성지사"], obj["화성지사"])
