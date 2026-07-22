# -*- coding: utf-8 -*-
"""실적분석 오케스트레이션 (UI 비의존).

입력: 계획본({연도}년 {손익|자본}예산_계획.xlsx) + ERP(zrfm2.XLSX) + 마스터.
출력: {연도}년 {손익|자본}예산_실적.xlsx, zrfm2_V1({budget}).xlsx.
"""
import os

from . import config_store, org_structure, loaders, master_data, erp_loader
from . import matching, excel_actual_writer, normalize


def run_actual(plan_path, zrfm2_path, master_path, config_dir, out_dir, year, budget,
               new_policy="group"):
    # 구성 로드(시드 자동 영속화)
    dept_config = config_store.load_dept_config(config_dir, year)
    config_store.save_dept_config(config_dir, year, dept_config)
    pl_config = config_store.load_item_config(config_dir, year, "손익")
    cap_config = config_store.load_item_config(config_dir, year, "자본")
    item_config = pl_config if budget == "손익" else cap_config
    item_alias = config_store.load_item_alias(config_dir)
    dept_alias = config_store.load_dept_alias(config_dir)
    config_store.save_item_alias(config_dir, item_alias)
    config_store.save_dept_alias(config_dir, dept_alias)

    def _alias(x):
        return config_store.SEED_ITEM_ALIAS.get(x["과목"], x["과목"])

    def _actual_on(x):
        # 실적 분석 대상: 포함=True AND 실적반영≠False. 실적반영=False(예: 건설공사)는
        # 계획본엔 그대로 두되 실적 산출물(양식1·종합표)에서만 제외한다.
        return x.get("포함") and x.get("실적반영", True)

    pl_items = {_alias(x) for x in pl_config if _actual_on(x)}       # 실적 대상 손익 과목
    cap_items = {_alias(x) for x in cap_config if _actual_on(x)}     # 실적 대상 자본 과목
    pl_all = {_alias(x) for x in pl_config}                         # 손익 전체 과목
    cap_all = {_alias(x) for x in cap_config}                       # 자본 전체 과목
    budget_items = pl_items if budget == "손익" else cap_items
    budget_all = pl_all if budget == "손익" else cap_all
    other_budget_all = cap_all if budget == "손익" else pl_all

    dept_columns = org_structure.build_dept_columns(dept_config)
    # 종합표 과목행: 실적반영=False 과목 제외(계획 종합표는 pipeline_plan이 전체 사용)
    item_rows = org_structure.build_item_rows(
        [x for x in item_config if x.get("실적반영", True)])
    plan_depts = {d["이름"] for d in dept_config if d.get("포함")}   # 선택 지사 = 분석 대상

    # 마스터(코드->과목/부서)
    master = master_data.load_master(master_path) if master_path and os.path.exists(master_path) else \
        {"code_to_item": {}, "code_to_attr": {}, "deptcode_to_branch": {}}

    # 계획본 로드 + 예산과목 명칭 통일(구명→현명, 계정코드 동일 개명 흡수)
    plan_df = loaders.load_business_plan(plan_path)
    plan_df["예산과목"] = plan_df["예산과목"].map(
        lambda x: normalize.normalize_item(x, item_alias)
    )

    # 선택된 항목만 실적분석: 명시적으로 '포함 해제'된 과목·지사의 계획행은 제외.
    #   (미지정 값은 보존 → 전체 선택 시 불변식 유지. 제외분 전표는 zrfm2_V1 '미반영'.)
    all_dept_names = {d["이름"] for d in dept_config}

    def _keep_plan(row):
        it, dp = row.get("예산과목"), row.get("처지사")
        if it in budget_all and it not in budget_items:
            return False   # 과목 포함 해제
        if dp in all_dept_names and dp not in plan_depts:
            return False   # 지사 포함 해제
        return True

    if len(plan_df):
        plan_df = plan_df[plan_df.apply(_keep_plan, axis=1)].reset_index(drop=True)

    # ERP 로드 + 정규화
    erp_df = erp_loader.load_erp(zrfm2_path)
    year_dist = erp_loader.detect_years(erp_df)
    erp_norm = matching.normalize_erp_df(
        erp_df, master["code_to_item"], item_alias, dept_alias, plan_depts,
    )

    # 매칭 (선택 지사 필터 + 미반영 분류)
    res = matching.match_actuals(
        plan_df, erp_norm, budget_items, pl_items, cap_items,
        threshold=config_store.SIMILARITY_THRESHOLD, new_policy=new_policy,
        small_threshold=config_store.SMALL_AMOUNT_THOUSAND,
        selected_depts=plan_depts, budget_all=budget_all,
        other_budget_all=other_budget_all,
    )

    # 연도 검증
    year_mismatch = None
    if year_dist and year not in year_dist:
        year_mismatch = f"선택연도 {year}이(가) ERP 데이터 연도분포 {dict(year_dist)}에 없음"

    plan_rows = res["plan_rows"]
    new_rows = res["new_rows"]
    exec_total = sum(r["실적금액"] for r in plan_rows if r["구분"] == "계획집행")
    new_total = sum(r["실적금액"] for r in new_rows)
    missing_cnt = sum(1 for r in plan_rows if r["구분"] == "미시행")
    small_rows = [r for r in new_rows if r["구분"] == "신규(소액집행)"]
    small_total = sum(r["실적금액"] for r in small_rows)

    # 미반영(선택 안 된 과목·지사/미분류/미매핑) 상위 집계
    unref_by_key = res.get("unreflected_by_key", {})
    unreflected_top = [
        (f"{it} / {dp}", round(g["금액"]), g["전표"])
        for (it, dp), g in sorted(
            unref_by_key.items(), key=lambda kv: -kv[1]["금액"])
    ]

    review = {
        "year": year,
        "year_dist": dict(year_dist),
        "year_mismatch": year_mismatch,
        "unmatched_dept": res["unmatched_dept"],
        "unmatched_dept_amt": res.get("unmatched_dept_amt", 0),
        "unclassified_item": res["unclassified_item"],
        "unclassified_item_amt": res.get("unclassified_item_amt", 0),
        "unreflected_amt": res.get("unreflected_amt", 0),
        "unreflected_top": unreflected_top[:30],
        "summary": {
            "계획행수": len(plan_rows),
            "계획집행 행수": sum(1 for r in plan_rows if r["구분"] == "계획집행"),
            "미시행 행수": missing_cnt,
            "신규 행수": len(new_rows),
            "  └ 소액집행 행수": len(small_rows),
            "계획집행 실적(천원)": round(exec_total),
            "신규 실적(천원)": round(new_total),
            "  └ 소액집행 실적(천원)": round(small_total),
            "총 실적(천원)": round(exec_total + new_total),
            "미반영(천원)": res.get("unreflected_amt", 0),
        },
    }

    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{year}년 {budget}예산_실적.xlsx")
    excel_actual_writer.write_actual_workbook(
        out_path, plan_rows, new_rows, dept_columns, item_rows, budget, year, review,
    )
    v1_path = os.path.join(out_dir, f"zrfm2_V1({budget}).xlsx")
    excel_actual_writer.write_zrfm2_v1(zrfm2_path, v1_path, res["erp_annotated"])
    matched_csv_path = os.path.join(out_dir, f"matched_{year}_{budget}.csv")
    excel_actual_writer.write_matched_csv(matched_csv_path, res["erp_annotated"])

    return {
        "output_path": out_path,
        "zrfm2_v1_path": v1_path,
        "matched_csv_path": matched_csv_path,
        "요약": review["summary"],
        "미매핑처지사": res["unmatched_dept"],
        "미매핑처지사금액": res.get("unmatched_dept_amt", 0),
        "미분류과목": res["unclassified_item"],
        "미분류과목금액": res.get("unclassified_item_amt", 0),
        "미반영금액": res.get("unreflected_amt", 0),
        "연도불일치": year_mismatch,
    }
