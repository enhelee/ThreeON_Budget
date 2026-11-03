# -*- coding: utf-8 -*-
"""한글(hwpx) 보고서 — 「열원 유지보수예산 집행성과분석」(연초 2월, 예산분석부 송부용).

흐름은 세 단계다.
  1) build_perf_inputs(conn, year) — 분석 결과(biz_line)를 보고서 칸 단위로 모은 «입력값».
     웹 화면이 이것을 그대로 보여 주고, 사람이 고친다(투자비처럼 앱에 없는 숫자도 여기서 넣는다).
  2) perf_cells(inputs) — 입력값으로 합계·잔액·실적률·점유율을 계산해 «칸에 들어갈 글자»로.
  3) render_perf_hwpx(template, inputs) — 양식 hwpx 의 표 칸과 문단 글자만 바꿔 새 파일로.
     서식(글꼴·테두리·문단 모양)은 양식 그대로 — 글자가 든 run 의 속성을 건드리지 않는다.

hwpx = zip 안의 XML(Contents/section0.xml). 숫자를 바꾸면 줄 배치 캐시(linesegarray)가 맞지 않게
되므로 고친 문단에서는 지운다 — 한글이 열 때 다시 계산한다.

양식 파일(templates/report_perf_template.hwpx)은 원본에서 숫자·원인 문장을 비운 것이다
(scripts/make_report_template.py). 저장소에 실데이터를 두지 않기 위해서다.
"""
import copy
import io
import math
import re
import zipfile
import xml.etree.ElementTree as ET
from decimal import Decimal, ROUND_HALF_UP

HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"
Q = lambda tag: f"{{{HP}}}{tag}"

GROUPS = ["중대형CHP", "소형CHP", "DH", "본사"]          # 양식 표의 열 순서

# 양식 행 이름 → 앱 예산과목(분석 결과의 과목명). 투자비는 앱에 없다 — 화면에서 직접 넣는다.
PERF_ITEMS = {
    "손익": [
        ("건물/구축물", ["수선유지비-건물/구축물"]),
        ("열원경상정비", ["수선유지비-열원경상정비"]),
        ("열원보완개선및기타", ["수선유지비-열원보완및개선"]),
        ("열원정기유지보수", ["수선유지비-열원정기유지보수"]),
        ("열원정기점검", ["수선유지비-열원정기점검"]),
        ("열원점검수수료", ["지급수수료-열원점검수수료"]),
    ],
    "자본": [
        ("건물", ["건물"]),
        ("구축물", ["구축물"]),
        ("기계장치", ["기계장치"]),
        ("공구와기구", ["공구와기구-열원시설공기구"]),
        ("자산화예비품", ["건설중인자산-자산화예비품"]),
        ("재생고온부품", ["건설중인자산-재생고온부품"]),
        ("저장품", ["저장품-열원(보수)"]),
        ("외주비-열원정기점검", ["외주비-열원정기점검"]),
        ("투자비", []),
    ],
}
# 원인 문장 머리에 붙는 짧은 이름(양식 문장 표기)
SHORT = {"열원경상정비": "경상정비", "열원보완개선및기타": "설비개선", "열원정기유지보수": "정기유지보수",
         "열원정기점검": "정기점검", "열원점검수수료": "지급수수료", "재생고온부품": "고온부품",
         "외주비-열원정기점검": "열원정기점검"}
BULLET_MIN_EOK = 5          # 잔액이 이 이상(억원)인 과목만 원인 문장 초안을 깐다
EOK = 100000                # 천원 → 억원


# ───────────────────────── 1) 입력값 ─────────────────────────

def _subject_label(budget):
    return {s: label for label, subs in PERF_ITEMS[budget] for s in subs}


CAPEX_PREFIX = ("수선유지비", "지급수수료")       # 이 머리로 시작하면 손익, 나머지 열원 과목은 자본


def _budget_of(item, code=None):
    code = str(code or "")
    if code[:1] == "6":
        return "손익"
    if code[:1] in ("1", "2"):
        return "자본"
    return "손익" if str(item).startswith(CAPEX_PREFIX) else "자본"


def report_years(conn):
    """보고서를 쓸 수 있는 해 — 분석 결과·예산계획·참고 엑셀 실적(2016년~) 중 하나라도 있는 해, 최근 해부터."""
    ys = set()
    for q in ("SELECT DISTINCT year FROM run", "SELECT DISTINCT year FROM dataset WHERE kind='plan'",
              "SELECT DISTINCT 연도 FROM reference_actual"):
        try:
            ys.update(str(r[0]) for r in conn.execute(q) if str(r[0]).isdigit())
        except Exception:
            pass
    return sorted(ys, reverse=True)


def year_rows(conn, year):
    """그 해 보고서 재료 — [{budget, 예산과목, 처지사, 배정, 실적(천원)}], 출처.

    1) 분석 결과(biz_line)가 있으면 그것(출처 «분석»).
    2) 없으면 중장기 예측의 참고 엑셀 실적(reference_actual — 지사×과목 실적, 2016년~)을 실적으로,
       그 해 예산계획(plan_row)을 배정으로(출처 «참고 엑셀»). 참고 엑셀에는 배정이 없다.
    3) 둘 다 없으면 빈 목록(출처 None)."""
    from . import db as dbm
    rows = []
    for budget in ("손익", "자본"):
        r = dbm.latest_run(conn, year, budget)
        if r:
            for _, x in dbm.load_biz_lines(conn, r["id"]).iterrows():
                rows.append({"budget": budget, "예산과목": x["예산과목"], "처지사": x["처지사"],
                             "배정": _num(x["연예산"]), "실적": _num(x["실적금액"])})
    if rows:
        return rows, "분석"
    try:
        ref = conn.execute(
            "SELECT 사업장, 예산과목, SUM(금액) FROM reference_actual WHERE 연도=? AND base_year="
            "(SELECT MAX(base_year) FROM reference_actual WHERE 연도=?) GROUP BY 사업장, 예산과목",
            (int(year), int(year))).fetchall()
    except Exception:
        ref = []
    for site, item, amt in ref:
        rows.append({"budget": _budget_of(item), "예산과목": item, "처지사": site, "배정": 0.0, "실적": _num(amt)})
    if not rows:
        return [], None
    plan = dbm.load_plan_df(conn, year)
    if plan is not None:
        for _, x in plan.iterrows():
            rows.append({"budget": _budget_of(x["예산과목"], x.get("예산코드")), "예산과목": x["예산과목"],
                         "처지사": x["처지사"], "배정": _num(x["연예산"]), "실적": 0.0})
    return rows, "참고 엑셀"


def source_note(sources):
    """{연도: 출처} → 안내 문장(참고 엑셀·자료 없음인 해만)."""
    ref = sorted(y for y, v in sources.items() if v == "참고 엑셀")
    none = sorted(y for y, v in sources.items() if v is None)
    out = []
    if ref:
        out.append(f"{', '.join(ref)}년은 분석 결과가 없어 중장기 예측의 참고 엑셀 실적을 썼습니다 — "
                   "배정은 그 해 예산계획이 있을 때만 들어갑니다(없으면 0).")
    if none:
        out.append(f"{', '.join(none)}년은 앱에 자료가 없습니다 — 그 칸은 0입니다. 보고서 값으로 넣어 주세요.")
    return out


def _group_of(conn, year):
    from . import config_store
    cfg = config_store.load_dept_config(conn, year)
    return {d["이름"]: d["그룹"] for d in cfg if d.get("포함", True)}, cfg


def build_perf_inputs(conn, year):
    """보고서 한 벌의 입력값(억원). 그 해 + 직전 2개년. 자료가 없는 해는 None."""
    y = int(year)
    years = [str(y - 2), str(y - 1), str(y)]
    warnings = []
    three, sources, by_year = {}, {}, {}
    for yy in years:
        rows, src = year_rows(conn, yy)
        sources[yy], by_year[yy] = src, rows
        three[yy] = {b: ({"배정": _eok(sum(r["배정"] for r in rows if r["budget"] == b)),
                          "실적": _eok(sum(r["실적"] for r in rows if r["budget"] == b))} if rows else None)
                     for b in ("손익", "자본")}

    cur = by_year[str(y)]
    group_of, cfg = _group_of(conn, year)
    items, groups = {}, {}
    for budget in ("손익", "자본"):
        label_of = _subject_label(budget)
        acc = {label: {"배정": 0.0, "실적": 0.0} for label, _ in PERF_ITEMS[budget]}
        gacc = {g: {"배정": 0.0, "실적": 0.0} for g in GROUPS}
        unmapped, ungrouped = set(), set()
        for row in (r for r in cur if r["budget"] == budget):
            p, a = row["배정"], row["실적"]
            label = label_of.get(row["예산과목"])
            if label is None:
                unmapped.add(str(row["예산과목"]))
            else:
                acc[label]["배정"] += p
                acc[label]["실적"] += a
            g = group_of.get(row["처지사"])
            if g in gacc:
                gacc[g]["배정"] += p
                gacc[g]["실적"] += a
            else:
                ungrouped.add(str(row["처지사"]))
        items[budget] = [{"label": label, "배정": _eok(v["배정"]), "실적": _eok(v["실적"])} for label, v in acc.items()]
        groups[budget] = {g: {"배정": _eok(v["배정"]), "실적": _eok(v["실적"])} for g, v in gacc.items()}
        if unmapped:
            warnings.append(f"{budget}: 보고서 행에 없는 예산과목 {len(unmapped)}개는 표에서 빠졌습니다 — {', '.join(sorted(unmapped))}")
        if ungrouped:
            warnings.append(f"{budget}: 지사 구성에 없는 조직 {len(ungrouped)}곳은 지사 유형별 표에서 빠졌습니다 — {', '.join(sorted(ungrouped))}")
    warnings += source_note(sources)
    hq = groups["손익"]["본사"]["배정"] + groups["자본"]["본사"]["배정"]
    hq_act = groups["손익"]["본사"]["실적"] + groups["자본"]["본사"]["실적"]
    if hq and hq_act / hq < 0.5:
        warnings.append(f"본사 배정 {n0(hq)}억원 중 실적은 {n0(hq_act)}억원뿐입니다 — 본사 발주분은 실적이 지사로 잡힙니다. "
                        "보고서처럼 배정을 지사 유형으로 나누려면 «지사 유형별» 배정을 직접 고쳐 주세요.")
    warnings.append("투자비는 앱 자료에 없습니다 — 자본 과목표의 «투자비»와 지사 유형별 자본, 과년도 자본에 직접 넣어 주세요.")

    counts = {g: sum(1 for d in cfg if d["그룹"] == g and d.get("포함", True)) for g in GROUPS if g != "본사"}
    prev_share = None
    prev_rows = by_year[years[1]]
    if prev_rows:
        pg, _ = _group_of(conn, years[1])
        tot = sum(r["실적"] for r in prev_rows)
        by = {g: sum(r["실적"] for r in prev_rows if pg.get(r["처지사"]) == g) for g in GROUPS}
        if tot:
            prev_share = {g: by[g] / tot * 100 for g in GROUPS}

    inputs = {"year": str(year), "date": f"{y + 1}. 02.", "three": {yy: three[yy] for yy in years[:2]},
              "items": items, "groups": groups, "group_counts": counts,
              "prev_group_share": prev_share, "warnings": warnings}
    inputs["texts"] = auto_texts(inputs)
    return inputs


def _num(v):
    """빈 칸(None·NaN — 계획 없는 신규 사업의 연예산)은 0."""
    try:
        v = float(v)
    except (TypeError, ValueError):
        return 0.0
    return 0.0 if math.isnan(v) else v


def _eok(v):
    return round(_num(v) / EOK, 4)


TEXT_MAX = 600


def _split_label(label, body):
    """«(라벨) 본문»으로 들어온 본문은 라벨을 떼어 낸다. 라벨 칸의 괄호도 벗긴다."""
    label = re.sub(r"^\s*\((.*)\)\s*$", r"\1", label).strip()
    m = re.match(r"^\s*\(([^)]{1,30})\)\s*(.*)$", body)
    if m and not label:
        label, body = m.group(1).strip(), m.group(2)
    return {"label": label[:30], "body": body.strip()}
BULLETS_MAX = 20


def _num_of(v):
    """화면에서 온 숫자(쉼표·빈칸·이상한 값) → float. 못 읽으면 0."""
    try:
        v = float(str(v).replace(",", "")) if v not in (None, "") else 0.0
    except ValueError:
        return 0.0
    return 0.0 if math.isnan(v) or math.isinf(v) else v


def _text_of(v):
    return str(v or "").replace("\r", "").replace("\n", " ")[:TEXT_MAX]


def normalize_inputs(raw, year):
    """웹에서 고쳐 온 입력값을 믿을 수 있는 모양으로 — 숫자는 숫자, 글은 길이 제한, 모르는 키는 버린다.

    표의 행·열은 서버가 정한 것만 쓴다(사람이 행을 늘리거나 이름을 바꿔 양식 밖으로 새지 않게)."""
    raw = raw if isinstance(raw, dict) else {}
    num, text = _num_of, _text_of

    def pair(d):
        d = d if isinstance(d, dict) else {}
        return {"배정": num(d.get("배정")), "실적": num(d.get("실적"))}

    y = int(year)
    three_raw = raw.get("three") or {}
    three = {}
    for yy in (str(y - 2), str(y - 1)):
        d = three_raw.get(yy) or {}
        three[yy] = {b: (pair(d[b]) if d.get(b) else None) for b in ("손익", "자본")}
    items_raw = raw.get("items") or {}
    items = {}
    for b, rows in PERF_ITEMS.items():
        got = {x.get("label"): x for x in (items_raw.get(b) or []) if isinstance(x, dict)}
        items[b] = [dict(label=label, **pair(got.get(label))) for label, _ in rows]
    groups_raw = raw.get("groups") or {}
    groups = {b: {g: pair((groups_raw.get(b) or {}).get(g)) for g in GROUPS} for b in ("손익", "자본")}
    counts_raw = raw.get("group_counts") or {}
    counts = {g: int(num(counts_raw[g])) for g in GROUPS if g in counts_raw}
    tx = raw.get("texts") or {}
    texts = {k: text(tx.get(k)) for k in ("box1", "box2", "s2_head", "s3_head", "son_head", "ja_head")}
    for k in ("s2_bullets", "son_bullets", "ja_bullets"):
        texts[k] = [_split_label(text(b.get("label")), text(b.get("body")))
                    for b in (tx.get(k) or [])[:BULLETS_MAX] if isinstance(b, dict)]
    if texts["ja_bullets"]:                              # 문서 화면에서 고치면 마지막 줄의 «끝.»이 본문에 딸려 온다
        last = texts["ja_bullets"][-1]
        last["body"] = re.sub(r"\s*끝\.\s*$", "", last["body"])
    for k in ("box1", "box2", "s2_head", "s3_head", "son_head", "ja_head"):
        texts[k] = texts[k].strip()
    ps = raw.get("prev_group_share")
    return {"year": str(y), "date": text(raw.get("date"))[:20] or f"{y + 1}. 02.", "three": three,
            "items": items, "groups": groups, "group_counts": counts,
            "prev_group_share": {g: num(ps.get(g)) for g in GROUPS} if isinstance(ps, dict) else None,
            "texts": texts}


# ───────────────────────── 2) 계산·글자 ─────────────────────────

def _r(v, nd=0):
    """사사오입(파이썬 round 는 짝수 쪽으로 — 보고서 표기와 어긋난다)."""
    q = Decimal(1).scaleb(-nd)
    return float(Decimal(str(v)).quantize(q, rounding=ROUND_HALF_UP))


def n0(v):
    return f"{int(_r(v)):,}"


def n1(v):
    return f"{_r(v, 1):,.1f}"


def tri(v, fmt=n0):
    """음수는 △ — 공문서 표기."""
    return ("△" + fmt(-v)) if _r(v, 1) < 0 else fmt(v)


def sgn(v, fmt=n0):
    return ("△" + fmt(-v)) if _r(v, 1) < 0 else ("+" + fmt(v))


def rate(plan, act):
    return act / plan * 100 if plan else None


def totals(inputs):
    """입력값에서 나오는 합계들 — 표와 문장이 같은 숫자를 쓰게 한 곳에서."""
    y = inputs["year"]
    it = inputs["items"]
    cur = {b: {"배정": sum(x["배정"] or 0 for x in it[b]), "실적": sum(x["실적"] or 0 for x in it[b])} for b in ("손익", "자본")}
    three = dict(inputs["three"])
    three[y] = cur
    for yy, d in three.items():
        if d.get("손익") and d.get("자본"):
            d = dict(d)
            d["합계"] = {k: d["손익"][k] + d["자본"][k] for k in ("배정", "실적")}
            three[yy] = d
    g = inputs["groups"]
    gsum = {g_: {k: g["손익"][g_][k] + g["자본"][g_][k] for k in ("배정", "실적")} for g_ in GROUPS}
    return {"three": three, "years": sorted(three), "cur": cur, "gsum": gsum}


def E(text, path, kind="num"):
    """고칠 수 있는 칸 — (글자, 칸 정보). 그냥 글자는 계산 칸(화면에서 못 고침)."""
    return (text, {"path": path, "kind": kind})


def perf_cells(inputs):
    """표 번호(양식의 바깥 표 순서, 0부터) → {(행, 열): 글자 | (글자, 칸 정보)}."""
    t = totals(inputs)
    three, years = t["three"], t["years"]
    cells = {}

    # 표2(1): 3개년 배정·실적·실적률
    c = {}
    for k, yy in enumerate(years):
        c[(0, 1 + 2 * k)] = (f"{yy}년", None)
        for r0, key in ((2, "손익"), (4, "자본"), (6, "합계")):
            d = (three.get(yy) or {}).get(key)
            for j, kk in enumerate(("배정", "실적")):
                txt = n0(d[kk]) if d else ""
                # 과년도 손익·자본만 고친다 — 올해는 과목표 합, 합계는 계산
                c[(r0, 1 + j + 2 * k)] = E(txt, f"three.{yy}.{key}.{kk}") if key != "합계" and yy != inputs["year"] else txt
            rr = rate(d["배정"], d["실적"]) if d else None
            c[(r0 + 1, 1 + 2 * k)] = f"{n0(rr)}%" if rr is not None else ""
    cells[1] = c

    # 표4(3): 지사 유형별 실적·점유율
    g = inputs["groups"]
    cnt = inputs.get("group_counts") or {}
    c = {"counts": {(0, 1 + i): (g_, cnt[g_]) for i, g_ in enumerate(GROUPS) if g_ in cnt}}
    for r0, src in ((1, g["손익"]), (2, g["자본"]), (3, t["gsum"])):
        tot = sum(src[g_]["실적"] for g_ in GROUPS)
        for i, g_ in enumerate(GROUPS):
            a = src[g_]["실적"]
            c[(r0, 1 + i)] = f"{n0(a)}({n0(a / tot * 100) if tot else 0}%)"
        c[(r0, 5)] = n0(tot)
    cells[3] = c

    # 표5(4): 지사 유형별 배정·실적·잔액·실적률
    c = {"counts": {(0, 2 + i): (g_, cnt[g_]) for i, g_ in enumerate(GROUPS) if g_ in cnt}}
    for r0, b in ((1, "손익"), (5, "자본")):
        src = g[b]
        cols = [src[g_] for g_ in GROUPS] + [{k: sum(src[g_][k] for g_ in GROUPS) for k in ("배정", "실적")}]
        for i, d in enumerate(cols):
            rr = rate(d["배정"], d["실적"])
            gname = GROUPS[i] if i < len(GROUPS) else None
            c[(r0, 2 + i)] = E(n0(d["배정"]), f"groups.{b}.{gname}.배정") if gname else n0(d["배정"])
            c[(r0 + 1, 2 + i)] = E(n0(d["실적"]), f"groups.{b}.{gname}.실적") if gname else n0(d["실적"])
            c[(r0 + 2, 2 + i)] = tri(d["배정"] - d["실적"])
            c[(r0 + 3, 2 + i)] = n1(rr) if rr is not None else "-"
    cells[4] = c

    # 표6(5)·표7(6): 과목별 — 행은 양식의 이름으로 찾는다(render 쪽). 여기서는 이름 → 네 칸.
    for ti, budget in ((5, "손익"), (6, "자본")):
        rows = {}
        for i, x in enumerate(inputs["items"][budget] + [{"label": "합 계", "배정": t["cur"][budget]["배정"], "실적": t["cur"][budget]["실적"]}]):
            p, a = x["배정"] or 0, x["실적"] or 0
            rr = rate(p, a)
            total = x["label"] == "합 계"
            rows[x["label"]] = [n1(p) if total else E(n1(p), f"items.{budget}.{i}.배정"),
                                n1(a) if total else E(n1(a), f"items.{budget}.{i}.실적"),
                                tri(p - a, n1), n1(rr) if rr is not None else "-"]
        cells[ti] = {"rows": rows}
    return cells


def auto_texts(inputs):
    """숫자로 쓸 수 있는 문장 초안. 원인(왜 늘었나)은 사람이 쓴다 — 칸만 깔아 둔다."""
    t = totals(inputs)
    y = int(inputs["year"])
    yy, py = y % 100, (y - 1) % 100
    cur = t["three"][str(y)]
    prev = t["three"].get(str(y - 1)) or {}

    def chg(key):
        if not prev.get(key):
            return ""
        d = cur[key]["실적"] - prev[key]["실적"]
        pct = d / prev[key]["실적"] * 100 if prev[key]["실적"] else 0
        return f"({sgn(d)}억원, {sgn(pct)}%)"

    box1 = (f"‘{yy}년 열원시설 손익예산 {n0(cur['손익']['실적'])}억원{chg('손익')}, "
            f"자본예산 {n0(cur['자본']['실적'])}억원{chg('자본')} 집행되었으며")
    if prev.get("합계"):
        d = cur["합계"]["실적"] - prev["합계"]["실적"]
        pct = d / prev["합계"]["실적"] * 100 if prev["합계"]["실적"] else 0
        box1 += f" 총액 기준 전년대비 {n0(abs(d))}억원({sgn(pct)}%) {'증가' if d >= 0 else '감소'}"
    tot_rate = rate(cur["합계"]["배정"], cur["합계"]["실적"])
    box2 = f"배정예산 대비 실적률은 {n0(tot_rate or 0)}%으로 ’22년 예산표준화 및 지속적인 Rolling으로 90% 전후 예산집행 실적률 달성 중"

    gs = t["gsum"]
    gtot = sum(gs[g]["실적"] for g in GROUPS) or 1
    top = max(GROUPS, key=lambda g: gs[g]["실적"])
    share = gs[top]["실적"] / gtot * 100
    s2_bullets = []
    ps = inputs.get("prev_group_share")
    if ps:
        s2_bullets.append({"label": "", "body": f"(원인 작성) 등으로 인해 ’{py}년 대비 {top} 예산 비율 "
                                                f"{'증가' if share >= ps[top] else '감소'}({n0(ps[top])}% → {n0(share)}%)"})
    rates = [rate(gs[g]["배정"], gs[g]["실적"]) for g in GROUPS if g != "본사"]
    rates = [r for r in rates if r is not None]
    floor = min(90, int(math.floor(min(rates) / 10) * 10)) if rates else 90

    def head(budget):
        c = cur[budget]
        r = rate(c["배정"], c["실적"]) or 0
        rem = c["배정"] - c["실적"]
        s = f"예산 집행률은 약 {n0(r)}%로 계획대비 약 {n0(abs(rem))}억원 {'미집행' if rem >= 0 else '초과 집행'} 되었으며"
        if prev.get(budget):
            dp = r - (rate(prev[budget]["배정"], prev[budget]["실적"]) or 0)
            s += f", 과년도 대비 {n0(abs(dp))}%p 실적률 {'개선' if dp >= 0 else '하락'}"
        return s

    def bullets(budget):
        out = []
        for x in inputs["items"][budget]:
            d = (x["실적"] or 0) - (x["배정"] or 0)
            if abs(d) >= BULLET_MIN_EOK:
                out.append({"label": SHORT.get(x["label"], x["label"]),
                            "body": f"배정 대비 {sgn(d)}억원 — (원인 작성)"})
        return out

    return {"box1": box1, "box2": box2,
            "s2_head": f"{top} 집행실적이 전체집행의 {n0(share)}%를 차지", "s2_bullets": s2_bullets,
            "s3_head": f"대체적으로 {floor}% 이상의 집행율 집계. 단, 본사 발주분에 한해 배정은 본사, 실적은 지사로 집계되어 집행율 낮음",
            "son_head": head("손익"), "son_bullets": bullets("손익"),
            "ja_head": head("자본"), "ja_bullets": bullets("자본")}


# ───────────────────────── 3) hwpx 쓰기 ─────────────────────────

def _text(el):
    """run/t 안의 글자. 전각 공백(fwSpace)·탭은 공백 하나로 센다."""
    out = []
    for t in el.iter(Q("t")):
        out.append(t.text or "")
        for ch in t:
            out.append(" " if ch.tag in (Q("fwSpace"), Q("tab"), Q("nbSpace")) else "")
            out.append(ch.tail or "")
    return "".join(out)


def _set_t(run, text):
    ts = run.findall(Q("t"))
    t = ts[0] if ts else ET.SubElement(run, Q("t"))
    for extra in ts[1:]:
        run.remove(extra)
    for ch in list(t):
        t.remove(ch)
    t.text = text


def _drop_layout(p):
    for ls in p.findall(Q("linesegarray")):
        p.remove(ls)


def set_cell(tc, value, mk=None):
    """value = 글자 | (글자, 칸 정보). mk 를 주면 칸 정보를 적어 둔다(웹 미리보기용)."""
    text, slot = value if isinstance(value, tuple) else (value, {"kind": "calc"})
    if mk is not None and slot:
        mk[tc] = slot
    sub = tc.find(Q("subList"))
    p, *rest = sub.findall(Q("p"))
    for extra in rest:
        sub.remove(extra)
    runs = p.findall(Q("run"))
    keep = next((r for r in runs if r.find(Q("t")) is not None), runs[0])
    _set_t(keep, text)
    for r in runs:
        if r is not keep:
            for t in r.findall(Q("t")):
                r.remove(t)
    _drop_layout(p)


LEAD = re.compile(r"^\s*[□○◈ㅇ]\s*(\([^)]*\))?\s*")


def set_body(p, body, label=None):
    """머리(□·○ 기호와 «(라벨)»)의 run 은 서식째 두고, 그 뒤 본문만 body 로 바꾼다.

    label 을 주면 괄호 안 라벨도 바꾼다(빈 문자열이면 괄호째 뺀다).
    돌려주는 값 (라벨 run, 본문 run) — 웹에서 그 자리를 고칠 칸으로 표시한다."""
    label_run = None
    runs = [r for r in p.findall(Q("run")) if r.find(Q("t")) is not None]
    texts = [_text(r) for r in runs]
    m = LEAD.match("".join(texts))
    lead_len = m.end() if m else 0
    pos, body_i = 0, len(runs)
    for i, s in enumerate(texts):
        if pos + len(s) > lead_len and s.strip():
            body_i = i
            break
        pos += len(s)
    if label and not (m and m.group(1)):               # 라벨 자리가 없는 ○ 문단 — 본문 앞에 붙인다
        body = f"({label}) {body}"
    if label and m and m.group(1) and not m.group(0).endswith((" ", "\u3000")) and body[:1] not in ("", " ", "「", "("):
        body = " " + body                               # «(정기점검)MI…» 처럼 붙지 않게
    relabel = (lambda v: re.sub(r"\([^)]*\)\s*", f"({label}) " if label else "", v, count=1)) \
        if label is not None and m and m.group(1) else None
    if body_i < len(runs) and pos < lead_len:          # 한 run 에 머리와 본문이 같이 — 머리 몫을 앞에 남긴다
        prefix = texts[body_i][:lead_len - pos]
        if relabel and "(" in prefix:
            prefix, relabel = relabel(prefix), None
        body = prefix + body
    if relabel:                                        # 라벨이 «(건물/구축물» «) » 처럼 run 여럿에 걸칠 수 있다
        opened = False
        for r in runs[:body_i]:
            v = _text(r)
            if not opened and "(" in v:
                head, _, rest = v.partition("(")
                closed = ")" in rest
                tail = rest.split(")", 1)[1] if closed else ""
                _set_t(r, (f"({label})" if label else "") + tail)
                if head:                                # «  ○ (» 처럼 기호와 라벨이 한 run — 기호 몫을 앞 run 으로 떼어 낸다
                    hr = copy.deepcopy(r)
                    _set_t(hr, head)
                    p.insert(list(p).index(r), hr)
                label_run = r if label else None
                opened = not closed
                if closed:
                    break
            elif opened:
                closed = ")" in v
                _set_t(r, v.split(")", 1)[1] if closed else "")
                if closed:
                    break
    if body_i < len(runs):
        body_run = runs[body_i]
        _set_t(body_run, body)
        for r in runs[body_i + 1:]:
            p.remove(r)
    else:                                               # 본문 run 이 없던 문단 — 마지막 run 을 본떠 하나 붙인다
        body_run = copy.deepcopy(runs[-1])
        _set_t(body_run, body)
        p.insert(list(p).index(runs[-1]) + 1, body_run)
    _drop_layout(p)
    return label_run, body_run


def _top_tables(sec):
    inner = {id(t) for tb in sec.iter(Q("tbl")) for t in tb.iter(Q("tbl")) if t is not tb}
    return [t for t in sec.iter(Q("tbl")) if id(t) not in inner]


def _cells(tbl):
    out = {}
    for tc in tbl.iter(Q("tc")):
        a = tc.find(Q("cellAddr"))
        out[(int(a.get("rowAddr")), int(a.get("colAddr")))] = tc
    return out


def set_count(tc, n):
    """«중대형 / CHP(9)»처럼 줄이 나뉜 머리 칸 — 서식·줄바꿈은 두고 괄호 숫자만."""
    for t in tc.iter(Q("t")):
        for node, attr in [(t, "text")] + [(ch, "tail") for ch in t]:
            v = getattr(node, attr) or ""
            if re.search(r"\(\d+\)", v):
                setattr(node, attr, re.sub(r"\(\d+\)", f"({n})", v))
    for p in tc.iter(Q("p")):
        _drop_layout(p)


def _fill_table(tbl, cells, mk=None, counts_path=None):
    m = _cells(tbl)
    for (r, c), (g, n) in (cells.get("counts") or {}).items():
        if (r, c) in m:
            set_count(m[(r, c)], n)
            if mk is not None:
                mk[m[(r, c)]] = {"path": f"group_counts.{g}", "kind": "count"}
    if "rows" in cells:                                 # 과목별 — 행 이름(1열, 합계는 0열)으로 찾는다
        for (r, c), tc in m.items():
            if c in (0, 1):
                name = _text(tc).strip()
                vals = cells["rows"].get(name) or cells["rows"].get(re.sub(r"\s+", " ", name))
                if vals:
                    for k, v in enumerate(vals):
                        set_cell(m[(r, 2 + k)], v, mk)
        return
    for rc, v in cells.items():
        if rc != "counts" and rc in m:
            set_cell(m[rc], v, mk)


def _paragraph_roles(sec):
    """바깥 문단 중 □ 머리 문단 4개와 그 뒤 ○ 문단 묶음."""
    ps = list(sec.findall(Q("p")))
    heads, groups = [], []
    for p in ps:
        s = _text(p).strip()
        if s.startswith("□"):
            heads.append(p)
            groups.append([])
        elif s.startswith("○") and groups:
            groups[-1].append(p)
    return ps, heads, groups


def _fill_bullets(sec, protos, bullets, end_mark=False, mk=None, key=None):
    """○ 문단을 bullets 개수만큼 — 첫 ○ 문단(과 그 뒤 빈 줄)을 본떠 같은 자리에 다시 깐다."""
    if not protos:
        return
    kids = list(sec)
    first, last = kids.index(protos[0]), kids.index(protos[-1])
    nxt = kids[first + 1] if first + 1 < len(kids) else None
    spacer = nxt if nxt is not None and nxt.tag == Q("p") and not _text(nxt).strip() and nxt not in protos else None
    proto = copy.deepcopy(protos[0])
    spacer = copy.deepcopy(spacer) if spacer is not None else None
    for el in kids[first:last + 1]:                     # 기존 ○ 문단과 그 사이 빈 줄
        if el in protos or (el.tag == Q("p") and not _text(el).strip()):
            sec.remove(el)
    at = first
    for k, b in enumerate(bullets):
        np = copy.deepcopy(proto)
        body = b.get("body", "")
        if end_mark and k == len(bullets) - 1:
            body = body.rstrip() + "  끝."
        lr, br = set_body(np, body, b.get("label", ""))
        if mk is not None and key:
            if lr is not None:
                mk[lr] = {"path": f"texts.{key}.{k}.label", "kind": "label"}
            mk[br] = {"path": f"texts.{key}.{k}.body", "kind": "body"}
            mk[("tools", np)] = {"del": (key, k)}
        sec.insert(at, np)
        at += 1
        if spacer is not None and k < len(bullets) - 1:
            sec.insert(at, copy.deepcopy(spacer))
            at += 1


def _end_line(sec, proto, kids_before):
    """첫 ○ 문단이 있던 자리에 기호 없는 «끝.» 문단(같은 문단 모양)."""
    at = len(sec)
    for el in kids_before[kids_before.index(proto):]:   # 원래 자리 뒤로 아직 남은 첫 요소 앞
        if el is not proto and any(el is k for k in sec):
            at = list(sec).index(el)
            break
    np = copy.deepcopy(proto)
    runs = [r for r in np.findall(Q("run")) if r.find(Q("t")) is not None]
    _set_t(runs[-1], "  끝.")
    for r in runs[:-1]:
        np.remove(r)
    _drop_layout(np)
    sec.insert(at, np)


def _ns_header(xml):
    root_tag = re.search(r"<(\w+:\w+)\s[^>]*>", xml[xml.index("?>") + 2:] if xml.startswith("<?xml") else xml)
    for pfx, uri in re.findall(r'xmlns:(\w+)="([^"]+)"', root_tag.group(0)):
        ET.register_namespace(pfx, uri)
    return root_tag.group(0)


def _serialize(root, orig_root_tag):
    s = ET.tostring(root, encoding="unicode")
    s = re.sub(r"^<[^>]+>", orig_root_tag, s, count=1)   # 원래 뿌리 태그(이름공간 선언 전부)를 그대로
    return '<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>' + s


def fill_perf(sec, inputs, mk=None):
    """양식 section 에 입력값을 채운다. mk(dict)를 주면 고칠 칸을 적어 둔다 — 웹 미리보기용.

    미리보기에서는 빈 ○ 줄도 남긴다(방금 «+ ○»로 늘린 줄에 바로 쓸 수 있게). 파일에는 빈 줄을 뺀다."""
    y = int(inputs["year"])
    tx = inputs["texts"]
    preview = mk is not None

    tops = _top_tables(sec)
    title = _cells(tops[0])[(1, 0)]
    set_cell(title, (re.sub(r"^\s*\d{2}년", f"{y % 100}년", _text(title)), None))
    for ti, c in perf_cells(inputs).items():
        _fill_table(tops[ti], c, mk)
    box = [p for p in tops[2].iter(Q("p")) if _text(p).strip()]
    for p, k in zip(box, ("box1", "box2")):
        _, br = set_body(p, tx[k])
        if preview:
            mk[br] = {"path": f"texts.{k}", "kind": "text"}

    ps, heads, groups = _paragraph_roles(sec)
    for p in ps:
        s = _text(p)
        if re.search(r"\d{4}\.\s*\d{1,2}\.", s) and "QC" in s:
            for run in p.findall(Q("run")):
                for t in run.findall(Q("t")):
                    for node, attr in [(t, "text")] + [(ch, "tail") for ch in t]:
                        v = getattr(node, attr) or ""
                        if re.search(r"\d{4}\.\s*\d{1,2}\.", v):
                            setattr(node, attr, re.sub(r"\d{4}\.\s*\d{1,2}\.", inputs.get("date") or "", v))
                            if preview:
                                mk[run] = {"path": "date", "kind": "date"}
            _drop_layout(p)
        elif re.match(r"^\s*1\.\s*\d{2}년", s):
            for t in p.iter(Q("t")):
                if t.text and re.search(r"\d{2}년", t.text):
                    t.text = re.sub(r"\d{2}년", f"{y % 100}년", t.text, count=1)
                    break
            _drop_layout(p)

    keys = ["s2", "s3", "son", "ja"]
    kids_before = list(sec)
    for k, head, protos in zip(keys, heads, groups):
        _, br = set_body(head, tx[f"{k}_head"])
        bl = tx.get(f"{k}_bullets", [])
        if not preview:
            bl = [b for b in bl if (b.get("body") or "").strip() or (b.get("label") or "").strip()]
        if preview:
            mk[br] = {"path": f"texts.{k}_head", "kind": "text"}
            if protos:
                mk[("tools", head)] = {"add": f"{k}_bullets"}
        _fill_bullets(sec, protos, bl, end_mark=(k == "ja"), mk=mk, key=f"{k}_bullets")
        if k == "ja" and not bl and protos:               # ○ 가 하나도 없으면 표 뒤에 «끝.» 한 줄
            _end_line(sec, protos[0], kids_before)
    return sec


def render_perf_hwpx(template_bytes, inputs):
    zin, sec, root_tag = load_section(template_bytes)
    return repack(zin, fill_perf(sec, inputs), root_tag)


def preview_perf_html(template_bytes, inputs):
    """같은 채우기를 HTML 로 — 화면에 보이는 것과 내려받는 파일이 같은 길을 지난다."""
    from . import hwpx_html
    zin, sec, _ = load_section(template_bytes)
    mk = {}
    fill_perf(sec, inputs, mk)
    return hwpx_html.render(zin, sec, mk)


def load_section(template_bytes):
    """(zip, section 뿌리, 원래 뿌리 태그) — 양식 손질 스크립트도 같은 길로 읽는다."""
    zin = zipfile.ZipFile(io.BytesIO(template_bytes))
    xml = zin.read("Contents/section0.xml").decode("utf-8")
    root_tag = _ns_header(xml)
    return zin, ET.fromstring(xml.encode("utf-8")), root_tag


def repack(zin, sec, root_tag, replace=None):
    """replace = {zip 안 경로: 새 내용(bytes)} — 양식 손질 때 문서 속성 등을 갈아 끼운다."""
    replace = replace or {}
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as zout:
        for info in zin.infolist():                      # 순서·압축 방식 그대로(mimetype 이 맨 앞·무압축)
            data = zin.read(info.filename)
            if info.filename in replace:
                data = replace[info.filename]
            elif info.filename == "Contents/section0.xml":
                data = _serialize(sec, root_tag).encode("utf-8")
            elif info.filename == "Preview/PrvText.txt":
                data = preview_text(sec).encode("utf-8")
            elif info.filename == "Preview/PrvImage.png":
                data = BLANK_PNG                         # 옛 숫자가 찍힌 미리보기 그림을 남기지 않는다
            zi = zipfile.ZipInfo(info.filename, date_time=info.date_time)
            zi.compress_type = info.compress_type
            zi.external_attr = info.external_attr
            zout.writestr(zi, data)
    return out.getvalue()


def preview_text(sec):
    lines = []
    for p in sec.iter(Q("p")):
        s = _text(p).strip()
        if s and p.find(f"{Q('run')}/{Q('tbl')}") is None:
            lines.append(s)
    return "\r\n".join(lines)[:1000]


def section_text(hwpx_bytes):
    """검증용 — 만든 파일의 본문 글자 전부."""
    z = zipfile.ZipFile(io.BytesIO(hwpx_bytes))
    sec = ET.fromstring(z.read("Contents/section0.xml"))
    return "\n".join(_text(p) for p in sec.iter(Q("p")))


def _blank_png():
    import struct
    import zlib
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    raw = b"\x00\xff\xff\xff"
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


BLANK_PNG = _blank_png()
