# -*- coding: utf-8 -*-
"""사업 실적 묻기 — «25년 파주지사 정기점검 보수 얼마 들었어?», «파주 터빈 점검 비용?», «몇 년도에 무슨 공사 했어?».

질문에서 연도·지사·낱말을 뽑아 «분석이 끝난 사업 줄(biz_line, 연도별 최신 실행)»을 찾는다.
숫자는 그 줄의 실적금액·연예산(천원) 그대로 — 여기서 새로 계산하는 것은 합계뿐이다.
낱말은 동의어로 넓힌다(«터빈» = GT·가스터빈·ST·증기터빈). 모든 낱말이 사업명에 들어간 줄만 답한다
— 하나만 걸린 줄로 «비슷한 사업»을 지어 말하지 않는다(숫자가 틀리면 앱의 강점이 무너진다).
"""
import re

# 질문 낱말 → 사업명에서 찾을 표기(소문자·띄어쓰기 없음)
SYNONYMS = {
    # «st»·«gen» 같은 짧은 영문은 다른 낱말 속에 섞여(system·cost) 넣지 않는다
    "터빈": ("터빈", "gt", "가스터빈", "증기터빈"),
    "가스터빈": ("가스터빈", "gt"),
    "증기터빈": ("증기터빈",),
    "보일러": ("보일러", "hrsg", "배열회수"),
    "배열회수보일러": ("배열회수", "hrsg"),
    "점검": ("점검", "정비"),
    "정비": ("정비", "점검"),
    "보수": ("보수", "수선", "수리"),
    "수리": ("수리", "보수", "수선"),
    "장기유지보수": ("ltsa", "장기유지보수"),
    "ltsa": ("ltsa", "장기유지보수"),
}
# 묻는 말 — 낱말에서 뺀다
STOP = {"얼마", "얼마나", "들었", "들었어", "들었나", "들어갔", "썼", "썼어", "쓴", "쓰인", "쓴돈", "비용", "금액", "돈",
        "실적", "실적이", "집행", "집행액", "했을", "할", "때", "한", "적", "있어", "있었어", "있나", "있었나", "몇", "년도",
        "언제", "무슨", "어떤", "어느", "공사", "사업", "공사는", "사업은", "했어", "했었어", "했던", "했나", "했지", "해",
        "알려줘", "알려", "줘", "좀", "그", "거", "것", "건", "중", "총", "전체", "모두", "다", "들", "이력", "보여줘", "뭐",
        "뭐야", "있는지", "했는지", "하는", "드는", "든", "지사", "년", "올해", "작년", "재작년", "작년에", "올해에"}
PARTICLES = ("에서는", "에서", "에는", "으로", "할때", "했을때", "에", "은", "는", "이", "가", "을", "를", "의", "로", "도", "때", "요")
COST_CUES = ("얼마", "비용", "들었", "들어갔", "썼", "쓴돈", "쓰인", "금액", "집행액", "실적이", "돈")
HISTORY_CUES = ("한적", "했었", "했던", "몇년도", "몇년에", "이력", "언제했", "있었어", "했나", "무슨공사", "어떤공사", "무슨사업", "어떤사업")
ASK_STEMS = COST_CUES + HISTORY_CUES + ("몇년", "한적", "언제", "알려", "있어", "있었")
TABLE_ROWS = 8


def _norm(s):
    return re.sub(r"[\s.,!?~·…'\"«»()\[\]{}:;/\\\-_#]+", "", str(s or "").lower())


def _short_dept(name):
    return re.sub(r"(지사|사업소|사업처|건설처|발전처|본부|처)$", "", name)


def find_dept(q, depts):
    """질문에 든 지사(정식 이름). «파주지사»·«파주» 모두. 가장 긴 것."""
    n = _norm(q)
    hits = [d for d in depts if _norm(d) in n or (len(_short_dept(d)) >= 2 and _norm(_short_dept(d)) in n)]
    return max(hits, key=len) if hits else None


def find_years(q, base_year=None):
    """«2025», «25년(도)», «작년», «23~25년» → 연도 목록(없으면 [])."""
    ys = re.findall(r"(?<!\d)(20\d{2})(?!\d)", q)
    ys += [str(2000 + int(m)) for m in re.findall(r"(?<![\d])(\d{2})\s*년", q)]
    n = _norm(q)
    if base_year and str(base_year).isdigit():
        b = int(base_year)
        if "재작년" in n:
            ys.append(str(b - 2))
        elif "작년" in n or "지난해" in n or "전년도" in n:
            ys.append(str(b - 1))
        if "올해" in n or "금년" in n:
            ys.append(str(b))
    return sorted(set(ys))


def keywords(q, dept=None):
    """묻는 말·연도·지사·조사를 빼고 남은 낱말들."""
    t = re.sub(r"(?<!\d)(20\d{2}|\d{2})\s*년도?", " ", q)
    if dept:
        for d in (dept, _short_dept(dept)):
            if len(d) >= 2:
                t = t.replace(d, " ")
    out = []
    for w in re.split(r"[\s,.!?~·…'\"«»()\[\]{}:;/\\]+", t.lower()):
        for _ in range(2):
            for p in PARTICLES:
                if len(w) > len(p) + 1 and w.endswith(p):
                    w = w[: -len(p)]
                    break
        if (not w or w in STOP or w in PARTICLES or w.isdigit()
                or w.startswith(ASK_STEMS)):                 # «얼마야»·«한적있어»·«몇년도에»
            continue
        out.append(w)
    return out


def _alts(word):
    return SYNONYMS.get(word, (word,))


def _hit(name_n, word):
    return any(a in name_n for a in _alts(word))


def is_history(n):
    """«한 적·몇 년도»면 이력 — 단 «얼마»가 같이 있으면 금액 질문(«어떤 공사에 얼마 들었어?»)."""
    return any(c in n for c in HISTORY_CUES) and not any(c in n for c in COST_CUES)


def is_fact_question(n):
    return any(c in n for c in COST_CUES + HISTORY_CUES)


def won(v):
    """천원 → «12.3억원» / «8,400만원» / «930천원»(읽기 쉽게, 원래 단위는 표에)."""
    v = float(v or 0)
    if abs(v) >= 100000:
        return f"{v / 100000:,.1f}억원"
    if abs(v) >= 10:
        return f"{v / 10:,.0f}만원"
    return f"{v:,.0f}천원"


def search(lines, years, dept, words):
    """조건에 맞는 사업 줄. 낱말은 모두 들어가야 한다(동의어 중 하나)."""
    out = []
    for r in lines:
        if years and r["연도"] not in years:
            continue
        if dept and r["처지사"] != dept:
            continue
        nn = _norm(r["사업명"])
        if all(_hit(nn, w) for w in words):
            out.append(r)
    return out


def answer(q, n, data, base_year=None):
    """사업 실적 답 카드에 넣을 값 — None 이면 이 질문은 여기서 답하지 않는다.

    data = {"lines": [{"연도","예산","처지사","예산과목","사업명","연예산","실적금액"}…], "years": [...], "depts": [...]}
    """
    if not data or not data.get("lines"):
        return None
    dept = find_dept(q, data.get("depts") or [])
    years = find_years(q, base_year)
    words = keywords(q, dept)
    history = is_history(n)
    if not words:
        # «어떤 공사에 얼마 들었어?» → 그 해 실적이 큰 사업 / «파주 무슨 공사 한 적 있어?» → 연도별 요약
        return _overview(data["lines"], years, dept) if history and dept else _top(data["lines"], years or [str(base_year)] if base_year else years, dept)
    rows = search(data["lines"], years, dept, words)
    scope = " · ".join(x for x in (dept or "전체 지사", "·".join(years) + "년" if years else "모든 연도") if x)
    looked = f"{scope} · «{' '.join(words)}» 들어간 사업으로 봤어요"
    if not rows:
        # 낱말을 하나씩 따로 찾으면 몇 건인지 — 어떤 낱말을 빼고 다시 물으면 될지 알려 준다
        alone = [f"«{w}» {len(search(data['lines'], years, dept, [w]))}건" for w in words] if len(words) > 1 else []
        hint = f" 낱말 하나씩은 {', '.join(alone)} 있어요." if alone else " 낱말을 바꿔 물어봐 주세요(예: «정기점검», «GT», «보수»)."
        return {"text": f"{scope}에서 «{' '.join(words)}» 이(가) 모두 들어간 사업은 못 찾았어요.{hint}",
                "ctx": looked, "table": None, "found": 0}
    if history:
        return _history(data["lines"], years, dept, words, q, rows)
    return _cost(rows, years, dept, words, looked)


def _narrow(table, dept):
    """대화창 폭(약 290px)에 맞게 — 지사를 정해 물었으면 «지사» 칸은 뺀다(모두 같은 값)."""
    if not dept:
        return table
    return [row[:1] + row[2:] for row in table]


def _cost(rows, years, dept, words, looked):
    act = sum(r["실적금액"] or 0 for r in rows)
    plan = sum(r["연예산"] or 0 for r in rows)
    yrs = sorted({r["연도"] for r in rows})
    rows = sorted(rows, key=lambda r: (r["연도"], r["실적금액"] or 0), reverse=True)
    head = ["연도", "지사", "사업", "예산(천원)", "실적(천원)"]
    table = _narrow([head] + [[r["연도"], r["처지사"], r["사업명"], f"{r['연예산'] or 0:,.0f}", f"{r['실적금액'] or 0:,.0f}"]
                              for r in rows[:TABLE_ROWS]], dept)
    yr = f"{yrs[0]}년" if len(yrs) == 1 else f"{yrs[0]}~{yrs[-1]}년"
    who = dept or "전체 지사"
    text = (f"{who} {yr} «{' '.join(words)}» 사업 {len(rows)}건에 실적 {won(act)}이 들었어요"
            f"(예산 {won(plan)}{f', 집행률 {act / plan * 100:.0f}%' if plan else ''}).")
    if len(rows) > TABLE_ROWS:
        text += f" 표는 최근 연도·실적이 큰 순으로 {TABLE_ROWS}건만 보여 줘요."
    if len(yrs) > 1:
        by = {y: sum(r["실적금액"] or 0 for r in rows if r["연도"] == y) for y in yrs}
        text += "\n연도별: " + " · ".join(f"{y} {won(v)}" for y, v in by.items())
    return {"text": text, "ctx": looked, "table": table, "found": len(rows)}


def _history(lines, years, dept, words, q, rows=None):
    rows = rows if rows is not None else search(lines, years, dept, words)
    if not rows:
        return {"text": "그 조건으로 한 사업을 못 찾았어요.", "ctx": "", "table": None, "found": 0}
    rows = sorted(rows, key=lambda r: (r["연도"], r["실적금액"] or 0), reverse=True)
    done = [r for r in rows if (r["실적금액"] or 0) > 0]
    yrs = sorted({r["연도"] for r in done}, reverse=True)
    what = f"«{' '.join(words)}» " if words else ""
    who = dept or "전체 지사"
    if not done:
        return {"text": f"{who}에서 {what}사업은 계획에만 있고 실적(돈이 나간 기록)은 없어요.", "ctx": "",
                "table": None, "found": 0}
    text = f"{who}에서 {what}사업은 {', '.join(y + '년' for y in yrs)}에 했어요(실적이 있는 것 {len(done)}건)."
    head = ["연도", "지사", "사업", "실적(천원)"]
    table = _narrow([head] + [[r["연도"], r["처지사"], r["사업명"], f"{r['실적금액'] or 0:,.0f}"] for r in done[:TABLE_ROWS]], dept)
    if len(done) > TABLE_ROWS:
        text += f" 표는 최근·큰 순 {TABLE_ROWS}건만 보여 줘요."
    scope = f"{who} · {'·'.join(years) + '년' if years else '모든 연도'}"
    return {"text": text, "ctx": f"{scope}{' · «' + ' '.join(words) + '»' if words else ''}으로 봤어요",
            "table": table, "found": len(done)}


def _top(lines, years, dept):
    """낱말 없이 «얼마 들었어» — 그 해(그 지사) 실적이 큰 사업."""
    rows = [r for r in lines if (not years or r["연도"] in years) and (not dept or r["처지사"] == dept)
            and (r["실적금액"] or 0) > 0]
    if not rows:
        return None
    rows.sort(key=lambda r: r["실적금액"] or 0, reverse=True)
    who = dept or "전체 지사"
    yr = "·".join(years) + "년" if years else "모든 연도"
    act = sum(r["실적금액"] or 0 for r in rows)
    head = ["연도", "지사", "사업", "실적(천원)"]
    table = _narrow([head] + [[r["연도"], r["처지사"], r["사업명"], f"{r['실적금액']:,.0f}"] for r in rows[:TABLE_ROWS]], dept)
    return {"text": f"{who} {yr}에 실적이 있는 사업은 {len(rows)}건, 모두 {won(act)}이에요. 큰 순서로 {min(TABLE_ROWS, len(rows))}건이에요. "
                    f"궁금한 공사 이름을 넣어 물어보면 그것만 모아 드려요(예: «{who if dept else '파주지사'} 정기점검 얼마 들었어?»).",
            "ctx": f"{who} · {yr}으로 봤어요", "table": table, "found": len(rows)}


def _overview(lines, years, dept):
    """«○○지사 무슨 공사 한 적 있어?» — 연도별 사업 수·실적 합·가장 큰 사업."""
    rows = [r for r in lines if r["처지사"] == dept and (not years or r["연도"] in years) and (r["실적금액"] or 0) > 0]
    if not rows:
        return {"text": f"{dept}에서 실적이 있는 사업을 못 찾았어요.", "ctx": "", "table": None, "found": 0}
    yrs = sorted({r["연도"] for r in rows}, reverse=True)
    head = ["연도", "사업 수", "실적 합(천원)", "가장 큰 사업"]
    table = [head]
    for y in yrs:
        ys = [r for r in rows if r["연도"] == y]
        big = max(ys, key=lambda r: r["실적금액"] or 0)
        table.append([y, f"{len(ys)}건", f"{sum(r['실적금액'] for r in ys):,.0f}", big["사업명"]])
    return {"text": f"{dept}은(는) {', '.join(y + '년' for y in yrs)}에 실적이 있는 사업이 모두 {len(rows)}건이에요. "
                    f"공사 이름을 넣어 물어보면(예: «{dept} 정기점검 언제 했어?») 그 공사만 연도별로 보여 드려요.",
            "ctx": f"{dept} · 연도별로 봤어요", "table": table, "found": len(rows)}
