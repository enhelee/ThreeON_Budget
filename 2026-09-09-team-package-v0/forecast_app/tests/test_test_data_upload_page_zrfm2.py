"""views/test_data_upload_page.py의 zrfm2 원본 실적 업로드 경로를 AppTest로 검증한다.
'실적 업데이트(zrfm2)' 화면과 같은 validate_upload()를 재사용해 원본 엑셀을 정리한 뒤,
project_type_test_page.render_predict_review_and_save()를 통해 예측 -> 확정 -> 저장까지
이어지는지 확인한다 - 실제 업로드 UI는 이 화면(계획 및 실적 업로드)에 있다."""
import io
import pandas as pd
import pytest
from openpyxl import Workbook
from streamlit.testing.v1 import AppTest
import project_type_classifier as ptc

_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


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
    import views.test_data_upload_page as page
    page.render()


def _zrfm2_workbook_bytes(rows) -> bytes:
    """rows: [(공급업체, 손익센터, 전기일, 텍스트, 금액, 약정항목텍스트), ...]"""
    wb = Workbook()
    ws = wb.active
    ws.append(["공급업체", "손익 센터", "FM 전기일", "텍스트",
               "FM 영역통화로 표시된 지급예산금액", "약정항목 텍스트"])
    for r in rows:
        ws.append(list(r))
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_zrfm2_upload_in_plan_and_actual_page_flows_through_to_saved_backdata(isolated):
    zrfm2_bytes = _zrfm2_workbook_bytes([
        ("협력사A", "700001", "2025-03-15", "정기사업 1호기 공사", 1_000_000, "기계장치"),
        ("협력사B", "700001", "2025-04-10", "노후설비개체 2호기 공사", 2_000_000, "기계장치"),
    ])

    at = AppTest.from_function(_run_render, default_timeout=30)
    at.run()
    assert not at.exception

    uploader = next(u for u in at.file_uploader if u.key == "tdata_zrfm2_upload")
    uploader.set_value([("zrfm2_export.xlsx", zrfm2_bytes, _XLSX_MIME)])
    at.run()
    assert not at.exception

    assert any("2건을 인식" in c.value for c in at.caption)

    save_button = next(b for b in at.button if b.key == "ptest_save_backdata")
    save_button.click().run()
    assert not at.exception

    import views.project_type_test_page as ptest_page
    saved = ptest_page.load_shared_actual_df()
    assert len(saved) == 2
    assert set(saved["사업장"].astype(str)) == {"700001"}
    assert saved["금액"].sum() == pytest.approx(3_000_000.0)
    assert saved["투자유형_확정"].isin(["정기사업", "노후설비개체", "설비개선", "환경강화"]).all()

    # "3) 실적 연동 상태"에도 즉시 반영된다
    assert any("연동되어 있습니다" in s.value for s in at.success)


def test_zrfm2_upload_keeps_profit_and_loss_accounts_as_actuals(isolated):
    """실제 버그 재현: 손익예산 계정과목(예: 수선유지비-열원경상정비)은 투자유형 분류기 범위(기계장치·
    외주비) 밖이라는 이유로 실적 자체가 통째로 빠지면 안 된다 - 예측만 비워두고 금액은 그대로 남아야
    '배정 대비 실적'에서 손익예산이 실적으로 잡힌다."""
    zrfm2_bytes = _zrfm2_workbook_bytes([
        ("협력사A", "700001", "2025-03-15", "정기사업 1호기 공사", 1_000_000, "기계장치"),
        ("협력사B", "700001", "2025-04-10", "경상정비 공사", 5_000_000, "수선유지비-열원경상정비"),
    ])

    at = AppTest.from_function(_run_render, default_timeout=30)
    at.run()

    uploader = next(u for u in at.file_uploader if u.key == "tdata_zrfm2_upload")
    uploader.set_value([("zrfm2_export.xlsx", zrfm2_bytes, _XLSX_MIME)])
    at.run()
    assert not at.exception

    # 캡션에 "기계장치·외주비 범위(1건)"과 "그 외 1건(손익예산 등)"이 함께 표시돼야 한다(제외가 아님).
    assert any("기계장치·외주비 범위" in c.value and "1건" in c.value for c in at.caption)

    save_button = next(b for b in at.button if b.key == "ptest_save_backdata")
    save_button.click().run()
    assert not at.exception

    import views.project_type_test_page as ptest_page
    saved = ptest_page.load_shared_actual_df()
    assert len(saved) == 2  # 손익예산 행이 빠지지 않고 그대로 남아있어야 한다
    assert saved["금액"].sum() == pytest.approx(6_000_000.0)

    pl_row = saved[saved["예산과목"] == "수선유지비-열원경상정비"].iloc[0]
    assert pl_row["금액"] == pytest.approx(5_000_000.0)
    assert pl_row["투자유형_확정"] in ("", None) or pd.isna(pl_row["투자유형_확정"])  # 예측 대상 밖 - 빈 값

    capital_row = saved[saved["예산과목"] == "기계장치"].iloc[0]
    assert capital_row["투자유형_확정"] in ("정기사업", "노후설비개체", "설비개선", "환경강화")


def test_zrfm2_section_shows_info_without_trained_model(isolated, monkeypatch):
    """모델이 없으면 업로드 폼 대신 안내만 뜬다(에러 없이)."""
    monkeypatch.setattr(ptc, "MODEL_PATHS", {
        "투자유형": str(isolated / "missing_major.joblib"),
        "투자유형세부": str(isolated / "missing_minor.joblib"),
    })
    assert not ptc.has_any_model()

    at = AppTest.from_function(_run_render, default_timeout=30)
    at.run()
    assert not at.exception
    assert any("아직 학습된 모델이 없습니다" in i.value for i in at.info)
    assert not any(u.key == "tdata_zrfm2_upload" for u in at.file_uploader)
