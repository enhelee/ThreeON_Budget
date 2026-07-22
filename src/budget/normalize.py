# -*- coding: utf-8 -*-
"""예산과목·처지사 표기 정규화.

ERP(zrfm2)와 계획본의 표기 차이를 흡수해 매칭 정확도를 높인다.
- 예산과목: alias 맵으로 계획본 표준 표기로 환원.
- 처지사: override 맵 → 공백/괄호 제거 후 정확일치 → 접두(양방향) → 유사도 → 실패시 None.
실패(미매핑) 값은 호출측에서 검토리포트로 보고한다.
"""
import re

from rapidfuzz import fuzz

_PAREN = re.compile(r"\([^)]*\)")
_SPACE = re.compile(r"\s+")


def _clean(s):
    """공백(전각 포함)·괄호 내용 제거."""
    if s is None:
        return ""
    s = str(s).replace("　", " ")  # 전각 공백
    s = _PAREN.sub("", s)
    s = _SPACE.sub("", s)
    return s.strip()


def normalize_item(name, alias_map):
    """예산과목명을 계획본 표준 표기로 환원. 매핑 없으면 원문 그대로."""
    if name is None:
        return None
    key = str(name).strip()
    return alias_map.get(key, key)


def normalize_dept(raw, plan_depts, override_map=None, threshold=90):
    """ERP 지사명 raw를 계획 처지사(plan_depts) 중 하나로 정규화.

    반환: 매칭된 처지사명(str) 또는 None(미매핑).
    """
    override_map = override_map or {}
    if raw is None:
        return None
    key = str(raw).strip()
    if key in override_map:
        return override_map[key]
    if key in plan_depts:
        return key

    cleaned = _clean(key)
    if not cleaned:
        return None
    if cleaned in override_map:
        return override_map[cleaned]
    if cleaned in plan_depts:
        return cleaned

    # 접두 관계(양방향) — 고유 후보일 때만 채택
    prefix_hits = [
        d for d in plan_depts
        if d.startswith(cleaned) or cleaned.startswith(d)
    ]
    if len(prefix_hits) == 1:
        return prefix_hits[0]

    # 유사도 폴백
    best, best_score = None, 0
    for d in plan_depts:
        score = fuzz.ratio(cleaned, d)
        if score > best_score:
            best, best_score = d, score
    if best_score >= threshold:
        return best
    return None
