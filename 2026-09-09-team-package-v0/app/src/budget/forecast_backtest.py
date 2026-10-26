# -*- coding: utf-8 -*-
"""전망 방식 백테스트 — 과거 실적으로 «그 전 해들로 그 해 맞히기»를 되풀이해 오차를 잰다.

2026-10-26 백테스트 제안 ⑤(목표 단위 합의). 칸(지사×과목×연도) 하나하나를 맞히는 것은 사람이
세운 연예산도 44~64% 틀리는 한계라, 실제로 쓰는 단위 둘을 주 지표로 둔다.
  과목 합계 오차     연도마다 과목별 전사 합계의 |예측−실적| 합 ÷ 실적 합 (백테스트 약 25%)
  지사 3년 누적 오차  최근 3개 시험 연도를 지사별로 묶은 |예측−실적| 합 ÷ 실적 합 (약 15%)
  칸별 오차         참고용(백테스트 42.8%)
계획으로 받는 줄 — 기계장치 중 고온부품재·LTSA·CRI(«유형»), 건설중인자산-재생고온부품 — 은 평균으로 맞힐
대상이 아니라 뺀다. A급정비(외주비-열원정기점검)는 일정 규칙으로 따로 잰다(설비별 등급이 있을 때).
2026-10-26 다른 세션의 백테스트 브랜치에서 옮김 — 실적은 이 앱의 «마감 + 참고 엑셀» 모집단이다.
"""
import pandas as pd

from . import benchmark, forecast_calc

PLANNED_ACCOUNTS = {"건설중인자산-재생고온부품"}


def _regular(actuals):
    """평균으로 맞힐 실적만 — 계획 성격 줄(재생고온부품 과목, 기계장치·정기유지보수의 정기비용 «유형»)을 뺀다."""
    a = actuals[~actuals["예산과목"].isin(PLANNED_ACCOUNTS)]
    return benchmark.drop_regular(a)


def _predict(train, grade_hist, target_year):
    """train 으로 표준금액을 만들고 target_year 의 등급으로 지사×과목 예측값을 고른다."""
    std = benchmark.compute_standard_amounts(train, grade_hist)
    if std.empty:
        return {}
    grades = {}
    if not grade_hist.empty:
        for site, g in grade_hist.groupby("사업장"):
            by_year = dict(zip(g["연도"].astype(int), g["등급"]))
            known = [y for y in by_year if y <= target_year]
            grades[site] = by_year.get(target_year, by_year[max(known)] if known else None)
    by_cell = {}
    for site, acct, grade, amount in zip(std["사업장"], std["예산과목"], std["등급"], std["표준금액"]):
        by_cell.setdefault((site, acct), []).append((grade, float(amount)))
    out = {}
    for (site, acct), pairs in by_cell.items():
        hit = [a for g, a in pairs if g == grades.get(site)] or [a for _, a in pairs]
        out[(site, acct)] = sum(hit) / len(hit)
    return out


def run(actuals: pd.DataFrame, grade_hist: pd.DataFrame, window: int, targets: list = None,
        unit_grades: pd.DataFrame = None, site_groups: dict = None) -> dict:
    """한 학습 기간(window)으로 시험 연도마다 예측 → 지표 dict."""
    if actuals.empty:
        return {"window": window, "targets": [], "cell": None, "account": None, "site3": None, "overhaul": None}
    reg = _regular(actuals[actuals["예산과목"] != forecast_calc.A_OVERHAUL_ACCOUNT])
    years = sorted(int(y) for y in actuals["연도"].unique())
    if targets is None:
        need = max(int(window or 0), 1)
        targets = [y for y in years if len([p for p in years if p < y]) >= need][-5:]
    cells = []
    for t in targets:
        train = benchmark.recent_window(reg[reg["연도"] < t], window)
        pred = _predict(train, grade_hist, t)
        act = reg[reg["연도"] == t].groupby(["사업장", "예산과목"])["금액"].sum().to_dict()
        for key in set(pred) | set(act):
            cells.append({"연도": t, "사업장": key[0], "예산과목": key[1],
                          "예측": pred.get(key, 0.0), "실적": act.get(key, 0.0)})
    df = pd.DataFrame(cells, columns=["연도", "사업장", "예산과목", "예측", "실적"])
    return {"window": window, "targets": targets, **_metrics(df),
            "overhaul": _overhaul(actuals, unit_grades, site_groups or {}, targets)}


def _ratio(err, base):
    return float(err / base) if base else None


def _metrics(df):
    if df.empty:
        return {"cell": None, "account": None, "site3": None}
    cell = _ratio((df["예측"] - df["실적"]).abs().sum(), df["실적"].abs().sum())
    acc = df.groupby(["연도", "예산과목"])[["예측", "실적"]].sum()
    account = _ratio((acc["예측"] - acc["실적"]).abs().sum(), acc["실적"].abs().sum())
    last3 = sorted(df["연도"].unique())[-3:]
    s3 = df[df["연도"].isin(last3)].groupby("사업장")[["예측", "실적"]].sum()
    site3 = _ratio((s3["예측"] - s3["실적"]).abs().sum(), s3["실적"].abs().sum())
    by_acct = [{"예산과목": a, "오차": _ratio((g["예측"] - g["실적"]).abs().sum(), g["실적"].abs().sum()),
                "실적": float(g["실적"].sum())}
               for a, g in df.groupby("예산과목")]
    by_acct.sort(key=lambda r: -r["실적"])
    return {"cell": cell, "account": account, "site3": site3, "by_account": by_acct}


def _overhaul(actuals, unit_grades, site_groups, targets):
    """A급정비 일정 규칙의 시험 — 총액 오차·맞힌 해·헛예측 칸."""
    if unit_grades is None or unit_grades.empty or not targets:
        return None
    sites = sorted(set(unit_grades["사업장"]))
    a = actuals[actuals["예산과목"] == forecast_calc.A_OVERHAUL_ACCOUNT]
    act = a.groupby(["사업장", "연도"])["금액"].sum().to_dict()
    years = {s: forecast_calc.overhaul_years(unit_grades, s) for s in sites}
    pred_sum = act_sum = 0.0
    hits = events = false_pos = 0
    for t in targets:
        amounts = forecast_calc.overhaul_amounts(actuals, sites, site_groups, before_year=t)
        for s in sites:
            p = amounts.get(s, 0.0) if t in years[s] else 0.0
            r = act.get((s, t), 0.0)
            pred_sum += p
            act_sum += r
            if r > 0:
                events += 1
                hits += 1 if p > 0 else 0
            elif p > 0:
                false_pos += 1
    return {"total": _ratio(pred_sum - act_sum, act_sum), "hits": hits, "events": events,
            "false_positive": false_pos}


def compare_windows(actuals, grade_hist, windows=(2, 3, 5, 10), unit_grades=None, site_groups=None):
    """학습 기간별 같은 시험 연도(최근 5개년)로 비교. 앞쪽 해는 학습 자료가 기간보다 짧으면 있는 만큼 쓴다
    — 2026-10-26 백테스트(2021~2025 대상)와 같은 방식이다."""
    years = sorted(int(y) for y in actuals["연도"].unique()) if not actuals.empty else []
    targets = years[1:][-5:]
    return [run(actuals, grade_hist, w, targets, unit_grades, site_groups) for w in windows]
