# -*- coding: utf-8 -*-
"""보정 규칙(담당자 보정사전) 파일 해석.

담당자 도구(Claude/src/pipeline.js parseCorrections)의 보정사전 엑셀을 그대로 받는다.
  지사 | 예산과목 | 전표텍스트 | … | 올바른사업명 | (계획사업명)
- 올바른사업명 = 담당자가 정한 사업. «제외…»로 시작하면 실적에서 뺀다.
- 계획사업명 = 사업명 대응표 칸. 담당자 도구는 집계표(양식2/3) 이름을 쓰고 이 앱은
  계획본(양식1) 이름을 쓰므로, 채워 두면 그 이름으로 붙인다(비면 올바른사업명).
- 키는 (지사, 과목, normalize.corr_key(전표텍스트)) — 회차·연도가 달라도 같은 키라
  한 번 맞춘 규칙이 매년 다시 쓰인다. 지사가 비면 모든 지사에 건다.
과목·지사 표기는 분석 때 그 해 별칭·마스터로 정규화한다(pipeline_actual).
"""
import io
import unicodedata

import openpyxl

from . import normalize

ASSIGN = "배정"
EXCLUDE = "제외"


def _s(v):
    return unicodedata.normalize("NFC", "" if v is None else str(v)).strip()


def _find_header(rows):
    """앞 6줄 안에서 «전표텍스트»와 «사업명»이 함께 있는 줄을 머리글로 본다(JS 와 같은 규칙)."""
    for hr, row in enumerate(rows[:6]):
        h = [_s(x).replace(" ", "") for x in (row or [])]
        if any("전표텍스트" in x for x in h) and any("사업명" in x for x in h):
            return hr, h
    raise ValueError("머리글(전표텍스트·사업명)을 찾지 못했습니다 — 보정사전 양식인지 확인하세요.")


def _col(h, *keys, avoid=()):
    for k in keys:
        for i, x in enumerate(h):
            if k in x and not any(a in x for a in avoid):
                return i
    return -1


def parse_rows(rows):
    """2차원 값 목록 → {"rules": [규칙 dict], "skipped": 사업명·텍스트가 빈 줄 수}.

    같은 키가 여러 번 나오면 뒤 줄이 이긴다(담당자 도구의 Map.set 과 같다)."""
    rows = [list(r) for r in rows]
    hr, h = _find_header(rows)
    ci_dep = _col(h, "지사", "부서")
    ci_acct = _col(h, "예산과목", "과목")
    ci_text = _col(h, "전표텍스트")
    ci_plan = _col(h, "계획사업명", "대응")
    ci_biz = _col(h, "올바른")
    if ci_biz < 0:
        ci_biz = _col(h, "사업명", avoid=("내가붙인", "계획"))
    if min(ci_acct, ci_text, ci_biz) < 0:
        raise ValueError("예산과목·전표텍스트·사업명 칸이 모두 있어야 합니다.")

    def cell(row, i):
        return _s(row[i]) if 0 <= i < len(row) else ""

    out, skipped = {}, 0
    for row in rows[hr + 1:]:
        biz, key = cell(row, ci_biz), normalize.corr_key(cell(row, ci_text))
        if not biz or not key:
            if any(_s(x) for x in row):
                skipped += 1
            continue
        dept = cell(row, ci_dep)
        item = normalize._SPACE.sub("", cell(row, ci_acct))
        exclude = biz.startswith(EXCLUDE)
        out[(dept, item, key)] = {
            "처지사": dept, "과목": item, "텍스트키": key,
            "동작": EXCLUDE if exclude else ASSIGN,
            "사업명": None if exclude else (cell(row, ci_plan) or biz),
            "원사업명": biz,
        }
    return {"rules": list(out.values()), "skipped": skipped}


def parse_xlsx(data):
    """엑셀 bytes → parse_rows. 머리글이 있는 첫 시트를 쓴다."""
    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    try:
        last = None
        for ws in wb.worksheets:
            rows = [list(r) for r in ws.iter_rows(values_only=True)]
            try:
                return parse_rows(rows)
            except ValueError as e:
                last = e
        raise last or ValueError("시트가 없습니다.")
    finally:
        wb.close()


def to_match_map(rules, item_alias=None, code_to_item=None, dept_names=None, dept_alias=None):
    """저장된 규칙 → match_actuals 의 corr_rules 맵. 과목·지사 표기를 그 해 기준으로 맞춘다.

    과목이 계정코드(숫자)면 마스터로 과목명을 찾는다. 지사를 못 맞추면 원문 그대로 둔다
    (그 지사 전표가 없으니 걸리지 않을 뿐 다른 지사를 건드리지 않는다)."""
    item_alias = item_alias or {}
    out = {}
    for r in rules:
        item = r["과목"]
        if code_to_item and item.isdigit() and item in code_to_item:
            item = code_to_item[item]
        item = normalize.normalize_item(item, item_alias)
        dept = r["처지사"] or ""
        if dept and dept_names:
            dept = normalize.normalize_dept(dept, dept_names, dept_alias) or dept
        out[(dept, item, r["텍스트키"])] = {"동작": r["동작"], "사업명": r["사업명"]}
    return out
