# -*- coding: utf-8 -*-
"""예산 표준화(3단계) — 과년도 실적을 지사×예산과목×정비등급으로 통계 내어 표준금액을 만든다.

Phase 6-2. 전망 앱 v2 `standardization.py` 의 **계산부**를 그대로 옮긴 것이다.
함수 이름·인자·반환 형태를 v2 와 같게 두었고, v2 테스트 15개를 함께 옮겨
`tests/test_benchmark.py` 에서 돌린다 — «같은 계산»이 말이 아니라 실행으로 남는다.

옮기지 않은 것: 파일 IO(`load_*`/`save_*`)와 엑셀 import. 상태는 6-5 에서 DB 표로
가고, 엑셀 파서는 지사 표시명 매핑이 `dept_config` 로 바뀐 뒤에 옮긴다. 한 번에
둘을 바꾸면 깨졌을 때 어느 쪽 탓인지 모른다.

과목 집합과 별칭은 v2 의 `builtin_categories` 상수가 아니라 budget_app 구성에서 온다.
두 집합의 차이는 세 과목뿐이고(budget_app 에만 수선유지비-비저장품(보수자재)·
수선유지비-소모품(자재공기구), v2 에만 외주비-기타) **셋 다 실제 ERP 자료에 0건**이라
결과가 달라지지 않는다(실측 2026-09-19, zrfm2 43,840행 · 과목 15종). 별칭은 두 앱이 동일하다.
"""
import re

import pandas as pd

from . import config_store, normalize

PROFIT_LOSS_ACCOUNTS = {x["과목"] for x in config_store.SEED_ITEMS["손익"]}
CAPITAL_ACCOUNTS = {x["과목"] for x in config_store.SEED_ITEMS["자본"]}
ALL_ACCOUNTS = PROFIT_LOSS_ACCOUNTS | CAPITAL_ACCOUNTS

METHOD_OPTIONS = ["등급별 평균", "최근실적", "3개년 평균", "5개년 평균"]
# 산정 규칙(benchmark_rule)에서만 고르는 방식 — 예산표준화 V3 엑셀이 실제로 쓰는 7가지를 담는다.
#   등급별 최근실적 : 그 등급을 가장 최근에 시행한 해의 실적(엑셀 «등급별»의 기본형)
#   지정연도 평균   : 연도목록의 실적 평균(없는 해는 0) — 참조지사를 주면 그 지사의 실적
#   최대값          : 연도목록(없으면 전체)의 최대
#   예산 대체       : 기준연도 계획본 금액(실적이 쌓이기 전의 신규 지사)
#   등급 차용       : 참조지사·참조등급의 표준금액(유사 용량 지사, 같은 지사의 다른 등급)
#   직접 입력       : 조정액을 그대로 표준금액으로
RULE_METHODS = METHOD_OPTIONS + ["등급별 최근실적", "지정연도 평균", "최대값", "예산 대체", "등급 차용", "직접 입력"]
DEFAULT_METHOD = "등급별 평균"

# 자본 «기계장치» 중 정기(LTSA/CRI) 성격의 투자유형세부는 등급별 표준화에서 뺀다
# — 연도별 집행계획으로 따로 산정하기 때문이다(v2 표준화방향 시트).
LTSA_LIKE_DETAILS = {"LTSA", "CRI"}

DEFAULT_WINDOW = 3          # 학습 기간 기본값. 백테스트 2021~2025: 2년 45.3% · 3년 42.8% · 5년 46.7% · 10년 52.6%(칸별)


def recent_window(actuals_df: pd.DataFrame, n_years) -> pd.DataFrame:
    """실적이 있는 해 중 최근 n 개년만. n 이 없거나 0 이하면 전부."""
    if actuals_df.empty or not n_years or int(n_years) <= 0:
        return actuals_df
    keep = sorted(actuals_df["연도"].unique())[-int(n_years):]
    return actuals_df[actuals_df["연도"].isin(keep)]


CURRENT_YEAR_FALLBACK = 2025      # 정비등급 이력이 하나도 없을 때만 쓰는 기본값


def reference_year_for_undated(grade_history_df: pd.DataFrame) -> int:
    """연도 정보가 없는 테스트모드 업로드분(예: '투자유형 예측 테스트' 결과)에 붙일 '현재' 연도.
    정비등급 이력의 가장 최근 연도를 쓴다 - 임의의 값(예: 9999)을 쓰면 엑셀 양식의 실제 연도 칸과
    매칭이 안 돼 연도별 실적 표가 비어 보이는 문제가 있다. 표준화·중장기예산 테스트 모드가 공유해서 쓴다."""
    if grade_history_df.empty:
        return CURRENT_YEAR_FALLBACK
    return int(grade_history_df["연도"].max())


def get_method_dict(method_map: pd.DataFrame) -> dict:
    """{(사업장, 예산과목): 방식} 딕셔너리로 변환. 없는 조합은 호출측에서 DEFAULT_METHOD를 쓰면 된다."""
    if method_map.empty:
        return {}
    return {(r["사업장"], r["예산과목"]): r["방식"] for _, r in method_map.iterrows()}


def _apply_method(yearly: pd.Series, grade: str, grade_by_year: dict, method: str) -> tuple:
    """yearly: 연도(index)->금액. 반환: (표준금액, 비고)"""
    if yearly.empty:
        return 0.0, "실적없음"

    if method == "최근실적":
        latest_year = yearly.index.max()
        return float(yearly.loc[latest_year]), "최근실적"

    if method == "3개년 평균":
        recent = yearly.sort_index().iloc[-3:]
        return float(recent.mean()), "3개년 평균"

    if method == "5개년 평균":
        recent = yearly.sort_index().iloc[-5:]
        return float(recent.mean()), "5개년 평균"

    if method == "등급별 최근실적":
        matching_years = [y for y, g in grade_by_year.items() if g == grade and y in yearly.index]
        if matching_years:
            return float(yearly.loc[max(matching_years)]), f"등급별 최근실적({max(matching_years)})"
        latest_year = yearly.index.max()
        return float(yearly.loc[latest_year]), "등급별 최근실적(해당등급 실적없음 - 최근실적 대체)"

    # 기본: 등급별 평균 - 이 등급이 적용된 연도만 평균, 없으면 전체 평균으로 대체
    matching_years = [y for y, g in grade_by_year.items() if g == grade and y in yearly.index]
    if matching_years:
        return float(yearly.loc[matching_years].mean()), "등급별 평균"
    return float(yearly.mean()), "등급별 평균(해당등급 실적없음 - 전체평균 대체)"


ETA_SQUARED_THRESHOLD = 0.3


CV_THRESHOLD = 0.15


def recommend_method(yearly: pd.Series, grade_by_year: dict) -> tuple:
    """항목별 실적 패턴(연도 수, 변동성, 등급별 편차)을 통계적으로 분석해 산출방식을 추천한다.
    사람이 미리 방식을 정해둔 항목이 아닐 때 기본값으로 쓰인다.

    - 등급별로 나눴을 때 그룹 간 평균 차이가 전체 분산의 상당 부분을 설명하면(η² 기준)
      '등급별 평균'을 추천한다 - 실제로 등급이 금액을 가르는 경우다.
    - 등급 차이가 뚜렷하지 않아도 연도별 변동이 작으면 '최근실적'으로 충분하다고 본다.
    - 등급도 안 갈리고 변동도 있으면, 데이터가 충분할 때(5개년 이상) '5개년 평균'으로
      완만화하고, 데이터가 적으면 '3개년 평균'을 추천한다.

    반환: (방식, 추천사유)
    """
    n_years = len(yearly)
    if n_years == 0:
        return DEFAULT_METHOD, "실적 없음"
    if n_years == 1:
        return "최근실적", "실적이 1개년뿐이라 그대로 사용"

    mean = yearly.mean()
    std = yearly.std(ddof=0)
    cv = (std / mean) if mean else 0.0

    groups = {}
    for year, amount in yearly.items():
        grade = grade_by_year.get(year)
        if grade is not None:
            groups.setdefault(grade, []).append(amount)
    multi_grade_groups = {g: v for g, v in groups.items() if v}

    eta_sq = None
    if len(multi_grade_groups) >= 2:
        ss_total = ((yearly - mean) ** 2).sum()
        if ss_total > 0:
            ss_between = sum(len(v) * (sum(v) / len(v) - mean) ** 2 for v in multi_grade_groups.values())
            eta_sq = ss_between / ss_total

    if eta_sq is not None and eta_sq >= ETA_SQUARED_THRESHOLD:
        return "등급별 평균", f"등급별 그룹 간 편차가 뚜렷함(설명력 {eta_sq*100:.0f}%) - 등급별로 나눠서 계산"

    if cv < CV_THRESHOLD:
        return "최근실적", f"연도별 변동이 작음(변동계수 {cv*100:.0f}%) - 최근실적만으로 충분"

    if n_years >= 5:
        return "5개년 평균", f"등급 차이는 뚜렷하지 않고 변동성이 있음(변동계수 {cv*100:.0f}%) - 5개년 평균으로 완만화"

    return "3개년 평균", f"데이터가 {n_years}개년뿐이고 변동성이 있음(변동계수 {cv*100:.0f}%) - 3개년 평균"


def get_current_grade(site: str, grade_history_df: pd.DataFrame):
    """해당 지사의 정비등급 이력 중 가장 최근 연도의 등급(없으면 None).
    연도 정보가 없는 데이터(예: '투자유형 예측 테스트' 업로드분)에 임시 등급을 붙일 때 쓴다."""
    site_hist = grade_history_df[grade_history_df["사업장"] == site]
    if site_hist.empty:
        return None
    latest_year = site_hist["연도"].max()
    return site_hist.loc[site_hist["연도"] == latest_year, "등급"].iloc[0]


def has_ltsa_detail(actuals_df: pd.DataFrame) -> bool:
    """정기비용(LTSA·CRI·고온부품)을 실적에서 분리할 수 있는가 — 사업 단위 «유형»(2026-10-26)이나
    v2 의 «투자유형세부_확정» 열이 있으면 된다."""
    return "유형" in actuals_df.columns or "투자유형세부_확정" in actuals_df.columns


# ── 정기비용 성격 판정 (표준화 방향 1·4-4) ─────────────────────────────────────
# 등급별 표준화에서 빼는 실적. 기계장치의 고온부품재생·LTSA·CRI 는 연도별 집행계획(고온부품·
# 정기계약·CRI 규칙)으로 따로 잡고, 정기유지보수 안의 LTSA(동탄 GT·연료전지)도 같다.
REGULAR_EXCLUDED = {"기계장치": {"LTSA", "CRI", "고온부품재생"},
                    "수선유지비-열원정기유지보수": {"LTSA"}}
_RE_SPACE = re.compile(r"\s+")
_RE_CRI = re.compile(r"(?<![A-Z])CRI(?![A-Z])")      # «CRITICAL» 같은 낱말 속 CRI 는 아님


def regular_type(account: str, name) -> str:
    """사업명 키워드로 정기비용 성격을 판정한다. 사람이 고친 값(actual_tag)이 이것보다 앞선다."""
    if account not in REGULAR_EXCLUDED:
        return "기타"
    n = _RE_SPACE.sub("", str(name or "")).upper()
    if "LTSA" in n or "장기유지보수" in n or "장기서비스" in n:
        return "LTSA"
    if account == "기계장치":
        if _RE_CRI.search(n) or "로터" in n:
            return "CRI"
        if "고온부품" in n or (("재생" in n) and ("GT" in n or "가스터빈" in n)):
            return "고온부품재생"
    return "기타"


def drop_regular(df: pd.DataFrame) -> pd.DataFrame:
    """정기비용 실적을 뺀다 — «유형» 열 기준. 열이 없으면 그대로."""
    if "유형" not in df.columns or df.empty:
        return df
    excluded = df.apply(lambda r: r["유형"] in REGULAR_EXCLUDED.get(r["예산과목"], ()), axis=1)
    return df[~excluded]


def apply_usage_events(df: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    """«실적사용시작» 이벤트 — 그 해 이전 실적을 표준화에서 뺀다(신규 지사·설비 전환·역무 증가).
    예산과목이 비면 그 지사의 모든 과목."""
    if events is None or events.empty or df.empty:
        return df
    keep = pd.Series(True, index=df.index)
    for _, e in events[events["유형"] == "실적사용시작"].iterrows():
        m = (df["사업장"] == e["사업장"]) & (df["연도"] < int(e["연도"]))
        if str(e.get("예산과목") or "").strip():
            m &= df["예산과목"] == e["예산과목"]
        keep &= ~m
    return df[keep]


def parse_years(text) -> list:
    """'2023,2021' · '2021~2025' · '2021-2025' → [2023, 2021] · [2021..2025]."""
    out = []
    for part in re.split(r"[,\s·/]+", str(text or "").strip()):
        if not part:
            continue
        m = re.fullmatch(r"(\d{4})\s*[~\-]\s*(\d{4})", part)
        if m:
            a, b = sorted((int(m.group(1)), int(m.group(2))))
            out.extend(range(a, b + 1))
        elif part.isdigit():
            out.append(int(part))
    return out




def _rule_dict(rules: pd.DataFrame) -> dict:
    if rules is None or rules.empty:
        return {}
    return {(r["사업장"], r["예산과목"], r["등급"]): r for _, r in rules.iterrows()}


def _txt(v) -> str:
    """규칙 칸의 글자 — None·NaN(빈 칸) → ''."""
    if v is None or (isinstance(v, float) and v != v):
        return ""
    return str(v).strip()


def _num(v, default):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    return default if f != f else f


def prepare_actuals(actuals_df: pd.DataFrame, item_alias: dict = None, events: pd.DataFrame = None) -> pd.DataFrame:
    """표준화 모집단 — 과목 이름 정규화 · 표준화 과목만 · 정기비용(LTSA·CRI·고온부품재생) 제외 · «실적사용시작» 이전 제외.
    용량 환산(capacity.py)도 같은 모집단을 쓴다."""
    alias = item_alias if item_alias is not None else config_store.seed_item_alias()
    df = actuals_df.copy()
    if not df.empty:
        df["예산과목"] = df["예산과목"].apply(lambda v: normalize.normalize_item(v, alias))
        df = df[df["예산과목"].isin(ALL_ACCOUNTS)]
        if "유형" in df.columns:
            df = drop_regular(df)
        elif "투자유형세부_확정" in df.columns:
            machine_mask = df["예산과목"] == "기계장치"
            ltsa_mask = machine_mask & df["투자유형세부_확정"].isin(LTSA_LIKE_DETAILS)
            df = df[~ltsa_mask]
        # 둘 다 없으면 '기계장치'를 정기비용 분리 없이 총액 그대로 쓴다(화면이 한 번 안내한다).
        df = apply_usage_events(df, events)
    return df


def compute_standard_amounts(actuals_df: pd.DataFrame, grade_history_df: pd.DataFrame,
                              method_map: pd.DataFrame = None, overrides: pd.DataFrame = None,
                              item_alias: dict = None, rules: pd.DataFrame = None,
                              events: pd.DataFrame = None, budget_lookup: dict = None,
                              window: int = None) -> pd.DataFrame:
    """
    actuals_df: 사업장, 연도, 예산과목, 금액 컬럼 필요. «유형» 열(정기비용 성격)이 있으면 기계장치의
                고온부품재생·LTSA·CRI 와 정기유지보수의 LTSA 를 빼고 표준화한다(REGULAR_EXCLUDED).
                v2 의 '투자유형세부_확정' 열도 같은 뜻으로 받는다.
    grade_history_df: 사업장, 연도, 등급 (대표 등급)
    rules: 산정 규칙(benchmark_rule) — (사업장, 예산과목, 등급|'*') 마다 방식·연도목록·보정률·
           참조지사·참조등급·조정액. 규칙 > method_map(사용자지정) > recommend_method(자동추천) 순.
    events: 지사 구조변화(site_event) — «실적사용시작» 이전 실적은 뺀다.
    budget_lookup: {(사업장, 예산과목): 기준연도 계획금액} — «예산 대체» 방식이 쓴다.
    window: 학습 기간(최근 N개년). 규칙 없는 칸(사용자지정·자동추천)만 이 창 안 실적을 쓴다 — 산정
            규칙은 엑셀처럼 연도를 직접 가리키므로 전체 실적을 본다.
    overrides(수동수정)는 무엇보다 앞선다.
    반환: 사업장, 구분(손익/자본), 예산과목, 등급, 표준금액, 산출방식, 방식출처, 추천사유, 비고, 근거
    """
    result_cols = ["사업장", "구분", "예산과목", "등급", "표준금액", "산출방식", "방식출처", "추천사유", "비고", "근거"]
    rule_dict = _rule_dict(rules)
    if actuals_df.empty and not rule_dict:
        return pd.DataFrame(columns=result_cols)

    df = prepare_actuals(actuals_df, item_alias, events)

    # 연도별 합계는 한 번의 groupby 로 — 지사×과목 그룹마다 groupby 하면 계산 시간의 절반이다(백테스트 13초 → 6초).
    def _yearly(frame):
        cells = {}
        if not frame.empty:
            for (site, account, year), amount in frame.groupby(["사업장", "예산과목", "연도"])["금액"].sum().items():
                cells.setdefault((site, account), {})[year] = amount
        return {k: pd.Series(v, dtype=float).sort_index() for k, v in cells.items()}

    yearly_by = _yearly(df)
    yearly_win = _yearly(recent_window(df, window)) if window else yearly_by
    grades_by_site = {}
    for site, g in grade_history_df.groupby("사업장") if not grade_history_df.empty else []:
        grades_by_site[site] = dict(zip(g["연도"], g["등급"]))

    method_dict = get_method_dict(method_map) if method_map is not None else {}
    override_dict = {}
    if overrides is not None and not overrides.empty:
        override_dict = {(r["사업장"], r["예산과목"], r["등급"]): r["표준금액"] for _, r in overrides.iterrows()}
    budget_lookup = budget_lookup or {}
    empty = pd.Series(dtype=float)
    memo = {}

    def from_rule(site, account, grade, rule, depth):
        method = str(rule["방식"])
        ref_site = _txt(rule.get("참조지사")) or site
        ref_grade = _txt(rule.get("참조등급")) or grade
        years = parse_years(_txt(rule.get("연도목록")))
        factor = _num(rule.get("보정률"), 1.0)
        adjust = _num(rule.get("조정액"), 0.0)
        yearly = yearly_by.get((ref_site, account), empty)
        basis = ""
        if method == "직접 입력":
            return adjust, method, "직접 입력값"
        if method == "등급 차용":
            if (ref_site, ref_grade) == (site, grade):
                return 0.0, method, "자기 자신을 차용할 수 없음"
            base = resolve(ref_site, account, ref_grade, depth + 1)[0]
            basis = f"{ref_site} {ref_grade} 표준금액"
            note = basis
        elif method == "예산 대체":
            base = budget_lookup.get((site, account))
            note = "기준연도 계획본" if base is not None else "기준연도 계획본 없음 - 0"
            base = float(base or 0.0)
            basis = note
        elif method in ("지정연도 평균", "최대값"):
            use = years or sorted(int(y) for y in yearly.index)
            vals = [float(yearly.get(y, 0.0)) for y in use]
            base = (max(vals) if method == "최대값" else sum(vals) / len(vals)) if vals else 0.0
            who = "" if ref_site == site else f"{ref_site} "
            basis = f"{who}{'·'.join(str(y) for y in use)} {'최대' if method == '최대값' else '평균'}"
            note = basis
        else:
            base, note = _apply_method(yearly, grade, grades_by_site.get(ref_site, {}), method)
            basis = note if ref_site == site else f"{ref_site} {note}"
        amount = base * factor + adjust
        if factor != 1.0:
            basis += f" ×{factor:g}"
        if adjust:
            basis += f" {'+' if adjust > 0 else '−'}{abs(adjust):,.0f}"
        return amount, note, basis

    def resolve(site, account, grade, depth=0):
        """(표준금액, 산출방식, 방식출처, 추천사유, 비고, 근거)"""
        key = (site, account, grade)
        if key in memo:
            return memo[key]
        if depth > 6:
            return (0.0, "등급 차용", "규칙", "", "차용이 순환함", "")
        if key in override_dict:
            out = (float(override_dict[key]), "수동수정", "수동수정", "", "사용자가 직접 입력", "직접 입력")
        else:
            rule = rule_dict.get(key)
            if rule is None:
                rule = rule_dict.get((site, account, "*"))
            if rule is not None:
                amount, note, basis = from_rule(site, account, grade, rule, depth)
                reason = _txt(rule.get("사유"))
                out = (amount, str(rule["방식"]), "규칙", reason, note, basis)
            else:
                yearly = yearly_win.get((site, account), empty)
                gby = grades_by_site.get(site, {})
                explicit = method_dict.get((site, account))
                if explicit:
                    method, source, reason = explicit, "사용자지정", ""
                else:
                    method, reason = recommend_method(yearly, gby)
                    source = "자동추천"
                amount, note = _apply_method(yearly, grade, gby, method)
                out = (amount, method, source, reason, note, note)
        memo[key] = out
        return out

    combos = {}
    for (site, account) in yearly_win:
        combos.setdefault((site, account), set())
    for (site, account, grade) in rule_dict:
        if account in ALL_ACCOUNTS:
            combos.setdefault((site, account), set())
            if grade != "*":
                combos[(site, account)].add(grade)
    for (site, account, grade) in override_dict:
        if (site, account) in combos:
            combos[(site, account)].add(grade)

    rows = []
    for (site, account) in sorted(combos):
        category = "손익" if account in PROFIT_LOSS_ACCOUNTS else "자본"
        grades = set(grades_by_site.get(site, {}).values()) | combos[(site, account)]
        for grade in sorted(grades) or ["표준"]:
            amount, method, source, reason, note, basis = resolve(site, account, grade)
            rows.append({"사업장": site, "구분": category, "예산과목": account, "등급": grade,
                         "표준금액": amount, "산출방식": method, "방식출처": source,
                         "추천사유": reason if source in ("자동추천", "규칙") else "",
                         "비고": note, "근거": basis})

    return pd.DataFrame(rows, columns=result_cols) if rows else pd.DataFrame(columns=result_cols)
