# -*- coding: utf-8 -*-
"""필수 필드 결측치 탐지."""
import math

REQUIRED_FIELDS = ["처지사", "예산과목", "연예산", "사업명"]


def _is_blank(v):
    if v is None:
        return True
    if isinstance(v, float) and math.isnan(v):
        return True
    if isinstance(v, str) and v.strip() == "":
        return True
    return False


def missing_fields(row):
    return [f for f in REQUIRED_FIELDS if _is_blank(row[f])]


def collect_missing_rows(df):
    out = []
    for _, row in df.iterrows():
        mf = missing_fields(row)
        if mf:
            out.append({"행번호": int(row["_row"]), "사업명": row["사업명"], "누락필드": mf})
    return out
