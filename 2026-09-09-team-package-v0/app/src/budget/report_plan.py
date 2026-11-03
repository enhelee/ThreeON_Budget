# -*- coding: utf-8 -*-
"""한글(hwpx) 보고서 — 「[붙임2] 열원시설 유지보수예산 집행실적 및 계획」(5월, 유지보수 실적·계획 첨부).

2월용(report_hwpx 의 집행성과분석)과 같은 길을 쓴다: 입력값 → 양식 채우기 → hwpx / 웹 미리보기.
다른 점은 표가 18개라는 것 — 그래서 입력값의 중심을 «과목 × 연도» 한 장(matrix)으로 둔다.
  과목마다  Y-2·Y-1·Y 년의 배정·실적 + Y+1 년 배정
3개년 실적(표8·9), 당해 집행률(표10~12), 다음해 계획(표16~18), 3개년 비교(표7)가 모두 이 한 장에서
나오므로, 한 칸을 고치면 그 숫자를 쓰는 모든 표가 같이 바뀐다.
3개년 합계표(표7)만은 과거 보고서 값(투자비 포함 등)과 맞추려고 칸별로 덮어쓸 수 있다(over).
정비등급표(표6·15)는 중장기 예측의 지사별 등급(site_grade)을 처음 값으로 쓴다.
"""
import re

from . import report_hwpx as rh
from .report_hwpx import E, Q, n0, n1, rate, sgn, tri, _num

EOK = rh.EOK

# (행 키, 양식에 나오는 이름들, 앱 예산과목, 과목명 안의 낱말) — 양식마다 표기가 달라 이름을 여럿 둔다
PLAN_ROWS = {
    "손익": [
        ("정기점검", ["정기점검보수", "열원정기점검"], ["수선유지비-열원정기점검"], []),
        ("경상정비", ["경상정비공사/용역", "열원경상정비"], ["수선유지비-열원경상정비"], []),
        ("유지보수용역", ["유지보수용역/진단"], ["수선유지비-열원정기유지보수"], []),
        ("설비개선", ["설비개선/보완"], ["수선유지비-열원보완및개선"], []),
        ("건물구축물", ["건물/구축물"], ["수선유지비-건물/구축물"], []),
        ("비저장품", ["비저장품(보수자재)"], [], ["비저장품"]),
        ("소모품", ["소모품(자재공기구)"], [], ["소모품"]),
        ("지급수수료", ["지급수수료/열원점검"], ["지급수수료-열원점검수수료"], []),
    ],
    "자본": [
        ("건물구축물", ["건물/구축물"], ["건물", "구축물"], []),
        ("기계장치", ["기계장치"], ["기계장치"], []),
        ("공구와기구", ["공구와기구"], ["공구와기구-열원시설공기구"], []),
        ("자산화예비품", ["자산화예비품"], ["건설중인자산-자산화예비품"], []),
        ("재생고온부품", ["재생고온부품"], ["건설중인자산-재생고온부품"], []),
        ("저장품", ["저장품(열원)"], ["저장품-열원(보수)"], []),
        ("열원정기점검", ["외주비-열원정기점검"], ["외주비-열원정기점검"], []),
        ("열원공사비", ["외주비-열원공사비"], ["외주비-열원공사비"], []),
        ("열원기술용역비", ["외주비-열원기술용역비"], ["외주비-열원기술용역비"], []),
        ("열원자재비", ["재료비-열원자재비"], ["재료비-열원자재비"], []),
    ],
}
# 원인 문장 머리 이름
SHORT = {"정기점검": "정기점검", "경상정비": "경상정비", "유지보수용역": "유지보수용역", "설비개선": "설비개선",
         "건물구축물": "건물/구축물", "비저장품": "비저장품", "소모품": "소모품", "지급수수료": "지급수수료",
         "기계장치": "기계장치", "공구와기구": "공구와기구", "자산화예비품": "예비품", "재생고온부품": "고온부품",
         "저장품": "저장품", "열원정기점검": "열원정기점검", "열원공사비": "열원공사비",
         "열원기술용역비": "기술용역비", "열원자재비": "열원자재비"}
GRADE_SITES = ["화성", "판교", "파주", "삼송", "동탄", "광교", "양산", "대구", "청주", "수원", "강남"]
GROUP_HEADS = {"수선유지비", "자산", "예비품", "건가"}


def _row_of(budget):
    out = {}
    for key, _, subs, kws in PLAN_ROWS[budget]:
        for s in subs:
            out[s] = key
    return out, [(kw, key) for key, _, _, kws in PLAN_ROWS[budget] for kw in kws]


def _match(budget, subject):
    exact, kws = _row_of(budget)
    if subject in exact:
        return exact[subject]
    return next((key for kw, key in kws if kw in str(subject)), None)


def _norm(name):
    return re.sub(r"\s+|\(점유율\)", "", name or "")


def _label_index(budget):
    """양식의 행 이름(공백·«(점유율)» 뺀 것) → 행 키."""
    return {_norm(n): key for key, names, _, _ in PLAN_ROWS[budget] for n in names}


# ───────────────────────── 1) 입력값 ─────────────────────────

def build_plan_inputs(conn, year):
    from . import db as dbm
    y = int(year)
    years = [str(y - 2), str(y - 1), str(y)]
    nxt = str(y + 1)
    warnings = []
    matrix = {b: [{"key": key, "label": names[0], "v": {yy: {"배정": 0.0, "실적": 0.0} for yy in years} | {nxt: {"배정": 0.0}}}
                  for key, names, _, _ in PLAN_ROWS[b]] for b in ("손익", "자본")}
    idx = {b: {r["key"]: r for r in matrix[b]} for b in matrix}
    unmapped = set()
    sources = {}
    for yy in years:
        rows, sources[yy] = rh.year_rows(conn, yy)
        for row in rows:
            key = _match(row["budget"], row["예산과목"])
            if key is None:
                unmapped.add(f"{row['budget']}·{row['예산과목']}")
                continue
            idx[row["budget"]][key]["v"][yy]["배정"] += row["배정"] / EOK
            idx[row["budget"]][key]["v"][yy]["실적"] += row["실적"] / EOK
    plan = dbm.load_plan_df(conn, nxt)
    plan_budgets = set()
    if plan is not None:
        for _, row in plan.iterrows():
            code = str(row.get("예산코드") or "")
            b = "손익" if code.startswith("6") else "자본" if code[:1] in ("1", "2") else None
            for bb in ([b] if b else ("손익", "자본")):
                key = _match(bb, row["예산과목"])
                if key:
                    idx[bb][key]["v"][nxt]["배정"] += _num(row["연예산"]) / EOK
                    plan_budgets.add(bb)
                    break
            else:
                unmapped.add(f"{nxt}계획·{row['예산과목']}")
    warnings += rh.source_note(sources)
    for b in ("손익", "자본"):
        if b not in plan_budgets:
            warnings.append(f"{nxt}년 {b} 예산계획이 앱에 없습니다 — 다음해 계획표(배정)의 {b} 칸을 직접 넣어 주세요.")
    if unmapped:
        warnings.append(f"보고서 행에 없는 예산과목 {len(unmapped)}개는 빠졌습니다 — {', '.join(sorted(unmapped))}")
    warnings.append("건가의 열원공사비·기술용역비·자재비(옛 투자비)는 앱 분석에 없을 수 있습니다 — 보고서 값으로 확인해 주세요.")

    grades = {str(g): {s: "" for s in GRADE_SITES} for g in range(y - 2, y + 3)}
    try:
        base = conn.execute("SELECT MAX(base_year) FROM site_grade").fetchone()[0]
        if base:
            for site, yr, gr in conn.execute("SELECT 사업장, 연도, 등급 FROM site_grade WHERE base_year=?", (base,)):
                short = next((s for s in GRADE_SITES if str(site).startswith(s)), None)
                if short and str(yr) in grades:
                    grades[str(yr)][short] = gr
    except Exception:
        conn.rollback() if hasattr(conn, "rollback") else None
    if not any(v for g in grades.values() for v in g.values()):
        warnings.append("정비등급 자료가 없습니다 — 정비등급표를 직접 채워 주세요.")

    inputs = {"year": str(y), "matrix": matrix, "over": {}, "grades": grades, "warnings": warnings}
    inputs["texts"] = auto_texts(inputs)
    return inputs


TEXT_KEYS = ("box5_0", "box5_1", "box5_2", "box14_0", "box14_1", "h0", "h1", "h2", "h6", "h7", "a3", "a4", "a5")
BULLET_KEYS = ("g3", "g4", "g7")


def normalize_inputs(raw, year):
    raw = raw if isinstance(raw, dict) else {}
    y = int(year)
    years = [str(y - 2), str(y - 1), str(y)]
    nxt = str(y + 1)
    num = rh._num_of
    text = rh._text_of
    mraw = raw.get("matrix") or {}
    matrix = {}
    for b, rows in PLAN_ROWS.items():
        got = {r.get("key"): r for r in (mraw.get(b) or []) if isinstance(r, dict)}
        matrix[b] = []
        for key, names, _, _ in rows:
            v = (got.get(key) or {}).get("v") or {}
            vv = {yy: {"배정": num((v.get(yy) or {}).get("배정")), "실적": num((v.get(yy) or {}).get("실적"))} for yy in years}
            vv[nxt] = {"배정": num((v.get(nxt) or {}).get("배정"))}
            matrix[b].append({"key": key, "label": names[0], "v": vv})
    over = {}
    for k, v in (raw.get("over") or {}).items():
        if re.fullmatch(r"\d{4}\.(손익|자본)\.(배정|실적)", str(k)) and v not in (None, ""):
            over[k] = num(v)
    graw = raw.get("grades") or {}
    grades = {str(g): {s: text((graw.get(str(g)) or {}).get(s))[:12] for s in GRADE_SITES} for g in range(y - 2, y + 3)}
    tx = raw.get("texts") or {}
    texts = {k: text(tx.get(k)).strip() for k in TEXT_KEYS}
    for k in BULLET_KEYS:
        texts[k] = [rh._split_label(text(b.get("label")), text(b.get("body")))
                    for b in (tx.get(k) or [])[:rh.BULLETS_MAX] if isinstance(b, dict)]
    return {"year": str(y), "matrix": matrix, "over": over, "grades": grades, "texts": texts}


# ───────────────────────── 2) 계산 ─────────────────────────

def _sum(inputs, budget, yy, k):
    return sum(r["v"][yy].get(k, 0) or 0 for r in inputs["matrix"][budget])


def tot3(inputs, yy, budget, k):
    """표7·10·16 의 손익·자본 합 — 덮어쓴 값(over)이 있으면 그것."""
    return inputs["over"].get(f"{yy}.{budget}.{k}", _sum(inputs, budget, yy, k))


def _chg(cur, prev, pct_fmt=n1):
    d = cur - prev
    if abs(rh._r(d)) < 0.5 and abs(rh._r(prev)) < 0.5:
        return "- <->"
    if abs(rh._r(prev)) < 0.5:
        return sgn(d)
    if abs(rh._r(d)) < 0.5:
        return "- <->" if abs(d) < 1e-9 else f"0 <0%>"
    return f"{sgn(d)} <{sgn(d / prev * 100, pct_fmt)}%>"


def auto_texts(inputs):
    y = int(inputs["year"])
    yy, ny = y % 100, (y + 1) % 100
    Y, P, N = str(y), str(y - 1), str(y + 1)
    T = lambda yr, b, k: tot3(inputs, yr, b, k)
    act = {b: T(Y, b, "실적") for b in ("손익", "자본")}
    pact = {b: T(P, b, "실적") for b in ("손익", "자본")}
    tot, ptot = sum(act.values()), sum(pact.values())
    d = tot - ptot
    pct = lambda a, b: (a - b) / b * 100 if b else 0
    plan = {b: T(Y, b, "배정") for b in ("손익", "자본")}
    r_all = rate(sum(plan.values()), tot) or 0
    rr = {b: rate(plan[b], act[b]) or 0 for b in plan}
    nplan = {b: _sum(inputs, b, N, "배정") for b in ("손익", "자본")}
    nd = sum(nplan.values()) - sum(plan.values())

    def row(b, key):
        return next(r for r in inputs["matrix"][b] if r["key"] == key)

    def grp(b, keys, yr, k="실적"):
        return sum(row(b, kk)["v"][yr].get(k, 0) for kk in keys)

    def ratio(cur, prev):
        """«(+19%)» — 전년이 0이면 비율 대신 «(신규)»."""
        return f"({sgn(pct(cur, prev))}%)" if abs(prev) >= 0.05 else "(신규)"

    def piece(name, cur, prev, unit="억원"):
        dd = cur - prev
        return f"{name} {n0(abs(dd))}{unit}{ratio(cur, prev)} {'증가' if dd >= 0 else '감소'}"

    son_items = [k for k, *_ in PLAN_ROWS["손익"] if k != "지급수수료"]
    a3 = (f"전년대비 {piece('수선유지비', grp('손익', son_items, Y), grp('손익', son_items, P))}, "
          f"{piece('지급수수료', grp('손익', ['지급수수료'], Y), grp('손익', ['지급수수료'], P))}로 "
          f"전체 손익예산 {n0(abs(act['손익'] - pact['손익']))}억({sgn(pct(act['손익'], pact['손익']))}%) "
          f"{'증가' if act['손익'] >= pact['손익'] else '감소'}")
    gj = {"자산": ["건물구축물", "기계장치", "공구와기구"], "예비품": ["자산화예비품", "재생고온부품", "저장품"],
          "건가": ["열원정기점검", "열원공사비", "열원기술용역비", "열원자재비"]}
    a4 = ("전년대비 " + ", ".join(piece(g, grp("자본", ks, Y), grp("자본", ks, P), "억") for g, ks in gj.items())
          + f"로 총 자본예산 {n0(abs(act['자본'] - pact['자본']))}억 {'증가' if act['자본'] >= pact['자본'] else '감소'}"
          f"({sgn(pct(act['자본'], pact['자본']))}%)")
    prev_rate = rate(T(P, "손익", "배정") + T(P, "자본", "배정"), ptot) or 0
    a5 = (f"‘{yy}년 예산 집행률은 전체 {n0(r_all)}%(잔액: {n0(sum(plan.values()) - tot)}억원), "
          f"손익 {n0(rr['손익'])}%(잔액: {n0(plan['손익'] - act['손익'])}억원), "
          f"자본 {n0(rr['자본'])}%(잔액: {n0(plan['자본'] - act['자본'])}억원)로 과년도 대비 {'상승' if r_all >= prev_rate else '하락'}")

    g = inputs["grades"]
    big = [s for s in GRADE_SITES if g.get(Y, {}).get(s) in ("MI", "A")]
    b_next = [s for s in GRADE_SITES if g.get(N, {}).get(s) in ("TI", "HGPI", "B") or "TI" in (g.get(N, {}).get(s) or "")
              or "HGPI" in (g.get(N, {}).get(s) or "")]

    def cause(b):
        out = []
        for r in inputs["matrix"][b]:
            dd = r["v"][Y]["실적"] - r["v"][P]["실적"]
            if abs(dd) >= rh.BULLET_MIN_EOK:
                out.append({"label": SHORT[r["key"]],
                            "body": f"전년대비 {n0(abs(dd))}억{ratio(r['v'][Y]['실적'], r['v'][P]['실적'])} "
                                    f"{'증가' if dd >= 0 else '감소'} — (원인 작성)"})
        return out

    g7 = [{"label": f"{b}예산", "body": f"전년도 대비 {'증가' if nplan[b] >= plan[b] else '감소'}({sgn(nplan[b] - plan[b])}억) — (원인 작성)"}
          for b in ("손익", "자본")]
    return {
        "box5_0": f"‘{yy}년 열원시설 유지보수예산은 총 {n0(tot)}억원 집행되었으며 전년대비 {n0(abs(d))}억원({n0(abs(pct(tot, ptot)))}%){'증가' if d >= 0 else '감소'}",
        "box5_1": f"전년 대비 손익예산({sgn(act['손익'] - pact['손익'])}억원) 및 자본예산({sgn(act['자본'] - pact['자본'])}억원) 집행실적 {'증가' if d >= 0 else '감소'}",
        "box5_2": f"배정예산 대비 실적률은 {n0(r_all)}%(손익 {n0(rr['손익'])}%, 자본예산 {n0(rr['자본'])}%) 수준",
        "box14_0": f"전년도 배정액 대비 {n0(abs(nd))}억원 {'증가' if nd >= 0 else '감소'}한({sgn(pct(sum(nplan.values()), sum(plan.values())))}%) {n0(sum(nplan.values()))}억원 편성",
        "box14_1": f"전년대비 손익예산 {sgn(nplan['손익'] - plan['손익'])}억원, 자본예산 {sgn(nplan['자본'] - plan['자본'])}억원",
        "h0": "유지보수 예산 실적·계획 분석을 통해 합리적인 예산배분 및 열원시설 신뢰성 강화를 지속적으로 추진하고자 함",
        "h1": f"’{yy}년도 {', '.join(big)} 대정비 시행" if big else f"’{yy}년도 (정비 내용 작성)",
        "h2": "’22년 예산표준화 최초시행 이후 지속적인 Rolling으로 실적률 지속 상승",
        "h6": f"{', '.join(b_next[:2])} 등 {len(b_next)}개지사 B급(TI, HGPI) 예정" if b_next else "(정비등급 계획 작성)",
        "h7": f"발전기 불시정지 및 열공급 중단 최소화를 위해 노후화 설비의 전반적인 유지보수 예산 {'증가' if nd >= 0 else '감소'}",
        "a3": a3, "a4": a4, "a5": a5,
        "g3": cause("손익"), "g4": cause("자본"), "g7": g7,
    }


# ───────────────────────── 3) 표 채우기 ─────────────────────────

def _walk(tbl, budget):
    """표의 행을 위에서부터: (행 번호, 종류, 행 키|None, 데이터 시작 열). 종류 item·sub·total·head."""
    m = rh._cells(tbl)
    labels = _label_index(budget)
    rows = sorted({r for r, _ in m})
    out = []
    for r in rows:
        if r == 0:
            continue
        c1 = m.get((r, 1))
        c0 = m.get((r, 0))
        name = _norm(rh._text(c1)) if c1 is not None else _norm(rh._text(c0)) if c0 is not None else ""
        if c1 is None and c0 is not None:
            span = c0.find(Q("cellSpan"))
            if span is None or span.get("colSpan") != "2":
                continue
        if name in ("소계",):
            out.append((r, "sub", None))
        elif name in ("합계", "총계"):
            out.append((r, "total", None))
        elif name in labels:
            out.append((r, "item", labels[name]))
    return m, out


def _val(inputs, budget, key, yy, k):
    r = next(x for x in inputs["matrix"][budget] if x["key"] == key)
    return r["v"].get(yy, {}).get(k, 0) or 0


def _path(inputs, budget, key, yy, k):
    i = next(i for i, x in enumerate(inputs["matrix"][budget]) if x["key"] == key)
    return f"matrix.{budget}.{i}.v.{yy}.{k}"


def _fill_trend(tbl, inputs, budget, mk):
    """표8·9 — 3개년 실적(점유율) + 전년대비 증감."""
    y = int(inputs["year"])
    yrs = [str(y - 2), str(y - 1), str(y)]
    m, rows = _walk(tbl, budget)
    for i, yy in enumerate(yrs):
        if (0, 2 + i) in m:
            rh.set_cell(m[(0, 2 + i)], (f"{yy}년", None), mk)
    items = [k for _, kind, k in rows if kind == "item"]
    total = {yy: sum(_val(inputs, budget, k, yy, "실적") for k in items) for yy in yrs}
    pend = []
    for r, kind, key in rows:
        if kind == "item":
            vals = {yy: _val(inputs, budget, key, yy, "실적") for yy in yrs}
            pend.append(key)
        elif kind == "sub":
            vals = {yy: sum(_val(inputs, budget, k, yy, "실적") for k in pend) for yy in yrs}
            pend = []
        else:
            vals = total
        for i, yy in enumerate(yrs):
            v = vals[yy]
            txt = n0(v) if kind == "total" else f"{n0(v)} ({n0(v / total[yy] * 100) if total[yy] else 0}%)"
            cell = E(txt, _path(inputs, budget, key, yy, "실적")) if kind == "item" else txt
            rh.set_cell(m[(r, 2 + i)], cell, mk)
        rh.set_cell(m[(r, 5)], _chg(vals[yrs[2]], vals[yrs[1]]), mk)


def _fill_exec(tbl, inputs, budget, mk):
    """표11·12 — 당해 배정·실적·차액(실적−배정)·집행율."""
    Y = inputs["year"]
    m, rows = _walk(tbl, budget)
    items = [k for _, kind, k in rows if kind == "item"]
    pend = []
    for r, kind, key in rows:
        if kind == "item":
            p, a = _val(inputs, budget, key, Y, "배정"), _val(inputs, budget, key, Y, "실적")
            pend.append(key)
        else:
            ks = pend if kind == "sub" else items
            p = sum(_val(inputs, budget, k, Y, "배정") for k in ks)
            a = sum(_val(inputs, budget, k, Y, "실적") for k in ks)
            if kind == "sub":
                pend = []
        rr = rate(p, a)
        rh.set_cell(m[(r, 2)], E(n0(p), _path(inputs, budget, key, Y, "배정")) if kind == "item" else n0(p), mk)
        rh.set_cell(m[(r, 3)], E(n0(a), _path(inputs, budget, key, Y, "실적")) if kind == "item" else n0(a), mk)
        rh.set_cell(m[(r, 4)], tri(a - p), mk)
        rh.set_cell(m[(r, 5)], f"{n0(rr)}%" if rr is not None else "-", mk)


def _fill_plan(tbl, inputs, budget, mk):
    """표17·18 — 배정 Y-1·Y·Y+1 + 전년대비 증감."""
    y = int(inputs["year"])
    yrs = [str(y - 1), str(y), str(y + 1)]
    m, rows = _walk(tbl, budget)
    for i, yy in enumerate(yrs):
        if (0, 2 + i) in m:
            rh.set_cell(m[(0, 2 + i)], (f"{yy}년", None), mk)
    items = [k for _, kind, k in rows if kind == "item"]
    for r, kind, key in rows:
        ks = [key] if kind == "item" else items
        vals = [sum(_val(inputs, budget, k, yy, "배정") for k in ks) for yy in yrs]
        for i, yy in enumerate(yrs):
            cell = E(n0(vals[i]), _path(inputs, budget, key, yy, "배정")) if kind == "item" else n0(vals[i])
            rh.set_cell(m[(r, 2 + i)], cell, mk)
        rh.set_cell(m[(r, 5)], _chg(vals[2], vals[1]), mk)


def _fill_three(tbl, inputs, mk):
    """표7 — 3개년 배정·실적·실적률(손익·자본·합계). 손익·자본 칸은 덮어쓰기(over) 가능."""
    y = int(inputs["year"])
    yrs = [str(y - 2), str(y - 1), str(y)]
    m = rh._cells(tbl)
    for i, yy in enumerate(yrs):
        rh.set_cell(m[(0, 1 + 2 * i)], (f"{yy}년", None), mk)
        vals = {}
        for r0, b in ((2, "손익"), (4, "자본")):
            for j, k in enumerate(("배정", "실적")):
                v = tot3(inputs, yy, b, k)
                vals[(b, k)] = v
                rh.set_cell(m[(r0, 1 + j + 2 * i)], E(n0(v), f"over.{yy}.{b}.{k}"), mk)
            rr = rate(vals[(b, "배정")], vals[(b, "실적")])
            rh.set_cell(m[(r0 + 1, 1 + 2 * i)], f"{n0(rr)}%" if rr is not None else "", mk)
        p = vals[("손익", "배정")] + vals[("자본", "배정")]
        a = vals[("손익", "실적")] + vals[("자본", "실적")]
        rh.set_cell(m[(6, 1 + 2 * i)], n0(p), mk)
        rh.set_cell(m[(6, 2 + 2 * i)], n0(a), mk)
        rr = rate(p, a)
        rh.set_cell(m[(7, 1 + 2 * i)], f"{n0(rr)}%" if rr is not None else "", mk)


def _fill_exec_total(tbl, inputs, mk):
    """표10 — 당해 손익·자본·합계 배정·실적·차액·집행율."""
    Y = inputs["year"]
    m = rh._cells(tbl)
    rows = [(1, ("손익",)), (2, ("자본",)), (3, ("손익", "자본"))]
    for r, bs in rows:
        p = sum(tot3(inputs, Y, b, "배정") for b in bs)
        a = sum(tot3(inputs, Y, b, "실적") for b in bs)
        rr = rate(p, a)
        rh.set_cell(m[(r, 1)], n0(p), mk)
        rh.set_cell(m[(r, 2)], n0(a), mk)
        rh.set_cell(m[(r, 3)], tri(a - p), mk)
        rh.set_cell(m[(r, 4)], f"{n0(rr)}%" if rr is not None else "-", mk)


def _fill_plan_total(tbl, inputs, mk):
    """표16 — 배정·실적률(Y-1, Y) + 배정 Y+1 · 증감(비율)."""
    y = int(inputs["year"])
    P, Y, N = str(y - 1), str(y), str(y + 1)
    m = rh._cells(tbl)
    for i, yy in enumerate((P, Y, N)):
        rh.set_cell(m[(0, 1 + 2 * i)], (f"{yy}년", None), mk)
    for r, bs in ((2, ("손익",)), (3, ("자본",)), (4, ("손익", "자본"))):
        vals = {}
        for yy in (P, Y):
            p = sum(tot3(inputs, yy, b, "배정") for b in bs)
            a = sum(tot3(inputs, yy, b, "실적") for b in bs)
            vals[yy] = p
            c = 1 if yy == P else 3
            rh.set_cell(m[(r, c)], n0(p), mk)
            rr = rate(p, a)
            rh.set_cell(m[(r, c + 1)], f"{n0(rr)}%" if rr is not None else "-", mk)
        nv = sum(_sum(inputs, b, N, "배정") for b in bs)
        rh.set_cell(m[(r, 5)], n0(nv), mk)
        d = nv - vals[Y]
        rh.set_cell(m[(r, 6)], f"{tri(d)} ({sgn(d / vals[Y] * 100) if vals[Y] else '-'}%)", mk)


def _fill_grades(tbl, inputs, years, mk):
    m = rh._cells(tbl)
    for i, yy in enumerate(years):
        r = 1 + i
        if (r, 0) not in m:
            continue
        rh.set_cell(m[(r, 0)], (yy, None), mk)
        for j, site in enumerate(GRADE_SITES):
            if (r, 1 + j) in m:
                g = inputs["grades"].get(yy, {}).get(site) or ""
                rh.set_cell(m[(r, 1 + j)], E(g or "-", f"grades.{yy}.{site}", "grade"), mk)


# ───────────────────────── 문단 ─────────────────────────

STATIC_O = re.compile(r"^○\s*(손익예산|자본예산)\s*$")


def plan_roles(sec):
    """바깥 문단을 위에서부터 읽어 □ 머리(9개)·(실적분석) 자동 문장·○ 원인 묶음·이어지는 줄을 가른다."""
    heads, autos, groups, conts = [], {}, {}, []
    last = None
    for p in sec.findall(Q("p")):
        s = rh._text(p).strip()
        has_tbl = p.find(f"{Q('run')}/{Q('tbl')}") is not None
        if has_tbl:
            last = None
            continue
        if s.startswith("□"):
            heads.append(p)
            last = None
        elif s.startswith("○"):
            if STATIC_O.match(s):
                last = None
            elif "(실적분석)" in s:
                autos[len(heads) - 1] = p
                last = p
            else:
                groups.setdefault(len(heads) - 1, []).append(p)
                last = p
        elif s and last is not None and not s.startswith(("<", "*", ".")):
            conts.append(p)                              # ○ 문장이 줄을 넘겨 다음 문단으로 이어진 것
        else:
            last = None if s else last
    return heads, autos, groups, conts


def fill_plan(sec, inputs, mk=None):
    y = int(inputs["year"])
    yy, ny = y % 100, (y + 1) % 100
    tx = inputs["texts"]
    preview = mk is not None
    tops = rh._top_tables(sec)

    # 제목·장 머리의 연도 — «‘» «25년» «～‘» 처럼 글자 조각이 나뉘어 있어 «NN년»을 차례로 갈아 끼운다
    def sub_year(tc, years):
        it = iter(years)
        for t in tc.iter(Q("t")):
            if t.text:
                t.text = re.sub(r"\d{2}년", lambda mm: f"{next(it, mm.group(0)[:2])}년", t.text)
        for p in tc.iter(Q("p")):
            rh._drop_layout(p)
    sub_year(rh._cells(tops[0])[(1, 0)], [f"{yy:02d}", f"{ny:02d}"])
    sub_year(rh._cells(tops[3])[(0, 2)], [f"{yy:02d}"])
    sub_year(rh._cells(tops[12])[(0, 2)], [f"{ny:02d}"])

    _fill_grades(tops[5], inputs, [str(y - 2), str(y - 1), str(y)], mk)
    _fill_three(tops[6], inputs, mk)
    _fill_trend(tops[7], inputs, "손익", mk)
    _fill_trend(tops[8], inputs, "자본", mk)
    _fill_exec_total(tops[9], inputs, mk)
    _fill_exec(tops[10], inputs, "손익", mk)
    _fill_exec(tops[11], inputs, "자본", mk)
    _fill_grades(tops[14], inputs, [str(y), str(y + 1), str(y + 2)], mk)
    _fill_plan_total(tops[15], inputs, mk)
    _fill_plan(tops[16], inputs, "손익", mk)
    _fill_plan(tops[17], inputs, "자본", mk)

    for ti, prefix in ((4, "box5"), (13, "box14")):
        box = [p for p in tops[ti].iter(Q("p")) if rh._text(p).strip()]
        for i, p in enumerate(box):
            k = f"{prefix}_{i}"
            if k in tx:
                _, br = rh.set_body(p, tx[k])
                if preview:
                    mk[br] = {"path": f"texts.{k}", "kind": "text"}

    heads, autos, groups, conts = plan_roles(sec)
    for p in conts:
        sec.remove(p)
    for i, head in enumerate(heads):
        k = f"h{i}"
        if k in tx:
            _, br = rh.set_body(head, tx[k])
            if preview:
                mk[br] = {"path": f"texts.{k}", "kind": "text"}
        elif i == 8:                                    # «’26년도 유지보수 배정예산 세부항목» — 연도만
            sub_year(head, [f"{ny:02d}"])
    for i, p in autos.items():
        k = f"a{i}"
        if k in tx:
            _, br = rh.set_body(p, tx[k], "실적분석")
            if preview:
                mk[br] = {"path": f"texts.{k}", "kind": "text"}
    for i, protos in groups.items():
        k = f"g{i}"
        if k not in tx:
            continue
        bl = tx[k] if preview else [b for b in tx[k] if (b.get("body") or "").strip() or (b.get("label") or "").strip()]
        if preview:
            mk[("tools", heads[i])] = {"add": k}
        rh._fill_bullets(sec, protos, bl, mk=mk, key=k)
    return sec


def render_plan_hwpx(template_bytes, inputs):
    zin, sec, root_tag = rh.load_section(template_bytes)
    return rh.repack(zin, fill_plan(sec, inputs), root_tag)


def preview_plan_html(template_bytes, inputs):
    from . import hwpx_html
    zin, sec, _ = rh.load_section(template_bytes)
    mk = {}
    fill_plan(sec, inputs, mk)
    return hwpx_html.render(zin, sec, mk)
