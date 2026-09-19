# -*- coding: utf-8 -*-
"""전망 상태(3·4단계) 영속화 — DB 에 산다. v2 의 `load_*`/`save_*` 자리.

Phase 6-5. 전망 앱 v2 는 정비등급·산출방식·수정값·팩터·고온부품·본사배분 3종·돌발사업
아홉 가지를 CWD 의 CSV 로 두었다. Render `/data` 는 비영속이라 배포마다 사라졌고,
사내 이관 뒤에도 «실행 폴더»라는 숨은 의존이 남는다. `config_store`(PR #12)와 같은
이유로 같은 모양으로 옮긴다.

**전부 전망 기준연도(base_year) 축을 갖는다** (사용자 결정 2026-09-19). v2 는
BASE_YEAR=2026 이 상수여서 그 상태가 사실상 «26년 기준 전망의 가정 한 벌»이었다.
27년 전망을 시작할 때 26년 가정이 덮여 사라지면 «작년 전망과 무엇이 달라졌나»를 볼
길이 없다. 연도별 기준정보에서 배운 것 — 연도 없는 상태를 DB 로 옮기면 나중에 되돌리기
어렵다 — 를 그대로 적용한다.

  base_year : 어느 해에 세운 전망인가(«26년 기준»). 문자열 '2026'.
  연도       : 정비·사업의 대상연도. 2026년 기준 전망 안에 «2027년 TI 정비»가 있다.

반환 DataFrame 은 **v2 의 load_* 가 돌려주던 것과 같은 컬럼·dtype** 이다. 그래야
6-2(`benchmark`)·6-4(`forecast_calc`)에서 옮긴 계산부에 그대로 들어간다.

마지막 절은 6-4 가 남긴 두 훅(`forecast_calc.get_site_display_name` ·
`get_current_site_type`)에 끼울 `dept_config`·`dept_master` 기반 해석기다. v2 는
`site_type_map.csv`·`dept_code_master.csv` 를 읽어 풀었다.
"""
import os

import pandas as pd

from . import config_store, forecast_calc
from . import db as dbm

# ── 표 이름과 v2 컬럼 ────────────────────────────────────────────────────────
TABLES = ("site_grade", "benchmark_method", "benchmark_override", "forecast_factor",
          "forecast_hot_parts", "hq_master", "hq_ratio", "hq_temp", "forecast_surprise")

GRADE_COLS = ["사업장", "연도", "등급"]
METHOD_COLS = ["사업장", "예산과목", "방식"]
OVERRIDE_COLS = ["사업장", "예산과목", "등급", "표준금액"]
FACTOR_COLS = ["팩터명", "연간비율", "활성"]
HOT_PARTS_COLS = ["사업장", "연도", "항목", "금액"]
HQ_MASTER_FIXED_COLS = list(forecast_calc.HQ_MASTER_FIXED_COLS)      # 대분류·중분류·세부내역
HQ_RATIO_COLS = ["사업장", "계약체결금액"]
HQ_TEMP_COLS = ["사업명", "예산과목", "연도", "금액"]
SURPRISE_COLS = ["사업장", "연도", "예산과목", "금액", "사유"]

# v2 load_factors 의 기본값. 처음 읽는 기준연도에 심고 DB 에 고정한다.
DEFAULT_FACTORS = [{"팩터명": "물가상승률", "연간비율": 0.015, "활성": True}]

# v2 가 CWD 에 두던 파일 이름 — import_v2_csv_dir 가 이걸 찾는다.
V2_FILES = {
    "site_grade": "site_year_grade.csv",
    "benchmark_method": "standardization_method_map.csv",
    "benchmark_override": "standardization_overrides.csv",
    "forecast_factor": "longterm_factors.csv",
    "forecast_hot_parts": "hot_parts_plan.csv",
    "hq_master": "hq_master_table.csv",
    "hq_ratio": "hq_allocation_ratio.csv",
    "hq_temp": "hq_temp_projects.csv",
    "forecast_surprise": "surprise_projects.csv",
}


# ── 공통 ─────────────────────────────────────────────────────────────────────
def _s(v):
    """문자열 셀. NaN·None → ''."""
    if v is None or (isinstance(v, float) and v != v):
        return ""
    return str(v).strip()


def _f(v, default=0.0):
    """숫자 셀 → float. 빈 값·NaN → default(None 이면 None)."""
    if v is None or v == "":
        return default
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    return default if f != f else f


def _i(v):
    return int(float(v))


def _b(v):
    return bool(config_store.to_bool(v, True))


def _budget_col(base_year):
    """기준연도 총액 열 이름 — v2 의 «26년예산»을 기준연도에 맞춰 만든다."""
    return f"{int(base_year) % 100:02d}년예산"


def _frame(rows, cols, ints=(), floats=(), bools=()):
    df = pd.DataFrame(rows, columns=cols)
    if df.empty:
        return df
    for c in ints:
        df[c] = df[c].astype(int)
    for c in floats:
        df[c] = df[c].astype(float)
    for c in bools:
        df[c] = df[c].astype(bool)
    return df


def _replace(conn, table, base_year, cols, rows):
    """그 기준연도 한 벌을 통째로 갈아 끼운다 — 다른 기준연도는 건드리지 않는다."""
    conn.execute(f"DELETE FROM {table} WHERE base_year=?", (str(base_year),))
    if rows:
        sql = (f"INSERT INTO {table}(base_year,{','.join(cols)}) "
               f"VALUES({','.join('?' * (len(cols) + 1))})")
        conn.executemany(sql, [(str(base_year), *r) for r in rows])
    conn.commit()


def _select(conn, table, base_year, cols, order):
    return conn.execute(
        f"SELECT {','.join(cols)} FROM {table} WHERE base_year=? ORDER BY {order}",
        (str(base_year),)).fetchall()


# ── 정비등급 이력 (사업장, 연도, 등급) ──────────────────────────────────────
def load_grade_history(conn, base_year) -> pd.DataFrame:
    rows = _select(conn, "site_grade", base_year, GRADE_COLS, "사업장, 연도")
    return _frame(rows, GRADE_COLS, ints=["연도"])


def save_grade_history(conn, base_year, df: pd.DataFrame) -> pd.DataFrame:
    rows = {}
    for _, r in df.iterrows():
        site, grade = _s(r["사업장"]), _s(r["등급"])
        if not site or not grade or _s(r["연도"]) == "":
            continue
        rows[(site, _i(r["연도"]))] = grade          # 같은 키는 뒤의 것이 이긴다
    _replace(conn, "site_grade", base_year, GRADE_COLS,
             [(s, y, g) for (s, y), g in rows.items()])
    return load_grade_history(conn, base_year)


# ── 산출방식 (사업장, 예산과목, 방식) ─────────────────────────────────────────
def load_method_map(conn, base_year) -> pd.DataFrame:
    return _frame(_select(conn, "benchmark_method", base_year, METHOD_COLS, "사업장, 예산과목"),
                  METHOD_COLS)


def save_method_map(conn, base_year, df: pd.DataFrame) -> pd.DataFrame:
    rows = {}
    for _, r in df.iterrows():
        site, acct, method = _s(r["사업장"]), _s(r["예산과목"]), _s(r["방식"])
        if site and acct and method:
            rows[(site, acct)] = method
    _replace(conn, "benchmark_method", base_year, METHOD_COLS,
             [(s, a, m) for (s, a), m in rows.items()])
    return load_method_map(conn, base_year)


# ── 수동 수정값 (사업장, 예산과목, 등급, 표준금액) ──────────────────────────
def load_overrides(conn, base_year) -> pd.DataFrame:
    return _frame(_select(conn, "benchmark_override", base_year, OVERRIDE_COLS,
                          "사업장, 예산과목, 등급"),
                  OVERRIDE_COLS, floats=["표준금액"])


def save_overrides(conn, base_year, df: pd.DataFrame) -> pd.DataFrame:
    rows = {}
    for _, r in df.iterrows():
        site, acct, grade = _s(r["사업장"]), _s(r["예산과목"]), _s(r["등급"])
        amount = _f(r["표준금액"], None)
        if site and acct and grade and amount is not None:
            rows[(site, acct, grade)] = amount
    _replace(conn, "benchmark_override", base_year, OVERRIDE_COLS,
             [(s, a, g, v) for (s, a, g), v in rows.items()])
    return load_overrides(conn, base_year)


# ── 팩터 (팩터명, 연간비율, 활성) ─────────────────────────────────────────────
def load_factors(conn, base_year) -> pd.DataFrame:
    """없으면 v2 기본값(물가상승률 1.5%)을 심고 그것을 돌려준다.

    읽기가 쓰기를 하는 것은 dept_config 와 같은 이유다 — «그 기준연도를 처음 연
    순간»의 시드가 DB 에 고정되어야, 나중에 시드를 고쳐도 과거 기준연도의 전망이
    조용히 바뀌지 않는다.
    """
    rows = _select(conn, "forecast_factor", base_year, FACTOR_COLS, "순서, 팩터명")
    if not rows:
        return save_factors(conn, base_year, pd.DataFrame(DEFAULT_FACTORS))
    return _frame(rows, FACTOR_COLS, floats=["연간비율"], bools=["활성"])


def save_factors(conn, base_year, df: pd.DataFrame) -> pd.DataFrame:
    rows, seen = [], set()
    for _, r in df.iterrows():
        name = _s(r["팩터명"])
        if not name or name in seen:
            continue
        seen.add(name)
        rows.append((name, _f(r["연간비율"]), 1 if _b(r.get("활성", True)) else 0, len(rows)))
    _replace(conn, "forecast_factor", base_year, FACTOR_COLS + ["순서"], rows)
    return load_factors(conn, base_year) if rows else _frame([], FACTOR_COLS)


# ── 고온부품 (사업장, 연도, 항목, 금액) ─────────────────────────────────────
def load_hot_parts(conn, base_year) -> pd.DataFrame:
    return _frame(_select(conn, "forecast_hot_parts", base_year, HOT_PARTS_COLS,
                          "사업장, 연도, 항목"),
                  HOT_PARTS_COLS, ints=["연도"], floats=["금액"])


def save_hot_parts(conn, base_year, df: pd.DataFrame) -> pd.DataFrame:
    rows = {}
    for _, r in df.iterrows():
        site, item = _s(r["사업장"]), _s(r["항목"])
        if site and item and _s(r["연도"]) != "":
            rows[(site, _i(r["연도"]), item)] = _f(r["금액"])
    _replace(conn, "forecast_hot_parts", base_year, HOT_PARTS_COLS,
             [(s, y, i, v) for (s, y, i), v in rows.items()])
    return load_hot_parts(conn, base_year)


# ── 본사 원가분배 마스터 — 넓은 표 ↔ 셀 단위 긴 표 ────────────────────────────
_HQ_CELL_COLS = ["행", "열", "열순서"] + HQ_MASTER_FIXED_COLS + ["금액"]


def load_hq_master(conn, base_year) -> pd.DataFrame:
    """v2 모양(대분류·중분류·세부내역·NN년예산·<지사…>)의 넓은 표로 되돌린다.
    비어 있으면 v2 와 같이 고정 열 + 기준연도 예산 열만 가진 빈 표."""
    cells = _select(conn, "hq_master", base_year, _HQ_CELL_COLS, "행, 열순서")
    if not cells:
        return pd.DataFrame(columns=HQ_MASTER_FIXED_COLS + [_budget_col(base_year)])
    value_cols, rows = [], {}
    for 행, 열, _순서, 대, 중, 세, 금액 in cells:
        if 열 not in value_cols:
            value_cols.append(열)
        row = rows.setdefault(행, {"대분류": 대, "중분류": 중, "세부내역": 세})
        row[열] = 금액
    out = pd.DataFrame([rows[k] for k in sorted(rows)], columns=HQ_MASTER_FIXED_COLS + value_cols)
    for c in value_cols:
        out[c] = out[c].astype(float)
    return out


def save_hq_master(conn, base_year, wide: pd.DataFrame) -> pd.DataFrame:
    value_cols = [c for c in wide.columns if str(c) not in HQ_MASTER_FIXED_COLS]
    rows = []
    for i, (_, r) in enumerate(wide.iterrows()):
        fixed = tuple(_s(r.get(c, "")) for c in HQ_MASTER_FIXED_COLS)
        for j, c in enumerate(value_cols):
            rows.append((i, str(c), j, *fixed, _f(r[c])))
    _replace(conn, "hq_master", base_year, _HQ_CELL_COLS, rows)
    return load_hq_master(conn, base_year)


# ── 본사 배분비율 (사업장, 계약체결금액) ───────────────────────────────────────
def load_hq_ratio(conn, base_year) -> pd.DataFrame:
    return _frame(_select(conn, "hq_ratio", base_year, HQ_RATIO_COLS, "사업장"),
                  HQ_RATIO_COLS, floats=["계약체결금액"])


def save_hq_ratio(conn, base_year, df: pd.DataFrame) -> pd.DataFrame:
    rows = {}
    for _, r in df.iterrows():
        site = _s(r["사업장"])
        if site:
            rows[site] = _f(r["계약체결금액"])
    _replace(conn, "hq_ratio", base_year, HQ_RATIO_COLS, list(rows.items()))
    return load_hq_ratio(conn, base_year)


# ── 본사 일시적 사업 (사업명, 예산과목, 연도, 금액) — 자연키 없음, id 순 ─────
def load_hq_temp_projects(conn, base_year) -> pd.DataFrame:
    return _frame(_select(conn, "hq_temp", base_year, HQ_TEMP_COLS, "id"),
                  HQ_TEMP_COLS, ints=["연도"], floats=["금액"])


def save_hq_temp_projects(conn, base_year, df: pd.DataFrame) -> pd.DataFrame:
    rows = [(_s(r["사업명"]), _s(r["예산과목"]), _i(r["연도"]), _f(r["금액"]))
            for _, r in df.iterrows() if _s(r["사업명"]) and _s(r["연도"]) != ""]
    _replace(conn, "hq_temp", base_year, HQ_TEMP_COLS, rows)
    return load_hq_temp_projects(conn, base_year)


def append_hq_temp_project(conn, base_year, 사업명, 예산과목, 연도, 금액):
    conn.execute(
        "INSERT INTO hq_temp(base_year,사업명,예산과목,연도,금액) VALUES(?,?,?,?,?)",
        (str(base_year), _s(사업명), _s(예산과목), _i(연도), _f(금액)))
    conn.commit()


# ── 지사별 돌발사업 (사업장, 연도, 예산과목, 금액, 사유) — 자연키 없음, id 순 ──
def load_surprise_projects(conn, base_year) -> pd.DataFrame:
    return _frame(_select(conn, "forecast_surprise", base_year, SURPRISE_COLS, "id"),
                  SURPRISE_COLS, ints=["연도"], floats=["금액"])


def save_surprise_projects(conn, base_year, df: pd.DataFrame) -> pd.DataFrame:
    rows = [(_s(r["사업장"]), _i(r["연도"]), _s(r["예산과목"]), _f(r["금액"]), _s(r.get("사유", "")))
            for _, r in df.iterrows() if _s(r["사업장"]) and _s(r["연도"]) != ""]
    _replace(conn, "forecast_surprise", base_year, SURPRISE_COLS, rows)
    return load_surprise_projects(conn, base_year)


def append_surprise_project(conn, base_year, 사업장, 연도, 예산과목, 금액, 사유):
    conn.execute(
        "INSERT INTO forecast_surprise(base_year,사업장,연도,예산과목,금액,사유) VALUES(?,?,?,?,?,?)",
        (str(base_year), _s(사업장), _i(연도), _s(예산과목), _f(금액), _s(사유)))
    conn.commit()


# ── 기준연도 관리 ─────────────────────────────────────────────────────────────
def list_base_years(conn) -> list:
    """상태가 하나라도 있는 기준연도들(정렬)."""
    years = set()
    for t in TABLES:
        years.update(r[0] for r in conn.execute(f"SELECT DISTINCT base_year FROM {t}"))
    return sorted(years)


def base_year_is_untouched(conn, base_year) -> bool:
    """그 기준연도에 사람이 쓴 것이 없는가. 읽기만으로 심기는 팩터 시드는 «손댄 것»이 아니다 —
    화면을 한 번 열었다는 이유로 연도 복사가 막히면 안 된다(copy-year 409 가드와 같은 논리)."""
    for t in TABLES:
        if t == "forecast_factor":
            continue
        n = conn.execute(f"SELECT COUNT(*) FROM {t} WHERE base_year=?", (str(base_year),)).fetchone()[0]
        if n:
            return False
    rows = _select(conn, "forecast_factor", base_year, FACTOR_COLS, "순서")
    if not rows:
        return True
    seed = [(d["팩터명"], d["연간비율"], 1 if d["활성"] else 0) for d in DEFAULT_FACTORS]
    return [(r[0], float(r[1]), int(r[2])) for r in rows] == seed


# 표별 «base_year 를 뺀» 컬럼 — copy_base_year 가 INSERT…SELECT 로 그대로 복제한다.
_COPY_COLS = {
    "site_grade": GRADE_COLS,
    "benchmark_method": METHOD_COLS,
    "benchmark_override": OVERRIDE_COLS,
    "forecast_factor": FACTOR_COLS + ["순서"],
    "forecast_hot_parts": HOT_PARTS_COLS,
    "hq_master": _HQ_CELL_COLS,
    "hq_ratio": HQ_RATIO_COLS,
    "hq_temp": HQ_TEMP_COLS,
    "forecast_surprise": SURPRISE_COLS,
}


def copy_base_year(conn, from_year, to_year):
    """한 기준연도의 상태 아홉 벌을 통째로 다른 기준연도로 복사한다. 대상에 있던 것은
    먼저 지운다 — 두 해가 섞이면 어느 가정으로 세운 전망인지 알 수 없다."""
    if str(from_year) == str(to_year):
        raise ValueError("같은 기준연도로는 복사할 수 없습니다.")
    for t in TABLES:
        cols = ",".join(_COPY_COLS[t])
        order = " ORDER BY id" if t in ("hq_temp", "forecast_surprise") else ""
        conn.execute(f"DELETE FROM {t} WHERE base_year=?", (str(to_year),))
        conn.execute(f"INSERT INTO {t}(base_year,{cols}) SELECT ?,{cols} FROM {t} WHERE base_year=?{order}",
                     (str(to_year), str(from_year)))
    conn.commit()


# ── v2 CSV 이관 ───────────────────────────────────────────────────────────────
_SAVERS = {
    "site_grade": save_grade_history,
    "benchmark_method": save_method_map,
    "benchmark_override": save_overrides,
    "forecast_factor": save_factors,
    "forecast_hot_parts": save_hot_parts,
    "hq_master": save_hq_master,
    "hq_ratio": save_hq_ratio,
    "hq_temp": save_hq_temp_projects,
    "forecast_surprise": save_surprise_projects,
}


def import_v2_csv_dir(conn, base_year, directory) -> dict:
    """v2 가 CWD 에 두던 CSV 를 한 기준연도로 들여온다. 있는 파일만, {표: 행수}.

    동료 PC 의 전망 앱 실행 폴더를 가리키면 그 상태가 그대로 넘어온다. 저장소의 v2 코드는
    6-8 에서 사라졌지만 이 함수는 남는다 — 동료 PC 에는 여전히 그 CSV 가 있고, 읽는 데
    v2 코드가 필요하지 않기 때문이다. 지사 컬럼은 v2 표시명 그대로 들어온다
    (v2 site_type_map 의 표시명은 budget_app 의 지사 이름과 동일하다 — 실측 2026-09-19).
    """
    report = {}
    for table, fname in V2_FILES.items():
        path = os.path.join(directory, fname)
        if not os.path.exists(path):
            continue
        df = pd.read_csv(path, dtype={"사업장": str} if table != "hq_master" else None)
        saved = _SAVERS[table](conn, base_year, df)
        report[table] = int(len(saved))
    return report


# ── 지사 해석기 — 6-4 가 남긴 두 훅에 끼운다 ────────────────────────────────
def _norm_code(code) -> str:
    s = _s(code)
    return s[:-2] if s.endswith(".0") else s


def _best_prefix_match(codes, query: str, min_len: int = 3):
    """앞자리를 가장 많이 공유하는 코드. v2 와 같이 자릿수는 무관(손익센터 4자리 ↔
    부서코드 6~7자리), 최소 3자리는 같아야 한다. 동률이면 사전순 앞."""
    best, best_len = None, min_len - 1
    for c in sorted(codes):
        n = 0
        for a, b in zip(c, query):
            if a != b:
                break
            n += 1
        if n > best_len:
            best, best_len = c, n
    return best


def make_site_display_resolver(conn, year):
    """사업장/부서 코드 → 지사명. v2 `mapping_config.get_site_display_name` 의 자리.

    v2 는 site_type_map.csv(표시명) → dept_code_master.csv(부서코드) → 접두사 매칭 →
    «미매핑(NNN0번대)» 순이었다. 여기서는 표시명 층이 dept_config(그 해 지사 이름)이고
    부서코드 층이 dept_master(그 해 마스터, 없으면 가장 가까운 과거 연도)다.
    """
    names = {x["이름"] for x in config_store.load_dept_config(conn, year)}
    code_map = dbm.load_deptcode_map(conn, year)

    def resolve(code) -> str:
        s = _norm_code(code)
        if not s:
            return _s(code)
        if s in names:
            return s
        if s in code_map:
            return code_map[s]
        if s.isdigit():
            alt = _best_prefix_match(code_map.keys(), s)
            if alt is not None:
                return code_map[alt]
            if len(s) == 4:
                return f"미매핑({s[:3]}0번대)"
        return s

    return resolve


def make_site_type_resolver(conn, year):
    """지사명 → 그 해의 지사그룹(본사·중대형CHP·소형CHP·DH). 없으면 «미매핑»."""
    groups = {x["이름"]: x["그룹"] for x in config_store.load_dept_config(conn, year)}
    return lambda site: groups.get(_s(site), "미매핑")


def bind_site_resolvers(conn, year):
    """forecast_calc 의 두 훅을 이 해의 dept_config·dept_master 로 갈아 끼운다.
    계산을 돌리기 직전에 한 번 부른다(API 층, 6-6)."""
    forecast_calc.get_site_display_name = make_site_display_resolver(conn, year)
    forecast_calc.get_current_site_type = make_site_type_resolver(conn, year)
