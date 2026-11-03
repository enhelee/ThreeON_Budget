# -*- coding: utf-8 -*-
"""예산과목·처지사 표기 정규화.

ERP(zrfm2)와 계획본의 표기 차이를 흡수해 매칭 정확도를 높인다.
- 예산과목: alias 맵으로 계획본 표준 표기로 환원.
- 처지사: override 맵 → 공백/괄호 제거 후 정확일치 → 접두(양방향) → 유사도 → 실패시 None.
실패(미매핑) 값은 호출측에서 검토리포트로 보고한다.
"""
import re
import unicodedata

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


_TEXTKEY = re.compile(r"[\s'\"‘’“”　]+")


def text_key(s):
    """학습·매칭 키용 텍스트 정규화: 공백·따옴표류 제거(표기 흔들림 흡수)."""
    if s is None:
        return None
    out = _TEXTKEY.sub("", str(s))
    return out or None


# 반복 전표 마커: 회차·분기·월·연도·비용인식을 지워 "N회/N월/YY년"만 다른 전표를 한 키로 모은다.
#   예) "가스터빈 LTSA 29회 기성" 과 "…33회 기성" → 같은 학습키 → 한 번 확정하면 매년 자동확정.
_INSTALLMENT = re.compile(
    r"\d+\s*회차?"           # 29회, 3회차
    r"|\d+\s*분기"           # 2분기
    r"|'?\s*\d{2,4}\s*년"    # '25년, 2025년
    r"|\d{1,2}\s*월\s*분?"   # 12월, 1월분
    r"|비용\s*역?\s*인식"    # 비용인식, 비용역인식
)


def learn_key(s):
    """학습키 정규화: text_key + 회차/분기/월/연도/비용인식 마커 제거.
    반복 기성·월별 전표(회차·연도만 다름)를 한 키로 묶어, 한 번 사람이 확정하면
    다음 해 같은 계약 전표가 자동확정되게 한다(재검토 방지)."""
    if s is None:
        return None
    out = _INSTALLMENT.sub("", str(s))
    return text_key(out)


# 보정 규칙 키: 담당자 도구(Claude/src/pipeline.js simNorm)와 **같은 키**가 나와야
#   그 도구에서 만든 보정사전이 이 앱에서도 맞는다. 순서·정규식을 그대로 옮겼다.
#   JS 의 \d·\b 는 ASCII 기준이라 [0-9]·re.A 로 맞춘다(파이썬은 한글도 단어 문자로 본다).
_CORR_SYNONYMS = (
    (re.compile(r"\bGT\b", re.I | re.A), "가스터빈"),
    (re.compile(r"\bHRSG\b", re.I | re.A), "배열회수보일러"),
)
_CORR_NOISE = tuple(re.compile(p) for p in (
    r"[0-9]+\s*회", r"[0-9]+\s*분기", r"'?[0-9]+\s*년?\s*[0-9]+\s*월",
    r"[0-9]+\s*월\s*분?", r"비용\s*역?\s*인식"))
_CORR_YEAR = re.compile(r"[0-9]{4}\s*년도?")
_CORR_PUNCT = re.compile(r"['\"’”()\[\]（）·:,\-_/]")


def corr_key(s):
    """보정 규칙 키: 동의어(GT·HRSG) → 회차·분기·월·비용인식 → 연도 → 구분자 → 공백 제거."""
    out = unicodedata.normalize("NFC", "" if s is None else str(s))
    for rx, rep in _CORR_SYNONYMS:
        out = rx.sub(rep, out)
    for rx in _CORR_NOISE:
        out = rx.sub(" ", out)
    out = _CORR_PUNCT.sub(" ", _CORR_YEAR.sub(" ", out))
    return _SPACE.sub("", out).strip()


def normalize_item(name, alias_map):
    """예산과목명을 계획본 표준 표기로 환원. 매핑 없으면 원문(공백 제거) 그대로.

    과목명 안의 공백(전각 포함)은 지운다 — 표준 과목명엔 공백이 없는데 23년 계획본에
    «건 물»이 섞여 «건물»과 다른 과목이 되어 1.3억이 빠졌다(2026-10-13 최종 테스트).
    alias 원표기도 같은 방식으로 맞춰 본다."""
    if name is None:
        return None
    key = _SPACE.sub("", str(name))
    if key in alias_map:
        return alias_map[key]
    for src, dst in alias_map.items():
        if _SPACE.sub("", str(src)) == key:
            return dst
    return key


def dept_from_text(text, plan_depts):
    """자유 텍스트(예: ERP J열 '(CHP)광교지사 고객지원부')에서 계획 처지사를
    부분문자열로 탐지. 가장 긴 매칭을 우선한다. 없으면 None."""
    if not text:
        return None
    s = str(text)
    hits = [d for d in plan_depts if d in s]
    if not hits:
        return None
    return max(hits, key=len)


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
