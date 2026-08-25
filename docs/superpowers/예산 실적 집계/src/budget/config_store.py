# -*- coding: utf-8 -*-
"""지사구성·예산과목구성 JSON 영속화. 연도별(및 과목은 손익/자본별)로 저장·자동 로드."""
import json
import os

DEPT_GROUPS = ["본사", "중대형CHP", "소형CHP", "DH"]
SIMUI_THRESHOLD_THOUSAND = 50000

_SEED_DEPTS = {
    "본사": ["플랜트기술처", "안전처", "통합운영처", "건설처", "미래사업처"],
    "중대형CHP": ["동탄지사", "화성지사", "파주지사", "광교지사", "판교지사", "삼송지사", "대구지사", "청주지사"],
    "소형CHP": ["수원사업소", "광주전남지사", "강남지사"],
    "DH": ["중앙지사", "고양사업소", "용인지사", "분당사업소", "세종지사", "김해사업소", "양산지사", "평택지사"],
}


def seed_dept_config():
    out = []
    for g in DEPT_GROUPS:
        for name in _SEED_DEPTS[g]:
            out.append({"이름": name, "그룹": g, "포함": True})
    return out


def _dept_path(config_dir, year):
    return os.path.join(config_dir, f"지사구성_{year}.json")


def normalize_dept_config(items):
    """지사 구성의 '포함' 값을 불리언으로 표준화(누락·NaN → True)."""
    return [dict(x, 포함=to_bool(x.get("포함"), True)) for x in items]


def load_dept_config(config_dir, year):
    path = _dept_path(config_dir, year)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return normalize_dept_config(json.load(f))
    return seed_dept_config()


def save_dept_config(config_dir, year, items):
    os.makedirs(config_dir, exist_ok=True)
    with open(_dept_path(config_dir, year), "w", encoding="utf-8") as f:
        json.dump(normalize_dept_config(items), f, ensure_ascii=False, indent=2,
                  allow_nan=False)


SEED_ITEMS = {
    "손익": [
        {"과목": "수선유지비-건물/구축물", "대분류": "수선유지비", "심의대상": True},
        {"과목": "수선유지비-열원정기점검", "대분류": "수선유지비", "심의대상": False},
        {"과목": "수선유지비-열원경상정비", "대분류": "수선유지비", "심의대상": False},
        {"과목": "수선유지비-열원정기유지보수", "대분류": "수선유지비", "심의대상": False},
        {"과목": "수선유지비-열원보완및개선", "대분류": "수선유지비", "심의대상": True},
        {"과목": "수선유지비-비저장품(보수자재)", "대분류": "수선유지비", "심의대상": False},
        {"과목": "수선유지비-소모품(자재공기구)", "대분류": "수선유지비", "심의대상": False},
        {"과목": "지급수수료-열원점검수수료", "대분류": "지급수수료", "심의대상": False},
    ],
    "자본": [
        {"과목": "건물", "대분류": "자산", "심의대상": False},
        {"과목": "구축물", "대분류": "자산", "심의대상": False},
        {"과목": "기계장치", "대분류": "자산", "심의대상": False},
        {"과목": "공구와기구-열원시설공기구", "대분류": "자산", "심의대상": False},
        {"과목": "저장품-열원(보수)", "대분류": "예비품", "심의대상": False},
        {"과목": "건설중인자산-재생고온부품", "대분류": "예비품", "심의대상": False},
        {"과목": "건설중인자산-자산화예비품", "대분류": "예비품", "심의대상": False},
        {"과목": "외주비-열원정기점검", "대분류": "A급정비", "심의대상": False},
        # 건설공사(외주비-열원공사비·재료비-열원자재비·외주비-열원기술용역비)는 계획엔 존재하나
        # zrfm2에 실적 계정이 없어 실적 자동집계 불가 — 실적 분석 범위 밖(사용자 결정).
        # '실적반영': False → 계획본엔 그대로 포함, 실적 산출물(양식1·종합표)에서만 제외.
        {"과목": "외주비-열원공사비", "대분류": "건설공사", "심의대상": False, "실적반영": False},
        {"과목": "재료비-열원자재비", "대분류": "건설공사", "심의대상": False, "실적반영": False},
        {"과목": "외주비-열원기술용역비", "대분류": "건설공사", "심의대상": False, "실적반영": False},
    ],
}


def seed_item_config(budget):
    return [normalize_item_row(dict(x, 포함=True)) for x in SEED_ITEMS[budget]]


ITEM_BOOL_FIELDS = {"심의대상": False, "포함": True, "실적반영": True}


def to_bool(v, default):
    """체크박스 값 정규화. None/NaN/'' → default, 'FALSE'/'0' → False.

    st.data_editor가 만든 DataFrame은 일부 행에 없는 열을 NaN으로 채우는데,
    NaN은 파이썬에서 truthy라 그대로 두면 판정이 뒤집히고 JSON에도
    비표준 토큰 `NaN`이 기록된다. 저장·로드 양쪽에서 반드시 정규화한다.
    """
    if v is None:
        return default
    if isinstance(v, bool):
        return v
    if isinstance(v, float) and v != v:      # NaN
        return default
    if isinstance(v, str):
        s = v.strip().lower()
        if s == "":
            return default
        return s not in ("false", "0", "no", "n", "아니오", "x")
    return bool(v)


def normalize_item_row(row):
    """예산과목 구성 1행의 불리언 필드를 표준화(누락·NaN 보정)."""
    out = dict(row)
    for k, default in ITEM_BOOL_FIELDS.items():
        out[k] = to_bool(out.get(k), default)
    return out


def normalize_item_config(items):
    return [normalize_item_row(x) for x in items]


def _item_path(config_dir, year, budget):
    return os.path.join(config_dir, f"과목구성_{year}_{budget}.json")


def load_item_config(config_dir, year, budget):
    path = _item_path(config_dir, year, budget)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return normalize_item_config(json.load(f))
    return seed_item_config(budget)


def save_item_config(config_dir, year, budget, items):
    os.makedirs(config_dir, exist_ok=True)
    with open(_item_path(config_dir, year, budget), "w", encoding="utf-8") as f:
        json.dump(normalize_item_config(items), f, ensure_ascii=False, indent=2,
                  allow_nan=False)


# ---------------------------------------------------------------------------
# 정규화 맵 (2단계 실적분석) — 표기 불일치 해소용. config로 편집·영속화 가능.
# ---------------------------------------------------------------------------

# 예산과목 alias: {구 표기 -> 현 표기}. 계정코드가 같은 동일 과목의 연도별
# 명칭 변경만 통일한다. 24년 '수선유지비-열원보완개선및기타'는 25년에
# '수선유지비-열원보완및개선'으로 개명(계정코드 60909009 동일) → 통일.
# (계정코드가 다른 서로 다른 과목은 여기에 넣지 말 것. 구성에 없으면 결측 분류.)
SEED_ITEM_ALIAS = {
    "수선유지비-열원보완개선및기타": "수선유지비-열원보완및개선",
}

# 처지사 정규화 override: {ERP 원문 -> 계획 처지사}. 접두/유사도 규칙으로
# 자동 처리되지 않는 예외만 등록한다.
SEED_DEPT_ALIAS = {
    "판교사업소": "판교지사",
    "분당지사": "분당사업소",
    "서울중앙지사": "중앙지사",
    "대구우드칩": "대구지사",
    "미래개발원": "미래사업처",
    "본사(광양태양광)": "미래사업처",
    "본사(강릉태양광)": "미래사업처",
    "본사(함백태양광)": "미래사업처",
    "서울남부지사": "강남지사",
    "경남지사(양산RPS 태양광)": "양산지사",
    "고양 PLB": "고양사업소",
}


def seed_item_alias():
    return dict(SEED_ITEM_ALIAS)


def seed_dept_alias():
    return dict(SEED_DEPT_ALIAS)


def _item_alias_path(config_dir):
    return os.path.join(config_dir, "예산과목_별칭.json")


def _dept_alias_path(config_dir):
    return os.path.join(config_dir, "처지사_별칭.json")


def load_item_alias(config_dir):
    """시드 기본값 + 파일(사용자 편집) 병합. 파일 항목이 우선."""
    merged = seed_item_alias()
    path = _item_alias_path(config_dir)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            merged.update(json.load(f))
    return merged


def save_item_alias(config_dir, mapping):
    os.makedirs(config_dir, exist_ok=True)
    with open(_item_alias_path(config_dir), "w", encoding="utf-8") as f:
        json.dump(mapping, f, ensure_ascii=False, indent=2)


def load_dept_alias(config_dir):
    """시드 기본값 + 파일(사용자 편집) 병합. 파일 항목이 우선."""
    merged = seed_dept_alias()
    path = _dept_alias_path(config_dir)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            merged.update(json.load(f))
    return merged


def save_dept_alias(config_dir, mapping):
    os.makedirs(config_dir, exist_ok=True)
    with open(_dept_alias_path(config_dir), "w", encoding="utf-8") as f:
        json.dump(mapping, f, ensure_ascii=False, indent=2)


# 사업명 유사도 매칭 임계값(%). 요구사항: 80% 이상.
SIMILARITY_THRESHOLD = 80

# 소액 임계값(천원). 신규(미확정) 전표 중 건당 |금액| ≤ 이 값이면 (지사×예산과목)별로
# 묶어 "{지사} {예산과목} 집행" 타이틀로 일괄 확정한다. 2,000,000원 = 2,000천원.
SMALL_AMOUNT_THOUSAND = 2000
