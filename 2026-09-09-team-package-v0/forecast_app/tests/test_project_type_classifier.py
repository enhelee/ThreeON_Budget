import pandas as pd
import pytest
import project_type_classifier as ptc


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    """실제 학습데이터/모델 파일을 건드리지 않도록 임시 경로로 격리."""
    monkeypatch.setattr(ptc, "TRAINING_PATH", str(tmp_path / "train.csv"))
    monkeypatch.setattr(ptc, "META_PATH", str(tmp_path / "meta.json"))
    monkeypatch.setattr(ptc, "MODEL_PATHS", {
        "투자유형": str(tmp_path / "major.joblib"),
        "투자유형세부": str(tmp_path / "minor.joblib"),
    })
    return tmp_path


def _sample(n=40):
    # 투자유형세부는 실제 양식과 마찬가지로 '설비개선'일 때만 채운다.
    majors = ["정기사업", "노후설비개체", "설비개선", "환경강화"]
    rows = []
    for i in range(n):
        m = majors[i % 4]
        minor = f"세부{'A' if (i // 4) % 2 == 0 else 'B'}" if m == "설비개선" else ""
        rows.append({
            "사업명": f"{m} {i}호기 공사", "예산과목": "기계장치",
            "투자유형": m, "투자유형세부": minor,
        })
    return pd.DataFrame(rows)


def test_append_dedupes_by_name_and_account(isolated):
    df = pd.DataFrame([
        {"사업명": "A공사", "예산과목": "기계장치", "투자유형": "정기사업", "투자유형세부": "x"},
        {"사업명": "A공사", "예산과목": "기계장치", "투자유형": "노후설비개체", "투자유형세부": "y"},  # 같은 키 → 최신으로 갱신
        {"사업명": "B공사", "예산과목": "외주비-열원공사비", "투자유형": "LTSA", "투자유형세부": "z"},
    ])
    n = ptc.append_training_examples(df)
    assert n == 2
    saved = ptc.load_training_data()
    a = saved[saved["사업명"] == "A공사"].iloc[0]
    assert a["투자유형"] == "노후설비개체"  # keep="last"


def test_append_skips_rows_without_name_or_label(isolated):
    df = pd.DataFrame([
        {"사업명": "", "예산과목": "기계장치", "투자유형": "정기사업", "투자유형세부": "x"},   # 사업명 없음
        {"사업명": "C공사", "예산과목": "기계장치", "투자유형": "", "투자유형세부": ""},        # 라벨 없음
        {"사업명": "D공사", "예산과목": "기계장치", "투자유형": "환경강화", "투자유형세부": ""},  # 유효
    ])
    n = ptc.append_training_examples(df)
    assert n == 1


def test_append_skips_out_of_scope_budget_account(isolated):
    """기계장치/외주비 계열이 아닌 예산과목(예: 재료비-열원자재비)은 학습 대상에서 제외한다."""
    df = pd.DataFrame([
        {"사업명": "E공사", "예산과목": "재료비-열원자재비", "투자유형": "기타", "투자유형세부": ""},
        {"사업명": "F공사", "예산과목": "기계장치", "투자유형": "기타", "투자유형세부": ""},
    ])
    n = ptc.append_training_examples(df)
    assert n == 1
    saved = ptc.load_training_data()
    assert list(saved["사업명"]) == ["F공사"]


def test_summary_counts_per_target(isolated):
    ptc.append_training_examples(_sample(40))
    s = ptc.training_summary()
    assert s["count"] == 40
    assert s["per_target"]["투자유형"]["classes"] == 4
    # 세부는 '설비개선' 10건(세부A 5 · 세부B 5)만 라벨로 잡힌다 - 나머지 유형은 제외.
    assert s["per_target"]["투자유형세부"]["labeled"] == 10
    assert s["per_target"]["투자유형세부"]["classes"] == 2


def test_can_train_requires_minimums(isolated):
    ptc.append_training_examples(_sample(8))   # 8건 < 10
    assert ptc.can_train("투자유형") is False
    ptc.append_training_examples(_sample(40))
    assert ptc.can_train("투자유형") is True


def test_train_and_predict_roundtrip(isolated):
    ptc.append_training_examples(_sample(40))
    results = ptc.train_all()
    assert results["투자유형"] is not None
    assert ptc.has_any_model()
    pred = ptc.predict(pd.DataFrame([{"사업명": "정기사업 99호기 공사", "예산과목": "수선유지비-열원정기점검"}]))
    assert pred.iloc[0]["투자유형_예측"] == "정기사업"
    assert 0.0 <= pred.iloc[0]["투자유형_확신도"] <= 1.0


def test_minor_target_excludes_rows_with_other_major(isolated):
    """투자유형세부는 투자유형='설비개선'인 행만 학습에 쓰여야 한다."""
    df = pd.DataFrame([
        {"사업명": "A", "예산과목": "기계장치", "투자유형": "정기사업", "투자유형세부": "실수로채움"},
        {"사업명": "B", "예산과목": "기계장치", "투자유형": "설비개선", "투자유형세부": "AX/DX"},
    ])
    ptc.append_training_examples(df)
    sub = ptc._labeled_subset(ptc.load_training_data(), "투자유형세부")
    assert list(sub["사업명"]) == ["B"]


def test_predict_blanks_minor_when_major_not_parent(isolated):
    ptc.append_training_examples(_sample(40))
    ptc.train_all()
    pred = ptc.predict(pd.DataFrame([
        {"사업명": "정기사업 5호기 공사", "예산과목": "수선유지비-열원정기점검"},
        {"사업명": "설비개선 2호기 공사", "예산과목": "수선유지비-열원정기점검"},
    ]))
    non_biseol = pred[pred["투자유형_예측"] != "설비개선"]
    biseol = pred[pred["투자유형_예측"] == "설비개선"]
    if not non_biseol.empty:
        assert (non_biseol["투자유형세부_예측"] == "").all()
        assert non_biseol["투자유형세부_확신도"].isna().all()
    if not biseol.empty:
        assert (biseol["투자유형세부_예측"] != "").all()


def test_predict_without_model_adds_no_columns(isolated):
    pred = ptc.predict(pd.DataFrame([{"사업명": "무엇", "예산과목": "가"}]))
    assert "투자유형_예측" not in pred.columns


def test_train_and_save_meta_preserves_other_targets(isolated):
    """한 라벨만 재학습해도, meta에 기록된 다른 라벨의 이전 결과는 지워지지 않아야 한다."""
    ptc.append_training_examples(_sample(40))
    ptc.train_all()
    meta_before = ptc.load_meta()
    assert "투자유형세부" in meta_before["results"]

    ptc.train_and_save_meta("투자유형")  # 투자유형만 다시 학습
    meta_after = ptc.load_meta()
    assert "투자유형" in meta_after["results"]
    assert "투자유형세부" in meta_after["results"]  # 그대로 남아있어야 함
    assert meta_after["results"]["투자유형세부"] == meta_before["results"]["투자유형세부"]


def test_reset_models_keeps_training_data(isolated):
    ptc.append_training_examples(_sample(40))
    ptc.train_all()
    ptc.reset_models()
    assert not ptc.has_any_model()
    assert ptc.training_summary()["count"] == 40
