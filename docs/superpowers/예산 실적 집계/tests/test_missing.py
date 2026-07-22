import pandas as pd
from budget import missing


def test_missing_fields_detects_blank_and_none():
    row = {"처지사": "", "예산과목": "수선유지비-건물/구축물", "연예산": None, "사업명": "X"}
    assert missing.missing_fields(row) == ["처지사", "연예산"]


def test_missing_fields_zero_amount_not_missing():
    row = {"처지사": "화성지사", "예산과목": "A", "연예산": 0.0, "사업명": "X"}
    assert missing.missing_fields(row) == []


def test_collect_missing_rows():
    df = pd.DataFrame([
        {"_row": 4, "처지사": "화성지사", "예산과목": "A", "연예산": 100.0, "사업명": "X"},
        {"_row": 5, "처지사": None, "예산과목": "B", "연예산": 50.0, "사업명": "Y"},
        {"_row": 6, "처지사": "강남지사", "예산과목": None, "연예산": None, "사업명": None},
    ])
    result = missing.collect_missing_rows(df)
    assert len(result) == 2
    assert result[0] == {"행번호": 5, "사업명": "Y", "누락필드": ["처지사"]}
    assert result[1]["행번호"] == 6
    assert set(result[1]["누락필드"]) == {"예산과목", "연예산", "사업명"}
