# -*- coding: utf-8 -*-
"""DB 기반 실적분석 실행 — 보안 저장소(SQLite)에서 읽어 분석·기록.

파일 업로드는 db.ingest_*로 흡수되어 원본 파일이 남지 않고, 분석은 항상
DB의 최신 데이터셋 + 사용자 오버라이드(전표 재배정)를 반영해 실행된다.
"""
import os

from . import config_store, erp_loader, spec_io
from . import db as dbm
from . import pipeline_actual

# 팀 v2 앱(예산예측프로그램_팀공유_v2)으로 넘기는 연계 산출물 파일명. {y}=연도.
TEAM_BUNDLE_FILES = {
    "json": "팀연계_{y}_사업실적연결.json",   # 「예산 실적 집계 → 사업 실적 연결」 업로드용
    "matched": "matched_{y}.csv",            # 연동규격 §3-4 (손익+자본 통합)
    "budget": "budget_{y}.csv",              # 연동규격 §3-2
    "data": "data_{y}.csv",                  # 연동규격 §3-1
}


def team_bundle_paths(out_dir, year):
    return {k: os.path.join(out_dir, v.format(y=year)) for k, v in TEAM_BUNDLE_FILES.items()}


def export_team_bundle(conn, config_dir, out_dir, year, budgets=("손익", "자본")):
    """손익·자본 최신 분석을 (기록 없이) 재실행해 팀 v2 연계 파일 4종을 만든다.

    - 팀연계_{y}_사업실적연결.json : spec_io.build_team_result_json (schemaVersion 1)
    - matched_{y}.csv / budget_{y}.csv / data_{y}.csv : 연동규격_INTERFACE CSV 계약
    record_run=False — 새 실행 이력을 남기면 방금 만든 파일이 '최신 run보다 오래됨'이 되어
    매 다운로드마다 재생성된다(server.py /api/export와 같은 함정).
    반환: {"paths": {...}, "summary": JSON summary, "run_ids": {budget: run_id}}
    """
    frames, run_ids = {}, {}
    for budget in budgets:
        res = run_actual_db(conn, config_dir, out_dir, year, budget,
                            make_files=False, record_run=False)
        frames[budget] = res["erp_annotated"]
        run_ids[budget] = res.get("run_id")
    os.makedirs(out_dir, exist_ok=True)
    paths = team_bundle_paths(out_dir, year)
    result = spec_io.build_team_result_json(
        year, frames, meta={"runIds": run_ids, "budgets": list(budgets)})
    spec_io.write_team_result_json(paths["json"], result)
    spec_io.write_matched_csv_combined(frames, paths["matched"])

    item_alias = config_store.load_item_alias(config_dir)
    plan_df = dbm.load_plan_df(conn, year)
    if plan_df is not None:
        spec_io.write_budget_csv_from_df(plan_df, paths["budget"], normalize_item_alias=item_alias)
    erp_df = dbm.load_erp_df(conn, year)
    if erp_df is not None:
        tagged = erp_loader.tag_excluded(erp_df, year)
        clean = erp_df[tagged["제외사유"].isna()]     # 합계행·타연도 제외 = '정제 실적'
        spec_io.write_data_csv_from_df(clean, paths["data"], year=None,
                                       normalize_item_alias=item_alias)
    return {"paths": paths, "summary": result["summary"], "run_ids": run_ids}


def run_actual_db(conn, config_dir, out_dir, year, budget, new_policy="group",
                  master_path=None, make_files=True, record_run=True):
    """DB의 최신 계획/ERP 데이터셋으로 실적분석 실행 + 결과를 run으로 기록.

    make_files=False면 Excel/CSV를 만들지 않는다 — 화면 갱신용 빠른 분석
    (실측 2025 손익: 13.8초 → 5.3초). 파일은 내보내기 시점에 생성한다.
    record_run=False면 실행 이력(run/match_line/biz_line)을 남기지 않는다 —
    내보내기용 파일 재생성처럼 '결과를 바꾸지 않는 재실행'에 쓴다.

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
    biz_deletes = dbm.list_biz_deletes(conn, year, budget)  # 삭제(분석 제외) 사업
    res = pipeline_actual.run_actual_frames(
        plan_df, erp_df, master_path, config_dir, out_dir, year, budget,
        new_policy=new_policy, zrfm2_src_path=None, overrides=overrides,
        learned=learned, biz_edits=biz_edits,
        attr_map=attr_map, code_to_item=code_to_item, deptcode_map=deptcode_map,
        manual_biz=manual_biz, biz_deletes=biz_deletes, make_files=make_files,
    )
    if record_run:
        run_id = dbm.save_run(conn, year, budget, res["요약"], res["erp_annotated"])
        dbm.save_biz_lines(conn, run_id, budget, res["plan_rows"], res["new_rows"])
        res["run_id"] = run_id
    else:
        # 내보내기용 재실행 — 새 실행 이력을 남기지 않는다. 남기면 방금 만든 파일이
        #   'run보다 오래됨'으로 판정돼 매 다운로드마다 다시 생성된다.
        cur = dbm.latest_run(conn, year, budget)
        res["run_id"] = cur["id"] if cur else None
    return res
