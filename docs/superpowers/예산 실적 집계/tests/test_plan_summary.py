import pandas as pd
from budget import plan_summary


def test_aggregate_simui_split():
    df = pd.DataFrame([
        {"예산과목": "수선유지비-건물/구축물", "처지사": "화성지사", "연예산": 60000.0},
        {"예산과목": "수선유지비-건물/구축물", "처지사": "화성지사", "연예산": 10000.0},
        {"예산과목": "수선유지비-열원경상정비", "처지사": "화성지사", "연예산": 30000.0},
        {"예산과목": "제외과목", "처지사": "화성지사", "연예산": 999.0},
    ])
    item_rows = [
        {"대분류": "수선유지비", "과목들": [
            {"과목": "수선유지비-건물/구축물", "심의대상": True},
            {"과목": "수선유지비-열원경상정비", "심의대상": False},
        ]},
    ]
    matrix = plan_summary.aggregate(df, item_rows)
    assert matrix[("수선유지비-건물/구축물", "이상")]["화성지사"] == 60000.0
    assert matrix[("수선유지비-건물/구축물", "미만")]["화성지사"] == 10000.0
    assert matrix[("수선유지비-열원경상정비", None)]["화성지사"] == 30000.0
    assert ("제외과목", None) not in matrix


def test_aggregate_skips_missing_amount():
    df = pd.DataFrame([
        {"예산과목": "A", "처지사": "강남지사", "연예산": None},
        {"예산과목": "A", "처지사": "강남지사", "연예산": 5.0},
    ])
    item_rows = [{"대분류": "x", "과목들": [{"과목": "A", "심의대상": False}]}]
    matrix = plan_summary.aggregate(df, item_rows)
    assert matrix[("A", None)]["강남지사"] == 5.0
