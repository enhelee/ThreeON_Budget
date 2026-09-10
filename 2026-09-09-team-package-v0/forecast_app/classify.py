"""
투자유형 1차 분류 (키워드 규칙 기반 프로토타입)
- 실제 5개년 라벨 데이터 확보 전까지 사용하는 임시 로직
- 나중에 지도학습 모델로 교체 예정 (인터페이스는 동일하게 유지: text -> (label, confidence))
"""
import pandas as pd

KEYWORD_RULES = {
    "LTSA": ["LTSA", "OEM", "장기서비스"],
    "정기사업": ["정기점검", "정기보수", "계획예방정비", "TA"],
    "노후설비개체": ["노후"],
    "AX/DX": ["자동화", "스마트", "AI", "DCS", "디지털"],
    "운영안정성 제고": ["신뢰도", "안정화", "보강", "예비설비"],
    "환경강화": ["탈황", "집진", "대기오염", "환경"],
    "교육강화": ["교육", "역량강화", "워크숍"],
    "보안강화": ["CCTV", "출입통제", "사이버보안", "방호"],
}


def classify_with_confidence(text: str):
    """
    텍스트에 매칭되는 유형별 키워드 개수를 세어 확신도를 계산한다.
    - 한 유형에서만 키워드가 나오면 확신도 높음
    - 여러 유형에서 겹치면 확신도 낮아짐(애매함)
    - 아무 키워드도 없으면 '미분류', 확신도 0
    """
    text = str(text)
    matches = {}
    for label, keywords in KEYWORD_RULES.items():
        count = sum(1 for kw in keywords if kw in text)
        if count > 0:
            matches[label] = count

    if not matches:
        return "미분류", 0.0, {}

    total = sum(matches.values())
    best_label = max(matches, key=matches.get)
    best_count = matches[best_label]

    if len(matches) == 1:
        confidence = min(0.95, 0.7 + 0.1 * best_count)
    else:
        confidence = round(best_count / total, 2) * 0.85

    return best_label, round(confidence, 2), matches


def classify_dataframe(df: pd.DataFrame, text_col: str = "전표헤더텍스트") -> pd.DataFrame:
    labels, confidences = [], []
    for text in df[text_col]:
        label, conf, _ = classify_with_confidence(text)
        labels.append(label)
        confidences.append(conf)
    out = df.copy()
    out["예측유형"] = labels
    out["확신도"] = confidences
    return out.sort_values("확신도").reset_index(drop=True)
