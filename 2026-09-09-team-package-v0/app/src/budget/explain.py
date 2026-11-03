# -*- coding: utf-8 -*-
"""근거 설명 자동 초안 — 검토 대기 한 줄을 사람이 읽는 문장으로(2026-10-27, 경진대회 B).

차이 사유를 백지에서 쓰면 담당자가 전표를 다 열어 «무엇이 얼마나»부터 다시 세야 한다. 여기서는
분석 결과에 이미 있는 사실 — 계획·실적, 큰 전표, 전년 같은 사업, 매칭 근거 — 만 모아 문장으로 만든다.
LLM 없이 규칙만 쓴다(폐쇄망 그대로 · 같은 입력이면 같은 문장 · 문장마다 근거 숫자가 있다).

원인은 단정하지 않는다. 전표 글자에 «이월»·«기성»·«정산» 같은 말이 보이면 «추정»으로만 붙이고,
사람이 고치거나 지운 뒤 저장한다. 숫자는 바꾸지 않는다.
"""
import re

from . import review_queue as rqm

TOP_N = 3                    # 상위 전표 몇 건을 문장에 넣나
PREV_MIN_SIM = 0.80          # 전년 «같은 사업» 판정 — 연도 글자를 지운 사업명 유사도
DRAFT_MAX = 500              # 차이 사유 칸 길이(variance_note)
TEXT_MAX = 24                # 문장에 넣는 전표 글자 길이

# 전표 글자 → 원인 «추정». 순서 = 우선순위(먼저 걸린 것 하나만이 아니라 걸린 것 모두, 중복 없이).
HINT_WORDS = (
    (r"이월|전년도|전년분|미지급", "전년 이월분 집행"),
    (r"기성", "기성(분할) 대금 집행"),
    (r"정산|추가\s*정산|설계\s*변경|설변", "정산·설계변경 증액"),
    (r"선급", "선급금 집행"),
    (r"긴급|돌발|고장|파손|복구", "긴급·돌발 정비"),
    (r"취소|반제|역분개|대체", "취소·대체 전표"),
)
_RE_YEARWORD = re.compile(r"(?<!\d)(?:20\d{2}|'\d{2}|\d{2})\s*년(?:도)?|(?<!\d)20\d{2}(?!\d)")


def money(v):
    """천원 → 읽는 돈. 1억 이상은 «12.3억원», 1백만 이상은 «345백만 원», 그 밑은 천원."""
    v = float(v or 0)
    sign = "−" if v < 0 else ""
    a = abs(v)
    if a >= 100_000:
        return f"{sign}{a / 100_000:,.1f}억원"
    if a >= 1_000:
        return f"{sign}{a / 1_000:,.0f}백만 원"
    return f"{sign}{a:,.0f} 천원"


def _text(v):
    t = v.get("텍스트")
    return "" if t is None or (isinstance(t, float) and t != t) else str(t)


def _short(t):
    t = re.sub(r"\s+", " ", "" if t is None or (isinstance(t, float) and t != t) else str(t)).strip()
    return t if len(t) <= TEXT_MAX else t[:TEXT_MAX - 1] + "…"


def strip_year(name):
    return _RE_YEARWORD.sub(" ", str(name or "")).strip()


def prev_match(name, prev_lines):
    """전년 같은 사업 — 같은 지사의 전년 사업 줄에서 연도 글자를 뺀 이름이 가장 닮은 것.

    prev_lines [{"사업명", "실적금액", "연예산"}] (같은 예산·지사, 과목은 해마다 이름이 바뀌어 보지 않는다)
    반환: {"name", "actual", "plan", "sim"} | None
    """
    base = strip_year(name)
    groups = {}
    for r in prev_lines or []:
        n = str(r.get("사업명") or "")
        if not n:
            continue
        g = groups.setdefault(n, {"name": n, "actual": 0.0, "plan": 0.0})
        g["actual"] += rqm._num(r.get("실적금액"))
        g["plan"] += rqm._num(r.get("연예산"))
    best = None
    for g in groups.values():
        a, b = rqm._equip(name), rqm._equip(g["name"])
        if a and b and not (a & b):
            continue                       # 연도가 다른 건 당연 — 설비가 다르면 다른 사업
        s = rqm._sim(base, strip_year(g["name"]))
        if s >= PREV_MIN_SIM and (best is None or s > best["sim"]):
            best = {**g, "sim": round(s, 2)}
    return best


MIX_SHARE = 0.5              # 저확신·재배정 전표가 초과액(또는 실적)의 이 이상이면 추정에 올린다


def _amt(vs):
    return sum(abs(rqm._num(v.get("금액천원"))) for v in vs)


def hints(vouchers, plan=0.0, actual=0.0):
    """원인 «추정» [(label, 전표 수, 금액)] — 전표 글자 낱말 + 귀속 모양(저확신·재배정 비중)."""
    out = []
    for pat, label in HINT_WORDS:
        hit = [v for v in vouchers if re.search(pat, _text(v))]
        if hit:
            out.append((label, len(hit), _amt(hit)))
    excess = actual - plan
    low = [v for v in vouchers if v.get("확신도") is not None and rqm._num(v.get("확신도")) < rqm.LOW_CONF]
    if plan > 0 and excess > 0 and _amt(low) >= MIX_SHARE * excess:
        out.append((f"다른 사업 전표 혼입 가능 — 확신도 낮은 전표가 초과액의 {min(_amt(low) / excess, 1) * 100:,.0f}%",
                    len(low), _amt(low)))
    manual = [v for v in vouchers if str(v.get("근거") or "").startswith("재배정")]
    if actual > 0 and _amt(manual) >= MIX_SHARE * actual:
        out.append((f"사람이 재배정해 모은 전표가 실적의 {min(_amt(manual) / actual, 1) * 100:,.0f}% — 의도한 통합 집행인지 확인",
                    len(manual), _amt(manual)))
    neg = [v for v in vouchers if rqm._num(v.get("금액천원")) < 0]
    if neg and _amt(neg) >= 0.1 * max(abs(actual), 1):
        out.append(("취소·재전기 전표 포함 — 같은 금액이 +/−로 상쇄됐는지 확인", len(neg), -_amt(neg)))
    return out


def _basis_text(vouchers):
    counts = {}
    for v in vouchers:
        b = str(v.get("근거") or "확인 불가")
        counts[b] = counts.get(b, 0) + 1
    parts = [f"{k} {n}건" for k, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))]
    low = [v for v in vouchers if v.get("확신도") is not None and rqm._num(v.get("확신도")) < rqm.LOW_CONF]
    s = "매칭 근거: " + " · ".join(parts[:4]) + (f" 외 {len(parts) - 4}종" if len(parts) > 4 else "")
    if low:
        s += f" (확신도 0.8 미만 {len(low)}건 {money(sum(abs(rqm._num(v.get('금액천원'))) for v in low))})"
    return s


def build(line, vouchers, prev=None):
    """검토 대기 한 줄 → {"facts": [문장], "hints": [추정], "draft": 사유 초안}.

    line      {"plan", "actual", "name", "dir"} — 검토 대기 항목(천원)
    vouchers  이 줄의 전표 전부 [{텍스트, 금액천원, 확신도, 근거}]
    prev      prev_match(...) 결과 | None
    """
    plan, actual = rqm._num(line.get("plan")), rqm._num(line.get("actual"))
    facts = []
    # ① 계획 → 실적
    if plan > 0 and actual == 0:
        head = f"미시행 — 계획 {money(plan)} 전액이 집행되지 않았다."
    elif plan > 0:
        rate = actual / plan * 100
        diff = actual - plan
        head = (f"계획 {money(plan)} 대비 {money(actual)} 집행({rate:,.0f}%, "
                f"{money(abs(diff))} {'초과' if diff > 0 else '미집행'}).")
    else:
        head = f"계획 없이 {money(actual)} 집행(신규)."
    if actual <= -rqm.NEG_MIN:
        head = f"실적이 {money(actual)}로 음수 — 취소·대체 전표가 계획 집행보다 크다."
    facts.append(head)
    # ② 큰 전표
    vs = sorted(vouchers, key=lambda v: -abs(rqm._num(v.get("금액천원"))))
    tot = sum(abs(rqm._num(v.get("금액천원"))) for v in vs)
    if vs and tot > 0:
        top = vs[:TOP_N]
        share = sum(abs(rqm._num(v.get("금액천원"))) for v in top) / tot * 100
        names = ", ".join(f"«{_short(_text(v)) or '전표 글자 없음'}» {money(v.get('금액천원'))}" for v in top)
        lead = f"전표 {len(vs):,}건 중 " if len(vs) > len(top) else f"전표 {len(vs):,}건: "
        facts.append(f"{lead}상위 {len(top)}건({names})이 실적의 {share:,.0f}%." if len(vs) > len(top)
                     else f"{lead}{names}.")
    # ③ 전년
    if prev:
        p_act = prev["actual"]
        if p_act > 0 and actual > 0:
            ratio = actual / p_act
            cmp = f"{ratio:,.1f}배" if ratio >= 1.5 or ratio <= 0.67 else f"{(ratio - 1) * 100:+,.0f}%"
            facts.append(f"전년 같은 사업(«{_short(prev['name'])}») 실적 {money(p_act)} 대비 {cmp}.")
        else:
            facts.append(f"전년 같은 사업(«{_short(prev['name'])}») 실적 {money(p_act)}.")
    # ④ 매칭 근거 — 화면 설명에만(사유 초안에는 넣지 않는다: 사유는 «왜 썼나»이지 «어떻게 붙었나»가 아니다)
    draft = " ".join(facts)
    if vs:
        facts.append(_basis_text(vs))
    hs = hints(vs, plan, actual)
    hint_texts = [f"{label} (전표 {n}건 {money(amt)})" for label, n, amt in hs]
    if hs:
        draft += " 추정 원인: " + ", ".join(label for label, _, _ in hs) + "."
    if len(draft) > DRAFT_MAX:
        draft = draft[:DRAFT_MAX - 1] + "…"
    return {"facts": facts, "hints": hint_texts, "draft": draft}
