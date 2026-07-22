# -*- coding: utf-8 -*-
"""계획 사업 ↔ ERP 전표 매칭으로 행별 실적금액 도출.

매칭 우선순위(요구사항):
  1순위 예산과목  — ERP 계정코드→표준과목명→alias 정규화 후 계획 과목과 동일
  2순위 처지사    — ERP 지사명 정규화 후 계획 처지사와 동일
  3순위 사업명    — 위 두 키가 같은 그룹 내에서 사업명 유사도(토큰셋) ≥ 임계값
각 ERP 전표는 가장 유사한 단일 계획행에 귀속(중복합산 방지). 귀속되지 않은
전표는 신규사업으로 (예산과목×처지사)별 집계한다.
"""
from collections import defaultdict

from rapidfuzz import fuzz

from . import normalize


def normalize_erp_df(erp_df, code_to_item, item_alias, dept_alias, plan_depts):
    """ERP DataFrame에 과목정규/처지사정규 컬럼 추가."""
    df = erp_df.copy()
    canon_items, canon_depts = [], []
    for _, row in df.iterrows():
        base = code_to_item.get(row["계정코드"]) if row["계정코드"] else None
        if not base:
            base = row["예산과목원문"]
        canon_items.append(normalize.normalize_item(base, item_alias))
        canon_depts.append(
            normalize.normalize_dept(row["지사원문"], plan_depts, dept_alias)
        )
    df["과목정규"] = canon_items
    df["처지사정규"] = canon_depts
    return df


def _sim(a, b):
    if not a or not b:
        return 0.0
    return fuzz.WRatio(str(a), str(b))


def match_actuals(plan_df, erp_norm_df, budget_items, pl_items, cap_items,
                  threshold=80, new_policy="group"):
    """계획행별 실적금액 산출 + 신규사업 집계.

    plan_df: 계획본 양식1(월별) 로드 결과(loaders.PLAN_COLUMNS + _row).
    erp_norm_df: normalize_erp_df 결과(과목정규/처지사정규 포함, 전체 예산 혼재).
    budget_items: 이번 예산(손익|자본)에 속한 과목 set(정규 표기).
    pl_items, cap_items: 손익/자본 전체 과목 set(미분류 판정용).
    threshold: 사업명 유사도(%) — 세부 귀속 tie-break 및 저유사 플래그 기준.
    new_policy:
      "group"       — (권장) (과목×처지사)에 계획행이 하나도 없을 때만 신규.
                       계획행 있는 그룹의 전표는 사업명 최고유사 계획행에 귀속.
      "strict_name" — 사업명 유사도 ≥ threshold 인 전표만 계획집행, 나머지 신규
                       (사용자 원지침 그대로. 표기 차이로 신규가 과대해질 수 있음).

    반환 dict: plan_rows, new_rows, erp_annotated, unmatched_dept,
               unclassified_item.
    """
    known = pl_items | cap_items

    # 이번 예산에 해당하는 ERP 전표만 대상
    erp = erp_norm_df
    in_budget_idx = [
        i for i, it in enumerate(erp["과목정규"]) if it in budget_items
    ]

    # 그룹: (과목정규, 처지사정규) -> [erp positional index]
    groups = defaultdict(list)
    for i in in_budget_idx:
        key = (erp["과목정규"].iloc[i], erp["처지사정규"].iloc[i])
        groups[key].append(i)

    # 계획행 그룹핑: (과목, 처지사) -> [plan row dict]
    plan_by_key = defaultdict(list)
    plan_rows = []
    for _, prow in plan_df.iterrows():
        rec = dict(prow)
        rec["실적금액"] = 0.0
        rec["매칭전표수"] = 0
        rec["저유사전표수"] = 0
        rec["구분"] = "미시행"
        plan_rows.append(rec)
        plan_by_key[(rec.get("예산과목"), rec.get("처지사"))].append(rec)

    # ERP별 귀속 결과
    attributed = {}      # erp idx -> plan rec / None(신규)
    erp_match_name = {}  # erp idx -> 귀속된 계획 사업명 / None(신규)

    for key, idxs in groups.items():
        candidates = plan_by_key.get(key, [])
        for i in idxs:
            erp_name = erp["사업명"].iloc[i]
            amt = erp["금액천원"].iloc[i]
            if not candidates:
                attributed[i] = None       # 그룹에 계획행 없음 → 신규
                erp_match_name[i] = None
                continue
            best, best_score = None, -1
            for prec in candidates:
                s = _sim(erp_name, prec.get("사업명"))
                if s > best_score:
                    best, best_score = prec, s
            if new_policy == "strict_name" and best_score < threshold:
                attributed[i] = None       # 엄격정책: 사업명 미달 → 신규
                erp_match_name[i] = None
            else:
                best["실적금액"] += (amt or 0.0)
                best["매칭전표수"] += 1
                if best_score < threshold:
                    best["저유사전표수"] += 1
                attributed[i] = best
                erp_match_name[i] = best.get("사업명")

    # 계획행 구분 확정
    for rec in plan_rows:
        rec["구분"] = "계획집행" if rec["매칭전표수"] > 0 else "미시행"

    # 신규사업: 귀속 안된 in-budget 전표를 (과목,처지사)별 집계
    new_group = defaultdict(lambda: {"금액": 0.0, "전표": [], "사업명들": []})
    for i in in_budget_idx:
        if attributed.get(i) is None:
            key = (erp["과목정규"].iloc[i], erp["처지사정규"].iloc[i])
            g = new_group[key]
            g["금액"] += (erp["금액천원"].iloc[i] or 0.0)
            if erp["전표번호"].iloc[i]:
                g["전표"].append(erp["전표번호"].iloc[i])
            if erp["사업명"].iloc[i]:
                g["사업명들"].append(erp["사업명"].iloc[i])

    new_rows = []
    for (item, dept), g in new_group.items():
        distinct = list(dict.fromkeys(g["사업명들"]))
        label = " / ".join(distinct[:3])
        if len(distinct) > 3:
            label += f" 외 {len(distinct) - 3}건"
        name = f"[신규] {label}" if label else "[신규] (사업명 없음)"
        new_rows.append({
            "예산과목": item,
            "처지사": dept if dept else "(미매핑)",
            "사업명": name,
            "실적금액": g["금액"],
            "구분": "신규",
            "전표건수": len(g["전표"]),
            "비고": f"전표 {len(g['전표'])}건: " + ", ".join(g["전표"][:5])
                   + (" ..." if len(g["전표"]) > 5 else ""),
        })
    new_rows.sort(key=lambda x: (str(x["예산과목"]), str(x["처지사"])))

    # 검토 항목: 미매핑 처지사 / 미분류 과목 (in-budget 전표 기준)
    unmatched_dept = sorted({
        erp["지사원문"].iloc[i] for i in in_budget_idx
        if erp["처지사정규"].iloc[i] is None and erp["지사원문"].iloc[i]
    })
    unclassified_item = sorted({
        erp["과목정규"].iloc[i] for i in range(len(erp))
        if erp["과목정규"].iloc[i] and erp["과목정규"].iloc[i] not in known
    })

    # zrfm2_V1용 R열: 귀속 계획 사업명 / [신규] / 빈값(타예산·미분류)
    r_labels = []
    for i in range(len(erp)):
        if i in erp_match_name:
            r_labels.append(erp_match_name[i] if erp_match_name[i] else "[신규]")
        else:
            r_labels.append("")
    erp_annotated = erp.copy()
    erp_annotated["매칭사업명"] = r_labels

    return {
        "plan_rows": plan_rows,
        "new_rows": new_rows,
        "erp_annotated": erp_annotated,
        "unmatched_dept": unmatched_dept,
        "unclassified_item": unclassified_item,
    }
