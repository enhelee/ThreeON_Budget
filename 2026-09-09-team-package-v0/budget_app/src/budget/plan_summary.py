# -*- coding: utf-8 -*-
"""필터된 업로드 데이터를 (예산과목,심의구분) x 처지사 매트릭스로 집계."""
from collections import defaultdict
import pandas as pd
from .config_store import SIMUI_THRESHOLD_THOUSAND


def aggregate(df, item_rows):
    item_flags = {}
    for cat in item_rows:
        for it in cat["과목들"]:
            item_flags[it["과목"]] = it["심의대상"]

    matrix = defaultdict(lambda: defaultdict(float))
    for _, row in df.iterrows():
        item = row["예산과목"]
        if item not in item_flags:
            continue
        amt = row["연예산"]
        if pd.isna(amt):
            continue
        dept = row["처지사"]
        if item_flags[item]:
            key = (item, "이상") if amt >= SIMUI_THRESHOLD_THOUSAND else (item, "미만")
        else:
            key = (item, None)
        matrix[key][dept] += float(amt)
    return {k: dict(v) for k, v in matrix.items()}
