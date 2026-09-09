"""
민감할 수 있는 매핑 정보(사업장코드->지사유형, 예산과목->손익/자본)를
로컬 CSV로 관리한다. 이 파일들은 .gitignore에 포함해 절대 공유되지 않도록 한다.

사업장->지사유형은 시간에 따라 바뀔 수 있으므로(예: 소형CHP -> 중대형CHP 개편),
'적용시작연도' 기준의 이력 테이블로 관리한다.
"""
import os
import pandas as pd

SITE_TYPE_PATH = "site_type_map.csv"       # 컬럼: 사업장, 표시명, 지사유형, 적용시작연도
ACCOUNT_CAT_PATH = "account_category_map.csv"  # 컬럼: 계정과목, 손익자본구분

SITE_TYPE_OPTIONS = ["중대형CHP", "소형CHP", "DH", "본사"]
CATEGORY_OPTIONS = ["손익", "자본"]

# 손익예산실적집계표(양식2)에서 확인된 기본 지사유형 매핑. 언제든 '설정' 화면에서 수정/추가 가능.
# 실제 '사업 영역' 값이 이름이 아니라 코드(예: 3070)라면, 표시명 컬럼에 실제 이름을 채워주세요.
DEFAULT_SITE_TYPES = {
    "동탄지사": "중대형CHP", "화성지사": "중대형CHP", "파주지사": "중대형CHP", "광교지사": "중대형CHP",
    "판교지사": "중대형CHP", "삼송지사": "중대형CHP", "대구지사": "중대형CHP", "청주지사": "중대형CHP",
    "수원사업소": "소형CHP", "광주전남지사": "소형CHP", "강남지사": "소형CHP",
    "중앙지사": "DH", "고양사업소": "DH", "용인지사": "DH", "분당사업소": "DH",
    "세종지사": "DH", "김해사업소": "DH", "양산지사": "DH", "평택지사": "DH",
    "플랜트기술처": "본사", "안전처": "본사", "통합운영처": "본사", "건설처": "본사", "미래사업처": "본사",
}


def _seed_default_site_map() -> pd.DataFrame:
    return pd.DataFrame([
        {"사업장": site, "표시명": site, "지사유형": t, "적용시작연도": 1900} for site, t in DEFAULT_SITE_TYPES.items()
    ])


# get_site_display_name()/get_current_site_type()가 실적 데이터 수천 행에 .apply()로 호출되면서
# 매 행마다 이 CSV를 다시 읽어들이는 게 실제 성능 병목이었다(대시보드 첫 계산이 오래 걸리는 원인).
# 파일 내용이 안 바뀌었으면(경로+mtime 동일) 다시 읽지 않도록 캐시한다.
_site_type_map_cache = {}


def load_site_type_map() -> pd.DataFrame:
    if os.path.exists(SITE_TYPE_PATH):
        cache_key = (os.path.abspath(SITE_TYPE_PATH), os.path.getmtime(SITE_TYPE_PATH))
        cached = _site_type_map_cache.get(cache_key)
        if cached is not None:
            return cached.copy()
        df = pd.read_csv(SITE_TYPE_PATH, dtype={"사업장": str})
        if "적용시작연도" not in df.columns:
            df["적용시작연도"] = 1900
        if "표시명" not in df.columns:
            df["표시명"] = df["사업장"]
        _site_type_map_cache.clear()  # 이전 버전은 버리고 최신 것만 보관(무한정 쌓이지 않게)
        _site_type_map_cache[cache_key] = df
        return df.copy()
    # 파일이 없으면 실제 조직 구조 기반 기본값으로 시작 (필요시 '설정'에서 수정)
    seed = _seed_default_site_map()
    save_site_type_map(seed)
    return seed


def save_site_type_map(df: pd.DataFrame):
    df.to_csv(SITE_TYPE_PATH, index=False)
    _site_type_map_cache.clear()  # 저장 직후에도 mtime이 바뀌지만, 명시적으로 즉시 무효화해둔다


def load_account_category_map() -> pd.DataFrame:
    if os.path.exists(ACCOUNT_CAT_PATH):
        return pd.read_csv(ACCOUNT_CAT_PATH)
    return pd.DataFrame(columns=["계정과목", "손익자본구분"])


def save_account_category_map(df: pd.DataFrame):
    df.to_csv(ACCOUNT_CAT_PATH, index=False)


def _code_prefix3(code) -> str:
    """4자리 숫자 코드(예: '2021', '3070.0')의 앞 3자리를 반환. 4자리 숫자가 아니면 None."""
    s = str(code).strip()
    if s.endswith(".0"):
        s = s[:-2]
    if s.isdigit() and len(s) == 4:
        return s[:3]
    return None


def _find_by_prefix(codes: list, target_code) -> str:
    """
    codes(등록된 사업장 코드 목록) 중에서, target_code와 앞 3자리가 같은 코드를 찾아 반환한다.
    (예: 등록된 코드가 '2020'이고 target이 '2021'이면 '2020'을 반환 - 같은 지사로 취급)
    못 찾으면 None.
    """
    target_prefix = _code_prefix3(target_code)
    if target_prefix is None:
        return None
    for c in codes:
        if _code_prefix3(c) == target_prefix:
            return c
    return None


def _normalize_digits(code) -> str | None:
    """숫자 코드를 비교용 문자열로 정규화한다(엑셀이 붙인 '.0' 제거). 숫자가 아니거나 3자리 미만이면 None."""
    if code is None:
        return None
    s = str(code).strip()
    if s.endswith(".0"):
        s = s[:-2]
    return s if s.isdigit() and len(s) >= 3 else None


def _common_prefix_len(a: str, b: str) -> int:
    n = 0
    for x, y in zip(a, b):
        if x != y:
            break
        n += 1
    return n


def _best_prefix_match(codes: list, query_code) -> str | None:
    """
    codes(자릿수가 다를 수 있는 코드 목록, 예: 6~7자리 부서코드) 중에서 query_code(예: 4자리 손익센터)와
    앞자리를 가장 많이 공유하는 코드를 찾는다. 최소 앞 3자리 이상 같아야 인정하며,
    (예: 손익센터 '4020'은 부서코드 '4020001'과 4자리가 모두 일치하므로,
    같은 '402' 접두만 공유하는 '4022004'보다 우선 선택된다.)
    못 찾으면 None.
    """
    q = _normalize_digits(query_code)
    if q is None:
        return None
    best_code, best_len = None, 2  # 3자리 미만 일치는 인정하지 않음
    for code in codes:
        c = _normalize_digits(code)
        if c is None:
            continue
        n = _common_prefix_len(q, c)
        if n > best_len:
            best_len, best_code = n, code
    return best_code


def _resolve_site_type(site_map: pd.DataFrame) -> dict:
    """사업장별로 (적용시작연도, 지사유형) 목록을 연도 오름차순으로 정리해서 반환.

    '표시명'을 아직 채우지 않은 placeholder 행(설정 화면의 '사업장 코드 가져오기'로 등록만 하고
    실제 이름/유형을 확인하지 않은 경우 - 표시명이 사업장 코드 그대로 남아있음)은 실제로 검증된
    매핑이 아니므로 제외한다. 이 행을 그대로 두면, 예를 들어 '세종지사'(DH) 코드에 우연히 잘못된
    기본값(예: 중대형CHP)이 채워진 placeholder가 있을 때 실제 지사유형 대신 그 값이 그대로
    쓰여버리는 문제가 생긴다(get_site_display_name()은 이미 placeholder를 건너뛰고 있었다)."""
    df = site_map
    if "표시명" in df.columns:
        is_placeholder = df.apply(lambda r: _is_unfilled_placeholder(r["사업장"], r.get("표시명")), axis=1)
        df = df[~is_placeholder]
    lookup = {}
    for site, group in df.groupby("사업장"):
        rows = group.sort_values("적용시작연도")[["적용시작연도", "지사유형"]].values.tolist()
        lookup[site] = rows
    return lookup


def get_site_type(lookup: dict, site: str, year: int) -> str:
    rows = lookup.get(site)
    if not rows:
        # 정확히 등록된 코드가 없으면, 앞 3자리가 같은 등록된 코드를 같은 지사로 취급한다.
        alt = _find_by_prefix(list(lookup.keys()), site)
        rows = lookup.get(alt) if alt else None
    if not rows:
        return "미매핑"
    applicable = [t for start, t in rows if start <= year]
    return applicable[-1] if applicable else "미매핑"


def get_current_site_type(site: str) -> str:
    """사업장의 '현재(가장 최근에 적용된)' 지사유형을 반환한다.
    행별 '연도'(전기일)가 없는 데이터(예: '투자유형 예측 테스트' 업로드 결과)에 사용한다.

    입력이 원시 코드(예: 손익센터 4자리)일 때, 그 코드로 직접 등록된 이력이 없으면 표시명으로
    변환한 뒤 다시 한 번 찾아본다 - 예: '4040'이 site_type_map에 직접 등록돼 있지 않아도
    dept_code_master 등을 통해 '세종지사'로 풀리면 그 이름으로 등록된 유형(DH)을 찾는다."""
    site_map = load_site_type_map()
    if site_map.empty:
        return "미매핑"
    lookup = _resolve_site_type(site_map)
    direct = get_site_type(lookup, site, 9999)
    if direct != "미매핑":
        return direct
    resolved_name = get_site_display_name(site)
    if resolved_name == site:
        return "미매핑"
    return get_site_type(lookup, resolved_name, 9999)


DEPT_MASTER_PATH = "dept_code_master.csv"  # 예산계획 업로드 시 저장되는 부서코드 마스터 (부서코드, 부서명, 처.지사)

# get_site_display_name()도 실적 데이터에 .apply()로 행마다 호출되므로, site_type_map과 같은
# 이유로 dept_code_master.csv도 mtime 기준으로 캐시한다.
_dept_master_cache = {}


def _load_dept_master_cached() -> pd.DataFrame | None:
    if not os.path.exists(DEPT_MASTER_PATH):
        return None
    cache_key = (os.path.abspath(DEPT_MASTER_PATH), os.path.getmtime(DEPT_MASTER_PATH))
    cached = _dept_master_cache.get(cache_key)
    if cached is not None:
        return cached.copy()
    try:
        dept = pd.read_csv(DEPT_MASTER_PATH, dtype=str)
    except Exception:
        return None
    _dept_master_cache.clear()
    _dept_master_cache[cache_key] = dept
    return dept.copy()


def _normalize_code_for_lookup(code) -> list:
    """'3070.0', '3070', ' 3070 ' 등 다양한 표기를 비교 가능하게 후보 목록으로 만든다"""
    s = str(code).strip()
    candidates = {s}
    if s.endswith(".0"):
        candidates.add(s[:-2])
    return list(candidates)


def _is_unfilled_placeholder(site_code, display_name) -> bool:
    """
    '설정' 화면의 '사업장 코드 가져오기'로 등록만 되고 아직 실제 이름을 채우지 않은
    placeholder인지 확인한다 (사업장 값 자체가 숫자 코드이고, 표시명이 그 코드 그대로인 경우).
    이런 placeholder는 아직 '등록된 이름'으로 치지 않고 dept_code_master 등 다른 소스를 먼저 시도한다.
    """
    code_digits = _normalize_digits(site_code)
    if code_digits is None:
        return False
    return _normalize_digits(display_name) == code_digits


def get_site_display_name(code) -> str:
    """
    사업장/부서 코드(예: 3070.0)를 실제 부서명/지사명으로 변환한다.
    1) site_type_map.csv의 '표시명' 컬럼 (설정 화면에서 직접 입력한 값) - 정확히 일치
       (단, '가져오기'로 등록만 되고 표시명을 코드 그대로 안 채운 placeholder는 건너뛴다)
    2) site_type_map.csv에 정확히 없어도, 4자리 코드의 앞 3자리가 같은 등록된 코드가 있으면 같은 지사로 취급
    3) dept_code_master.csv (예산계획에서 저장된 부서코드 마스터, 보통 6~7자리) - 정확히 일치
    4) dept_code_master.csv에도 정확히 없으면, 앞자리를 가장 많이 공유하는 부서코드를 같은 사업소로 취급
       (실적의 손익센터는 4자리, 예산의 부서코드는 6~7자리로 자릿수가 다를 수 있어 최소 3자리만 같아도 인정)
    5) 그래도 못 찾았는데 4자리 숫자 코드라면, "미매핑({앞3자리}0번대)"로 정규화해 같은 접두사끼리는
       최소한 하나로 묶이게 한다 (예: '2020'/'2021'/'2023' → 모두 "미매핑(2020번대)").
    그 외(4자리 숫자가 아닌 값 등)는 원래 코드값을 그대로 반환한다.
    """
    candidates = _normalize_code_for_lookup(code)
    norm_candidates = [c.replace(".0", "") if c.endswith(".0") else c for c in candidates]

    site_map = load_site_type_map()
    if not site_map.empty and "사업장" in site_map.columns:
        site_map = site_map.copy()
        site_map["_norm"] = site_map["사업장"].astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
        match = site_map[site_map["_norm"].isin(norm_candidates)]
        if not match.empty:
            row = match.iloc[0]
            name = row.get("표시명")
            if pd.notna(name) and str(name).strip() and not _is_unfilled_placeholder(row["사업장"], name):
                return str(name)

        # 정확히 일치하는 코드가 없으면, 앞 3자리가 같은 등록된 코드를 찾아 같은 지사로 취급
        registered_codes = site_map["_norm"].tolist()
        alt_code = _find_by_prefix(registered_codes, code)
        if alt_code is not None:
            alt_match = site_map[site_map["_norm"] == alt_code]
            if not alt_match.empty:
                row = alt_match.iloc[0]
                name = row.get("표시명")
                if pd.notna(name) and str(name).strip() and not _is_unfilled_placeholder(row["사업장"], name):
                    return str(name)

    dept = _load_dept_master_cached()
    if dept is not None:
        if "부서코드" in dept.columns:
            dept["_norm"] = dept["부서코드"].astype(str).str.strip().str.replace(r"\.0$", "", regex=True)

            def _dept_name(row) -> str | None:
                # '처, 지사'가 지사/처 단위의 이름이라 종합표가 인식하는 24개 지사명과 맞다.
                # '부서명'은 그 안의 세부 부서(예: '동탄지사 고객지원부')라 더 잘게 쪼개져 있어,
                # '처, 지사'가 비어있을 때만 대신 쓴다.
                name = row.get("처, 지사") or row.get("처.지사") or row.get("부서명")
                return str(name) if pd.notna(name) and str(name).strip() else None

            match = dept[dept["_norm"].isin(norm_candidates)]
            if not match.empty:
                name = _dept_name(match.iloc[0])
                if name:
                    return name

            # 정확히 일치하는 부서코드가 없으면, 앞자리를 가장 많이 공유하는 등록된 부서코드를 찾아
            # 같은 사업소로 취급한다. 실적의 손익센터(4자리)와 예산의 부서코드(6~7자리)는 자릿수가
            # 다르므로, 자릿수가 같아야 하는 _find_by_prefix 대신 자릿수 무관 매칭을 사용한다.
            alt_code = _best_prefix_match(dept["_norm"].tolist(), code)
            if alt_code is not None:
                alt_match = dept[dept["_norm"] == alt_code]
                if not alt_match.empty:
                    name = _dept_name(alt_match.iloc[0])
                    if name:
                        return name

    # 어느 마스터에도 등록되지 않은 4자리 숫자 코드는, 앞 3자리가 같으면 서로 같은 지사로 묶는다.
    # 아직 실제 표시명은 없지만 최소한 같은 그룹으로는 집계되며, '설정'에서 등록하면 그 이름이 우선 적용된다.
    prefix = _code_prefix3(code)
    if prefix is not None:
        return f"미매핑({prefix}0번대)"

    return str(code)


def _site_type_with_fallback(lookup: dict, site: str, year: int) -> str:
    """원시 코드로 직접 등록된 이력이 없으면 표시명으로 변환해 다시 찾아본다
    (get_current_site_type()과 같은 폴백 - 자세한 설명은 그 함수 docstring 참고)."""
    direct = get_site_type(lookup, site, year)
    if direct != "미매핑":
        return direct
    resolved_name = get_site_display_name(site)
    if resolved_name == site:
        return "미매핑"
    return get_site_type(lookup, resolved_name, year)


def apply_mappings(df: pd.DataFrame) -> pd.DataFrame:
    """분류 확정 데이터에 지사유형(연도별 이력 반영), 손익자본구분 컬럼을 매핑해서 붙인다."""
    from builtin_categories import get_category_for_account

    out = df.copy()
    out["사업장"] = out["사업장"].astype(str)

    site_map = load_site_type_map()
    if not site_map.empty:
        lookup = _resolve_site_type(site_map)
        out["지사유형"] = out.apply(lambda r: _site_type_with_fallback(lookup, r["사업장"], int(r["연도"])), axis=1)
    else:
        out["지사유형"] = "미매핑"

    out["손익자본구분"] = out["계정과목"].apply(get_category_for_account)

    return out