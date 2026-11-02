# -*- coding: utf-8 -*-
"""설비 용량 · 신규 발전설비 지사 표준금액(용량 환산) — 2026-10-28 사용자 요청.

양산(2023)·대구(2024)·청주(2025) 는 발전설비(복합 열병합)를 새로 지어 그 전 실적이 지금 설비와 맞지 않고,
새 설비 실적은 1~3년뿐이라 정비등급별(MI·TI/HGPI·CI·간이) 표준금액을 자기 실적으로 세울 수 없다.
수원은 유류 39MW 를 개체 중(2029.2 준공 136MW)이라 2029년부터 같은 방식, 2027~28 은 발전설비 정비를 뺀다.

**규칙(기준 지사 = 화성·파주·광교·판교·삼송, 실제 운영 데이터 2016~2025 로 찾음)**
  한 해 정비비(표준화 과목 합계) = 고정분 F + 등급별 단가 k[등급] × 설비용량(MW)
    F·k[간이] = 기준 지사 «간이» 해 평균의 용량 회귀(절편·기울기) — 지사 공통 몫(DH·건물·상시 정비)이 있다
    k[MI]·k[TI/HGPI]·k[CI] = 기준 지사마다 (그 등급 해 평균 − F) ÷ MW 의 중앙값(지사 하나가 튀어도 덜 흔들림)
  과목별 금액 = 그 등급 합계 × 기준 지사들의 그 등급 해 과목 비중
  과목 = 전망 표가 표준금액으로 채우는 과목(MODEL_ACCOUNTS). 고온부품 신품구매·LTSA·CRI 는 따로 잡힌다.
  모형 고르기(2016~2025, 한 지사씩 빼고 맞혀 본 오차 LOO): «고정분 + 등급별 단가»가 후보 넷 중 가장 작았다
  (단순 비례·간이×등급배수·단순 선형보다). 지금 값은 화면 «설비용량·신규표준» 탭과 fit_model()["loo"].
  TI 와 HGPI 는 같은 등급으로 본다(사용자 기준 «TI or HGPI»).
  정비제외 해(수원 2027~28) = 고정분 F 만(발전설비 정비 없이 DH·공통 몫) — 간이 과목 비중으로 나눈다.

용량 출처: 사용자 엑셀 «한난_발전설비용량_261028.xlsx»(한난 홈페이지 전력사업·지사안내, KPX 등록 2023.3).
"""
import numpy as np
import pandas as pd

from . import benchmark, forecast_calc

GRADE_CLASS = {"TI": "TI/HGPI", "HGPI": "TI/HGPI"}
CLASSES = ["MI", "TI/HGPI", "CI", "간이"]
EXCLUDED = "정비제외"
METHOD = "용량 환산"
POWER = "발전설비"          # 설비 현황 «구분» — 용량 환산에 쓰는 줄
# 전망 표가 표준금액으로 채우는 과목만 — 건설중인자산-재생고온부품(고온부품 신품구매)·LTSA·CRI 는 따로
# (고온부품 계획·정기계약·CRI 규칙) 잡히므로 여기 넣으면 TI·MI 해 몫의 30~40%가 표에 안 나타난다.
MODEL_ACCOUNTS = {src.split(":", 1)[1] for _, src in forecast_calc.SITE_TABLE_LINES if src.startswith("표준화:")}

CAPACITY_COLS = ["사업장", "설비", "구분", "용량MW", "준공연도", "비고"]
RULE_COLS = ["사업장", "역할", "적용시작연도", "용량MW", "정비제외연도", "비고"]

# 사용자 엑셀 «요약» + «기타 소형 상세» 시트 그대로(2026-10-28). 화면에서 고쳐 저장하면 저장값이 이긴다.
DEFAULT_CAPACITY = [
    ("수원사업소", "열병합(유류)", POWER, 39, 1997, "개체 중 — 개체 후 136MW('29.2 준공 예정). 출처 시트는 141MW 로 적혀 있음"),
    ("수원사업소", "열병합(개체 후)", POWER, 136, 2029, "'29.2월 준공 예정"),
    ("화성지사", "복합 열병합(LNG)", POWER, 512, 2007, "GT 161×2 + ST 190"),
    ("판교지사", "복합 열병합(LNG)", POWER, 146, 2010, "GT 78 + ST 68"),
    ("파주지사", "복합 열병합(LNG)", POWER, 516, 2011, "GT 163×2 + ST 189"),
    ("삼송지사", "구역전기 열병합(LNG)", POWER, 100, 2011, "KPX 등록 GT1·GT2·ST 각 68(등록값)"),
    ("광교지사", "복합 열병합(LNG)", POWER, 145, 2012, "GT 103 + ST 42"),
    ("동탄지사", "복합 열병합(LNG)", POWER, 757, 2017, "1·2호기 CC 각 378 (GT 246 + ST 132)"),
    ("광주전남지사", "열병합", POWER, 22, 2017, "신재생 비중앙"),
    ("양산지사", "복합 열병합(LNG)", POWER, 119, 2023, "GT 78 + ST 41 (개체 준공)"),
    ("대구지사", "복합 열병합(LNG)", POWER, 270, 2024, "기존 유류 44MW 대체"),
    ("청주지사", "복합 열병합(LNG)", POWER, 270, 2025, "기존 유류 58MW 대체"),
    ("강남지사", "CES 열병합(동남권 유통단지·가락 구역전기)", "기타 소형", 33.8, None, "열병합/구역전기"),
    ("동탄지사", "연료전지(PAFC, 2018.12)", "기타 소형", 11.44, 2018, "연료전지"),
    ("중앙지사", "상암열원(상암2지구 구역전기)", "기타 소형", 9, None, "열병합/구역전기"),
    ("대구지사", "우드칩 발전", "기타 소형", 3, None, "바이오(우드칩)"),
    ("중앙지사", "신재생설비(상암·난지 바이오 등)", "기타 소형", 3, None, "신재생"),
    ("본사", "광양항 자전거도로 태양광(제1~3발전소)", "기타 소형", 1.2, None, "태양광"),
    ("본사", "미래개발원 연료전지(PAFC, 2020.10)", "기타 소형", 0.1, 2020, "연료전지"),
    ("광주전남지사", "신안 증도 태양광", "기타 소형", 0.806, None, "태양광"),
    ("파주지사", "신재생설비", "기타 소형", 0.6228, None, "태양광"),
    ("세종지사", "신재생설비", "기타 소형", 0.54025, None, "태양광"),
    ("강남지사", "신재생설비", "기타 소형", 0.425, None, "태양광"),
    ("광교지사", "신재생설비", "기타 소형", 0.3797, None, "태양광"),
    ("화성지사", "신재생설비", "기타 소형", 0.2592, None, "태양광"),
    ("광주전남지사", "신재생설비", "기타 소형", 0.252, None, "태양광"),
    ("판교지사", "신재생설비", "기타 소형", 0.1856, None, "태양광"),
    ("분당사업소", "신재생설비", "기타 소형", 0.1516, None, "태양광"),
    ("수원사업소", "신재생설비", "기타 소형", 0.14546, None, "태양광"),
    ("삼송지사", "신재생설비", "기타 소형", 0.1269, None, "태양광"),
    ("양산지사", "신재생설비", "기타 소형", 0.09996, None, "태양광"),
    ("고양사업소", "신재생설비", "기타 소형", 0.046097, None, "태양광"),
]

DEFAULT_RULES = [
    ("화성지사", "기준", None, None, "", ""),
    ("파주지사", "기준", None, None, "", ""),
    ("광교지사", "기준", None, None, "", ""),
    ("판교지사", "기준", None, None, "", ""),
    ("삼송지사", "기준", None, None, "", ""),
    ("양산지사", "대상", 2023, None, "", "2023 발전설비 설치 완료 — 그 전 실적은 표준화에서 뺌"),
    ("대구지사", "대상", 2024, None, "", "2024 발전설비 설치 완료"),
    ("청주지사", "대상", 2025, None, "", "2025 발전설비 설치 완료"),
    ("수원사업소", "대상", 2029, 136, "2027~2028", "개체 중 — 27~28 은 발전설비 정비 제외(DH 만), 29 부터 개체 후 용량"),
]


def default_capacity() -> pd.DataFrame:
    return pd.DataFrame(DEFAULT_CAPACITY, columns=CAPACITY_COLS)


def default_rules() -> pd.DataFrame:
    return pd.DataFrame(DEFAULT_RULES, columns=RULE_COLS)


def _num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if f != f else f


def site_mw(capacity: pd.DataFrame, site: str):
    """발전설비 용량(MW) — 그 지사 «발전설비» 줄 중 가장 늦게 준공한 것(수원은 개체 후 136). 없으면 None."""
    if capacity is None or capacity.empty:
        return None
    rows = capacity[(capacity["사업장"] == site) & (capacity["구분"] == POWER)]
    if rows.empty:
        return None
    rows = rows.assign(_y=rows["준공연도"].apply(lambda v: _num(v) or 0)).sort_values("_y")
    return _num(rows.iloc[-1]["용량MW"])


def _clean_rules(rules: pd.DataFrame, capacity: pd.DataFrame):
    """(기준 {지사: MW}, 대상 {지사: {mw, start, excluded:set}})"""
    refs, targets = {}, {}
    for _, r in (rules if rules is not None else default_rules()).iterrows():
        site = str(r["사업장"]).strip()
        mw = _num(r.get("용량MW")) or site_mw(capacity, site)
        if not site or not mw:
            continue
        if str(r["역할"]).strip() == "기준":
            refs[site] = mw
        elif str(r["역할"]).strip() == "대상":
            start = _num(r.get("적용시작연도"))
            targets[site] = {"mw": mw, "start": int(start) if start else None,
                             "excluded": set(benchmark.parse_years(r.get("정비제외연도") or ""))}
    return refs, targets


def _future(target: dict, base_year) -> bool:
    """적용시작연도가 기준연도 뒤 — 아직 지금 설비로 돌아가는 지사(수원 2029, 2026 기준)."""
    return base_year is not None and bool(target["start"]) and int(target["start"]) > int(base_year)


def usage_events(rules: pd.DataFrame, capacity: pd.DataFrame, base_year=None) -> pd.DataFrame:
    """대상 지사의 적용시작연도 → «실적사용시작»(그 전 실적은 지금 설비와 맞지 않는다).
    시작이 기준연도 뒤면 넣지 않는다 — 그 지사 과거 실적은 아직 지금 설비 것이라 시작 전 해의 표준금액이 된다."""
    _, targets = _clean_rules(rules, capacity)
    rows = [{"사업장": s, "연도": t["start"], "유형": "실적사용시작", "예산과목": "", "비고": "용량 환산 대상"}
            for s, t in targets.items() if t["start"] and not _future(t, base_year)]
    return pd.DataFrame(rows, columns=["사업장", "연도", "유형", "예산과목", "비고"])


def fit_model(prepared: pd.DataFrame, grade_hist: pd.DataFrame, refs: dict) -> dict:
    """기준 지사 실적(prepare_actuals 를 거친 것) → {fixed, k, shares, table, loo}. 금액 단위 천원."""
    gy = {(s, int(y)): GRADE_CLASS.get(str(g), str(g))
          for s, y, g in zip(grade_hist["사업장"], grade_hist["연도"], grade_hist["등급"])} if not grade_hist.empty else {}
    a = prepared[prepared["사업장"].isin(refs) & prepared["예산과목"].isin(MODEL_ACCOUNTS)] if not prepared.empty else prepared
    if a.empty:
        return {"fixed": 0.0, "k": {}, "shares": {}, "table": [], "loo": {}, "refs": refs}
    cell = a.groupby(["사업장", "연도", "예산과목"])["금액"].sum().unstack(fill_value=0.0)
    cell["_등급"] = [gy.get((s, int(y))) for s, y in cell.index]
    cell = cell[cell["_등급"].isin(CLASSES)]
    accounts = [c for c in cell.columns if c != "_등급"]
    site_grade = cell.groupby([cell.index.get_level_values(0), "_등급"])[accounts].mean()   # (지사, 등급) × 과목 평균
    totals = site_grade.sum(axis=1)                                                          # (지사, 등급) 합계 평균
    years = cell.groupby([cell.index.get_level_values(0), "_등급"]).size()

    def fit(t):
        """t: {지사: 등급별 합계 평균} → (F, k_간이, {등급: k})"""
        easy = {s: v for (s, g), v in t.items() if g == "간이"}
        xs = np.array([refs[s] for s in easy], dtype=float)
        ys = np.array(list(easy.values()), dtype=float)
        if len(set(xs)) >= 2:
            k_easy, f = np.polyfit(xs, ys, 1)
        else:
            f, k_easy = 0.0, (ys.sum() / xs.sum() if len(xs) else 0.0)
        f = max(0.0, float(f))
        k = {"간이": max(0.0, float(k_easy))}
        for g in ("MI", "TI/HGPI", "CI"):
            per = [(v - f) / refs[s] for (s, gg), v in t.items() if gg == g]
            k[g] = max(0.0, float(np.median(per))) if per else k["간이"]
        return f, k

    f, k = fit(totals.to_dict())
    shares = {}
    for g in CLASSES:
        rows = site_grade[site_grade.index.get_level_values(1) == g]
        tot = float(rows.values.sum())
        shares[g] = {acc: float(rows[acc].sum()) / tot for acc in accounts if tot and rows[acc].sum() != 0}
    # 한 지사씩 빼고 맞혀 본 오차 — 화면에 «이 규칙이 얼마나 맞나»를 같이 보인다
    loo = {}
    for s in refs:
        rest = {key: v for key, v in totals.to_dict().items() if key[0] != s}
        if not rest:
            continue
        f2, k2 = fit(rest)
        for (ss, g), act in totals.items():
            if ss == s and act:
                loo.setdefault(g, []).append(abs(f2 + k2[g] * refs[s] - act) / act)
    table = [{"사업장": s, "용량MW": refs[s], "등급": g, "해수": int(years.get((s, g), 0)),
              "평균금액": float(v), "MW당": float(v) / refs[s]} for (s, g), v in totals.items()]
    return {"fixed": f, "k": k, "shares": shares, "table": table, "refs": refs,
            "loo": {g: float(np.mean(v)) for g, v in loo.items()},
            "loo_all": float(np.mean([e for v in loo.values() for e in v])) if loo else None}


def _rows_for(site, mw, total, share, grade, note):
    out = []
    for acc, w in share.items():
        out.append({"사업장": site, "구분": "손익" if acc in benchmark.PROFIT_LOSS_ACCOUNTS else "자본",
                    "예산과목": acc, "등급": grade, "표준금액": total * w, "산출방식": METHOD,
                    "방식출처": "용량규칙", "추천사유": "", "비고": note, "근거": note})
    return out


def standard_rows(model: dict, site: str, target: dict) -> pd.DataFrame:
    """대상 지사의 등급별 표준금액(과목별). 등급: MI·TI·HGPI·CI·간이·표준(=간이) [+ 정비제외]."""
    f, k, mw = model["fixed"], model["k"], target["mw"]
    rows = []
    for grade in ("MI", "TI", "HGPI", "CI", "간이", "표준"):
        g = GRADE_CLASS.get(grade, "간이" if grade == "표준" else grade)
        if g not in k or not model["shares"].get(g):
            continue
        total = f + k[g] * mw
        note = f"용량 환산 · 고정 {f / 1e5:,.1f}억 + {k[g] / 1e5:.3f}억/MW × {mw:g}MW ({g})"
        rows += _rows_for(site, mw, total, model["shares"][g], grade, note)
    if target["excluded"] and model["shares"].get("간이"):
        note = f"정비제외 · 고정분 {f / 1e5:,.1f}억만(발전설비 정비 없음)"
        rows += _rows_for(site, mw, f, model["shares"]["간이"], EXCLUDED, note)
    return pd.DataFrame(rows)


def apply_capacity(std: pd.DataFrame, prepared: pd.DataFrame, grade_hist: pd.DataFrame,
                   capacity: pd.DataFrame, rules: pd.DataFrame, base_year=None):
    """표준금액 표에서 대상 지사 줄을 용량 환산 값으로 바꾼다(수동수정 줄은 그대로). → (std, model, targets)

    적용시작연도가 기준연도 뒤인 대상(_future)은 표의 지금 설비 줄을 그대로 두고, 시작 해부터 쓸 용량 환산 줄을
    targets[지사]["rows"] 로 따로 돌려준다(전망 표가 해마다 고른다). 정비제외 줄은 시작 전 해라 표에 넣는다."""
    refs, targets = _clean_rules(rules, capacity)
    if not refs or not targets:
        return std, None, targets
    model = fit_model(prepared, grade_hist, refs)
    if not model["k"]:
        return std, model, targets
    keep = std[~std["사업장"].isin(targets) | (std["방식출처"] == "수동수정")] if not std.empty else std
    manual = {(r["사업장"], r["예산과목"], r["등급"]) for _, r in keep.iterrows() if r["방식출처"] == "수동수정"}
    future = {s for s, t in targets.items() if _future(t, base_year)}
    if future and not std.empty:
        keep = pd.concat([keep, std[std["사업장"].isin(future) & (std["방식출처"] != "수동수정")]], ignore_index=True)
    new = [standard_rows(model, s, t) for s, t in targets.items()]
    new = pd.concat([n for n in new if not n.empty], ignore_index=True) if any(not n.empty for n in new) else pd.DataFrame()
    if not new.empty and manual:
        new = new[[(s, a, g) not in manual for s, a, g in zip(new["사업장"], new["예산과목"], new["등급"])]]
    if not new.empty and future:
        later = new["사업장"].isin(future) & (new["등급"] != EXCLUDED)
        for s in future:
            targets[s]["rows"] = new[later & (new["사업장"] == s)].reset_index(drop=True)
        new = new[~later]
    out = pd.concat([keep, new], ignore_index=True) if not new.empty else keep
    return out, model, targets


def excluded_grades(targets: dict) -> pd.DataFrame:
    """정비제외 해 → 등급 «정비제외»(전망 계산에만 끼운다 — 저장된 등급 이력은 그대로)."""
    rows = [{"사업장": s, "연도": y, "등급": EXCLUDED} for s, t in targets.items() for y in sorted(t["excluded"])]
    return pd.DataFrame(rows, columns=["사업장", "연도", "등급"])
