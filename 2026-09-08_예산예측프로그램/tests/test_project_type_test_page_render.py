"""views/project_type_test_page.py의 render() 전체 흐름(직접 지정한 파일 업로드 -> 칸 맞추기 ->
예측 -> 확정 -> 저장)을 AppTest로 검증한다. zrfm2 원본 업로드는 이제 'Test 모드 계획 및 실적
업로드' 화면(views/test_data_upload_page.py)으로 옮겼으므로 여기서는 다루지 않는다."""
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest
import project_type_classifier as ptc


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(ptc, "TRAINING_PATH", str(tmp_path / "train.csv"))
    monkeypatch.setattr(ptc, "META_PATH", str(tmp_path / "meta.json"))
    monkeypatch.setattr(ptc, "MODEL_PATHS", {
        "투자유형": str(tmp_path / "major.joblib"),
        "투자유형세부": str(tmp_path / "minor.joblib"),
    })

    majors = ["정기사업", "노후설비개체", "설비개선", "환경강화"]
    rows = []
    for i in range(40):
        m = majors[i % 4]
        rows.append({"사업명": f"{m} {i}호기 공사", "예산과목": "기계장치", "투자유형": m, "투자유형세부": ""})
    ptc.append_training_examples(pd.DataFrame(rows))
    ptc.train_all()
    assert ptc.has_any_model()

    yield tmp_path


def _run_render():
    import views.project_type_test_page as page
    page.render()


def test_flexible_upload_flows_through_to_prediction_and_save(isolated):
    """업로드 형식 선택 없이(라디오 제거됨) 바로 파일 업로드 -> 칸 맞추기 -> 예측까지 이어진다."""
    csv_text = "사업명,예산과목,사업장,금액\n정기사업 3호기 공사,기계장치,700001,500000\n"

    at = AppTest.from_function(_run_render, default_timeout=30)
    at.run()
    assert not at.exception
    assert not any(r.key == "ptest_upload_mode" for r in at.radio)  # 라디오는 제거되어 있어야 함

    uploader = next(u for u in at.file_uploader if u.key == "ptest_upload")
    uploader.set_value([("actuals.csv", csv_text.encode("utf-8-sig"), "text/csv")])
    at.run()
    assert not at.exception
    assert any(s.value == "2) 칸 맞추기" for s in at.subheader)
    assert not any(s.value == "예측 결과" for s in at.subheader)  # 버튼 누르기 전엔 예측이 실행되지 않아야 함

    predict_button = next(b for b in at.button if b.key == "ptest_predict_btn")
    predict_button.click().run()
    assert not at.exception
    assert any(s.value == "예측 결과" for s in at.subheader)

    predict_status = next(s for s in at.status if s.label == "예측 완료")
    assert predict_status.state == "complete"

    save_button = next(b for b in at.button if b.key == "ptest_save_backdata")
    save_button.click().run()
    assert not at.exception

    import views.project_type_test_page as page
    saved = page.load_shared_actual_df()
    assert len(saved) == 1
    assert saved.iloc[0]["사업장"] == "700001"
