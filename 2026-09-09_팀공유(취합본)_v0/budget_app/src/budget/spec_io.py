# -*- coding: utf-8 -*-
"""연동규격(연동규격_INTERFACE.md) CSV 계약 어댑터.

두 코드베이스(본인 앱 ↔ budget_app)를 **파일 계약**으로 잇기 위한 입출력 계층.
budget_app의 검증된 매칭 엔진은 그대로 두고, 규격 CSV ↔ 내부 모델 변환만 담당한다.

규격 파일(모두 utf-8-sig, 금액 단위 **원**):
  - data_{연도}.csv       : 정제 실적 (거래처명·사업장·전기일·전표헤더텍스트·금액·계정과목)
  - budget_{연도}.csv     : 예산 계획 (사업명·예산과목·연예산 합계·부서코드·부서명·예산코드·속성·주관부서명)
  - classified_{연도}.csv : data 6칸 + 투자유형_확정 (★본인 소비)
  - matched_{연도}.csv    : data 6칸 + 사업코드 + 사업명 + 매칭확신도 (동료 내부)

내부 단위는 천원. 경계에서 ×1000 / ÷1000 변환.

⚠️ 미확정 공백(연동_통합가이드.md §4):
  - 투자유형_확정 : 분류 로직 미구현(보류). classifier 훅으로 주입, 기본 '미분류'.
  - 사업코드      : 우리 계획·실적에 없음 → matched 출력 시 공란.
  - 거래처명      : zrfm2엔 공급업체 '코드'만 → 이름 아님(코드로 채움).
  - 사업장→처지사 : 손익센터 코드. 코드→지사 매핑은 budget_csv로 구성(dept_map_from_budget).
"""
import csv as _csv
import json
from datetime import datetime, timezone

import pandas as pd

from . import erp_loader, loaders, normalize

# ── 규격 컬럼 이름(정확히 이 문자열. budget의 부서 칸엔 줄바꿈 포함) ──────────
DATA_COLUMNS = ["거래처명", "사업장", "전기일", "전표헤더텍스트", "금액", "계정과목"]
BUDGET_COL_사업명 = "사업명"
BUDGET_COL_예산과목 = "예산과목"
BUDGET_COL_연예산 = "연예산 합계"
BUDGET_COL_부서코드 = "예산귀속 \n부서코드"        # ← 줄바꿈(\n) 포함, 규격 §3-2
BUDGET_COL_부서명 = "예산귀속\n부서명(처.지사)"     # ← 줄바꿈(\n) 포함
BUDGET_COL_예산코드 = "예산코드"
BUDGET_COL_속성 = "속성"
BUDGET_COL_주관부서 = "주관부서명"
BUDGET_COLUMNS = [
    BUDGET_COL_사업명, BUDGET_COL_예산과목, BUDGET_COL_연예산, BUDGET_COL_부서코드,
    BUDGET_COL_부서명, BUDGET_COL_예산코드, BUDGET_COL_속성, BUDGET_COL_주관부서,
]
CLASSIFIED_COLUMNS = DATA_COLUMNS + ["투자유형_확정"]
MATCHED_SPEC_COLUMNS = DATA_COLUMNS + ["사업코드", "사업명", "매칭확신도"]

INVESTMENT_TYPES = [
    "LTSA", "정기사업", "노후설비개체", "AX/DX",
    "운영안정성 제고", "환경강화", "교육강화", "보안강화",
]
UNCLASSIFIED = "미분류"

WON_PER_THOUSAND = 1000


def _to_won(thousand):
    return None if thousand is None or pd.isna(thousand) else round(float(thousand) * WON_PER_THOUSAND)


def _to_thousand(won):
    return None if won is None or (isinstance(won, float) and pd.isna(won)) else float(won) / WON_PER_THOUSAND


# ══════════════════════════════════════════════════════════════════════════
# 쓰기: budget_app 자체 데이터 → 규격 CSV (본인/동료 교환용)
# ══════════════════════════════════════════════════════════════════════════

def write_data_csv(zrfm2_path, out_path, year=None, normalize_item_alias=None):
    """zrfm2.XLSX → 규격 data_{연도}.csv (원 단위).

    year 지정 시 해당 연도 전표만. 계정과목은 별칭 정규화(선택).
    거래처명=공급업체 코드(이름 아님 — 규격 §3-1 대비 공백 gap), 사업장=손익센터 코드.
    """
    erp = erp_loader.load_erp(zrfm2_path)
    return write_data_csv_from_df(erp, out_path, year=year,
                                  normalize_item_alias=normalize_item_alias)


def write_data_csv_from_df(erp, out_path, year=None, normalize_item_alias=None):
    """내부 ERP DataFrame(erp_loader.ERP_COLUMNS 스키마, DB 로드본 포함) → data_{연도}.csv."""
    rows = []
    for _, r in erp.iterrows():
        if year and r["연도"] and str(r["연도"]) != str(year):
            continue
        item = r["예산과목원문"]
        if normalize_item_alias is not None:
            item = normalize.normalize_item(item, normalize_item_alias)
        rows.append({
            "거래처명": r.get("거래처코드"),      # ⚠️ 코드(이름 아님)
            "사업장": r.get("사업장코드"),
            "전기일": r.get("전기일"),
            "전표헤더텍스트": r.get("사업명"),
            "금액": r.get("금액원"),
            "계정과목": item,
        })
    df = pd.DataFrame(rows, columns=DATA_COLUMNS)
    df.to_csv(out_path, index=False, encoding="utf-8-sig")
    return out_path


def write_budget_csv(plan_path, out_path, normalize_item_alias=None):
    """계획본(양식1(월별)) → 규격 budget_{연도}.csv (연예산 원 단위)."""
    df = loaders.load_business_plan(plan_path)
    return write_budget_csv_from_df(df, out_path, normalize_item_alias=normalize_item_alias)


def write_budget_csv_from_df(df, out_path, normalize_item_alias=None):
    """내부 계획 DataFrame(loaders.PLAN_COLUMNS 스키마, DB 로드본 포함) → budget_{연도}.csv."""
    rows = []
    for _, r in df.iterrows():
        item = r.get("예산과목")
        if normalize_item_alias is not None:
            item = normalize.normalize_item(item, normalize_item_alias)
        rows.append({
            BUDGET_COL_사업명: r.get("사업명"),
            BUDGET_COL_예산과목: item,
            BUDGET_COL_연예산: _to_won(r.get("연예산")),
            BUDGET_COL_부서코드: r.get("부서코드"),
            BUDGET_COL_부서명: r.get("처지사"),
            BUDGET_COL_예산코드: r.get("예산코드"),
            BUDGET_COL_속성: r.get("속성"),
            BUDGET_COL_주관부서: r.get("주관부서명"),
        })
    out = pd.DataFrame(rows, columns=BUDGET_COLUMNS)
    out.to_csv(out_path, index=False, encoding="utf-8-sig")
    return out_path


def write_matched_csv(erp_annotated, out_path):
    """매칭 결과(matching.match_actuals의 erp_annotated) → 규격 matched_{연도}.csv.

    사업코드는 우리 데이터에 없음 → 공란(연동_통합가이드 §4-3 확정 전까지).
    """
    def col(name):
        return erp_annotated[name] if name in erp_annotated.columns else [None] * len(erp_annotated)

    out = pd.DataFrame({
        "거래처명": list(col("거래처코드")),
        "사업장": list(col("사업장코드")),
        "전기일": list(col("전기일")),
        "전표헤더텍스트": list(col("사업명")),
        "금액": list(col("금액원")),
        "계정과목": list(col("과목정규")),
        "사업코드": [None] * len(erp_annotated),        # ⚠️ gap
        "사업명": list(col("매칭사업명")),
        "매칭확신도": list(col("매칭확신도")),
    }, columns=MATCHED_SPEC_COLUMNS)
    out.to_csv(out_path, index=False, encoding="utf-8-sig")
    return out_path


def write_classified_csv(erp_annotated, out_path, classifier=None,
                         normalize_item_alias=None):
    """매칭 결과 → 규격 classified_{연도}.csv (data 6칸 + 투자유형_확정).

    classifier: 전표헤더텍스트(str) → 투자유형(str) 함수. None이면 전부 '미분류'.
    ⚠️ 투자유형 분류는 담당 확정 전까지 보류 → 기본 '미분류'(연동_통합가이드 §4-1).
    """
    def col(name):
        return erp_annotated[name] if name in erp_annotated.columns else [None] * len(erp_annotated)

    texts = list(col("사업명"))
    types = []
    for t in texts:
        v = classifier(t) if classifier else UNCLASSIFIED
        if v not in INVESTMENT_TYPES:
            v = UNCLASSIFIED
        types.append(v)
    items = list(col("과목정규"))
    if normalize_item_alias is not None:
        items = [normalize.normalize_item(x, normalize_item_alias) for x in items]
    out = pd.DataFrame({
        "거래처명": list(col("거래처코드")),
        "사업장": list(col("사업장코드")),
        "전기일": list(col("전기일")),
        "전표헤더텍스트": texts,
        "금액": list(col("금액원")),
        "계정과목": items,
        "투자유형_확정": types,
    }, columns=CLASSIFIED_COLUMNS)
    out.to_csv(out_path, index=False, encoding="utf-8-sig")
    return out_path


# ══════════════════════════════════════════════════════════════════════════
# 읽기: 규격 CSV → budget_app 내부 모델 (본인이 CSV를 넘겨줄 때 수용)
# ══════════════════════════════════════════════════════════════════════════

def read_data_csv(path):
    """규격 data_{연도}.csv → 내부 ERP DataFrame(erp_loader.ERP_COLUMNS 호환).

    금액(원)→금액천원 환산. 사업장(손익센터 코드)은 지사원문에 담되, 코드→지사
    정규화는 dept_map_from_budget 등 별도 매핑 필요(연동_통합가이드 §4).
    """
    df = pd.read_csv(path, dtype=str, keep_default_na=True)
    recs = []
    for i, r in df.iterrows():
        amt = r.get("금액")
        amt = float(amt) if amt not in (None, "") and not pd.isna(amt) else None
        recs.append({
            "계정코드": None,
            "예산과목원문": r.get("계정과목"),
            "연도": None,
            "전표번호": None,
            "금액원": amt,
            "금액천원": (amt / 1000.0 if amt is not None else None),
            "사업명": r.get("전표헤더텍스트"),
            "지사원문": r.get("사업장"),          # ⚠️ 코드(이름 아님)
            "부서부원문": None,
            "전기일": r.get("전기일"),
            "사업장코드": r.get("사업장"),
            "거래처코드": r.get("거래처명"),
            "_erp_row": i + 2,
        })
    return pd.DataFrame(recs, columns=erp_loader.ERP_COLUMNS)


def read_budget_csv(path):
    """규격 budget_{연도}.csv → 내부 계획 DataFrame(loaders.PLAN_COLUMNS 호환).

    연예산 합계(원)→연예산(천원) 환산.
    """
    df = pd.read_csv(path, dtype=str, keep_default_na=True)
    recs = []
    for i, r in df.iterrows():
        won = r.get(BUDGET_COL_연예산)
        try:
            won = float(won) if won not in (None, "") and not pd.isna(won) else None
        except (TypeError, ValueError):
            won = None
        recs.append({
            "주관부서명": r.get(BUDGET_COL_주관부서),
            "부서코드": r.get(BUDGET_COL_부서코드),
            "처지사": r.get(BUDGET_COL_부서명),
            "부서부": None,
            "속성": r.get(BUDGET_COL_속성),
            "예산코드": r.get(BUDGET_COL_예산코드),
            "예산과목": r.get(BUDGET_COL_예산과목),
            "사업명": r.get(BUDGET_COL_사업명),
            "산출내역": None,
            "연예산": (won / 1000.0 if won is not None else None),
            "_row": i + 2,
        })
    return pd.DataFrame(recs, columns=loaders.PLAN_COLUMNS + ["_row"])


def dept_map_from_budget(budget_df, digits=3):
    """budget 내부 DataFrame에서 부서코드 앞 N자리 → 처지사명 매핑 구성.

    규격 §6-3: 실적 손익센터(4자리)와 계획 부서코드(6~7자리)는 앞 3자리가
    같으면 같은 사업소. 이 매핑으로 data의 사업장(코드)→처지사(이름) 환원.
    """
    m = {}
    for _, r in budget_df.iterrows():
        code = r.get("부서코드")
        name = r.get("처지사")
        if code and name:
            key = str(code).strip()[:digits]
            m.setdefault(key, name)
    return m


def resolve_dept_by_code(site_code, dept_map, digits=3):
    """손익센터 코드 → 처지사명(dept_map_from_budget 결과 사용). 실패 시 None."""
    if not site_code:
        return None
    return dept_map.get(str(site_code).strip()[:digits])


# ══════════════════════════════════════════════════════════════════════════
# 팀 v2 앱(예산예측프로그램_팀공유_v2) 「사업 실적 연결」 계약 — 결과 JSON (schemaVersion 1)
# ══════════════════════════════════════════════════════════════════════════
# 동료 앱의 checkpoint_actuals.prepare_result()가 읽는 형식. 금액은 **천원**(KRW_THOUSAND),
# sourceTotals의 amountWon만 원. 검증 규칙(동료 코드 기준):
#   - sourceYears == [연도] 단일 연도
#   - groups(13열)·details(8열)·exclusions(8열) 헤더 행이 정확히 일치
#   - 묶음마다 details 반영 실적 합계 == 묶음 전표 합계 (원 단위로 정확히)
#   - (원장,지사,과목,집계표 원본행) 중복 금지, 원본행은 1 이상 정수
#   - 배정/제외한 (원장,지사,과목)은 sourceTotals에 반드시 존재
# 우리 매칭 결과(erp_annotated)를 이 형식으로 바꾼다. 묶음 = (원장×지사×과목×귀속 사업) 단위,
# 계획집행은 계획행 원본 행번호(_row)를, 신규는 합성 행번호(NEW_ROW_BASE+n)를 '집계표 원본행'으로 쓴다.

TEAM_JSON_SCHEMA_VERSION = 1
TEAM_JSON_AMOUNT_UNIT = "KRW_THOUSAND"
TEAM_JSON_GROUP_HEADER = [
    "묶음ID", "원장", "지사", "예산과목", "처리방법", "전표 합계(천원)", "사업 실적 합계(천원)",
    "단수차이(천원)", "전표항목수", "사업수", "대상 사업명", "전표텍스트", "참조전표번호",
]
TEAM_JSON_DETAIL_HEADER = [
    "묶음ID", "원장", "지사", "예산과목", "집계표 원본행", "사업명", "기준 실적(천원)", "반영 실적(천원)",
]
TEAM_JSON_EXCLUSION_HEADER = [
    "원장", "지사", "예산과목", "전표텍스트", "제외 금액(천원)", "담당자 제외 사유", "보정ID", "참조전표번호",
]
# 동료 검토 화면(review_data.load_result)이 존재만 확인하는 부가 표 — 헤더만 채운다.
TEAM_JSON_AUX_TABLES = {
    "corrections": ["보정ID", "원장", "지사", "예산과목", "사업명", "금액(천원)", "비고"],
    "differences": ["원장", "지사", "예산과목", "전표텍스트", "금액(천원)", "사유"],
    "spareDates": ["원장", "지사", "예산과목", "전기일", "양수(천원)", "음수(천원)", "순액(천원)"],
    "spareSources": ["원장", "지사", "예산과목", "전기일", "전표텍스트", "금액(천원)"],
}
UNKNOWN_ORG = "(지사 미확인)"
UNKNOWN_ACCOUNT = "(과목 미확인)"
NEW_ROW_BASE = 2_000_000          # 신규 사업(계획행 없음)의 합성 '집계표 원본행' 시작값
ASSIGNED_GUBUN = ("계획집행", "신규")
EXCLUDED_GUBUN = ("미반영",)
NEW_LABEL_PREFIX = "[신규] "


def _s(v):
    """NaN/None → None, 그 외 strip 문자열."""
    if v is None:
        return None
    if isinstance(v, float) and v != v:
        return None
    s = str(v).strip()
    return s or None


def _won_int(rec):
    """전표 금액을 정수 원으로. 금액원이 없으면 금액천원×1000."""
    w = rec.get("금액원")
    if w is None or (isinstance(w, float) and w != w):
        t = rec.get("금액천원")
        if t is None or (isinstance(t, float) and t != t):
            return 0
        return int(round(float(t) * WON_PER_THOUSAND))
    return int(round(float(w)))


def _thousand(won):
    """정수 원 → 천원 float. repr가 소수 3자리 이하로 나와 동료 검증(Decimal(str)×1000)을 통과한다."""
    return won / WON_PER_THOUSAND


def _row_scope(rec, ledger):
    """(원장, 지사, 과목) — 정규화 처지사가 없으면 ERP 원문 지사명, 그것도 없으면 '(지사 미확인)'."""
    org = _s(rec.get("처지사정규")) or _s(rec.get("지사원문")) or UNKNOWN_ORG
    account = _s(rec.get("과목정규")) or _s(rec.get("예산과목원문")) or UNKNOWN_ACCOUNT
    return (ledger, org, account)


def clean_match_label(label):
    """'[신규] 이름' → '이름'. None/공란은 None."""
    s = _s(label)
    if s is None:
        return None
    if s.startswith(NEW_LABEL_PREFIX):
        s = s[len(NEW_LABEL_PREFIX):].strip()
    return s or None


def build_team_result_json(year, frames_by_budget, meta=None):
    """{'손익': erp_annotated, '자본': erp_annotated} → 팀 v2 결과 JSON(dict).

    포함 규칙(원장별 run 결과에서):
      구분 ∈ 계획집행·신규  → 배정(groups/details)
      구분 = 미반영          → exclusions (선택 해제 과목·지사, 미분류, 미매핑 전표)
      구분 = ''(타예산)·제외 → 건너뜀 (타예산은 상대 원장 run에서 집계되므로 중복 방지)
    총액 불변식: Σ sourceTotals = Σ 배정 + Σ 제외 (미배정순액 0).
    """
    year_i = int(str(year))
    groups, details, exclusions = [], [], []
    source_totals, assigned_won, excluded_won = {}, {}, {}
    bundles, order = {}, []
    new_row_counter = NEW_ROW_BASE

    for ledger, frame in frames_by_budget.items():
        if ledger not in ("손익", "자본"):
            raise ValueError(f"원장은 손익/자본이어야 합니다: {ledger}")
        if frame is None or len(frame) == 0:
            continue
        cols = set(frame.columns)
        for rec in frame.to_dict("records"):
            gubun = _s(rec.get("구분")) or ""
            if gubun not in ASSIGNED_GUBUN and gubun not in EXCLUDED_GUBUN:
                continue
            scope = _row_scope(rec, ledger)
            won = _won_int(rec)
            source_totals[scope] = source_totals.get(scope, 0) + won
            text = _s(rec.get("사업명"))
            doc = _s(rec.get("전표번호"))
            if gubun in EXCLUDED_GUBUN:
                excluded_won[scope] = excluded_won.get(scope, 0) + won
                exclusions.append([scope[0], scope[1], scope[2], text or "", _thousand(won),
                                   "미반영(선택 해제 과목·지사 / 미분류 / 미매핑)", "", doc or ""])
                continue
            assigned_won[scope] = assigned_won.get(scope, 0) + won
            label = clean_match_label(rec.get("매칭사업명")) or "(사업명 없음)"
            plan_row = rec.get("매칭행") if "매칭행" in cols else None
            try:
                plan_row = int(plan_row) if plan_row is not None and plan_row == plan_row else None
            except (TypeError, ValueError):
                plan_row = None
            has_plan_row = gubun == "계획집행" and plan_row is not None and plan_row >= 1
            key = (scope, "계획집행", plan_row) if has_plan_row else (scope, gubun, label)
            b = bundles.get(key)
            if b is None:
                if has_plan_row:
                    src_row = plan_row
                else:
                    src_row = new_row_counter
                    new_row_counter += 1
                b = {"scope": scope, "gubun": gubun, "label": label, "src_row": src_row,
                     "won": 0, "n": 0, "texts": [], "docs": []}
                bundles[key] = b
                order.append(key)
            b["won"] += won
            b["n"] += 1
            if text and text not in b["texts"] and len(b["texts"]) < 3:
                b["texts"].append(text)
            if doc and doc not in b["docs"] and len(b["docs"]) < 5:
                b["docs"].append(doc)

    for n, key in enumerate(order, 1):
        b = bundles[key]
        ledger, org, account = b["scope"]
        gid = f"{'P' if ledger == '손익' else 'C'}{n:06d}"
        amt = _thousand(b["won"])
        groups.append([gid, ledger, org, account, b["gubun"], amt, amt, 0, b["n"], 1,
                       b["label"], " / ".join(b["texts"]), ",".join(b["docs"])])
        details.append([gid, ledger, org, account, b["src_row"], b["label"], amt, amt])

    totals = [{"ledger": s[0], "org": s[1], "account": s[2], "amountWon": w}
              for s, w in sorted(source_totals.items())]
    summary = {}
    for ledger in frames_by_budget:
        src = sum(w for s, w in source_totals.items() if s[0] == ledger)
        asg = sum(w for s, w in assigned_won.items() if s[0] == ledger)
        exc = sum(w for s, w in excluded_won.items() if s[0] == ledger)
        summary[ledger] = {"sourceWon": src, "assignedWon": asg, "excludedWon": exc,
                           "unassignedWon": src - asg - exc,
                           "groups": sum(1 for k in order if k[0][0] == ledger)}

    return {
        "schemaVersion": TEAM_JSON_SCHEMA_VERSION,
        "amountUnit": TEAM_JSON_AMOUNT_UNIT,
        "amountMatching": True,
        "sourceYears": [year_i],
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "generator": {"name": "budget_app", "kind": "matching-engine-export", **(meta or {})},
        "summary": summary,
        "sourceTotals": totals,
        "reconciliation": {
            "groups": [TEAM_JSON_GROUP_HEADER] + groups,
            "details": [TEAM_JSON_DETAIL_HEADER] + details,
            "exclusions": [TEAM_JSON_EXCLUSION_HEADER] + exclusions,
            **{k: [v] for k, v in TEAM_JSON_AUX_TABLES.items()},
        },
    }


def write_team_result_json(out_path, result):
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    return out_path


def write_matched_csv_combined(frames_by_budget, out_path):
    """손익·자본 run 결과를 합쳐 규격 matched_{연도}.csv(연도 단일 파일) 생성.

    동료 앱(plan_vs_actual.py 등)은 `matched_{연도}.csv` 하나를 읽으므로 두 원장을 합친다.
    타예산(구분 '')·제외 행은 상대 원장에서 집계되므로 넣지 않는다(중복 방지).
    사업명 = 매칭사업명('[신규] ' 접두 제거), 미반영은 공란.
    """
    keep = list(ASSIGNED_GUBUN) + list(EXCLUDED_GUBUN)
    parts = []
    for ledger, frame in frames_by_budget.items():
        if frame is None or len(frame) == 0:
            continue
        f = frame.copy()
        gub = f["구분"].map(lambda v: _s(v) or "") if "구분" in f.columns \
            else pd.Series([""] * len(f), index=f.index)
        f = f[gub.isin(keep)].copy()
        gub = gub[gub.isin(keep)]
        if "매칭사업명" in f.columns:
            f["매칭사업명"] = [clean_match_label(v) if g in ASSIGNED_GUBUN else None
                            for v, g in zip(f["매칭사업명"], gub)]
        parts.append(f)
    combined = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
    return write_matched_csv(combined, out_path)
