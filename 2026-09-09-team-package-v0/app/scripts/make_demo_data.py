# -*- coding: utf-8 -*-
"""시연·심사용 가짜(합성) 데이터 생성 — 실데이터를 한 줄도 쓰지 않는다.

2026 공공 AI 대전환 챌린지 제출용(2026-11-09). 공모 규정상 민감자료를 쓸 수 없어서,
앱이 받는 엑셀 양식(칸 구조)만 같고 사업명·금액·전표는 전부 난수로 만든다.
지사·예산과목 이름은 앱에 이미 들어 있는 시드(config_store)를 그대로 쓴다 — 조직 구조라 공개 정보다.

만드는 것(demo_data/):
  {연도}_계획_양식1.xlsx   2016~2026 사업별 계획(양식1(월별) 시트, 3행 머리글)
  {연도}_zrfm2.xlsx        2016~2025 SAP 전표(zrfm2 열 위치 그대로, 마지막 줄 합계행 포함)
  마스터_예산과목.xlsx · 마스터_부서코드.xlsx   기준정보(가상 코드)
  보정규칙.xlsx            담당자 보정사전(배정·제외 몇 건)
  전망_기준정보.json        정비등급(2014~2035)·물가지수·정기계약·투자계획 — load_demo.py 가 API 로 넣는다

전표에는 시연에서 기능이 보이도록 일부러 «어려운 경우»를 섞는다:
  월별·회차 분납, 같은 참조전표번호의 인지세, 약칭·오타, 지사 별칭, 역분개(±),
  계획에 없는 신규사업, 텍스트가 애매한 전표(검토 큐), 200만원 미만 소액 구매.

실행:  python scripts/make_demo_data.py   (같은 시드면 항상 같은 파일)
"""
import datetime as dt
import json
import os
import random
import sys

import openpyxl
from openpyxl.styles import Font, PatternFill

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(APP, "src"))
from budget import config_store  # noqa: E402

OUT = os.path.join(APP, "demo_data")
SEED = 20261111
ACTUAL_YEARS = list(range(2016, 2026))        # 10개년 실적 — 표준화 백테스트(학습 2·3·5·10년)까지 보이게
PLAN_YEARS = ACTUAL_YEARS + [2026]

GROUPS = config_store.SEED_DEPTS_BY_YEAR["2025"]
SITES = [(s, g) for g in config_store.DEPT_GROUPS for s in GROUPS[g]]
GROUP_OF = dict(SITES)
GROUP_MULT = {"본사": 0.6, "중대형CHP": 1.0, "소형CHP": 0.5, "DH": 0.35}
OWNER = {"손익": "플랜트기술처", "자본": "플랜트기술처"}

# 과목 → (기준 연예산 천원, 지사당 사업 수 범위, 대상 그룹, 사업명 후보)
PL = {
    "수선유지비-건물/구축물": (150_000, (1, 3), "all",
                         ["사옥 외벽 도장", "주차장 방수공사", "기계실 지붕 보수", "울타리 교체", "배수로 정비"]),
    "수선유지비-열원정기점검": (300_000, (1, 2), "plant",
                         ["열원설비 정기점검", "보일러 법정검사", "첨두부하보일러 정기점검", "열교환기 세관"]),
    "수선유지비-열원경상정비": (1_200_000, (1, 3), "plant",
                         ["열원설비 경상정비 용역", "펌프류 경상정비", "밸브류 경상정비", "계측기 경상정비"]),
    "수선유지비-열원정기유지보수": (250_000, (2, 4), "all",
                           ["분산제어설비 유지보수", "굴뚝자동측정기 유지보수", "소방설비 유지보수",
                            "승강기 유지보수", "공조설비 유지보수"]),
    "수선유지비-열원보완및개선": (400_000, (1, 3), "plant",
                          ["급수펌프 효율개선", "탈질설비 보완", "배관 보온재 교체", "조명 고효율 개선",
                           "순환수 수처리 개선"]),
    "수선유지비-비저장품(보수자재)": (120_000, (1, 2), "plant",
                             ["보수자재 구매", "패킹 및 가스켓 구매", "배관 자재 구매"]),
    "수선유지비-소모품(자재공기구)": (60_000, (1, 2), "all",
                             ["소모성 공기구 구매", "안전용품 구매", "윤활유 구매"]),
    "지급수수료-열원점검수수료": (50_000, (1, 3), "plant",
                          ["계량기 검정 수수료", "압력용기 검사 수수료", "수질분석 수수료", "환경측정 대행 수수료"]),
}
CAP = {
    "건물": (500_000, (0, 1), "all", ["사무동 증축", "자재창고 신축"]),
    "구축물": (300_000, (0, 1), "plant", ["저장조 보강", "옹벽 보강"]),
    "기계장치": (800_000, (1, 3), "plant", ["순환펌프 교체", "열교환기 교체", "제어설비 교체", "인버터 교체"]),
    "공구와기구-열원시설공기구": (50_000, (0, 2), "plant", ["진동분석기 구매", "열화상카메라 구매"]),
    "저장품-열원(보수)": (300_000, (1, 1), "plant", ["보수용 저장품 구매"]),
    "건설중인자산-재생고온부품": (1_500_000, (1, 1), "chp", ["고온부품 재생"]),
    "건설중인자산-자산화예비품": (400_000, (1, 1), "chp", ["자산화 예비품 확보"]),
    "외주비-열원정기점검": (0, (1, 1), "chp", ["가스터빈 계획예방정비"]),
}
# A급정비(외주비-열원정기점검) 금액은 그 해 정비등급이 정한다(천원, 중대형CHP 기준)
OVERHAUL = {"간이": 300_000, "MI": 1_500_000, "TI": 4_000_000, "CI": 2_500_000}
GT_CYCLE = ["간이", "MI", "간이", "TI", "간이", "MI", "간이", "CI"]

PL_CODES = {n: f"6{900 + i:03d}{100 + i:03d}"[:8] for i, n in enumerate(PL)}
CAP_CODES = {n: f"1{500 + i:03d}{200 + i:03d}"[:8] for i, n in enumerate(CAP)}
ALL_CODES = {**PL_CODES, **CAP_CODES}
ATTR = {**{n: "제조" for n in PL}, **{n: "자본" for n in CAP}}
DEPT_CODE = {s: f"D{1000 + i * 10}" for i, (s, _) in enumerate(SITES)}
PART = ["운영부", "설비부", "기술부", "관리부"]
# ERP «이름(지사)» 칸에 가끔 나오는 옛 이름·별칭 — 앱의 SEED_DEPT_ALIAS 가 계획 지사로 바꾼다
ALIAS_RAW = {v: k for k, v in config_store.SEED_DEPT_ALIAS.items() if v in GROUP_OF}
VENDORS = [f"V{300000 + i}" for i in range(60)]
SYN = {"유지보수": "유지관리", "구매": "구입", "교체": "교체공사", "정기점검": "정기 점검", "용역": "용역비",
       "수수료": "수수료 지급", "보수": "보수공사"}
VAGUE = ["용역대금 지급", "수선 자재 대금", "기타 수선비", "외주 작업비 정산", "물품대금"]


def _eligible(scope, site):
    g = GROUP_OF[site]
    if scope == "all":
        return True
    if scope == "plant":
        return g != "본사"
    if scope == "chp":
        return g in ("중대형CHP", "소형CHP")
    return False


def grade_plan(rng):
    """지사×연도 정비등급(2014~2035). 가스터빈이 있는 CHP 는 주기를 돌고, DH 는 «표준»."""
    out = []
    for s, g in SITES:
        if g in ("중대형CHP", "소형CHP"):
            off = rng.randrange(len(GT_CYCLE))
            for y in range(2014, 2036):
                out.append({"사업장": s, "연도": y, "등급": GT_CYCLE[(y + off) % len(GT_CYCLE)]})
        elif g == "DH":
            for y in range(2014, 2036):
                out.append({"사업장": s, "연도": y, "등급": "표준"})
    return out


def plan_rows(rng, year, grades):
    """한 해 계획 사업 목록. 같은 사업은 해마다 이어지도록 사업 «틀»은 연도 무관 시드로 고른다."""
    rows = []
    infl = 1.025 ** (year - 2023)
    for s, g in SITES:
        frame = random.Random(f"{SEED}-{s}")         # 지사별 사업 틀은 매년 같다
        for budget, table in (("손익", PL), ("자본", CAP)):
            for item, (base, (lo, hi), scope, names) in table.items():
                if not _eligible(scope, s):
                    continue
                n = frame.randint(lo, hi)
                picks = frame.sample(names, min(n, len(names)))
                for name in picks:
                    if item == "외주비-열원정기점검":
                        gr = grades.get((s, year), "간이")
                        amt = OVERHAUL.get(gr, 300_000) * (1 if g == "중대형CHP" else 0.3)
                        name = f"가스터빈 {gr} 정비"
                    else:
                        amt = base * GROUP_MULT[g] / max(1, len(picks)) * frame.uniform(0.6, 1.6)
                    # 건물·구축물 신축은 해마다 있지 않다
                    if item in ("건물", "구축물") and rng.random() < 0.6:
                        continue
                    amt = round(amt * infl * rng.uniform(0.9, 1.12), -3)
                    rows.append({
                        "주관부서명": OWNER[budget], "부서코드": DEPT_CODE[s], "처지사": s,
                        "부서부": f"{s} {frame.choice(PART)}", "속성": ATTR[item],
                        "예산코드": ALL_CODES[item], "예산과목": item, "사업명": f"{s[:2]} {name}",
                        "산출내역": "가상 산출내역(시연용)", "연예산": amt, "_budget": budget,
                    })
    # 본사 배분: 경상정비는 본사(플랜트기술처)에 계획을 잡고 지사가 집행 — 앱 «본사 배분» 규칙 시연
    rows.append({"주관부서명": "플랜트기술처", "부서코드": DEPT_CODE["플랜트기술처"], "처지사": "플랜트기술처",
                 "부서부": "플랜트기술처 설비기획부", "속성": "제조", "예산코드": PL_CODES["수선유지비-열원경상정비"],
                 "예산과목": "수선유지비-열원경상정비", "사업명": "전사 경상정비 통합계약",
                 "산출내역": "가상 산출내역(시연용)", "연예산": round(3_000_000 * infl, -3), "_budget": "손익"})
    return rows


def write_plan(path, year, rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "양식1(월별)"
    ws["A1"] = f"{year}년 유지보수 예산 계획 (가상 데이터 · 시연용)"
    ws["A1"].font = Font(bold=True, size=13)
    ws["A2"] = "※ 사업명·금액은 모두 난수로 만든 합성 데이터입니다. 단위: 천원"
    head = ["주관부서명", "예산귀속부서코드", "예산귀속부서명(처.지사)", "예산귀속부서명(부)", "속성",
            "예산코드", "예산과목", "사업명", "산출내역", "연예산합계"]
    for j, h in enumerate(head, 1):
        c = ws.cell(3, j, h)
        c.font = Font(bold=True)
        c.fill = PatternFill("solid", fgColor="DDEBF7")
    keys = ["주관부서명", "부서코드", "처지사", "부서부", "속성", "예산코드", "예산과목", "사업명", "산출내역", "연예산"]
    for i, r in enumerate(rows, 4):
        for j, k in enumerate(keys, 1):
            ws.cell(i, j, r[k])
    for col, w in zip("ABCDEFGHIJ", (14, 12, 18, 22, 8, 11, 28, 34, 20, 14)):
        ws.column_dimensions[col].width = w
    wb.save(path)


def _variant(rng, name, month, k):
    """계획 사업명 → 전표 텍스트. 사람이 SAP 에 치는 방식처럼 흔들어 놓는다."""
    body = name.split(" ", 1)[1] if " " in name else name
    r = rng.random()
    if r < 0.30:
        t = f"{body} {month}월분"
    elif r < 0.45:
        t = f"{body} {k}차 기성"
    elif r < 0.60:
        t = body
        for a, b in SYN.items():
            if a in t:
                t = t.replace(a, b)
                break
    elif r < 0.70:
        t = body.replace(" ", "")
    elif r < 0.80:
        t = f"{str(month).zfill(2)}월 {body} 대금"
    else:
        t = f"{name} 지급"
    return t


def erp_rows(rng, year, plan, grades):
    """계획 사업마다 실적을 만들고 전표로 쪼갠다. 반환: zrfm2 행 dict 목록."""
    out = []
    doc = [int(f"{year % 100}0000000") + 1]

    def new_doc():
        doc[0] += rng.randint(1, 9)
        return str(doc[0])

    def add(site, item, text, amount_won, month, docno=None, dept_raw=None, part=None):
        day = min(28, rng.randint(1, 28))
        out.append({
            "계정코드": ALL_CODES[item], "약정항목텍스트": item, "기간": f"{year}.{month:03d}",
            "전기일": dt.date(year, month, day), "참조전표번호": docno or new_doc(),
            "금액": int(round(amount_won, -1)), "텍스트": text,
            "지사": dept_raw or site, "부서": part or f"{site} {rng.choice(PART)}",
            "손익센터": f"P{DEPT_CODE[site][1:]}", "거래처": rng.choice(VENDORS),
        })

    def raw_dept(site):
        if site in ALIAS_RAW and rng.random() < 0.5:
            return ALIAS_RAW[site]
        if GROUP_OF[site] == "본사":
            return "본　　사"                       # 본사 전표는 지사칸이 «본사», 부서칸에서 처를 찾는다
        return site

    for p in plan:
        site, item = p["처지사"], p["예산과목"]
        if site == "플랜트기술처" and item == "수선유지비-열원경상정비":
            # 본사 통합계약 → 지사들이 나눠 집행(지사에 같은 과목 계획이 없으면 본사 배분으로 귀속)
            for s, g in SITES:
                if g == "DH" and rng.random() < 0.5:
                    add(s, item, f"경상정비 통합계약 {s[:2]} 배분", p["연예산"] * 1000 * rng.uniform(0.04, 0.08),
                        rng.randint(3, 11))
            continue
        exec_rate = rng.choices([0, rng.uniform(0.55, 0.85), rng.uniform(0.85, 1.05)], [0.06, 0.34, 0.60])[0]
        total = p["연예산"] * 1000 * exec_rate
        if total <= 0:
            continue
        monthly = item in ("수선유지비-열원정기유지보수", "수선유지비-열원경상정비") and rng.random() < 0.6
        n = rng.randint(6, 12) if monthly else rng.choice([1, 1, 2, 3, 4])
        months = sorted(rng.sample(range(1, 13), n))
        parts = [rng.uniform(0.7, 1.3) for _ in months]
        for k, (m, w) in enumerate(zip(months, parts), 1):
            amt = total * w / sum(parts)
            text = _variant(rng, p["사업명"], m, k)
            dn = new_doc()
            add(site, item, text, amt, m, docno=dn, dept_raw=raw_dept(site), part=p["부서부"])
            if rng.random() < 0.06:                       # 같은 전표번호의 인지세 — 텍스트만 보면 놓친다
                add(site, item, "인지세", 20_000, m, docno=dn, dept_raw=raw_dept(site), part=p["부서부"])
            if rng.random() < 0.03:                       # 역분개(±) — 순액 0
                add(site, item, text, amt, m, dept_raw=raw_dept(site), part=p["부서부"])
                add(site, item, text, -amt, m, dept_raw=raw_dept(site), part=p["부서부"])

    plant_sites = [s for s, g in SITES if g != "본사"]
    # 계획에 없는 신규 사업(긴급 수리 등) — 같은 이름끼리 묶여 사업 한 줄이 된다
    for _ in range(18):
        s = rng.choice(plant_sites)
        item = rng.choice(["수선유지비-열원보완및개선", "수선유지비-건물/구축물", "기계장치"])
        name = rng.choice(["긴급 누수 보수", "낙뢰 피해 복구", "침수 설비 복구", "제어카드 긴급 교체"])
        for k in range(rng.randint(1, 3)):
            add(s, item, f"{name} {k + 1}차", rng.uniform(5e6, 6e7), rng.randint(2, 12))
    # 텍스트가 애매한 전표 — 확신도가 낮아 검토 큐로 간다
    for _ in range(70):
        s = rng.choice(plant_sites)
        item = rng.choice(list(PL)[:6])
        add(s, item, rng.choice(VAGUE), rng.uniform(3e6, 9e7), rng.randint(1, 12), dept_raw=raw_dept(s))
    # 200만원 미만 소액 구매 — 지사×과목 «소액자재구매»로 합산
    for _ in range(120):
        s = rng.choice(plant_sites)
        item = rng.choice(["수선유지비-비저장품(보수자재)", "수선유지비-소모품(자재공기구)"])
        add(s, item, rng.choice(["철물 구입", "공구 구입", "자재 구입", "부품 구입"]), rng.uniform(1e5, 1.9e6),
            rng.randint(1, 12))
    rng.shuffle(out)
    return out


def write_erp(path, rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "zrfm2"
    head = ["회사", "약정항목", "약정항목텍스트", "기간/연도", "FM 전기일", "참조 전표 번호", "지급예산금액",
            "텍스트", "이름", "이름", "통화", "손익 센터", "자금관리센터", "약정유형", "공급업체"]
    for j, h in enumerate(head, 1):
        ws.cell(1, j, h).font = Font(bold=True)
    r = 1
    for x in rows:
        r += 1
        vals = {1: "DEMO", 2: x["계정코드"], 3: x["약정항목텍스트"], 4: x["기간"], 5: x["전기일"],
                6: x["참조전표번호"], 7: x["금액"], 8: x["텍스트"], 9: x["지사"], 10: x["부서"],
                11: "KRW", 12: x["손익센터"], 15: x["거래처"]}
        for c, v in vals.items():
            ws.cell(r, c, v)
        ws.cell(r, 5).number_format = "yyyy-mm-dd"
    ws.cell(r + 1, 7, sum(x["금액"] for x in rows))      # SAP 추출본 마지막 줄 총계(앱이 «합계행»으로 거른다)
    wb.save(path)


def write_masters():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "예산코드"
    ws.append(["약정항목", "예산과목", "주관부서코드", "주관부서명", "속성", "비고"])
    for n, c in ALL_CODES.items():
        ws.append([c, n, DEPT_CODE["플랜트기술처"], "플랜트기술처", ATTR[n], "가상 코드(시연용)"])
    wb.save(os.path.join(OUT, "마스터_예산과목.xlsx"))
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "부서코드"
    ws.append(["부서코드", "부서명", "처지사", "비고"])
    for s, _ in SITES:
        for p in PART:
            ws.append([f"{DEPT_CODE[s]}{PART.index(p)}", f"{s} {p}", s, "가상 코드(시연용)"])
    wb.save(os.path.join(OUT, "마스터_부서코드.xlsx"))


def write_corr_rules(rng):
    """담당자 보정사전 — 애매한 텍스트 몇 개를 사람이 정해 둔 것처럼."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "보정사전"
    ws.append(["지사", "예산과목", "전표텍스트", "올바른사업명", "계획사업명", "비고"])
    ws.append(["동탄지사", "수선유지비-열원경상정비", "외주 작업비 정산", "동탄 펌프류 경상정비", "", "담당자 확인(가상)"])
    ws.append(["", "수선유지비-소모품(자재공기구)", "물품대금", "제외(유지보수 아님)", "", "전 지사 공통 제외(가상)"])
    ws.append(["광교지사", "수선유지비-열원보완및개선", "기타 수선비", "광교 배관 보온재 교체", "", "담당자 확인(가상)"])
    wb.save(os.path.join(OUT, "보정규칙.xlsx"))


def forecast_inputs(rng, grades_list):
    chp = [s for s, g in SITES if g in ("중대형CHP", "소형CHP")]
    regular = []
    for s in chp[:6]:
        for y in range(2026, 2036):
            regular.append({"사업장": s, "연도": y, "항목": "GT LTSA", "예산과목": "외주비-열원정기점검",
                            "금액": round(rng.uniform(800_000, 2_000_000), -3), "비고": "가상 정기계약"})
    invest = []
    for s in rng.sample([s for s, g in SITES if g != "본사"], 5):
        y = rng.randint(2027, 2034)
        invest.append({"사업장": s, "연도": y, "금액": round(rng.uniform(5e6, 2e7), -3), "비고": "가상 설비 개체 계획"})
    idx = (98.0, 101.4, 103.0, 102.6, 100.1, 108.0, 116.5, 119.8, 122.1, 124.3)
    price = [{"연도": y, "지수": v, "비고": "가상 지수(시연용)"} for y, v in zip(range(2016, 2026), idx)]
    return {"base_year": "2026", "grades": grades_list, "regular_contract": regular,
            "investment_plan": invest, "price_index": price}


def main():
    rng = random.Random(SEED)
    os.makedirs(OUT, exist_ok=True)
    gl = grade_plan(rng)
    grades = {(x["사업장"], x["연도"]): x["등급"] for x in gl}
    summary = {}
    for y in PLAN_YEARS:
        plan = plan_rows(rng, y, grades)
        write_plan(os.path.join(OUT, f"{y}_계획_양식1.xlsx"), y, plan)
        s = {"계획행": len(plan), "계획합계(억)": round(sum(p["연예산"] for p in plan) / 1e5, 1)}
        if y in ACTUAL_YEARS:
            erp = erp_rows(rng, y, plan, grades)
            write_erp(os.path.join(OUT, f"{y}_zrfm2.xlsx"), erp)
            s.update({"전표": len(erp), "전표합계(억)": round(sum(e["금액"] for e in erp) / 1e8, 1)})
        summary[y] = s
    write_masters()
    write_corr_rules(rng)
    with open(os.path.join(OUT, "전망_기준정보.json"), "w", encoding="utf-8") as f:
        json.dump(forecast_inputs(rng, gl), f, ensure_ascii=False, indent=1)
    for y, s in summary.items():
        print(y, s)


if __name__ == "__main__":
    main()
