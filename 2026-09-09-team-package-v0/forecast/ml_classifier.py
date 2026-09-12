"""
사람이 확정한 분류 결과를 학습 데이터로 축적하고,
scikit-learn으로 로컬(오프라인)에서 재학습하는 모듈.
인터넷/외부 API 불필요 - 사내 분리망에서 완전히 동작한다.
"""
import os
import json
from datetime import datetime
import pandas as pd
import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.model_selection import cross_val_score

TRAINING_PATH = "training_data.csv"
MODEL_PATH = "type_classifier.joblib"
META_PATH = "training_meta.json"
MIN_SAMPLES_TO_TRAIN = 20
MIN_CLASSES_TO_TRAIN = 2


def append_training_examples(texts_labels: list[tuple[str, str]]):
    """(텍스트, 확정유형) 쌍을 학습 데이터에 누적 저장. 동일 텍스트는 최신 라벨로 갱신."""
    new_df = pd.DataFrame(texts_labels, columns=["text", "label"])
    if os.path.exists(TRAINING_PATH):
        existing = pd.read_csv(TRAINING_PATH)
        combined = pd.concat([existing, new_df], ignore_index=True)
        combined = combined.drop_duplicates(subset="text", keep="last")
    else:
        combined = new_df.drop_duplicates(subset="text", keep="last")
    combined.to_csv(TRAINING_PATH, index=False)
    return len(combined)


def training_data_summary() -> dict:
    if not os.path.exists(TRAINING_PATH):
        return {"count": 0, "per_class": {}}
    df = pd.read_csv(TRAINING_PATH)
    return {"count": len(df), "per_class": df["label"].value_counts().to_dict()}


def can_train() -> bool:
    summary = training_data_summary()
    return summary["count"] >= MIN_SAMPLES_TO_TRAIN and len(summary["per_class"]) >= MIN_CLASSES_TO_TRAIN


def train_model() -> dict:
    """training_data.csv로 TF-IDF + 로지스틱회귀 모델을 학습하고 저장한다."""
    df = pd.read_csv(TRAINING_PATH)

    pipeline = Pipeline([
        ("tfidf", TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4))),
        ("clf", LogisticRegression(max_iter=1000)),
    ])

    n_classes = df["label"].nunique()
    cv_folds = min(5, df["label"].value_counts().min(), len(df) // n_classes)
    cv_accuracy = None
    if cv_folds >= 2:
        scores = cross_val_score(pipeline, df["text"], df["label"], cv=cv_folds)
        cv_accuracy = round(scores.mean(), 3)

    pipeline.fit(df["text"], df["label"])
    joblib.dump(pipeline, MODEL_PATH)

    meta = {
        "trained_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "n_samples": len(df),
        "n_classes": n_classes,
        "per_class": df["label"].value_counts().to_dict(),
        "cv_accuracy": cv_accuracy,
    }
    with open(META_PATH, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    return meta


def load_training_meta() -> dict | None:
    if not os.path.exists(META_PATH):
        return None
    with open(META_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def reset_model():
    """학습된 모델만 삭제 -> 다음부터 키워드 규칙으로 되돌아감 (학습데이터는 보존)"""
    if os.path.exists(MODEL_PATH):
        os.remove(MODEL_PATH)
    if os.path.exists(META_PATH):
        os.remove(META_PATH)


def reset_all_training_data():
    """학습데이터와 모델을 전부 삭제 (되돌릴 수 없음)"""
    reset_model()
    if os.path.exists(TRAINING_PATH):
        os.remove(TRAINING_PATH)


def export_training_data() -> pd.DataFrame | None:
    if not os.path.exists(TRAINING_PATH):
        return None
    return pd.read_csv(TRAINING_PATH)


def import_training_data(df: pd.DataFrame, mode: str = "merge") -> int:
    """
    외부에서 수정한 학습데이터(text, label 컬럼)를 반영한다.
    mode='merge': 기존 데이터와 합치되 같은 text는 새 값으로 덮어씀
    mode='replace': 기존 데이터를 통째로 교체
    """
    df = df[["text", "label"]].dropna()
    if mode == "replace":
        df = df.drop_duplicates(subset="text", keep="last")
        df.to_csv(TRAINING_PATH, index=False)
        return len(df)
    else:
        return append_training_examples(list(zip(df["text"], df["label"])))


def load_model():
    if os.path.exists(MODEL_PATH):
        return joblib.load(MODEL_PATH)
    return None


def predict_with_model(model, texts: pd.Series):
    labels = model.predict(texts)
    proba = model.predict_proba(texts)
    confidences = proba.max(axis=1)
    return labels, confidences
