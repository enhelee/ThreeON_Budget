# -*- coding: utf-8 -*-
"""계획 사업 ↔ ERP 전표 매칭으로 행별 실적금액 도출.

매칭 우선순위(요구사항):
  1순위 예산과목  — ERP 계정코드→표준과목명→alias 정규화 후 계획 과목과 동일
  2순위 처지사    — ERP 지사명 정규화 후 계획 처지사와 동일
  3순위 참조전표번호 — **동일 참조전표번호 전표는 하나의 내역**으로 묶고,
         묶음 안에서 |금액|이 가장 큰 전표의 텍스트를 대표 사업명으로 사용.
         (예: 본 용역대금 8,072,425원 + 인지세 20,000원이 같은 전표번호면
          인지세도 본 용역과 같은 사업으로 귀속 — 텍스트만 보면 놓치는 케이스)
  4순위 사업명    — 위 키가 같은 그룹 내에서 대표 사업명 유사도(WRatio) ≥ 임계값
각 전표묶음은 가장 유사한 단일 계획행에 귀속(중복합산 방지). 귀속되지 않은
묶음은 신규사업으로, 대표 텍스트 유사도로 클러스터링해 사업 단위 행을 만든다
(부호 상쇄(±) 전표도 같은 클러스터에 묶여 순액으로 집계).
"""
from collections import defaultdict

import pandas as pd
from rapidfuzz import fuzz

from . import normalize


def _clean_na(v):
    """pandas NaN / None을 파이썬 None으로 정규화."""
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    return v


def normalize_erp_df(erp_df, code_to_item, item_alias, dept_alias, plan_depts):
    """ERP DataFrame에 과목정규/처지사정규 컬럼 추가."""
    df = erp_df.copy()
    has_j = "부서부원문" in df.columns
    canon_items, canon_depts = [], []
    for _, row in df.iterrows():
        code = _clean_na(row["계정코드"])
        base = code_to_item.get(code) if code else None
        if not base:
            base = _clean_na(row["예산과목원문"])
        canon_items.append(normalize.normalize_item(base, item_alias))

        raw_dept = _clean_na(row["지사원문"])
        j = _clean_na(row["부서부원문"]) if has_j else None
        # ① 복합키 별칭 'I열|J열' — I열이 '본　　사'처럼 뭉뚱그려져 있어 I열만으론
        #    구분할 수 없는 전표를 부서명(부)까지 보고 지정할 때 사용한다.
        d = dept_alias.get(f"{raw_dept}|{j}") if (raw_dept and j) else None
        if d is None:
            d = normalize.normalize_dept(raw_dept, plan_depts, dept_alias)
        if d is None:
            # ② J열(부서명(부)) 텍스트에서 처지사 탐지 → ③ J열 자체 별칭
            d = normalize.dept_from_text(j, plan_depts)
        if d is None and j:
            d = dept_alias.get(str(j).strip())
        if d is None and not j and raw_dept and \
                str(raw_dept).replace("　", "").replace(" ", "").strip() == "본사":
            # ④ 본사 전표인데 J열(부서명)이 아예 없어 단서가 전무한 경우만
            #    플랜트기술처로 기본 귀속(사용자 확정 규칙). J열에 부서명이
            #    있는 본사 전표(예: '경영지원처 총무부')는 기본 귀속하지 않고
            #    미매핑으로 보고한다 — 열원과 무관한 본사 사옥·IT 비용이
            #    플랜트기술처 실적으로 부풀려지는 것을 막기 위함.
            d = "플랜트기술처"
        canon_depts.append(d)
    # NaN 혼입 방지를 위해 object dtype으로 명시 저장
    df["과목정규"] = pd.Series(canon_items, index=df.index, dtype="object")
    df["처지사정규"] = pd.Series(canon_depts, index=df.index, dtype="object")
    return df


def _sim(a, b):
    if not a or not b:
        return 0.0
    return fuzz.WRatio(str(a), str(b))


def match_actuals(plan_df, erp_norm_df, budget_items, pl_items, cap_items,
                  threshold=80, new_policy="group", small_threshold=2000,
                  selected_depts=None, budget_all=None, other_budget_all=None,
                  overrides=None, learned=None):
    """계획행별 실적금액 산출 + 신규사업 집계 + 미반영 분류.

    plan_df: 계획본 양식1(월별) 로드 결과(loaders.PLAN_COLUMNS + _row).
    erp_norm_df: normalize_erp_df 결과(과목정규/처지사정규 포함, 전체 예산 혼재).
    budget_items: 이번 예산에서 **선택(포함)된** 과목 set(정규 표기) = 분석 대상.
    pl_items, cap_items: 손익/자본 **선택된** 과목 set(미분류 판정 하위호환용).
    threshold: 사업명 유사도(%) — 세부 귀속 tie-break 및 저유사 플래그 기준.
    new_policy:
      "group"       — (권장) (과목×처지사)에 계획행이 하나도 없을 때만 신규.
                       계획행 있는 그룹의 전표는 사업명 최고유사 계획행에 귀속.
      "strict_name" — 사업명 유사도 ≥ threshold 인 전표만 계획집행, 나머지 신규.
    selected_depts: 분석 대상 처지사 set(정규). None이면 지사 필터 없음(하위호환).
    budget_all: 이번 예산의 **전체** 과목 set(선택무관). 지정 시 미반영 분류 활성화.
    other_budget_all: 반대 예산 전체 과목 set. 이번 예산 파일에선 '타예산'(공란) 처리.
    overrides: {_erp_row 값 -> 사업명(str) 또는 {"사업명":..., "처지사":...|None}}
        — 사용자 수동 재배정. 해당 전표가 속한 참조전표번호 묶음 전체가 지정
        사업으로 귀속된다(같은 과목×지사의 계획 사업명이면 그 행으로, 아니면
        그 이름의 신규 사업으로 강제, 확신도 1.0). "처지사"를 지정하면 전표가
        **그 지사로 이동**해 귀속된다(타지사 이동·미매핑 지사 지정).
    learned: {(과목정규, 텍스트정규) -> 사업명} — 과년도 확정 결과 학습 맵.
        대표 텍스트가 학습 키와 일치하면 유사도보다 우선 적용(확신도 0.99).
        같은 그룹에 그 이름의 계획행이 있으면 그 행으로, 신규 클러스터엔 이름 부여.

    반환 dict: plan_rows, new_rows, erp_annotated, unmatched_dept,
               unclassified_item, unreflected_amt, unreflected_by_key.
    """
    known = pl_items | cap_items
    other_set = set(other_budget_all or [])
    have_scope = budget_all is not None

    # 이번 예산에 해당하는 ERP 전표만 대상
    erp = erp_norm_df
    items_norm = [_clean_na(x) for x in erp["과목정규"]]
    depts_norm = [_clean_na(x) for x in erp["처지사정규"]]
    # 합계행·타연도 전표(erp_loader.tag_excluded)는 어떤 집계에도 넣지 않는다.
    if "제외사유" in erp.columns:
        excl = [_clean_na(x) for x in erp["제외사유"]]
    else:
        excl = [None] * len(erp)
    has_j_col = "부서부원문" in erp.columns
    has_key_col = "_erp_row" in erp.columns

    # 오버라이드 정규화: str(사업명만) / dict(사업명+처지사) 모두 허용
    ov_norm = {}
    for k, v in (overrides or {}).items():
        if isinstance(v, dict):
            ov_norm[int(k)] = {"사업명": v.get("사업명"), "처지사": v.get("처지사")}
        else:
            ov_norm[int(k)] = {"사업명": v, "처지사": None}
    overrides = ov_norm

    # 지사 이동 오버라이드: 매칭 전에 처지사를 지정 지사로 바꿔치기 —
    # 미매핑 전표에 지사를 부여하거나, A지사 전표를 B지사로 옮길 때 사용.
    if overrides and has_key_col:
        keys = [_clean_na(x) for x in erp["_erp_row"]]
        for i, k in enumerate(keys):
            if k is None:
                continue
            ov = overrides.get(int(k))
            if ov and ov.get("처지사"):
                depts_norm[i] = ov["처지사"]

    def _dept_ok(d):
        return True if selected_depts is None else (d in selected_depts)

    # in-scope: 선택 과목 AND (지사 필터 없거나 선택 지사). 매칭·집계 대상.
    in_budget_idx = [i for i, it in enumerate(items_norm)
                     if not excl[i] and it in budget_items and _dept_ok(depts_norm[i])]
    in_scope_set = set(in_budget_idx)

    # 그룹: (과목정규, 처지사정규) -> [erp positional index]
    groups = defaultdict(list)
    for i in in_budget_idx:
        key = (items_norm[i], depts_norm[i])
        groups[key].append(i)

    # 계획행 그룹핑: (과목, 처지사) -> [plan row dict]
    plan_by_key = defaultdict(list)
    plan_rows = []
    for _, prow in plan_df.iterrows():
        rec = dict(prow)
        rec["실적금액"] = 0.0
        rec["매칭전표수"] = 0
        rec["저유사전표수"] = 0
        rec["임의귀속전표수"] = 0
        rec["_점수합"] = 0.0
        rec["구분"] = "미시행"
        plan_rows.append(rec)
        plan_by_key[(rec.get("예산과목"), rec.get("처지사"))].append(rec)

    # ERP별 귀속 결과
    attributed = {}      # erp idx -> plan rec / None(신규)
    erp_match_name = {}  # erp idx -> 귀속된 계획 사업명 / None(신규)
    erp_score = {}       # erp idx -> 최고 사업명 유사도(0~100)

    def _rec_row(rec):
        """귀속 계획행의 원본 행번호 — 동명 사업 구분용(전표 트리 정합)."""
        try:
            r = rec.get("_row")
            return int(r) if r is not None and r == r else None
        except (TypeError, ValueError):
            return None
    unattributed_vgroups = {}   # (item,dept) -> [묶음 dict] — 신규 클러스터링 입력

    def _amt(i):
        return _clean_na(erp["금액천원"].iloc[i]) or 0.0

    learned = learned or {}

    def _row_key(i):
        if not has_key_col:
            return None
        k = _clean_na(erp["_erp_row"].iloc[i])
        return int(k) if k is not None else None

    manual_cnt = 0    # 수동지정(오버라이드) 전표수
    learned_cnt = 0   # 학습 맵으로 확정된 전표수

    for key, idxs in groups.items():
        candidates = plan_by_key.get(key, [])
        # ── 참조전표번호 묶음: 같은 전표번호 = 하나의 내역.
        #    대표 텍스트 = 묶음 내 |금액| 최대 전표의 사업명(본 대금 전표).
        vmap = defaultdict(list)
        for i in idxs:
            doc = _clean_na(erp["전표번호"].iloc[i])
            vmap[str(doc) if doc else f"_행{i}"].append(i)
        vgroups = []
        for doc, rows in vmap.items():
            rep_i = max(rows, key=lambda i: abs(_amt(i)))
            ov = next((overrides[_row_key(i)] for i in rows
                       if _row_key(i) in overrides), None)
            vgroups.append({
                "전표번호": doc, "rows": rows,
                "대표명": _clean_na(erp["사업명"].iloc[rep_i]),
                "순액": sum(_amt(i) for i in rows),
                "수동지정": ov["사업명"] if ov else None,
            })

        for vg in vgroups:
            rep_name = vg["대표명"]
            # ── 수동 재배정(오버라이드): 묶음 전체를 지정 사업으로.
            if vg["수동지정"]:
                target = vg["수동지정"]
                prec = next((p for p in candidates if p.get("사업명") == target), None)
                manual_cnt += len(vg["rows"])
                if prec is not None:
                    for i in vg["rows"]:
                        erp_score[i] = 100.0
                        prec["실적금액"] += _amt(i)
                        prec["매칭전표수"] += 1
                        prec["_점수합"] += 100.0
                        attributed[i] = prec
                        erp_match_name[i] = target
                else:
                    # 지정 이름의 계획행이 없음 → 그 이름의 신규 사업으로 강제
                    for i in vg["rows"]:
                        erp_score[i] = 100.0
                        attributed[i] = None
                        erp_match_name[i] = None
                    vg["강제신규명"] = target
                    unattributed_vgroups.setdefault(key, []).append(vg)
                continue
            # ── 학습 맵: 과년도 확정 결과와 텍스트가 일치하면 유사도보다 우선.
            lname = learned.get((key[0], normalize.text_key(rep_name)))
            if lname:
                prec = next((p for p in candidates if p.get("사업명") == lname), None)
                if prec is not None:
                    learned_cnt += len(vg["rows"])
                    for i in vg["rows"]:
                        erp_score[i] = 99.0
                        prec["실적금액"] += _amt(i)
                        prec["매칭전표수"] += 1
                        prec["_점수합"] += 99.0
                        attributed[i] = prec
                        erp_match_name[i] = lname
                    continue
                if not candidates:
                    # 계획행 없는 그룹의 신규 클러스터에 학습된 이름 부여
                    learned_cnt += len(vg["rows"])
                    for i in vg["rows"]:
                        erp_score[i] = 99.0
                        attributed[i] = None
                        erp_match_name[i] = None
                    vg["강제신규명"] = lname
                    unattributed_vgroups.setdefault(key, []).append(vg)
                    continue
            if not candidates:
                for i in vg["rows"]:
                    attributed[i] = None       # 그룹에 계획행 없음 → 신규
                    erp_match_name[i] = None
                    erp_score[i] = 0.0
                unattributed_vgroups.setdefault(key, []).append(vg)
                continue
            # 대표 사업명 유사도 최고 계획행에 묶음 전체를 귀속. 동점(전표
            # 텍스트가 비어 점수가 모두 0인 경우 포함)이면 연예산이 큰 계획행 —
            # 입력 순서에 좌우되지 않고, 실무상 큰 사업에 귀속될 확률이 높다.
            best, best_score, best_budget = None, -1.0, None
            for prec in candidates:
                s = _sim(rep_name, prec.get("사업명"))
                pb = _clean_na(prec.get("연예산")) or 0.0
                if s > best_score or (s == best_score and pb > (best_budget or 0.0)):
                    best, best_score, best_budget = prec, s, pb
            if new_policy == "strict_name" and best_score < threshold:
                for i in vg["rows"]:
                    erp_score[i] = float(best_score)
                    attributed[i] = None       # 엄격정책: 사업명 미달 → 신규
                    erp_match_name[i] = None
                unattributed_vgroups.setdefault(key, []).append(vg)
                continue
            for i in vg["rows"]:
                erp_score[i] = float(best_score)
                best["실적금액"] += _amt(i)
                best["매칭전표수"] += 1
                best["_점수합"] += float(best_score)
                if best_score < threshold:
                    best["저유사전표수"] += 1
                    if len(candidates) > 1:
                        # 그룹에 계획행이 여럿인데 사업명이 못 맞은 건 = 임의 귀속.
                        # (과목×지사) 합계는 옳지만 사업 단위 배분은 신뢰도 낮음.
                        best["임의귀속전표수"] += 1
                attributed[i] = best
                erp_match_name[i] = best.get("사업명")

    # 계획행 구분 + 매칭확신도(0~1, 귀속전표 평균 유사도) 확정
    for rec in plan_rows:
        if rec["매칭전표수"] > 0:
            rec["구분"] = "계획집행"
            rec["매칭확신도"] = round(rec["_점수합"] / rec["매칭전표수"] / 100.0, 3)
        else:
            rec["구분"] = "미시행"
            rec["매칭확신도"] = None
        rec.pop("_점수합", None)

    # 신규사업: 귀속 안된 전표묶음을 **대표 텍스트 유사도로 클러스터링**해
    #   (과목×지사) 안에서 사업 단위 행을 만든다. '23년1월 …' / "'23년1월 …" 처럼
    #   표기만 다른 월별·상쇄(±) 전표들이 한 사업으로 묶여 순액으로 집계된다.
    #   클러스터 대표명 = |순액| 최대 묶음의 대표 텍스트.
    # 소액(클러스터 |순액| ≤ small_threshold)은 (과목×지사)로 묶어 '집행' 일괄 확정.
    NONAME = "(사업명 없음)"

    def _top_dept_part(rows):
        """전표들의 부서명(부) 최빈값 — 신규행의 '예산귀속 부서명(팀)'에 채운다."""
        if not has_j_col:
            return None
        names = [str(_clean_na(erp["부서부원문"].iloc[i]))
                 for i in rows if _clean_na(erp["부서부원문"].iloc[i])]
        if not names:
            return None
        return max(set(names), key=names.count)

    new_rows = []
    small_group = defaultdict(lambda: {"금액": 0.0, "전표": [], "rows": []})
    for (item, dept), vgs in unattributed_vgroups.items():
        clusters = []
        forced = {}   # 강제신규명 -> cluster (수동지정: 정확 이름 매칭만)
        for vg in sorted(vgs, key=lambda v: -abs(v["순액"])):
            fname = vg.get("강제신규명")
            if fname:
                target = forced.get(fname)
                if target is None:
                    target = {"대표명": fname, "순액": 0.0, "전표": [], "rows": [],
                              "수동": True}
                    forced[fname] = target
                    clusters.append(target)
                target["순액"] += vg["순액"]
                target["전표"].append(vg["전표번호"])
                target["rows"].extend(vg["rows"])
                continue
            rep = vg["대표명"]
            target = None
            for cl in clusters:
                if cl.get("수동"):
                    continue      # 수동 클러스터엔 자동 편입 금지
                if rep:
                    if cl["대표명"] and _sim(rep, cl["대표명"]) >= threshold:
                        target = cl
                        break
                elif not cl["대표명"]:
                    # 텍스트 없는 전표끼리는 (과목×지사) 내 하나로 병합
                    #   — 상쇄(±)쌍이 각각 행으로 흩어지는 것을 방지
                    target = cl
                    break
            if target is None:
                target = {"대표명": rep, "순액": 0.0, "전표": [], "rows": []}
                clusters.append(target)
            target["순액"] += vg["순액"]
            target["전표"].append(vg["전표번호"])
            target["rows"].extend(vg["rows"])
        for cl in clusters:
            if not cl.get("수동") and abs(cl["순액"]) <= small_threshold:
                g = small_group[(item, dept)]
                g["금액"] += cl["순액"]
                g["전표"].extend(cl["전표"])
                g["rows"].extend(cl["rows"])
                continue
            note = f"계획X·실적O / 전표 {len(cl['전표'])}건: " + ", ".join(cl["전표"][:5]) \
                   + (" ..." if len(cl["전표"]) > 5 else "")
            if cl.get("수동"):
                note = "수동지정 · " + note
            new_rows.append({
                "예산과목": item,
                "처지사": dept if dept else "(미매핑)",
                "부서부": _top_dept_part(cl["rows"]),
                "사업명": str(cl["대표명"]) if cl["대표명"] else NONAME,
                "실적금액": cl["순액"],
                "구분": "신규",
                "전표건수": len(cl["전표"]),
                "비고": note,
            })
            # zrfm2_V1·matched CSV 추적용: 신규 전표에 클러스터 사업명 라벨
            for i in cl["rows"]:
                erp_match_name[i] = f"[신규] {cl['대표명'] or NONAME}"
    # 소액 일괄 확정: "{지사} {예산과목} 집행"
    for (item, dept), g in small_group.items():
        dept_label = dept if dept else "(미매핑)"
        title = f"{dept_label} {item} 집행"
        new_rows.append({
            "예산과목": item,
            "처지사": dept_label,
            "부서부": _top_dept_part(g["rows"]),
            "사업명": title,
            "실적금액": g["금액"],
            "구분": "신규(소액집행)",
            "전표건수": len(g["전표"]),
            "비고": f"소액(순액≤{small_threshold:,}천원) 일괄확정 {len(g['전표'])}건",
        })
        for i in g["rows"]:
            erp_match_name[i] = f"[신규] {title}"
    # 과목 → 지사 → 금액 내림차순(사업 단위 검토가 쉬운 순서), 소액집행은 그룹 끝.
    new_rows.sort(key=lambda x: (str(x["예산과목"]), str(x["처지사"]),
                                 x["구분"] == "신규(소액집행)", -x["실적금액"]))

    # 검토 항목: 미매핑 처지사(선택 과목인데 정규화 실패) / 미분류 과목
    #   (지사 필터로 in_budget_idx에서 빠지므로 '선택 과목' 기준으로 별도 산출)
    sel_item_idx = [i for i, it in enumerate(items_norm)
                    if not excl[i] and it in budget_items]
    unmatched_dept = sorted({
        _clean_na(erp["지사원문"].iloc[i]) for i in sel_item_idx
        if depts_norm[i] is None and _clean_na(erp["지사원문"].iloc[i])
    })
    unmatched_dept_amt = round(sum(
        (_clean_na(erp["금액천원"].iloc[i]) or 0.0)
        for i in sel_item_idx if depts_norm[i] is None
    ))
    # 미매핑 상세: I열만으론 판단 불가한 '본　　사' 전표를 위해 J열(부서명(부))까지 보고
    _um = defaultdict(lambda: {"금액": 0.0, "전표": 0})
    for i in sel_item_idx:
        if depts_norm[i] is None:
            key = (str(_clean_na(erp["지사원문"].iloc[i]) or ""),
                   str(_clean_na(erp["부서부원문"].iloc[i]) or "") if has_j_col else "",
                   str(items_norm[i] or ""))
            g = _um[key]
            g["금액"] += _clean_na(erp["금액천원"].iloc[i]) or 0.0
            g["전표"] += 1
    unmatched_dept_detail = [
        (raw, j, item, round(g["금액"]), g["전표"])
        for (raw, j, item), g in sorted(_um.items(), key=lambda kv: -kv[1]["금액"])
    ]

    def _is_unclassified(i):
        return (not excl[i] and items_norm[i] and str(items_norm[i]).strip()
                and items_norm[i] not in known)

    unclassified_item = sorted({
        items_norm[i] for i in range(len(erp)) if _is_unclassified(i)
    })
    unclassified_item_amt = round(sum(
        (_clean_na(erp["금액천원"].iloc[i]) or 0.0) for i in range(len(erp))
        if _is_unclassified(i)
    ))
    excluded_by_reason = defaultdict(lambda: {"금액": 0.0, "전표": 0})
    for i in range(len(erp)):
        if excl[i]:
            g = excluded_by_reason[excl[i]]
            g["금액"] += _clean_na(erp["금액천원"].iloc[i]) or 0.0
            g["전표"] += 1

    # zrfm2_V1 / matched CSV용 전표별 주석: 매칭사업명 · 매칭확신도(0~1) · 구분
    #   in-scope → 계획집행/신규, 타예산 → 공란, 그 외(미선택 과목·지사/미분류/미매핑) → 미반영.
    r_labels, r_conf, r_gubun, r_rows = [], [], [], []
    unreflected_by_key = defaultdict(lambda: {"금액": 0.0, "전표": 0})
    unreflected_amt = 0.0
    for i in range(len(erp)):
        if excl[i]:
            r_labels.append("")
            r_conf.append(None)
            r_gubun.append(excl[i])       # 제외(합계행) / 제외(타연도)
            r_rows.append(None)
        elif i in in_scope_set:
            if attributed.get(i) is not None:
                r_labels.append(erp_match_name[i] if erp_match_name[i] else "[신규]")
                r_gubun.append("계획집행")
                r_rows.append(_rec_row(attributed[i]))
            else:
                r_labels.append(erp_match_name.get(i) or "[신규]")
                r_gubun.append("신규")
                r_rows.append(None)
            r_conf.append(round(erp_score.get(i, 0.0) / 100.0, 3))
        elif items_norm[i] in other_set:
            r_labels.append("")       # 타예산 전표
            r_conf.append(None)
            r_gubun.append("")
            r_rows.append(None)
        elif have_scope and items_norm[i] and str(items_norm[i]).strip():
            # 과목이 실재하는 전표만 미반영(선택 안 된 과목·지사/미분류/미매핑).
            # 과목이 빈 총계·잡행은 종전처럼 공란 처리(집계 제외).
            r_labels.append("")
            r_conf.append(None)
            r_gubun.append("미반영")
            r_rows.append(None)
            amt = _clean_na(erp["금액천원"].iloc[i]) or 0.0
            it = items_norm[i] or "(미분류)"
            dp = depts_norm[i] or (_clean_na(erp["지사원문"].iloc[i]) or "(미매핑)")
            g = unreflected_by_key[(str(it), str(dp))]
            g["금액"] += amt
            g["전표"] += 1
            unreflected_amt += amt
        else:
            r_labels.append("")       # 하위호환: 스코프 미지정 시 공란
            r_conf.append(None)
            r_gubun.append("")
            r_rows.append(None)
    erp_annotated = erp.copy()
    # 지사 이동 오버라이드가 반영된 처지사로 갱신(상세 화면·matched CSV 정합)
    erp_annotated["처지사정규"] = pd.Series(depts_norm, index=erp.index, dtype="object")
    erp_annotated["매칭사업명"] = pd.Series(r_labels, index=erp.index, dtype="object")
    erp_annotated["매칭확신도"] = pd.Series(r_conf, index=erp.index, dtype="object")
    erp_annotated["구분"] = pd.Series(r_gubun, index=erp.index, dtype="object")
    erp_annotated["매칭행"] = pd.Series(r_rows, index=erp.index, dtype="object")

    return {
        "plan_rows": plan_rows,
        "new_rows": new_rows,
        "erp_annotated": erp_annotated,
        "unmatched_dept": unmatched_dept,
        "unmatched_dept_amt": unmatched_dept_amt,
        "unmatched_dept_detail": unmatched_dept_detail,
        "unclassified_item": unclassified_item,
        "unclassified_item_amt": unclassified_item_amt,
        "unreflected_amt": round(unreflected_amt),
        "unreflected_by_key": dict(unreflected_by_key),
        "excluded_by_reason": dict(excluded_by_reason),
        "manual_cnt": manual_cnt,
        "learned_cnt": learned_cnt,
    }
