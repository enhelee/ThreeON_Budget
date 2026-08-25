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
