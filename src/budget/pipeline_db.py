# -*- coding: utf-8 -*-
"""DB 기반 실적분석 실행 — 보안 저장소(SQLite)에서 읽어 분석·기록.

파일 업로드는 db.ingest_*로 흡수되어 원본 파일이 남지 않고, 분석은 항상
DB의 최신 데이터셋 + 사용자 오버라이드(전표 재배정)를 반영해 실행된다.
"""
import os

from . import db as dbm
from . import pipeline_actual


def run_actual_db(conn, config_dir, out_dir, year, budget, new_policy="group",
                  master_path=None):
    """DB의 최신 계획/ERP 데이터셋으로 실적분석 실행 + 결과를 run으로 기록.

    반환: pipeline_actual 결과 dict + {"run_id": ...}.
    """
    plan_df = dbm.load_plan_df(conn, year)
    erp_df = dbm.load_erp_df(conn, year)
    if plan_df is None or erp_df is None:
        missing = []
        if plan_df is None:
            missing.append("계획")
        if erp_df is None:
            missing.append("ERP(zrfm2)")
        raise ValueError(f"{year}년 {' / '.join(missing)} 자료가 DB에 없습니다. "
                         "'자료 등록'에서 먼저 업로드하세요.")

    overrides = dbm.override_map(conn, year, budget)
    learned = dbm.load_learned(conn)
    biz_edits = dbm.list_biz_edits(conn, year, budget)
    attr_map = dbm.load_item_attr_map(conn)          # 마스터: 과목→속성(4종)
    code_to_item = dbm.load_code_to_item(conn)       # 마스터: 계정코드→과목명
    deptcode_map = dbm.load_deptcode_map(conn)       # 마스터: 부서코드→처지사
    manual_biz = dbm.list_manual_biz(conn, year, budget)   # 수동 추가 사업
    res = pipeline_actual.run_actual_frames(
        plan_df, erp_df, master_path, config_dir, out_dir, year, budget,
        new_policy=new_policy, zrfm2_src_path=None, overrides=overrides,
        learned=learned, biz_edits=biz_edits,
        attr_map=attr_map, code_to_item=code_to_item, deptcode_map=deptcode_map,
        manual_biz=manual_biz,
    )
    run_id = dbm.save_run(conn, year, budget, res["요약"], res["erp_annotated"])
    dbm.save_biz_lines(conn, run_id, budget, res["plan_rows"], res["new_rows"])
    res["run_id"] = run_id
    return res
