# -*- coding: utf-8 -*-
"""검토 큐 — «어디부터 볼지»를 돈으로 정해 주는 작업대(2026-10-27).

이상 알림·차이 사유·저확신 귀속이 각각 건수로만 보이면(알림 171건·사유 미입력 1,405건) 사람은 어디서
시작할지 모르고, 심사·보고 자리에서는 «아직 일이 안 끝났다»로 읽힌다. 여기서는 사업 한 줄을 검토
단위로 삼아 이유를 모으고, 그 줄에 걸린 돈(검토 금액)에 위험 가중을 곱해 줄을 세운다.
그리고 «남은 검토 금액의 80% 를 덮으려면 상위 몇 건을 보면 되는가»와 «처리한 금액이 몇 %인가»를 준다.

검토 금액(천원, 사업 한 줄) · 위험 가중
  차이        집행률 ±20%p 밖(dbm.is_variance) — |실적 − 계획|           × 1.0
  과다 귀속   이상 알림의 «과다 귀속»과 같은 판정(alerts.py) — 실적 − 계획            × 1.5
  음수 실적   실적 ≤ −NEG_MIN — |실적|                                  × 1.5
  저확신 귀속 확신도 0.8 미만 전표가 LOWCONF_MIN 이상 — 그 전표 금액       × 1.2
  (과다 귀속·음수는 숫자 자체가 틀렸을 수 있어 «설명»보다 먼저 본다.)
한 줄에 이유가 여럿이면 검토 금액은 그중 큰 값(같은 돈을 두 번 세지 않는다), 우선순위는 가중 금액 중 큰 값.

처리됨(resolved)
  사유      차이·과다·음수 이유가 있는 줄에 차이 사유가 적혀 있다
  승인      사람이 «이상 없음»을 눌렀다 — 승인 때 실적과 지금 실적이 다르면(재분석으로 숫자가 바뀜) 다시 연다
  재배정    이 줄의 전표를 다른 사업으로 옮겨 두었고 아직 분석에 반영 전이다(반영 후 숫자로 다시 판정)
저확신만 걸린 줄은 사유가 아니라 승인(또는 재배정)으로 닫는다 — 질문이 «설명»이 아니라 «귀속이 맞나»라서.

판단은 하지 않는다. 고르고 줄 세우기까지가 이 모듈의 일이고, 숫자는 바꾸지 않는다.
"""
import re

from rapidfuzz import fuzz

from .alerts import HIGH_AMT, NEG_MIN
from .db import is_variance, norm_text

LOW_CONF = 0.8                 # 학습 자동확정 기준(LEARN_MIN_CONF)과 같은 선 — 그 아래는 사람이 본다
LOWCONF_MIN = 10_000           # 저확신 전표 금액 합이 1천만 원(천원 단위) 이상인 줄만
WEIGHTS = {"overload": 1.5, "negative": 1.5, "lowconf": 1.2, "variance": 1.0}
LABELS = {"overload": "과다 귀속", "negative": "음수 실적", "lowconf": "저확신 귀속", "variance": "차이 사유"}
COVER_TARGET = 0.80
MANUAL_HINT = 0.50            # 귀속 금액의 이 이상을 사람이 재배정했으면 «사람이 붙인 전표» 힌트
ACK_TOL = 1.0                  # 승인 때 실적과 1천원 넘게 다르면 승인 무효(재분석으로 바뀐 숫자)

SUGGEST_MIN = 0.75             # 추천 재배정: 전표 글자↔사업명 유사도가 이 이상이고
SUGGEST_MARGIN = 0.15          #   지금 붙은 사업보다 이만큼 더 닮았을 때만 추천한다
# 글자는 닮아도 설비·연도가 다르면 다른 사업이다(운영 실측 2026-10-27: «GT LTSA 1월 비용인식» →
#   «연료전지 LTSA» 0.72, «2025년 판교 정기점검» → «2024년 판교 정기점검» 0.63). 양쪽에 다 적혀 있고
#   겹치지 않으면 추천하지 않는다. 한쪽에만 있으면 판단하지 않는다.
EQUIP_WORDS = {
    "GT": ("GT", "가스터빈", "G/T"), "ST": ("ST", "증기터빈", "S/T"), "연료전지": ("연료전지", "FC"),
    "SRF": ("SRF",), "DH": ("DH",), "보일러": ("보일러", "HRSG", "PLB", "BOILER"),
    "전기": ("전기",), "기계": ("기계",), "계측": ("계측", "제어"), "건축": ("건축", "건물"),
}
_RE_YEAR = re.compile(r"(?<!\d)(?:20(\d{2})년?|'(\d{2})년?|(\d{2})년)")


def _num(v):
    try:
        f = float(v or 0)
    except (TypeError, ValueError):
        return 0.0
    return 0.0 if f != f else f


def line_key(budget, item, dept, name):
    """차이 사유·승인과 같은 키 순서 (budget, 예산과목, 처지사, 사업명)."""
    return (str(budget), str(item or ""), str(dept or ""), str(name or ""))


def key_str(k):
    return "|".join(k)


def _merge_lines(lines):
    """같은 키(동명 사업)는 합친다 — 사유·승인이 이름으로 붙으므로 화면도 한 줄로 본다."""
    out = {}
    for r in lines:
        dept = r.get("처지사")
        if not dept:
            continue
        k = line_key(r["budget"], r.get("예산과목"), dept, r.get("사업명"))
        g = out.setdefault(k, {"plan": 0.0, "actual": 0.0, "gubun": r.get("구분")})
        g["plan"] += _num(r.get("연예산"))
        g["actual"] += _num(r.get("실적금액"))
        if not str(g["gubun"] or "").startswith("계획") and str(r.get("구분") or "").startswith("계획"):
            g["gubun"] = r.get("구분")
    return out


def _overload_keys(alerts):
    """이상 알림의 «과다 귀속»(사업 행) 키 — 판정 기준을 두 곳에 따로 두지 않는다."""
    return {line_key(a["budget"], a.get("item"), a.get("branch"), a.get("name"))
            for a in alerts or [] if a.get("kind") == "과다 귀속" and a.get("name")}


def _ctx_tags(alerts):
    """과목 단위 알림(급증·예산 초과) → {(budget, 과목, 지사): ["과목 급증 …"]} — 순위에는 안 쓰는 맥락."""
    tags = {}
    for a in alerts or []:
        if a.get("kind") not in ("급증", "예산 초과") or a.get("name") or not a.get("branch"):
            continue
        tags.setdefault((a["budget"], a.get("item") or "", a["branch"]), []).append(
            f"과목 {a['kind']}: {a['text']}")
    return tags


def _basis_hint(bs):
    tot, man = _num(bs.get("total")), _num(bs.get("manual"))
    if tot > 0 and man / tot >= MANUAL_HINT:
        return [f"귀속 금액의 {man / tot * 100:,.0f}%는 사람이 재배정한 전표 — 의도한 귀속이면 승인"]
    return []


def _reasons(plan, actual, lowconf_amt, overload=False):
    rs = []
    if actual <= -NEG_MIN:
        rs.append(("negative", abs(actual), f"실적 {actual:,.0f}천원 — 대체·취소 전표가 붙었는지 보세요"))
    if overload and plan > 0:
        rs.append(("overload", actual - plan,
                   f"계획의 {actual / plan:,.1f}배가 붙었어요 — 다른 사업 전표가 섞였을 수 있어요"))
    elif is_variance(plan, actual):
        if actual == 0:
            text = "미시행 — 계획 전액이 집행되지 않았어요"
        else:
            text = f"계획보다 {abs(actual - plan):,.0f}천원 {'더' if actual > plan else '덜'} 집행했어요"
        rs.append(("variance", abs(actual - plan), text))
    if lowconf_amt >= LOWCONF_MIN:
        rs.append(("lowconf", lowconf_amt, f"확신도 0.8 미만 전표 {lowconf_amt:,.0f}천원 — 귀속이 맞는지 보세요"))
    return rs


def build_items(lines, basis=None, notes=None, acks=None, moved=None, alerts=None):
    """사업 줄 → 검토 항목(이유가 하나라도 있는 줄만).

    lines   [{budget, 처지사, 예산과목, 사업명, 연예산, 실적금액, 구분}] (천원)
    basis   dbm.basis_by_line(...)       {line_key: {"total", "lowconf", "manual"}} (천원)
    notes   dbm.variance_notes(...)      {line_key: {"note", ...}}
    acks    dbm.review_acks(...)         {line_key: {"actual", "operator", "updated_at"}}
    moved   {line_key, ...}              재배정 저장·분석 반영 전
    alerts  alerts.compute_alerts(...)   과다 귀속 판정 + 과목 단위 맥락 태그
    반환: 미처리 먼저 우선순위 큰 순, 처리된 것은 뒤(같은 순서 규칙). 미처리에는 rank(1부터).
    """
    basis, notes, acks, moved = basis or {}, notes or {}, acks or {}, moved or set()
    ctx, over = _ctx_tags(alerts), _overload_keys(alerts)
    items = []
    for k, g in _merge_lines(lines).items():
        plan, actual = g["plan"], g["actual"]
        bs = basis.get(k) or {}
        rs = _reasons(plan, actual, _num(bs.get("lowconf")), k in over)
        if not rs:
            continue
        budget, item, dept, name = k
        amount = max(a for _, a, _ in rs)
        score = max(a * WEIGHTS[c] for c, a, _ in rs)
        codes = {c for c, _, _ in rs}
        note = (notes.get(k) or {}).get("note")
        ack = acks.get(k)
        ack_ok = bool(ack) and abs(_num(ack.get("actual")) - actual) <= ACK_TOL
        explainable = bool(codes & {"variance", "overload", "negative"})
        if k in moved:
            status = "moved"
        elif ack_ok:
            status = "approved"
        elif note and explainable:
            status = "noted"
        elif ack:
            status = "stale"
        else:
            status = "open"
        items.append({
            "key": key_str(k), "budget": budget, "item": item, "branch": dept, "name": name,
            "gubun": g["gubun"], "plan": round(plan), "actual": round(actual),
            "rate": round(actual / plan * 100, 1) if plan > 0 else None,
            "dir": None if plan <= 0 else ("over" if actual > plan else "under"),
            "amount": round(amount), "score": round(score),
            "risk": "높음" if amount >= HIGH_AMT else "보통",
            "reasons": [{"code": c, "label": LABELS[c], "amount": round(a), "text": t} for c, a, t in rs],
            "ctx": ctx.get((budget, item, dept), []) + _basis_hint(bs),
            "note": note, "ack": ack if ack else None,
            "status": status, "resolved": status in ("moved", "approved", "noted"),
            "needsNote": explainable,
        })
    items.sort(key=lambda x: (x["resolved"], -x["score"], -x["amount"], x["key"]))
    n = 0
    for it in items:
        if not it["resolved"]:
            n += 1
            it["rank"] = n
        else:
            it["rank"] = None
    return items


def coverage_curve(items):
    """미처리 항목을 순위대로 볼 때 «남은 검토 금액»의 누적 비율(0~1) 목록."""
    open_amt = [it["amount"] for it in items if not it["resolved"]]
    total = sum(open_amt)
    out, acc = [], 0.0
    for a in open_amt:
        acc += a
        out.append(round(acc / total, 4) if total else 1.0)
    return out


def summarize(items):
    curve = coverage_curve(items)
    total_amt = sum(it["amount"] for it in items)
    res_amt = sum(it["amount"] for it in items if it["resolved"])
    n80 = next((i + 1 for i, c in enumerate(curve) if c >= COVER_TARGET - 1e-9), len(curve))
    counts = {c: 0 for c in LABELS}
    for it in items:
        if not it["resolved"]:
            for r in it["reasons"]:
                counts[r["code"]] += 1
    return {
        "total": len(items), "open": len(curve), "resolved": len(items) - len(curve),
        "high_open": sum(1 for it in items if not it["resolved"] and it["risk"] == "높음"),
        "amount_total": round(total_amt), "amount_resolved": round(res_amt),
        "amount_open": round(total_amt - res_amt),
        "progress": round(res_amt / total_amt, 4) if total_amt else 1.0,
        "n80": n80, "cover_target": COVER_TARGET, "counts": counts,
    }


# ── 추천 재배정 ────────────────────────────────────────────────────────

def _sim(a, b):
    a, b = norm_text(a), norm_text(b)
    if not a or not b:
        return 0.0
    return fuzz.WRatio(a, b) / 100.0


def _equip(s):
    u = str(s or "").upper()
    return {k for k, words in EQUIP_WORDS.items()
            if any(re.search(rf"(?<![A-Z]){re.escape(w.upper())}(?![A-Z])", u) for w in words)}


def _years(s):
    return {next(g for g in m.groups() if g) for m in _RE_YEAR.finditer(str(s or ""))}


def conflicts(text, name):
    """전표 글자와 사업명이 설비나 연도로 서로 다른 것을 가리키는가(둘 다 적혀 있고 겹치지 않음)."""
    for f in (_equip, _years):
        a, b = f(text), f(name)
        if a and b and not (a & b):
            return True
    return False


def suggest(vouchers, current, candidates):
    """전표마다 «더 닮은 계획 사업»을 고른다(같은 예산·지사·과목 안).

    vouchers   [{erp_row_id, 텍스트, 금액천원, ...}]
    current    지금 붙은 사업명
    candidates [{"name", "plan", "actual"}] — 지금 사업은 빼고 넘긴다
    반환: 전표 dict 에 "suggest": {"target", "sim", "cur_sim", "remain", "why"} | None 을 붙인 목록.
    근거는 글자 유사도와 잔액(계획 − 실적)이 전부라, 화면에 그대로 «왜»로 보여 줄 수 있다.
    """
    out = []
    for v in vouchers:
        text = v.get("텍스트")
        cur = _sim(text, current)
        best = None
        for c in candidates:
            if conflicts(text, c["name"]):
                continue
            s = _sim(text, c["name"])
            remain = _num(c.get("plan")) - _num(c.get("actual"))
            fits = remain >= abs(_num(v.get("금액천원")))
            rank = s + (0.03 if fits else 0.0)        # 잔액이 받아 줄 수 있으면 아주 조금 앞으로
            if best is None or rank > best[0]:
                best = (rank, s, c, remain, fits)
        sug = None
        if best and best[1] >= SUGGEST_MIN and best[1] >= cur + SUGGEST_MARGIN:
            _, s, c, remain, fits = best
            why = f"전표 글자 유사도 {s:.2f} (지금 사업 {cur:.2f})"
            why += f" · 잔액 {remain:,.0f}천원" + (" 충분" if fits else " 부족")
            sug = {"target": c["name"], "sim": round(s, 2), "cur_sim": round(cur, 2),
                   "remain": round(remain), "why": why}
        out.append({**v, "suggest": sug})
    return out


def suggest_incoming(name, sibling_vouchers):
    """덜 집행된 사업 쪽에서 보기: 같은 과목의 다른 사업에 붙었지만 이 사업 이름을 더 닮은 전표.

    sibling_vouchers [{erp_row_id, 텍스트, 금액천원, "from": 지금 사업명}]
    """
    out = []
    for v in sibling_vouchers:
        if conflicts(v.get("텍스트"), name):
            continue
        s, cur = _sim(v.get("텍스트"), name), _sim(v.get("텍스트"), v.get("from"))
        if s >= SUGGEST_MIN and s >= cur + SUGGEST_MARGIN:
            out.append({**v, "sim": round(s, 2), "cur_sim": round(cur, 2),
                        "why": f"전표 글자 유사도 {s:.2f} (지금 붙은 «{v.get('from')}» {cur:.2f})"})
    out.sort(key=lambda x: (-x["sim"], -abs(_num(x.get("금액천원")))))
    return out
