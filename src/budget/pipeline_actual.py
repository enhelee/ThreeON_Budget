# -*- coding: utf-8 -*-
"""실적분석 오케스트레이션 (UI 비의존).

입력: 계획본({연도}년 {손익|자본}예산_계획.xlsx 또는 사업별 예산 원본) + ERP(zrfm2)
      + 마스터(선택).
출력: {연도}년 {손익|자본}예산_실적.xlsx, zrfm2_{연도}_V1({budget}).xlsx,
      matched_{연도}_{budget}.csv.

계획행은 **이번 예산의 실적 대상 과목**만 남긴다. 손익·자본이 섞인 원본을
그대로 올려도 각 산출물에 상대 예산 행이 섞이지 않는다(제외분은 검토리포트에 보고).
"""
import os
from collections import defaultdict

import pandas as pd

from . import config_store, org_structure, loaders, master_data, erp_loader
from . import matching, excel_actual_writer, normalize


def _num(v):
    try:
        if v is None or v != v:      # None / NaN
            return 0.0
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def run_actual(plan_path, zrfm2_path, master_path, config_dir, out_dir, year, budget,
               new_policy="group"):
    """파일 기반 실행(하위호환): 파일 로드 후 공용 코어로 위임."""
    plan_df = loaders.load_business_plan(plan_path)
    erp_df = erp_loader.load_erp(zrfm2_path)
    return run_actual_frames(
        plan_df, erp_df, master_path, config_dir, out_dir, year, budget,
        new_policy=new_policy, zrfm2_src_path=zrfm2_path,
    )


VALID_ATTRS = ("일반", "제조", "건가", "자산")


def run_actual_frames(plan_df, erp_df, master_path, config_dir, out_dir, year, budget,
                      new_policy="group", zrfm2_src_path=None, overrides=None,
                      learned=None, biz_edits=None, attr_map=None, code_to_item=None,
                      deptcode_map=None, manual_biz=None):
    """공용 코어 — DataFrame 입력(DB 기반 실행 포함).

    zrfm2_src_path가 있으면 원본 워크북에 주석을 달아 zrfm2_V1을 만들고,
    없으면(DB 모드) ERP DataFrame에서 zrfm2_V1을 새로 생성한다.
    overrides: {_erp_row -> 사업명} 수동 재배정(matching 참조).
    learned: {(과목, 텍스트정규) -> 사업명} 과년도 확정 학습 맵(matching 참조).
    biz_edits: [{예산과목, 처지사, 사업명, fields}] — 관리자 사업 내용 수정.
        매칭 전 계획행에 적용(사업명 변경 포함, 빈칸 입력 허용).
    attr_map: {예산과목 -> 속성} 마스터 — 계획 속성이 4종(일반/제조/건가/자산)이
        아니면(원본 품질 문제) 마스터 값으로 교정. 신규 행 속성도 이걸로 채움.
    code_to_item: {계정코드 -> 과목명} 마스터 — ERP 과목 정규화 보강.
    """
    # 구성 로드(시드 자동 영속화)
    dept_config = config_store.load_dept_config(config_dir, year)
    config_store.save_dept_config(config_dir, year, dept_config)
    pl_config = config_store.load_item_config(config_dir, year, "손익")
    cap_config = config_store.load_item_config(config_dir, year, "자본")
    config_store.save_item_config(config_dir, year, "손익", pl_config)
    config_store.save_item_config(config_dir, year, "자본", cap_config)
    item_config = pl_config if budget == "손익" else cap_config
    item_alias = config_store.load_item_alias(config_dir)
    dept_alias = config_store.load_dept_alias(config_dir)
    config_store.save_item_alias(config_dir, item_alias)
    config_store.save_dept_alias(config_dir, dept_alias)

    def _alias(x):
        return normalize.normalize_item(x["과목"], item_alias)

    def _actual_on(x):
        # 실적 분석 대상: 포함=True AND 실적반영≠False. 실적반영=False(예: 건설공사)는
        # 계획본엔 그대로 두되 실적 산출물(양식1·종합표)에서만 제외한다.
        return config_store.to_bool(x.get("포함"), True) and \
            config_store.to_bool(x.get("실적반영"), True)

    pl_items = {_alias(x) for x in pl_config if _actual_on(x)}       # 실적 대상 손익 과목
    cap_items = {_alias(x) for x in cap_config if _actual_on(x)}     # 실적 대상 자본 과목
    pl_all = {_alias(x) for x in pl_config}                         # 손익 전체 과목
    cap_all = {_alias(x) for x in cap_config}                       # 자본 전체 과목
    budget_items = pl_items if budget == "손익" else cap_items
    budget_all = pl_all if budget == "손익" else cap_all
    other_budget_all = cap_all if budget == "손익" else pl_all
    no_actual_items = {_alias(x) for x in item_config
                       if config_store.to_bool(x.get("포함"), True)
                       and not config_store.to_bool(x.get("실적반영"), True)}

    dept_columns = org_structure.build_dept_columns(dept_config)
    # 종합표 과목행: 실적반영=False 과목 제외(계획 종합표는 pipeline_plan이 전체 사용)
    item_rows = org_structure.build_item_rows(
        [x for x in item_config
         if config_store.to_bool(x.get("실적반영"), True)])
    all_dept_names = {d["이름"] for d in dept_config}
    plan_depts = {d["이름"] for d in dept_config if d.get("포함")}   # 선택 지사 = 분석 대상

    # 마스터(코드->과목/부서) — 파일 마스터 + DB 마스터(code_to_item) 병합
    master = master_data.load_master(master_path) if master_path and os.path.exists(master_path) else \
        {"code_to_item": {}, "code_to_attr": {}, "deptcode_to_branch": {}}
    if code_to_item:
        merged = dict(code_to_item)
        merged.update(master["code_to_item"])     # 파일 마스터가 있으면 우선
        master["code_to_item"] = merged

    # 계획본: 예산과목 명칭 통일(구명→현명, 계정코드 동일 개명 흡수)
    plan_df = plan_df.copy()
    plan_df["예산과목"] = plan_df["예산과목"].map(
        lambda x: normalize.normalize_item(x, item_alias)
    )

    # 수동 추가 사업(manual_biz): 계획본에 없는 사업을 계획행으로 편입.
    #   _row는 1,000,000+id 합성키(원본 행번호와 충돌 없음, 전표 트리 조인용).
    if manual_biz:
        add_rows = []
        for m in manual_biz:
            add_rows.append({
                "주관부서명": m.get("주관부서명"), "부서코드": None,
                "처지사": m.get("처지사"), "부서부": m.get("부서부"),
                "속성": m.get("속성"), "예산코드": None,
                "예산과목": normalize.normalize_item(m.get("예산과목"), item_alias),
                "사업명": m.get("사업명"), "산출내역": "(수동 추가)",
                "연예산": float(m.get("연예산") or 0.0),
                "_row": 1_000_000 + int(m["id"]),
            })
        plan_df = pd.concat([plan_df, pd.DataFrame(add_rows)], ignore_index=True)

    # 처지사 보정(부서코드 마스터): 처지사가 비었거나 지사구성에 없는 계획행은
    # 부서코드→처지사 매핑으로 채운다(매핑 결과가 등록된 지사일 때만).
    if deptcode_map:
        def _fix_dept(row):
            dp = row.get("처지사")
            if dp in all_dept_names:
                return dp
            code = row.get("부서코드")
            mapped = deptcode_map.get(str(code).strip()) if code is not None else None
            return mapped if mapped in all_dept_names else dp
        plan_df["처지사"] = plan_df.apply(_fix_dept, axis=1)

    # 속성 정규화(4종: 일반/제조/건가/자산) — 원본이 속성 칸에 과목명 등을 넣은
    # 경우(25년 자본 원본 등) 마스터(예산과목→속성)로 교정. 유효값은 그대로 둔다.
    if attr_map:
        def _fix_attr(row):
            a = row.get("속성")
            if a is not None and str(a).strip() in VALID_ATTRS:
                return str(a).strip()
            return attr_map.get(row.get("예산과목"), None)
        plan_df["속성"] = plan_df.apply(_fix_attr, axis=1)

    # 관리자 사업 내용 수정(biz_edit) — 매칭 전에 적용해 사업명 변경도 일관 반영.
    #   빈 문자열 입력은 '빈칸으로 지움'(None)으로 처리.
    for ed in (biz_edits or []):
        mask = ((plan_df["예산과목"] == ed.get("예산과목"))
                & (plan_df["처지사"] == ed.get("처지사"))
                & (plan_df["사업명"] == ed.get("사업명")))
        if not mask.any():
            continue
        for k, v in (ed.get("fields") or {}).items():
            if k in plan_df.columns:
                plan_df.loc[mask, k] = (v if v != "" else None)

    # 계획행 스코프 확정 — 이번 예산의 실적 대상 과목만 남긴다.
    #   손익·자본이 섞인 원본을 올려도 상대 예산 행이 섞이지 않는다.
    #   제외분은 사유별로 집계해 검토리포트에 보고(조용한 누락 금지).
    plan_excluded = defaultdict(lambda: {"행": 0, "연예산": 0.0, "과목": set()})

    def _plan_scope(row):
        it, dp = row.get("예산과목"), row.get("처지사")
        amt = _num(row.get("연예산"))
        if it in budget_items:
            if dp in all_dept_names and dp not in plan_depts:
                return "지사 미선택", amt      # 지사 포함 해제
            if dp not in all_dept_names:
                return "처지사 미등록(지사구성에 없음)", amt
            return None, amt
        if it in no_actual_items:
            return "실적반영 해제 과목(ERP 계정 없음 등)", amt
        if it in budget_all:
            return "과목 미선택(구성에서 포함 해제)", amt
        if it in other_budget_all:
            return f"타예산({'자본' if budget == '손익' else '손익'}) 과목", amt
        return "미분류 과목(구성에 없음)", amt

    if len(plan_df):
        keep = []
        for _, row in plan_df.iterrows():
            reason, amt = _plan_scope(row)
            keep.append(reason is None)
            if reason is not None:
                g = plan_excluded[reason]
                g["행"] += 1
                g["연예산"] += amt
                if row.get("예산과목"):
                    g["과목"].add(str(row.get("예산과목")))
        plan_df = plan_df[keep].reset_index(drop=True)

    plan_total = float(sum(_num(v) for v in plan_df["연예산"])) if len(plan_df) else 0.0

    # ERP: 합계행/타연도 표기 + 정규화
    year_dist = erp_loader.detect_years(erp_df)
    erp_df = erp_loader.tag_excluded(erp_df, year)
    # 처지사 정규화는 **전체 지사명** 기준(선택 여부와 무관). 선택 필터는 매칭에서
    # 적용한다. 선택 지사만으로 정규화하면 해제된 지사가 '미매핑'으로 오분류된다.
    erp_norm = matching.normalize_erp_df(
        erp_df, master["code_to_item"], item_alias, dept_alias, all_dept_names,
    )

    # 매칭 (선택 지사 필터 + 미반영 분류)
    res = matching.match_actuals(
        plan_df, erp_norm, budget_items, pl_items, cap_items,
        threshold=config_store.SIMILARITY_THRESHOLD, new_policy=new_policy,
        small_threshold=config_store.SMALL_AMOUNT_THOUSAND,
        selected_depts=plan_depts, budget_all=budget_all,
        other_budget_all=other_budget_all, overrides=overrides, learned=learned,
    )

    # 연도 검증
    year_mismatch = None
    if year_dist and year not in year_dist:
        year_mismatch = (f"선택연도 {year}이(가) ERP 데이터 연도분포 {dict(year_dist)}에 "
                         "없음 — 연도 필터를 적용하지 않고 전체를 집계했습니다.")

    plan_rows = res["plan_rows"]
    new_rows = res["new_rows"]
    # 신규 행 속성: 마스터(예산과목→속성)로 채움 — 상세 화면 속성 필터 커버
    if attr_map:
        for r in new_rows:
            if not r.get("속성"):
                r["속성"] = attr_map.get(r.get("예산과목"))
    # 요약은 양식1(월별) 시트에 기록되는 값(행별 반올림)과 동일 기준으로 낸다.
    #   → 검토리포트 총액 = 종합표 SUMIFS 총액.
    exec_total = sum(round(r["실적금액"]) for r in plan_rows if r["구분"] == "계획집행")
    new_total = sum(round(r["실적금액"]) for r in new_rows)
    raw_total = sum(r["실적금액"] for r in plan_rows) + sum(r["실적금액"] for r in new_rows)
    missing_cnt = sum(1 for r in plan_rows if r["구분"] == "미시행")
    small_rows = [r for r in new_rows if r["구분"] == "신규(소액집행)"]
    small_total = sum(round(r["실적금액"]) for r in small_rows)
    ambiguous_cnt = sum(r.get("임의귀속전표수", 0) for r in plan_rows)
    ambiguous_amt = sum(round(r["실적금액"]) for r in plan_rows
                        if r.get("임의귀속전표수", 0))

    # 과목별 계획 대비 실적 대조표(진단의 핵심). 종합표와 같은 모집단.
    by_item = defaultdict(lambda: {
        "계획": 0.0, "계획행": 0, "집행행": 0, "미시행행": 0, "집행": 0.0, "신규": 0.0})
    for r in plan_rows:
        g = by_item[r.get("예산과목")]
        g["계획"] += _num(r.get("연예산"))
        g["계획행"] += 1
        if r["구분"] == "계획집행":
            g["집행행"] += 1
            g["집행"] += round(r["실적금액"])
        else:
            g["미시행행"] += 1
    for r in new_rows:
        by_item[r["예산과목"]]["신규"] += round(r["실적금액"])

    item_table, warnings = [], []
    for it in sorted(by_item, key=lambda k: str(k)):
        g = by_item[it]
        actual = g["집행"] + g["신규"]
        rate = (actual / g["계획"] * 100.0) if g["계획"] else None
        item_table.append([
            it, round(g["계획"]), round(actual), round(g["집행"]), round(g["신규"]),
            (round(rate, 1) if rate is not None else None),
            g["계획행"], g["집행행"], g["미시행행"],
        ])
        if g["계획"] and actual == 0:
            warnings.append(
                f"[{it}] 계획 {round(g['계획']):,}천원인데 ERP 실적 0 — "
                "해당 예산과목의 ERP 계정이 없거나 다른 과목으로 집행되었을 수 있음"
                "(과목 구성의 '실적반영' 해제 검토)")
        elif g["계획"] and g["신규"] > g["계획"]:
            warnings.append(
                f"[{it}] 신규 {round(g['신규']):,}천원 > 계획 {round(g['계획']):,}천원 — "
                "계획은 본사·총괄 단위, 실적은 지사 단위로 잡힌 과목일 수 있음"
                "(계획행이 없는 (과목×지사)는 전부 신규로 분류됨)")
        elif not g["계획"] and actual:
            warnings.append(
                f"[{it}] 계획 없음 / 실적 {round(actual):,}천원 — 전액 신규")
    if ambiguous_cnt and exec_total:
        share = ambiguous_amt / exec_total * 100.0
        warnings.append(
            f"계획집행 실적 중 {ambiguous_amt:,}천원({share:.0f}%)은 (과목×지사) 그룹에 "
            f"계획행이 여럿인데 사업명 유사도가 임계값 미만인 전표 {ambiguous_cnt:,}건을 "
            "포함한다 — 지사·과목 단위 집계(종합표)는 정확하나 개별 사업 행의 금액은 "
            "참고용으로 볼 것(양식1 비고의 '임의귀속' 표시 참조)")

    # 미반영(선택 안 된 과목·지사/미분류/미매핑) 상위 집계
    unref_by_key = res.get("unreflected_by_key", {})
    unreflected_top = [
        (f"{it} / {dp}", round(g["금액"]), g["전표"])
        for (it, dp), g in sorted(
            unref_by_key.items(), key=lambda kv: -kv[1]["금액"])
    ]
    excluded_rows = [
        (reason, round(g["금액"]), g["전표"])
        for reason, g in sorted(res.get("excluded_by_reason", {}).items())
    ]
    plan_excluded_rows = [
        (reason, g["행"], round(g["연예산"]), ", ".join(sorted(g["과목"])[:6]))
        for reason, g in sorted(plan_excluded.items(), key=lambda kv: -kv[1]["연예산"])
    ]

    total = exec_total + new_total
    review = {
        "year": year,
        "year_dist": dict(year_dist),
        "year_mismatch": year_mismatch,
        "unmatched_dept": res["unmatched_dept"],
        "unmatched_dept_amt": res.get("unmatched_dept_amt", 0),
        "unmatched_dept_detail": res.get("unmatched_dept_detail", []),
        "unclassified_item": res["unclassified_item"],
        "unclassified_item_amt": res.get("unclassified_item_amt", 0),
        "unreflected_amt": res.get("unreflected_amt", 0),
        "unreflected_top": unreflected_top[:30],
        "unmatched_dept_detail": res.get("unmatched_dept_detail", [])[:30],
        "excluded_rows": excluded_rows,
        "plan_excluded_rows": plan_excluded_rows,
        "item_table": item_table,
        "warnings": warnings,
        "summary": {
            "계획행수": len(plan_rows),
            "계획집행 행수": sum(1 for r in plan_rows if r["구분"] == "계획집행"),
            "미시행 행수": missing_cnt,
            "신규 행수": len(new_rows),
            "  └ 소액집행 행수": len(small_rows),
            "계획 연예산(천원)": round(plan_total),
            "계획집행 실적(천원)": exec_total,
            "신규 실적(천원)": new_total,
            "  └ 소액집행 실적(천원)": small_total,
            "총 실적(천원)": total,
            "집행률(%)": (round(total / plan_total * 100.0, 1) if plan_total else None),
            "반올림차이(천원)": round(total - raw_total, 3),
            "임의귀속 전표수": ambiguous_cnt,
            "임의귀속 계획행 실적(천원)": ambiguous_amt,
            "수동지정 전표수": res.get("manual_cnt", 0),
            "학습확정 전표수": res.get("learned_cnt", 0),
            "미반영(천원)": res.get("unreflected_amt", 0),
        },
    }

    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{year}년 {budget}예산_실적.xlsx")
    excel_actual_writer.write_actual_workbook(
        out_path, plan_rows, new_rows, dept_columns, item_rows, budget, year, review,
    )
    v1_path = os.path.join(out_dir, f"zrfm2_{year}_V1({budget}).xlsx")
    if zrfm2_src_path:
        excel_actual_writer.write_zrfm2_v1(zrfm2_src_path, v1_path, res["erp_annotated"])
    else:
        excel_actual_writer.write_zrfm2_v1_from_df(v1_path, res["erp_annotated"])
    matched_csv_path = os.path.join(out_dir, f"matched_{year}_{budget}.csv")
    excel_actual_writer.write_matched_csv(matched_csv_path, res["erp_annotated"])

    return {
        "output_path": out_path,
        "zrfm2_v1_path": v1_path,
        "matched_csv_path": matched_csv_path,
        "erp_annotated": res["erp_annotated"],
        "plan_rows": plan_rows,
        "new_rows": new_rows,
        "요약": review["summary"],
        "미매핑처지사": res["unmatched_dept"],
        "미매핑처지사금액": res.get("unmatched_dept_amt", 0),
        "미분류과목": res["unclassified_item"],
        "미분류과목금액": res.get("unclassified_item_amt", 0),
        "미반영금액": res.get("unreflected_amt", 0),
        "제외전표": excluded_rows,
        "계획행제외": plan_excluded_rows,
        "경고": warnings,
        "연도불일치": year_mismatch,
    }
