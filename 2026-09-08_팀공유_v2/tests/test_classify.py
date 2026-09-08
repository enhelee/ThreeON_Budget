from classify import classify_with_confidence, classify_dataframe, KEYWORD_RULES
import pandas as pd


def test_single_keyword_match_gives_high_confidence():
    label, conf, matches = classify_with_confidence("동탄지사 노후 배관 교체공사")
    assert label == "노후설비개체"
    assert conf >= 0.7
    assert matches == {"노후설비개체": 1}


def test_no_keyword_match_is_unclassified():
    label, conf, matches = classify_with_confidence("아무 의미 없는 텍스트")
    assert label == "미분류"
    assert conf == 0.0
    assert matches == {}


def test_overlapping_keywords_lower_confidence_than_single_match():
    _, single_conf, _ = classify_with_confidence("정기점검 수행")
    _, overlap_conf, _ = classify_with_confidence("정기점검 중 노후 설비 발견")
    assert overlap_conf < single_conf


def test_classify_dataframe_sorts_by_confidence_ascending():
    df = pd.DataFrame({"전표헤더텍스트": ["노후 배관 교체", "아무 텍스트", "LTSA 장기서비스 계약"]})
    out = classify_dataframe(df)
    assert list(out["확신도"]) == sorted(out["확신도"])
    assert "예측유형" in out.columns
