# -*- coding: utf-8 -*-
"""계획본 생성 오케스트레이션 (UI 비의존)."""
import os

from . import config_store, org_structure, loaders, classify, excel_plan_writer
from . import missing as missing_mod


def run_plan(business_plan_path, config_dir, out_dir, year, budget):
    dept_config = config_store.load_dept_config(config_dir, year)
    config_store.save_dept_config(config_dir, year, dept_config)  # 최초 실행 시 시드 영속화

    pl_config = config_store.load_item_config(config_dir, year, "손익")
    cap_config = config_store.load_item_config(config_dir, year, "자본")
    config_store.save_item_config(config_dir, year, "손익", pl_config)
    config_store.save_item_config(config_dir, year, "자본", cap_config)

    item_config = pl_config if budget == "손익" else cap_config
    pl_items = {x["과목"] for x in pl_config if x.get("포함")}
    cap_items = {x["과목"] for x in cap_config if x.get("포함")}

    df = loaders.load_business_plan(business_plan_path)
    missing_rows = missing_mod.collect_missing_rows(df)
    filtered_df, unclassified = classify.classify_rows(df, budget, pl_items, cap_items)

    dept_columns = org_structure.build_dept_columns(dept_config)
    item_rows = org_structure.build_item_rows(item_config)

    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{year}년 {budget}예산_계획.xlsx")
    excel_plan_writer.write_plan_workbook(
        out_path, filtered_df, dept_columns, item_rows, budget, year, missing_rows, unclassified,
    )

    total = float(filtered_df["연예산"].fillna(0).sum())
    return {
        "output_path": out_path,
        "요약": {
            "총액": total,
            "행수": len(filtered_df),
            "미분류과목": unclassified,
            "결측치건수": len(missing_rows),
        },
    }
