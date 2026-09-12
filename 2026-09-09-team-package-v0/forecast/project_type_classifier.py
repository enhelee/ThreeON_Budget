"""
사업명(+예산과목)을 보고 '투자유형·투자유형 세부'를 맞히는 분류기.

- 기존 ml_classifier.py 는 '전표헤더텍스트 -> 투자유형'(전표 단위)을 학습하는 별개 모듈이다.
  이 모듈은 사용자가 이미 분류해 둔 계획대비실적 양식 자료(사업명 단위)를 학습에 쓰기 위한 것이다.
- 실제 양식(집계표)에는 '구분', '구분/투자유형'(SUMIFS용 결합 보조컬럼) 등도 있지만,
  우리가 예측해야 하는 결과값은 '투자유형'과 '투자유형 세부' 둘뿐이다.
  (투자유형세부는 투자유형이 '설비개선'일 때만 채워지는 값 - AX/DX·GX·교육강화 등 11종)
- 입력(문제): 사업명 + 예산과목  /  정답(라벨): 투자유형, 투자유형세부 (각각 독립적으로 학습)
- 완전 오프라인(사내 분리망). scikit-learn TF-IDF(char n-gram) + 로지스틱회귀.
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

TRAINING_PATH = "project_type_training.csv"   # 컬럼: 사업명, 예산과목, 투자유형, 투자유형세부
MODEL_PATHS = {"투자유형": "project_type_model_major.joblib",
               "투자유형세부": "project_type_model_minor.joblib"}
META_PATH = "project_type_meta.json"

FEATURE_COLS = ["사업명", "예산과목"]
TARGETS = ["투자유형", "투자유형세부"]
CANON_COLS = FEATURE_COLS + TARGETS  # 학습데이터 표준 컬럼 순서

# '투자유형세부'는 상위 '투자유형'이 특정 값일 때만 의미가 있는 하위분류다
# (예: 세부 11종은 투자유형='설비개선'일 때만 채워짐). 그 상위값을 여기서 지정한다.
MINOR_TARGET_PARENT = {"투자유형세부": "설비개선"}

# 지금은 '기계장치'·'외주비' 계열 예산과목만 다룬다(예: 재료비-열원자재비 등은 범위 밖).
# 이 접두어로 시작하는 예산과목만 학습/예측 대상(범위 안)으로 취급한다.
IN_SCOPE_ACCOUNT_PREFIXES = ("기계장치", "외주비")

MIN_SAMPLES_TO_TRAIN = 10
MIN_CLASSES_TO_TRAIN = 2


def is_in_scope_account(account) -> bool:
    """예산과목이 지금 다루기로 한 범위(기계장치/외주비 계열)에 속하는지 확인한다."""
    a = str(account).strip()
    return any(a.startswith(p) for p in IN_SCOPE_ACCOUNT_PREFIXES)


def _build_text(df: pd.DataFrame) -> pd.Series:
    """사업명 + 예산과목을 하나의 텍스트로 합친다(모델 입력)."""
    parts = []
    for c in FEATURE_COLS:
        col = df[c].fillna("").astype(str) if c in df.columns else pd.Series([""] * len(df), index=df.index)
        parts.append(col)
    text = parts[0]
    for p in parts[1:]:
        text = text.str.cat(p, sep=" ")
    return text.str.strip()


def _normalize_incoming(df: pd.DataFrame) -> pd.DataFrame:
    """들어온 표를 표준 컬럼(사업명·예산과목·투자유형·투자유형세부)만 남긴 형태로 정리한다."""
    out = pd.DataFrame()
    for c in CANON_COLS:
        out[c] = df[c].astype(str).str.strip() if c in df.columns else ""
    # 사업명이 비었거나 라벨이 전부 빈 행은 학습에 쓸 수 없으므로 제외
    out = out[out["사업명"].astype(str).str.strip() != ""]
    # 지금 다루기로 한 범위(기계장치/외주비 계열)가 아닌 예산과목은 제외
    out = out[out["예산과목"].apply(is_in_scope_account)]
    has_label = pd.Series(False, index=out.index)
    for t in TARGETS:
        has_label = has_label | (out[t].astype(str).str.strip() != "")
    return out[has_label].reset_index(drop=True)


def append_training_examples(df: pd.DataFrame) -> int:
    """
    분류 완료 자료(사업명·예산과목·투자유형·투자유형세부)를 학습데이터에 누적한다.
    같은 (사업명, 예산과목) 조합은 최신 라벨로 갱신(중복 제거).
    반환: 누적 후 총 건수.
    """
    incoming = _normalize_incoming(df)
    if incoming.empty:
        return training_summary()["count"]

    if os.path.exists(TRAINING_PATH):
        existing = pd.read_csv(TRAINING_PATH, dtype=str).fillna("")
        for c in CANON_COLS:
            if c not in existing.columns:
                existing[c] = ""
        combined = pd.concat([existing[CANON_COLS], incoming[CANON_COLS]], ignore_index=True)
    else:
        combined = incoming[CANON_COLS]

    combined = combined.drop_duplicates(subset=["사업명", "예산과목"], keep="last").reset_index(drop=True)
    combined.to_csv(TRAINING_PATH, index=False)
    return len(combined)


def load_training_data() -> pd.DataFrame:
    if not os.path.exists(TRAINING_PATH):
        return pd.DataFrame(columns=CANON_COLS)
    df = pd.read_csv(TRAINING_PATH, dtype=str).fillna("")
    for c in CANON_COLS:
        if c not in df.columns:
            df[c] = ""
    return df[CANON_COLS]


def _labeled_subset(df: pd.DataFrame, target: str) -> pd.DataFrame:
    """
    해당 라벨(투자유형/세부)이 실제로 채워진 행만.
    target에 상위값 제약이 있으면(MINOR_TARGET_PARENT), 그 상위 '투자유형' 값과
    일치하는 행만 남긴다 - 예: 투자유형세부는 투자유형='설비개선'인 행만 학습에 쓴다.
    """
    sub = df[df[target].astype(str).str.strip() != ""]
    parent_value = MINOR_TARGET_PARENT.get(target)
    if parent_value is not None:
        sub = sub[sub["투자유형"].astype(str).str.strip() == parent_value]
    return sub


def training_summary() -> dict:
    df = load_training_data()
    summary = {"count": len(df), "per_target": {}}
    for t in TARGETS:
        sub = _labeled_subset(df, t)
        summary["per_target"][t] = {
            "labeled": len(sub),
            "classes": int(sub[t].nunique()) if not sub.empty else 0,
            "per_class": sub[t].value_counts().to_dict() if not sub.empty else {},
        }
    return summary


def can_train(target: str) -> bool:
    df = _labeled_subset(load_training_data(), target)
    return len(df) >= MIN_SAMPLES_TO_TRAIN and df[target].nunique() >= MIN_CLASSES_TO_TRAIN


def _new_pipeline() -> Pipeline:
    return Pipeline([
        ("tfidf", TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4))),
        ("clf", LogisticRegression(max_iter=1000)),
    ])


def train(target: str) -> dict:
    """한 라벨(투자유형 또는 투자유형세부)에 대해 모델을 학습·저장한다."""
    if target not in TARGETS:
        raise ValueError(f"알 수 없는 학습 대상: {target}")
    df = _labeled_subset(load_training_data(), target)
    if len(df) < MIN_SAMPLES_TO_TRAIN or df[target].nunique() < MIN_CLASSES_TO_TRAIN:
        raise ValueError(f"'{target}' 학습에 필요한 데이터가 부족합니다.")

    X = _build_text(df)
    y = df[target].astype(str)
    pipeline = _new_pipeline()

    n_classes = y.nunique()
    cv_folds = min(5, int(y.value_counts().min()), len(df) // n_classes)
    cv_accuracy = None
    if cv_folds >= 2:
        scores = cross_val_score(pipeline, X, y, cv=cv_folds)
        cv_accuracy = round(float(scores.mean()), 3)

    pipeline.fit(X, y)
    joblib.dump(pipeline, MODEL_PATHS[target])
    return {"target": target, "n_samples": len(df), "n_classes": int(n_classes), "cv_accuracy": cv_accuracy}


def _save_meta(results_update: dict):
    """results_update에 담긴 라벨의 결과만 meta에 병합 저장한다(다른 라벨의 기존 결과는 그대로 유지)."""
    meta = load_meta() or {}
    results = meta.get("results", {})
    results.update(results_update)
    meta["results"] = results
    meta["trained_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    with open(META_PATH, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)


def train_and_save_meta(target: str) -> dict:
    """한 라벨만 재학습하고, 그 결과를 meta에 병합 저장한다(다른 라벨의 기존 결과는 유지)."""
    result = train(target)
    _save_meta({target: result})
    return result


def train_all() -> dict:
    """학습 가능한 라벨을 모두 학습한다. 반환: {target: 결과 or None}"""
    results = {}
    for t in TARGETS:
        results[t] = train(t) if can_train(t) else None
    _save_meta({t: r for t, r in results.items() if r is not None})
    return results


def load_meta() -> dict | None:
    if not os.path.exists(META_PATH):
        return None
    with open(META_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def load_model(target: str):
    path = MODEL_PATHS.get(target)
    if path and os.path.exists(path):
        return joblib.load(path)
    return None


def has_any_model() -> bool:
    return any(os.path.exists(p) for p in MODEL_PATHS.values())


def predict(df: pd.DataFrame) -> pd.DataFrame:
    """
    사업명(+예산과목)이 있는 표에 투자유형/세부 예측 컬럼을 붙인다.
    학습된 모델이 없는 라벨은 예측하지 않는다(해당 컬럼 생략).
    투자유형세부는 '예측된 투자유형'이 그 상위값(MINOR_TARGET_PARENT, 예: '설비개선')과
    일치하는 행에만 값을 채우고, 나머지 행은 빈 값으로 둔다.
    반환: 입력 df + '투자유형_예측'/'투자유형_확신도' (+세부 동일).
    """
    out = df.copy()
    X = _build_text(out)
    major_pred = None
    for target in TARGETS:
        model = load_model(target)
        if model is None:
            continue
        proba = model.predict_proba(X)
        pred = pd.Series(model.predict(X), index=out.index)
        conf = pd.Series(proba.max(axis=1).round(2), index=out.index)

        parent_value = MINOR_TARGET_PARENT.get(target)
        if parent_value is not None and major_pred is not None:
            applies = major_pred == parent_value
            pred = pred.where(applies, "")
            conf = conf.where(applies, pd.NA)

        out[f"{target}_예측"] = pred
        out[f"{target}_확신도"] = conf
        if target == "투자유형":
            major_pred = pred
    return out


def reset_models():
    """학습된 모델만 삭제(학습데이터는 보존)."""
    for p in list(MODEL_PATHS.values()) + [META_PATH]:
        if os.path.exists(p):
            os.remove(p)


def reset_all():
    """학습데이터와 모델을 모두 삭제(되돌릴 수 없음)."""
    reset_models()
    if os.path.exists(TRAINING_PATH):
        os.remove(TRAINING_PATH)
