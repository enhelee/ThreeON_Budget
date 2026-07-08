"""
분류 방식을 자동 선택한다.
- 학습된 모델(type_classifier.joblib)이 있으면 그것을 사용
- 없으면 키워드 규칙(classify.py)으로 대체
"""
import pandas as pd
from classify import classify_dataframe as rule_based_classify
from ml_classifier import load_model, predict_with_model


def classify_dataframe(df: pd.DataFrame, text_col: str = "전표헤더텍스트") -> tuple[pd.DataFrame, str]:
    """반환: (분류결과 데이터프레임, 사용된 방식 'ml' 또는 'rule')"""
    model = load_model()
    if model is not None:
        labels, confidences = predict_with_model(model, df[text_col].astype(str))
        out = df.copy()
        out["예측유형"] = labels
        out["확신도"] = confidences.round(2)
        return out.sort_values("확신도").reset_index(drop=True), "ml"
    else:
        return rule_based_classify(df, text_col), "rule"
