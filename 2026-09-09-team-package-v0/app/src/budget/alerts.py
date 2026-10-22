# -*- coding: utf-8 -*-
"""이상 알림 — 분석 결과(사업 행)에서 사람이 먼저 볼 것을 규칙으로 골라 위험도 순으로 준다.

유사 제품 비교(2026-10-22, Planful Signals 등)의 «규칙 기반 이상 알림». ML 없이 합계와 비교만 쓴다.
입력은 db.load_biz_lines 의 행(천원 단위)이고, 판단은 하지 않는다 — 알림은 «여기를 보라»까지다.

규칙 네 가지(모든 금액 천원):
  급증       같은 예산·지사·과목의 실적이 전년의 2배 이상이고 SPIKE_MIN 이상 늘었다(전년 0 이면 올해 SPIKE_MIN 이상).
  예산 초과  같은 예산·지사·과목에서 실적이 계획을 OVER_MIN 이상 넘었다(계획 있는 것만).
  음수 실적  사업 행의 실적이 −NEG_MIN 이하다(계정대체·취소 전표가 엉뚱한 사업에 붙은 경우가 많다).
  미매칭 비중 계획에 못 붙은 실적(신규 + 미매핑)이 전체의 UNMATCHED_SHARE 이상이다 — 예산별, 그리고 지사별.
위험도: 금액이 HIGH_AMT(심의대상 기준 5천만 원) 이상이면 «높음», 아니면 «보통».
"""
from .config_store import SIMUI_THRESHOLD_THOUSAND

HIGH_AMT = SIMUI_THRESHOLD_THOUSAND          # 50,000천원
SPIKE_RATIO = 2.0
SPIKE_MIN = HIGH_AMT
OVER_MIN = 10_000
NEG_MIN = 1_000
UNMATCHED_SHARE = 0.20                       # 예산 전체
UNMATCHED_SHARE_HIGH = 0.30
BRANCH_UNMATCHED_SHARE = 0.30                # 지사별(금액 HIGH_AMT 이상만)

KINDS = ("급증", "예산 초과", "음수 실적", "미매칭 비중")


def _num(v):
    try:
        f = float(v or 0)
    except (TypeError, ValueError):
        return 0.0
    return 0.0 if f != f else f


def _is_new(gubun):
    return str(gubun or "").startswith("신규")


def _group(lines):
    """(budget, 지사, 과목) → {"plan", "actual"}."""
    out = {}
    for r in lines:
        k = (r["budget"], r.get("처지사") or "(미매핑)", r.get("예산과목") or "(과목 없음)")
        g = out.setdefault(k, {"plan": 0.0, "actual": 0.0})
        g["plan"] += _num(r.get("연예산"))
        g["actual"] += _num(r.get("실적금액"))
    return out


def _sev(amount):
    return "높음" if abs(amount) >= HIGH_AMT else "보통"


def compute_alerts(cur_lines, prev_lines=None, unmapped=None):
    """cur_lines/prev_lines: [{budget, 처지사, 예산과목, 사업명, 연예산, 실적금액, 구분}]
    unmapped: {budget: 미매핑 전표 금액 합(천원)} — 지사를 못 찾아 사업 행에 없는 실적.
    반환: [{kind, severity, budget, branch, item, name, amount, text}] — 높음 먼저, 금액 큰 순.
    """
    alerts = []
    cur = _group(cur_lines)

    # 예산 초과
    for (budget, branch, item), g in cur.items():
        over = g["actual"] - g["plan"]
        if g["plan"] > 0 and over >= OVER_MIN:
            alerts.append({"kind": "예산 초과", "severity": _sev(over), "budget": budget,
                           "branch": branch, "item": item, "name": None, "amount": round(over),
                           "text": f"계획 {g['plan']:,.0f} → 실적 {g['actual']:,.0f}천원 "
                                   f"({g['actual'] / g['plan'] * 100:,.1f}%)"})

    # 급증(전년 대비)
    if prev_lines:
        prev = _group(prev_lines)
        for k, g in cur.items():
            before = prev.get(k, {}).get("actual", 0.0)
            inc = g["actual"] - before
            if inc < SPIKE_MIN:
                continue
            if before > 0 and g["actual"] < before * SPIKE_RATIO:
                continue
            budget, branch, item = k
            why = (f"전년 {before:,.0f} → 올해 {g['actual']:,.0f}천원 ({g['actual'] / before:,.1f}배)"
                   if before > 0 else f"전년 실적 없음 → 올해 {g['actual']:,.0f}천원")
            alerts.append({"kind": "급증", "severity": _sev(inc), "budget": budget,
                           "branch": branch, "item": item, "name": None, "amount": round(inc),
                           "text": why})

    # 음수 실적(사업 행)
    for r in cur_lines:
        a = _num(r.get("실적금액"))
        if a <= -NEG_MIN:
            alerts.append({"kind": "음수 실적", "severity": _sev(a), "budget": r["budget"],
                           "branch": r.get("처지사") or "(미매핑)", "item": r.get("예산과목"),
                           "name": r.get("사업명"), "amount": round(a),
                           "text": f"실적 {a:,.0f}천원 — 대체·취소 전표가 붙었는지 전표를 확인하세요"})

    # 미매칭 비중 — 예산별
    unmapped = unmapped or {}
    by_budget = {}
    for r in cur_lines:
        b = by_budget.setdefault(r["budget"], {"total": 0.0, "new": 0.0})
        a = _num(r.get("실적금액"))
        b["total"] += a
        if _is_new(r.get("구분")):
            b["new"] += a
    for budget in sorted(set(by_budget) | set(unmapped)):
        b = by_budget.get(budget, {"total": 0.0, "new": 0.0})
        um = _num(unmapped.get(budget))
        total = b["total"] + um
        miss = b["new"] + um
        if total <= 0:
            continue
        share = miss / total
        if share >= UNMATCHED_SHARE:
            alerts.append({"kind": "미매칭 비중", "severity": "높음" if share >= UNMATCHED_SHARE_HIGH else "보통",
                           "budget": budget, "branch": None, "item": None, "name": None,
                           "amount": round(miss),
                           "text": f"계획에 못 붙은 실적 {share * 100:,.1f}% "
                                   f"(신규 {b['new']:,.0f} + 미매핑 {um:,.0f} / 전체 {total:,.0f}천원)"})

    # 미매칭 비중 — 지사별(큰 것만)
    by_branch = {}
    for r in cur_lines:
        k = (r["budget"], r.get("처지사") or "(미매핑)")
        g = by_branch.setdefault(k, {"total": 0.0, "new": 0.0})
        a = _num(r.get("실적금액"))
        g["total"] += a
        if _is_new(r.get("구분")):
            g["new"] += a
    for (budget, branch), g in by_branch.items():
        if g["total"] > 0 and g["new"] >= HIGH_AMT and g["new"] / g["total"] >= BRANCH_UNMATCHED_SHARE:
            alerts.append({"kind": "미매칭 비중", "severity": "보통", "budget": budget,
                           "branch": branch, "item": None, "name": None, "amount": round(g["new"]),
                           "text": f"신규(계획 외) 실적 {g['new'] / g['total'] * 100:,.1f}% "
                                   f"({g['new']:,.0f} / {g['total']:,.0f}천원)"})

    alerts.sort(key=lambda x: (x["severity"] != "높음", -abs(x["amount"])))
    return alerts


def summarize(alerts):
    counts = {k: 0 for k in KINDS}
    for a in alerts:
        counts[a["kind"]] += 1
    return {"total": len(alerts), "high": sum(a["severity"] == "높음" for a in alerts),
            "counts": counts}
