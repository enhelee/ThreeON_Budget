# -*- coding: utf-8 -*-
"""실적분석 오케스트레이션 (UI 비의존).

입력: 계획본({연도}년 {손익|자본}예산_계획.xlsx) + ERP(zrfm2.XLSX) + 마스터.
출력: {연도}년 {손익|자본}예산_실적.xlsx, zrfm2_V1({budget}).xlsx.
"""
import os

from . import config_store, org_structure, loaders, master_data, erp_loader
from . import matching, excel_actual_writer


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

    pl_items = {config_store.SEED_ITEM_ALIAS.get(x["과목"], x["과목"])
                for x in pl_config if x.get("포함")}
    cap_items = {config_store.SEED_ITEM_ALIAS.get(x["과목"], x["과목"])
                 for x in cap_config if x.get("포함")}
    budget_items = pl_items if budget == "손익" else cap_items

    dept_columns = org_structure.build_dept_columns(dept_config)
    item_rows = org_structure.build_item_rows(item_config)
    plan_depts = {d["이름"] for d in dept_config if d.get("포함")}

    # 마스터(코드->과목/부서)
    master = master_data.load_master(master_path) if master_path and os.path.exists(master_path) else \
        {"code_to_item": {}, "code_to_attr": {}, "deptcode_to_branch": {}}

    # 계획본 로드
    plan_df = loaders.load_business_plan(plan_path)

    # ERP 로드 + 정규화
    erp_df = erp_loader.load_erp(zrfm2_path)
    year_dist = erp_loader.detect_years(erp_df)
    erp_norm = matching.normalize_erp_df(
        erp_df, master["code_to_item"], item_alias, dept_alias, plan_depts,
    )

    # 매칭
    res = matching.match_actuals(
        plan_df, erp_norm, budget_items, pl_items, cap_items,
        threshold=config_store.SIMILARITY_THRESHOLD, new_policy=new_policy,
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

    review = {
        "year": year,
        "year_dist": dict(year_dist),
        "year_mismatch": year_mismatch,
        "unmatched_dept": res["unmatched_dept"],
        "unmatched_dept_amt": res.get("unmatched_dept_amt", 0),
        "unclassified_item": res["unclassified_item"],
        "unclassified_item_amt": res.get("unclassified_item_amt", 0),
        "summary": {
            "계획행수": len(plan_rows),
            "계획집행 행수": sum(1 for r in plan_rows if r["구분"] == "계획집행"),
            "미시행 행수": missing_cnt,
            "신규 행수": len(new_rows),
            "계획집행 실적(천원)": round(exec_total),
            "신규 실적(천원)": round(new_total),
            "총 실적(천원)": round(exec_total + new_total),
        },
    }

    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{year}년 {budget}예산_실적.xlsx")
    excel_actual_writer.write_actual_workbook(
        out_path, plan_rows, new_rows, dept_columns, item_rows, budget, year, review,
    )
    v1_path = os.path.join(out_dir, f"zrfm2_V1({budget}).xlsx")
    excel_actual_writer.write_zrfm2_v1(zrfm2_path, v1_path, res["erp_annotated"])

    return {
        "output_path": out_path,
        "zrfm2_v1_path": v1_path,
        "요약": review["summary"],
        "미매핑처지사": res["unmatched_dept"],
        "미매핑처지사금액": res.get("unmatched_dept_amt", 0),
        "미분류과목": res["unclassified_item"],
        "미분류과목금액": res.get("unclassified_item_amt", 0),
        "연도불일치": year_mismatch,
    }
