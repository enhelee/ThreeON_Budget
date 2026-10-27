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
from . import normalize
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
# 상쇄 짝(2026-10-27): 같은 지사×과목에서 더 쓴 줄 ↔ 덜 쓴 줄. 실측(로컬 2024·2025)으로 차이 줄의
#   85~88%가 반대 방향 줄과 같은 그룹에 있었다 — 사유를 쓰기 전에 «전표가 섞였나»부터 본다.
#   짝이 있다는 사실 자체가 근거라 글자 기준은 SUGGEST_MIN 보다 낮게 둔다.
PAIR_MIN = 0.60                # 덜 쓴 줄 이름과 전표 글자 유사도가 이 이상이고
PAIR_MARGIN = 0.05             #   지금 줄보다 이만큼 더 닮았을 때(금액이 부족분과 딱 맞으면 «덜 닮지 않음»이면 된다)
PAIR_PARTNERS = 3
COMBO_MAX_N = 12               # 묶음 합 찾기에 쓰는 묶음당 전표 수(큰 금액 순) — 2^12 조합까지만 본다              # 화면에 보일 짝 수
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
        rs.append(("negative", abs(actual), f"실적 {actual:,.0f} 천원 — 대체·취소 전표가 붙었는지 보세요"))
    if overload and plan > 0:
        rs.append(("overload", actual - plan,
                   f"계획의 {actual / plan:,.1f}배가 붙었어요 — 다른 사업 전표가 섞였을 수 있어요"))
    elif is_variance(plan, actual):
        if actual == 0:
            text = "미시행 — 계획 전액이 집행되지 않았어요"
        else:
            text = f"계획보다 {abs(actual - plan):,.0f} 천원 {'더' if actual > plan else '덜'} 집행했어요"
        rs.append(("variance", abs(actual - plan), text))
    if lowconf_amt >= LOWCONF_MIN:
        rs.append(("lowconf", lowconf_amt, f"확신도 0.8 미만 전표 {lowconf_amt:,.0f} 천원 — 귀속이 맞는지 보세요"))
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
    merged = _merge_lines(lines)
    gaps = _group_gaps(merged)
    items = []
    for k, g in merged.items():
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
            "pair": _pair_of(k, gaps),
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


def plan_totals(rows):
    """한 지사·과목의 분석 줄 → {사업명: {"name", "plan", "actual"}} (계획 사업만, 신규 제외, 빈 값은 0)."""
    out = {}
    for r in rows:
        if str(r.get("구분") or "").startswith("신규"):
            continue
        c = out.setdefault(r["사업명"], {"name": r["사업명"], "plan": 0.0, "actual": 0.0})
        c["plan"] += _num(r.get("연예산"))
        c["actual"] += _num(r.get("실적금액"))
    return out


def _gaps(lines):
    """{이름: {"plan","actual"}} → (더 쓴 {이름: 초과}, 덜 쓴 {이름: 부족}) — 차이(±20%p 밖) 줄만."""
    over, under = {}, {}
    for n, g in lines.items():
        plan, actual = _num(g.get("plan")), _num(g.get("actual"))
        if not is_variance(plan, actual):
            continue
        if actual > plan:
            over[n] = actual - plan
        elif actual < plan:
            under[n] = plan - actual
    return over, under


def _group_gaps(merged):
    """{(budget, 과목, 지사): {"over", "under", "normal"}} — normal = 그룹 총액이 계획의 ±20%p 안."""
    groups = {}
    for k, g in merged.items():
        groups.setdefault(k[:3], {})[k[3]] = g
    out = {}
    for gk, lines in groups.items():
        over, under = _gaps(lines)
        plan = sum(_num(g["plan"]) for g in lines.values())
        actual = sum(_num(g["actual"]) for g in lines.values())
        out[gk] = {"over": over, "under": under, "normal": not is_variance(plan, actual)}
    return out


def _pair_of(k, gaps):
    """이 줄과 반대 방향으로 벌어진 같은 그룹 줄 — 없으면 None.
    kind  상쇄형: 그룹 총액은 계획대로(돈이 그룹 안에서 자리만 바뀐 모양) · 혼합: 총액도 벌어짐
    offset 짝들로 메울 수 있는 금액 = min(내 갭, 짝 갭 합)."""
    G = gaps.get(k[:3])
    name = k[3]
    if not G:
        return None
    if name in G["over"]:
        mine, other = G["over"][name], G["under"]
    elif name in G["under"]:
        mine, other = G["under"][name], G["over"]
    else:
        return None
    if not other:
        return None
    partners = sorted(other.items(), key=lambda x: (-x[1], x[0]))
    return {"kind": "상쇄형" if G["normal"] else "혼합",
            "partners": [{"name": n, "gap": round(v)} for n, v in partners[:PAIR_PARTNERS]],
            "partner_total": len(partners),
            "offset": round(min(mine, sum(other.values())))}


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
        "pair_open": sum(1 for it in items if not it["resolved"] and it.get("pair")),
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
            why += f" · 잔액 {remain:,.0f} 천원" + (" 충분" if fits else " 부족")
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


def _combo_pick(vs, target):
    """묶음 전표 중 합이 target(±ACK_TOL)인 2건 이상 조합 — 딱 하나일 때만 돌려준다(여럿이면 고를 근거가 없다)."""
    vs = vs[:COMBO_MAX_N]
    hits = []
    for mask in range(1, 1 << len(vs)):
        if mask & (mask - 1) == 0:          # 1건은 단건 금액 일치가 맡는다
            continue
        pick = [v for i, v in enumerate(vs) if mask >> i & 1]
        if abs(sum(_num(v.get("금액천원")) for v in pick) - target) <= ACK_TOL:
            hits.append(pick)
            if len(hits) > 1:
                return None
    return hits[0] if hits else None


def _combos(over, under, by_line, used):
    """월별·분납 묶음(learn_key 같음 — 회차·월·연도만 다른 글자) 안에서 합이 부족분과 같은 조합.
    yield (src, dst, [전표], sim, cur). 서로 다른 묶음은 섞지 않는다 — 우연히 합이 맞는 것을 막는다."""
    for src in sorted(over):
        series = {}
        for v in by_line.get(src) or []:
            k = normalize.learn_key(v.get("텍스트"))
            if k and _num(v.get("금액천원")) > 0 and int(v.get("erp_row_id") or 0) not in used:
                series.setdefault(k, []).append(v)
        for vs in series.values():
            if len(vs) < 2:
                continue
            text = vs[0].get("텍스트")
            cur = _sim(text, src)
            for dst in sorted(under, key=lambda d: (-under[d], d)):
                if conflicts(text, dst):
                    continue
                s = _sim(text, dst)
                if s < cur:
                    continue
                pick = _combo_pick(sorted(vs, key=lambda v: (-_num(v.get("금액천원")), int(v.get("erp_row_id") or 0))),
                                   under[dst])
                if pick:
                    yield src, dst, pick, s, cur
                    break


def pair_moves(lines, by_line):
    """한 지사·과목 안에서 «더 쓴 줄의 전표 → 덜 쓴 줄» 이동 추천.

    lines   {사업명: {"plan", "actual"}} (천원, 계획 사업만)
    by_line {사업명: [{erp_row_id, 텍스트, 금액천원, ...}]}
    전표가 옮겨 갈 수 있는 조건 — 둘 다 차이 줄이고, 설비·연도가 충돌하지 않고,
      금액이 받을 줄의 남은 부족분과 보낼 줄의 남은 초과분 안이며, 다음 중 하나(이 순서로 채운다):
      ① 금액 일치: 남은 부족분과 금액이 같고(ACK_TOL), 글자가 지금 줄을 더 닮지 않았다
      ② 묶음 합: 월별·분납 묶음 안에서 합이 남은 부족분과 같은 조합이 딱 하나(글자 조건은 ①과 같다)
      ③ 글자: 받을 줄 이름 유사도 PAIR_MIN 이상, 지금 줄보다 PAIR_MARGIN 이상 더 닮았다
    한 전표는 한 번만. 같은 단계 안에서는 유사도 큰 순.
    반환: [{erp_row_id, from, target, 금액천원, 텍스트, 전기일, sim, cur_sim, exact, combo, why}]
          combo = 묶음 번호(1부터, 같은 번호는 함께 옮길 전표) | None
    """
    over, under = _gaps(lines)
    if not over or not under:
        return []
    cands = []
    for src, excess in over.items():
        for v in by_line.get(src) or []:
            amt = _num(v.get("금액천원"))
            if amt <= 0 or amt > excess + ACK_TOL:
                continue
            text = v.get("텍스트")
            cur = _sim(text, src)
            for dst, short in under.items():
                if amt > short + ACK_TOL or conflicts(text, dst):
                    continue
                s = _sim(text, dst)
                exact = abs(amt - short) <= ACK_TOL and s >= cur
                if exact or (s >= PAIR_MIN and s >= cur + PAIR_MARGIN):
                    cands.append((not exact, -s, -amt, int(v.get("erp_row_id") or 0), src, dst, v, s, cur, exact))
    cands.sort(key=lambda c: c[:4])
    left_over, left_under, used, out = dict(over), dict(under), set(), []

    def take(v, src, dst, s, cur, exact, combo, why):
        amt = _num(v.get("금액천원"))
        rid = int(v.get("erp_row_id") or 0)
        used.add(rid)
        left_over[src] -= amt
        left_under[dst] -= amt
        out.append({"erp_row_id": rid, "from": src, "target": dst, "금액천원": round(amt),
                    "텍스트": v.get("텍스트"), "전기일": v.get("전기일"),
                    "sim": round(s, 2), "cur_sim": round(cur, 2), "exact": exact, "combo": combo,
                    "why": why + f" · «{src}» 초과 {over[src]:,.0f} 천원"})

    def fits(amt, src, dst):
        return amt <= left_over[src] + ACK_TOL and amt <= left_under[dst] + ACK_TOL

    for _, _, _, rid, src, dst, v, s, cur, exact in cands:          # ① 금액 일치
        if exact and rid not in used and fits(_num(v.get("금액천원")), src, dst):
            take(v, src, dst, s, cur, True, None, f"«{dst}» 부족분 {under[dst]:,.0f} 천원과 금액 일치")
    n = 0
    for src, dst, pick, s, cur in _combos(over, left_under, by_line, used):   # ② 묶음 합
        total = sum(_num(v.get("금액천원")) for v in pick)
        if any(int(v.get("erp_row_id") or 0) in used for v in pick) or not fits(total, src, dst):
            continue
        n += 1
        for v in pick:
            take(v, src, dst, s, cur, False, n,
                 f"같은 계약 월별·분납 {len(pick)}건 합 {total:,.0f} 천원 = «{dst}» 부족분")
    for _, _, _, rid, src, dst, v, s, cur, exact in cands:          # ③ 글자
        if not exact and rid not in used and fits(_num(v.get("금액천원")), src, dst):
            take(v, src, dst, s, cur, False, None, f"전표 글자 유사도 {s:.2f} (지금 줄 {cur:.2f})")
    return out
