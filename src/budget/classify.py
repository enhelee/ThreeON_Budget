# -*- coding: utf-8 -*-
"""업로드 데이터를 손익/자본으로 분류, 미분류 예산과목 탐지."""


def classify_rows(df, budget, pl_items, cap_items):
    target = pl_items if budget == "손익" else cap_items
    filtered = df[df["예산과목"].isin(target)].reset_index(drop=True)
    known = pl_items | cap_items
    unclassified = sorted({
        str(v).strip() for v in df["예산과목"]
        if v is not None and str(v).strip() != "" and str(v).strip() not in known
    })
    return filtered, unclassified
