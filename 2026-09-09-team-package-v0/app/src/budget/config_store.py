# -*- coding: utf-8 -*-
"""지사구성·예산과목구성·별칭 영속화 — DB 에 산다.

연도별(및 과목은 손익/자본별)로 저장하고, 비어 있으면 시드를 심어 돌려준다.
파일(JSON) 시절에는 개발자 PC 와 배포 환경의 구성이 달랐다 — 그 JSON 이
.gitignore·.dockerignore 양쪽에 걸려 저장소에도 이미지에도 없었기 때문이다.
"""

DEPT_GROUPS = ["본사", "중대형CHP", "소형CHP", "DH"]
SIMUI_THRESHOLD_THOUSAND = 50000

# 연도별 지사 구성 시드.
#
# ⚠ 이 값들은 «그 연도를 처음 만들 때의 출발점»일 뿐이다. 한 번 심은 뒤의 편집은
#   전부 DB 에서 일어나므로, 여기를 고쳐도 이미 심어진 연도에는 영향이 없다.
#
# 지사는 성격이 바뀐다. 양산지사는 2023년 발전설비 건설 중이라 공식적으로 DH 였고
# 준공 후 중대형CHP 가 되었다. 대구·청주도 같은 시기에 소형CHP 에서 올라갔다.
# 연도 축 없는 목록 하나로는 이것을 담을 수 없었고, 그 결과 배포된 앱이 2025년
# 지사그룹별 집계를 1,973,199천원(양산지사 손익 계획) 어긋나게 내고 있었다.
SEED_DEPTS_BY_YEAR = {
    "2023": {
        "본사": ["플랜트기술처", "안전처", "통합운영처", "건설처", "미래사업처"],
        "중대형CHP": ["동탄지사", "화성지사", "파주지사", "광교지사", "판교지사", "삼송지사"],
        "소형CHP": ["수원사업소", "대구지사", "청주지사", "광주전남지사", "강남지사"],
        "DH": ["중앙지사", "고양사업소", "용인지사", "분당사업소", "세종지사",
               "김해사업소", "양산지사", "평택지사"],
    },
    "2025": {
        "본사": ["플랜트기술처", "안전처", "통합운영처", "건설처", "미래사업처"],
        "중대형CHP": ["동탄지사", "화성지사", "파주지사", "광교지사", "판교지사",
                      "삼송지사", "대구지사", "청주지사", "양산지사"],
        "소형CHP": ["수원사업소", "광주전남지사", "강남지사"],
        "DH": ["중앙지사", "고양사업소", "용인지사", "분당사업소", "세종지사",
               "김해사업소", "평택지사"],
    },
}


def _seed_year(year):
    """시드에 없는 연도는 가장 가까운 과거 연도를 쓴다(없으면 가장 이른 연도)."""
    years = sorted(SEED_DEPTS_BY_YEAR)
    past = [y for y in years if y <= str(year)]
    return past[-1] if past else years[0]


def seed_dept_config(year):
    src = SEED_DEPTS_BY_YEAR[_seed_year(year)]
    out = []
    for g in DEPT_GROUPS:
        for name in src[g]:
            out.append({"이름": name, "그룹": g, "포함": True})
    return out


def normalize_dept_config(items):
    """지사 구성의 '포함' 값을 불리언으로 표준화(누락·NaN → True)."""
    return [dict(x, 포함=to_bool(x.get("포함"), True)) for x in items]


def load_dept_config(conn, year):
    """그 해의 지사 구성. 없으면 시드를 심고 그것을 돌려준다.

    읽기가 쓰기를 하는 것이 어색해 보이지만, 이렇게 해야 «그 연도를 처음 연 순간»의
    시드가 DB 에 고정된다. 고정되지 않으면 나중에 시드를 고칠 때 과거 연도의
    분석 결과가 조용히 바뀐다.
    """
    rows = conn.execute(
        "SELECT 이름,그룹,포함 FROM dept_config WHERE year=? ORDER BY 순서,이름",
        (str(year),)).fetchall()
    if not rows:
        return save_dept_config(conn, year, seed_dept_config(year))
    return [{"이름": r[0], "그룹": r[1], "포함": bool(r[2])} for r in rows]


def save_dept_config(conn, year, items):
    """그 해 한 벌을 통째로 갈아 끼운다 — 다른 연도는 건드리지 않는다."""
    items = normalize_dept_config(items)
    conn.execute("DELETE FROM dept_config WHERE year=?", (str(year),))
    for i, x in enumerate(items):
        conn.execute(
            "INSERT INTO dept_config(year,이름,그룹,포함,순서) VALUES(?,?,?,?,?)",
            (str(year), x["이름"], x["그룹"], 1 if x["포함"] else 0, i))
    conn.commit()
    return items


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


def seed_item_config(year, budget):
    """과목 시드. 2023·2025 가 같아 아직 연도로 갈리지 않지만, 호출부가 연도를
    넘기게 해 두면 갈리는 날 여기만 고치면 된다."""
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


def load_item_config(conn, year, budget):
    rows = conn.execute(
        "SELECT 과목,대분류,심의대상,포함,실적반영 FROM item_config"
        " WHERE year=? AND budget=? ORDER BY 순서,과목",
        (str(year), budget)).fetchall()
    if not rows:
        return save_item_config(conn, year, budget, seed_item_config(year, budget))
    return [{"과목": r[0], "대분류": r[1], "심의대상": bool(r[2]),
             "포함": bool(r[3]), "실적반영": bool(r[4])} for r in rows]


def save_item_config(conn, year, budget, items):
    items = normalize_item_config(items)
    conn.execute("DELETE FROM item_config WHERE year=? AND budget=?",
                 (str(year), budget))
    for i, x in enumerate(items):
        conn.execute(
            "INSERT INTO item_config(year,budget,과목,대분류,심의대상,포함,실적반영,순서)"
            " VALUES(?,?,?,?,?,?,?,?)",
            (str(year), budget, x["과목"], x.get("대분류"),
             1 if x["심의대상"] else 0, 1 if x["포함"] else 0,
             1 if x["실적반영"] else 0, i))
    conn.commit()
    return items


# ---------------------------------------------------------------------------
# 정규화 맵 (2단계 실적분석) — 표기 불일치 해소용. config로 편집·영속화 가능.
# ---------------------------------------------------------------------------

# 예산과목 alias: {구 표기 -> 현 표기}. 계정코드가 같은 동일 과목의 연도별
# 명칭 변경만 통일한다. 24년 '수선유지비-열원보완개선및기타'는 25년에
# '수선유지비-열원보완및개선'으로 개명(계정코드 60909009 동일) → 통일.
# (계정코드가 다른 서로 다른 과목은 여기에 넣지 말 것. 구성에 없으면 결측 분류.)
SEED_ITEM_ALIAS = {
    "수선유지비-열원보완개선및기타": "수선유지비-열원보완및개선",
    # 팀 v2 앱(builtin_categories.ACCOUNT_NAME_ALIASES)과 동일 — '건가-' 접두 표기 통일(2026-09-08)
    "건가-외주비-열원정기점검": "외주비-열원정기점검",
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


def _load_alias(conn, 종류, seed):
    """시드 기본값 + DB(사용자 편집) 병합. DB 항목이 우선."""
    merged = dict(seed)
    for 원표기, 정규표기 in conn.execute(
            "SELECT 원표기,정규표기 FROM alias WHERE 종류=?", (종류,)).fetchall():
        merged[원표기] = 정규표기
    return merged


def load_item_alias(conn):
    return _load_alias(conn, "item", seed_item_alias())


def load_dept_alias(conn):
    return _load_alias(conn, "dept", seed_dept_alias())


def save_alias(conn, 종류, mapping):
    """그 종류 전체를 갈아 끼운다. 별칭은 연도 축이 없다 —
    오래된 표기가 몇 년 뒤 자료에 다시 나타나기 때문이다(설계 §3.2)."""
    conn.execute("DELETE FROM alias WHERE 종류=?", (종류,))
    for 원표기, 정규표기 in mapping.items():
        conn.execute("INSERT INTO alias(종류,원표기,정규표기) VALUES(?,?,?)",
                     (종류, 원표기, 정규표기))
    conn.commit()
    return mapping


def save_item_alias(conn, mapping):
    return save_alias(conn, "item", mapping)


def save_dept_alias(conn, mapping):
    return save_alias(conn, "dept", mapping)


# 사업명 유사도 매칭 임계값(%). 요구사항: 80% 이상.
SIMILARITY_THRESHOLD = 80

# 소액 임계값(천원). 신규(미확정) 전표 중 건당 |금액| ≤ 이 값이면 (지사×예산과목)별로
# 묶어 "{지사} {예산과목} 집행" 타이틀로 일괄 확정한다. 2,000,000원 = 2,000천원.
SMALL_AMOUNT_THOUSAND = 2000
