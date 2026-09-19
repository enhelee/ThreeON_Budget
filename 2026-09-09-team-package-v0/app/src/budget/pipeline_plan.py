# -*- coding: utf-8 -*-
"""계획본 생성 오케스트레이션 (UI 비의존)."""
import os

from . import config_store, org_structure, loaders, classify, excel_plan_writer
from . import missing as missing_mod
from . import normalize


def run_plan(business_plan_path, conn, out_dir, year, budget):
    # load_* 가 비어 있으면 시드를 심어 돌려준다 — 별도 save 호출은 필요 없다.
    dept_config = config_store.load_dept_config(conn, year)
    pl_config = config_store.load_item_config(conn, year, "손익")
    cap_config = config_store.load_item_config(conn, year, "자본")

    item_config = pl_config if budget == "손익" else cap_config
    # 예산과목 명칭 통일(계정코드 동일 개명 흡수) — 실적 분석과 동일 기준.
    # 구성(config)에도 같은 alias를 적용해야 구명으로 등록된 과목이 누락되지 않는다.
    item_alias = config_store.load_item_alias(conn)
    pl_items = {normalize.normalize_item(x["과목"], item_alias)
                for x in pl_config if x.get("포함")}
    cap_items = {normalize.normalize_item(x["과목"], item_alias)
                 for x in cap_config if x.get("포함")}

    df = loaders.load_business_plan(business_plan_path)
    df["예산과목"] = df["예산과목"].map(lambda x: normalize.normalize_item(x, item_alias))
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
