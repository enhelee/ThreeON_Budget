# -*- coding: utf-8 -*-
"""사업별 예산 업로드 파일 로드 (손익/자본 구분 없는 전체 사업).

열은 위치가 아니라 헤더 이름으로 찾는다. 현업 원본(주관부서예산 손익·자본·건설공사)은
«기준»·«ESG 연계»·«본부»·«중점전략 연계» 같은 열이 연도마다 끼어 있어 위치가 달라진다
(23·24년 12열, 25년 13열 — 앱 템플릿은 10열). 이름을 못 찾을 때만 템플릿 위치(1~10열)로 읽는다.
"""
import re

import pandas as pd
import openpyxl

PLAN_COLUMNS = [
    "주관부서명", "부서코드", "처지사", "부서부", "속성",
    "예산코드", "예산과목", "사업명", "산출내역", "연예산",
]

# 앱 열 → 헤더에서 찾을 이름들(공백·줄바꿈 제거 후 비교, 앞의 것이 우선)
_HEADER_NAMES = {
    "주관부서명": ["주관부서명"],
    "부서코드": ["예산귀속부서코드", "부서코드"],
    "처지사": ["예산귀속부서명(처.지사)", "처지사"],
    "부서부": ["예산귀속부서명(부)", "부서(부)", "부서부"],
    "속성": ["속성"],
    "예산코드": ["예산코드"],
    "예산과목": ["예산과목"],
    "사업명": ["사업명"],
    "산출내역": ["산출내역"],
    "연예산": ["연예산합계", "연예산"],
}
_WS = re.compile(r"\s+")


def _key(v):
    return _WS.sub("", str(v)) if v is not None else ""


def _blank(v):
    return v is None or str(v).strip() == ""


def _header_index(header_row):
    """헤더 행에서 앱 열마다의 0-기준 열 번호. 하나라도 못 찾으면 None."""
    pos = {}
    for j, v in enumerate(header_row):
        pos.setdefault(_key(v), j)
    idx = []
    for col in PLAN_COLUMNS:
        j = next((pos[n] for n in _HEADER_NAMES[col] if n in pos), None)
        if j is None:
            return None
        idx.append(j)
    return idx


def load_business_plan(path):
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        ws = wb["양식1(월별)"]
        rows = ws.iter_rows(min_row=3, values_only=True)
        header = next(rows, ())
        idx = _header_index(header) or list(range(len(PLAN_COLUMNS)))
        recs = []
        for r, row in enumerate(rows, 4):
            vals = [row[j] if j < len(row) else None for j in idx]
            if all(_blank(v) for v in vals):
                continue
            rec = dict(zip(PLAN_COLUMNS, vals))
            # 원본 양식의 빈 줄은 수식이 남아 과목·사업명이 0 으로 찍힌다 — 사업이 아니다
            if all(_blank(rec[c]) or str(rec[c]).strip() == "0" for c in ("예산과목", "사업명")):
                continue
            amt = rec["연예산"]
            rec["연예산"] = float(amt) if isinstance(amt, (int, float)) else None
            rec["_row"] = r
            recs.append(rec)
    finally:
        wb.close()
    cols = PLAN_COLUMNS + ["_row"]
    return pd.DataFrame(recs, columns=cols)


def load_business_plans(paths):
    """여러 파일(예: 손익·자본·건설공사)을 한 계획으로 합친다.

    _row 는 전표를 계획 행에 잇는 열쇠라 한 데이터셋 안에서 겹치면 안 된다 —
    두 번째 파일부터는 앞 파일들의 마지막 행 번호만큼 밀어 이어 붙인다.
    """
    frames, offset = [], 0
    for p in paths:
        df = load_business_plan(p)
        if len(df):
            df["_row"] = df["_row"] + offset
            offset = int(df["_row"].max())
        frames.append(df)
    if not frames:
        return pd.DataFrame(columns=PLAN_COLUMNS + ["_row"])
    return pd.concat(frames, ignore_index=True)
