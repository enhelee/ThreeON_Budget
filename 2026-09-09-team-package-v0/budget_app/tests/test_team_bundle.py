# -*- coding: utf-8 -*-
"""팀 v2 앱(예산예측프로그램_팀공유_v2) 연계 산출물 — 결과 JSON(schemaVersion 1)·통합 CSV.

동료 앱 checkpoint_actuals.prepare_result()의 검증 규칙을 우리 산출물이 항상 만족해야 한다.
형제 폴더에 v2 앱이 있으면 실제 동료 모듈로 교차 검증까지 수행한다(없으면 skip).
"""
import importlib.util
import json
import os
import sys

import pandas as pd
import pytest

from budget import spec_io, pipeline_db

from .test_db_pipeline import env  # noqa: F401  (DB 픽스처 재사용)

ROOT = r"C:\Users\User\Desktop\중장기 예산 소요 전망"
TEAM_V2 = os.path.join(ROOT, "예산예측프로그램_팀공유_v2")
ACC = "수선유지비-열원정기점검"


def _frames():
    """손익 run: 계획집행 2전표(동일 계획행 _row=7) + 신규 1 + 미반영 1 + 타예산 1 + 제외 1.
    자본 run: 신규(소액집행 라벨) 1 + 타예산(손익 전표) 1."""
    pl = pd.DataFrame([
        {"전표번호": "D1", "사업명": "화성 정기점검 1회", "금액원": 8_000_000, "금액천원": 8000.0,
         "과목정규": ACC, "처지사정규": "화성지사", "지사원문": "화성지사",
         "매칭사업명": "화성 정기점검 보수공사", "매칭확신도": 0.9, "구분": "계획집행", "매칭행": 7,
         "거래처코드": "1", "사업장코드": "3070", "전기일": "2025-03-02"},
        {"전표번호": "D2", "사업명": "화성 정기점검 2회", "금액원": 2_500_001, "금액천원": 2500.001,
         "과목정규": ACC, "처지사정규": "화성지사", "지사원문": "화성지사",
         "매칭사업명": "화성 정기점검 보수공사", "매칭확신도": 0.5, "구분": "계획집행", "매칭행": 7,
         "거래처코드": "1", "사업장코드": "3070", "전기일": "2025-04-02"},
        {"전표번호": "D3", "사업명": "대구 긴급공사", "금액원": 3_000_000, "금액천원": 3000.0,
         "과목정규": ACC, "처지사정규": "대구지사", "지사원문": "대구지사",
         "매칭사업명": "[신규] 대구 긴급공사", "매칭확신도": 0.0, "구분": "신규", "매칭행": None,
         "거래처코드": "2", "사업장코드": "4040", "전기일": "2025-05-01"},
        {"전표번호": "D4", "사업명": "본사 사옥 수선", "금액원": 700_000, "금액천원": 700.0,
         "과목정규": ACC, "처지사정규": None, "지사원문": "본　　사",
         "매칭사업명": "", "매칭확신도": None, "구분": "미반영", "매칭행": None,
         "거래처코드": "3", "사업장코드": "1000", "전기일": "2025-06-01"},
        {"전표번호": "D5", "사업명": "자본 전표(타예산)", "금액원": 99_000_000, "금액천원": 99000.0,
         "과목정규": "기계장치", "처지사정규": "화성지사", "지사원문": "화성지사",
         "매칭사업명": "", "매칭확신도": None, "구분": "", "매칭행": None,
         "거래처코드": "4", "사업장코드": "3070", "전기일": "2025-07-01"},
        {"전표번호": None, "사업명": None, "금액원": 999_999_999, "금액천원": 999999.999,
         "과목정규": None, "처지사정규": None, "지사원문": None,
         "매칭사업명": "", "매칭확신도": None, "구분": "제외(합계행)", "매칭행": None,
         "거래처코드": None, "사업장코드": None, "전기일": None},
    ])
    cap = pd.DataFrame([
        {"전표번호": "D5", "사업명": "자본 전표(타예산)", "금액원": 99_000_000, "금액천원": 99000.0,
         "과목정규": "기계장치", "처지사정규": "화성지사", "지사원문": "화성지사",
         "매칭사업명": "[신규] 화성지사 기계장치 집행", "매칭확신도": 0.0, "구분": "신규", "매칭행": None,
         "거래처코드": "4", "사업장코드": "3070", "전기일": "2025-07-01"},
        {"전표번호": "D1", "사업명": "화성 정기점검 1회", "금액원": 8_000_000, "금액천원": 8000.0,
         "과목정규": ACC, "처지사정규": "화성지사", "지사원문": "화성지사",
         "매칭사업명": "", "매칭확신도": None, "구분": "", "매칭행": None,
         "거래처코드": "1", "사업장코드": "3070", "전기일": "2025-03-02"},
    ])
    return {"손익": pl, "자본": cap}


def _rows(table):
    return table[0], table[1:]


def test_team_json_headers_and_invariants():
    res = spec_io.build_team_result_json("2025", _frames())
    assert res["schemaVersion"] == 1 and res["amountUnit"] == "KRW_THOUSAND"
    assert res["amountMatching"] is True and res["sourceYears"] == [2025]
    rec = res["reconciliation"]
    gh, groups = _rows(rec["groups"])
    dh, details = _rows(rec["details"])
    eh, excl = _rows(rec["exclusions"])
    assert gh == spec_io.TEAM_JSON_GROUP_HEADER and all(len(r) == 13 for r in groups)
    assert dh == spec_io.TEAM_JSON_DETAIL_HEADER and all(len(r) == 8 for r in details)
    assert eh == spec_io.TEAM_JSON_EXCLUSION_HEADER and all(len(r) == 8 for r in excl)
    for k in spec_io.TEAM_JSON_AUX_TABLES:          # 동료 검토 화면용 부가 표(헤더만)
        assert rec[k] and isinstance(rec[k][0], list)

    # 묶음: 계획집행(동일 계획행 2전표→1묶음) + 신규(손익) + 신규(자본) = 3
    assert len(groups) == 3
    by_gid = {g[0]: g for g in groups}
    for d in details:
        g = by_gid[d[0]]
        assert (d[1], d[2], d[3]) == (g[1], g[2], g[3])          # 지사·과목 일치
        assert round(d[7] * 1000) == round(g[5] * 1000)          # 반영 실적 == 전표 합계(원 단위)
        assert isinstance(d[4], int) and d[4] >= 1                # 집계표 원본행 정수
    plan_detail = [d for d in details if d[1] == "손익" and d[2] == "화성지사"][0]
    assert plan_detail[4] == 7 and plan_detail[7] == 10500.001    # 계획행 _row 승계, 천원 소수 유지
    new_detail = [d for d in details if d[2] == "대구지사"][0]
    assert new_detail[4] >= spec_io.NEW_ROW_BASE and new_detail[5] == "대구 긴급공사"   # '[신규] ' 제거
    # (지사·과목·원본행) 중복 없음
    assert len({(d[1], d[2], d[3], d[4]) for d in details}) == len(details)

    # 미반영 → exclusions, 지사 미확인은 원문 지사명 유지
    assert len(excl) == 1 and excl[0][1] == "본　　사" and excl[0][4] == 700.0
    # 타예산('')·제외행은 어디에도 없다 (원장 간 중복 방지)
    assert not any("합계행" in str(r) for r in groups + details + excl)
    assert sum(1 for g in groups if g[3] == "기계장치") == 1

    # 총액 불변식: Σ sourceTotals == Σ 배정 + Σ 제외, 미배정 0
    tot = {(t["ledger"], t["org"], t["account"]): t["amountWon"] for t in res["sourceTotals"]}
    assigned = {}
    for g in groups:
        k = (g[1], g[2], g[3])
        assigned[k] = assigned.get(k, 0) + round(g[5] * 1000)
    excluded = {}
    for e in excl:
        k = (e[0], e[1], e[2])
        excluded[k] = excluded.get(k, 0) + round(e[4] * 1000)
    assert set(assigned) | set(excluded) <= set(tot)
    for k, v in tot.items():
        assert v == assigned.get(k, 0) + excluded.get(k, 0)
    s = res["summary"]
    assert s["손익"]["sourceWon"] == 8_000_000 + 2_500_001 + 3_000_000 + 700_000
    assert s["손익"]["unassignedWon"] == 0 and s["자본"]["unassignedWon"] == 0
    assert s["자본"]["sourceWon"] == 99_000_000


def test_team_json_rejects_unknown_ledger():
    with pytest.raises(ValueError):
        spec_io.build_team_result_json("2025", {"기타": _frames()["손익"]})


def test_matched_csv_combined_merges_budgets(tmp_path):
    p = tmp_path / "matched_2025.csv"
    spec_io.write_matched_csv_combined(_frames(), str(p))
    out = pd.read_csv(p, dtype=str)
    assert list(out.columns) == spec_io.MATCHED_SPEC_COLUMNS
    # 손익 4행(계획집행2·신규1·미반영1) + 자본 1행(신규) — 타예산·합계행 없음
    assert len(out) == 5
    assert set(out["계정과목"]) == {ACC, "기계장치"}
    names = set(out["사업명"].dropna())
    assert names == {"화성 정기점검 보수공사", "대구 긴급공사", "화성지사 기계장치 집행"}
    assert out[out["전표헤더텍스트"] == "본사 사옥 수선"]["사업명"].isna().all()     # 미반영 = 공란
    assert out["금액"].astype(float).sum() == 8_000_000 + 2_500_001 + 3_000_000 + 700_000 + 99_000_000


def test_export_team_bundle_writes_four_files(env):
    conn, cfg, out = env
    pipeline_db.run_actual_db(conn, cfg, out, "2023", "손익", make_files=False)
    res = pipeline_db.export_team_bundle(conn, cfg, out, "2023")
    for k, p in res["paths"].items():
        assert os.path.exists(p), k
    data = json.load(open(res["paths"]["json"], encoding="utf-8"))
    assert data["sourceYears"] == [2023]
    # 픽스처 ERP 전체 13,500천원이 손익 배정으로 전부 잡힌다(미배정 0)
    assert res["summary"]["손익"]["assignedWon"] == 13_500_000
    assert res["summary"]["손익"]["unassignedWon"] == 0
    # 내보내기는 실행 이력을 남기지 않는다
    assert conn.execute("SELECT COUNT(*) FROM run").fetchone()[0] == 1
    m = pd.read_csv(res["paths"]["matched"], dtype=str)
    assert list(m.columns) == spec_io.MATCHED_SPEC_COLUMNS and len(m) == 3
    b = pd.read_csv(res["paths"]["budget"], dtype=str)
    assert list(b.columns) == spec_io.BUDGET_COLUMNS and len(b) == 2
    d = pd.read_csv(res["paths"]["data"], dtype=str)
    assert list(d.columns) == spec_io.DATA_COLUMNS and len(d) == 3


# ── 동료 v2 모듈로 교차 검증(형제 폴더에 있을 때만) ─────────────────────────
def _load_team_module(name):
    path = os.path.join(TEAM_V2, f"{name}.py")
    if TEAM_V2 not in sys.path:
        sys.path.insert(0, TEAM_V2)          # builtin_categories 등 내부 import 해결
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.skipif(not os.path.exists(os.path.join(TEAM_V2, "checkpoint_actuals.py")),
                    reason="팀 v2 앱 폴더 없음")
def test_team_json_accepted_by_v2_checkpoint_actuals(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)               # v2 모듈은 CWD에 site_type_map.csv 등을 만든다
    ca = _load_team_module("checkpoint_actuals")
    res = spec_io.build_team_result_json("2025", _frames())
    content = json.dumps(res, ensure_ascii=False)
    _, actuals, summary = ca.prepare_result(content, 2025)
    # 원 단위 사업별 배정 프레임: 화성(손익) 10,500,001 / 대구 3,000,000 / 화성(자본) 99,000,000
    by_site = actuals.groupby(["원장", "사업장"])["금액"].sum().to_dict()
    assert by_site[("손익", "화성지사")] == 10_500_001
    assert by_site[("손익", "대구지사")] == 3_000_000
    assert by_site[("자본", "화성지사")] == 99_000_000
    assert (summary["미배정순액(원)"] == 0).all()
    assert summary["제외금액(원)"].sum() == 700_000
    # 다른 연도로 올리면 동료 검증이 거부해야 한다(연도 잠금)
    with pytest.raises(ValueError):
        ca.prepare_result(content, 2024)
    # 표준화 엔진까지 흘러가는지(동료 compute_standard_amounts) — 최근실적 방식
    std = _load_team_module("standardization")
    grades = pd.DataFrame({"사업장": ["화성지사", "대구지사"], "연도": [2025, 2025], "등급": ["MI", "MI"]})
    methods = pd.DataFrame({"사업장": ["화성지사", "대구지사"], "예산과목": [ACC, ACC],
                            "방식": ["최근실적", "최근실적"]})
    result = std.compute_standard_amounts(actuals, grades, methods)
    v = result[result["예산과목"] == ACC].set_index("사업장")["표준금액"].to_dict()
    assert v["화성지사"] == 10_500_001 and v["대구지사"] == 3_000_000
