# -*- coding: utf-8 -*-
"""scripts/measure_match_precision.py — 점수 계산(정답 대조·확신도 구간·근거별)."""
import importlib.util
import os

import pandas as pd

_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts", "measure_match_precision.py")
_spec = importlib.util.spec_from_file_location("measure_match_precision", _PATH)
M = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(M)


def test_name_strips_new_prefix():
    assert M._name("[신규] 펌프 교체") == "펌프 교체"
    assert M._name(None) == ""
    assert M._name(float("nan")) == ""
    assert M._target({"사업명": "[신규] A", "처지사": None}) == "A"


def test_score_bands_and_flags():
    df = pd.DataFrame({
        "gt":    ["A", "A", "B", "B", "C"],
        "pred":  ["A", "X", "B", "Y", "C"],
        "conf":  [0.99, 0.90, 0.60, 0.30, None],
        "amt":   [100.0, 300.0, 50.0, 50.0, 0.0],
        "basis": ["학습", "사업명 유사", "사업명 유사", "임의 귀속(유사도 낮음)", ""],
    })
    s = M.score(df)
    assert s["전표수"] == 5 and s["일치"] == 3 and s["일치율%"] == 60.0
    assert s["금액가중 일치율%"] == 30.0                     # (100+50+0) / 500
    hi, mid, lo = s["구간"]
    assert (hi["전표수"], hi["정밀도%"]) == (2, 50.0)          # ≥0.80: A 맞고 X 틀림
    assert (mid["전표수"], mid["정밀도%"]) == (1, 100.0)
    assert lo["전표수"] == 2                                   # 0.30 과 확신도 없음
    assert s["자동확정 재현율%"] == 20.0                        # 5건 중 «자동확정 + 정답» 1건
    assert s["틀린 전표 중 저확신 표시%"] == 50.0               # 틀린 2건 중 저확신 1건
    by = {r["근거"]: r for r in s["근거별"]}
    assert by["사업명 유사"]["틀린 자동확정"] == 1 and by["(없음)"]["전표수"] == 1


def test_band_labels():
    assert M._band(0.95).startswith("≥0.80")
    assert M._band(0.80).startswith("≥0.80")
    assert M._band(0.6).startswith("0.50~")
    assert M._band(None).startswith("<0.50") and M._band(float("nan")).startswith("<0.50")


def test_audit_score_weights_by_population():
    hi, mid, lo = (b[2] for b in M.BANDS)
    sample = pd.DataFrame({
        "확신도 구간": [hi] * 4 + [mid] * 2 + [lo] * 3,
        "검수(O/X)":  ["O", "o", " O ", "X", "O", "O", "X", "O", None],
    })
    r = M.audit_score(sample, {hi: 600, mid: 200, lo: 200})
    assert r["검수 완료"] == 8 and r["미기입"] == 1
    by = {row["구간"]: row for row in r["구간별"]}
    assert (by[hi]["정답"], by[hi]["검수"], by[hi]["정밀도%"]) == (3, 4, 75.0)
    assert by[lo]["정밀도%"] == 50.0
    assert r["전체 추정 정밀도%"] == 75.0           # 0.75·0.6 + 1.0·0.2 + 0.5·0.2
    lo95, hi95 = (float(x) for x in by[hi]["95% 구간"].split("~"))
    assert lo95 < 75.0 < hi95


def test_wilson_empty():
    assert M._wilson(0, 0) == (None, None)


def test_score_empty_sample():
    df = pd.DataFrame(columns=["gt", "pred", "conf", "amt", "basis"])
    s = M.score(df)
    assert s["전표수"] == 0 and s["일치율%"] is None
