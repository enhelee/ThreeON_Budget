import pandas as pd
from budget import classify


def _df():
    return pd.DataFrame([
        {"_row": 4, "예산과목": "수선유지비-건물/구축물", "처지사": "화성지사", "연예산": 100.0},
        {"_row": 5, "예산과목": "건물", "처지사": "건설처", "연예산": 200.0},
        {"_row": 6, "예산과목": "알수없는과목", "처지사": "강남지사", "연예산": 10.0},
        {"_row": 7, "예산과목": None, "처지사": "강남지사", "연예산": 5.0},
    ])


def test_classify_pl_only():
    pl = {"수선유지비-건물/구축물"}
    cap = {"건물"}
    filtered, unclassified = classify.classify_rows(_df(), "손익", pl, cap)
    assert len(filtered) == 1
    assert filtered.iloc[0]["예산과목"] == "수선유지비-건물/구축물"
    assert unclassified == ["알수없는과목"]


def test_classify_capital_only():
    pl = {"수선유지비-건물/구축물"}
    cap = {"건물"}
    filtered, unclassified = classify.classify_rows(_df(), "자본", pl, cap)
    assert len(filtered) == 1
    assert filtered.iloc[0]["예산과목"] == "건물"
    assert unclassified == ["알수없는과목"]
