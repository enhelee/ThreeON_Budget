# -*- coding: utf-8 -*-
"""보정 규칙(담당자 보정사전) — 키 정규화·매칭 우선순위·제외·저장·API.

담당자가 ERP 를 보며 손으로 맞춘 «(지사, 과목, 전표텍스트) → 사업명 | 제외» 를
매년 자동으로 다시 쓰게 하는 장치다. 사업명은 계획본 이름(대응표로 고친 이름)이어야
붙는다 — 계획에 없는 이름이면 규칙을 건너뛰고 원래 매칭으로 간다(엉뚱한 신규 사업을
만들지 않는다).
"""
import io
import os
import sys

import openpyxl
import pandas as pd
import pytest

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from budget import corr_rules, matching, normalize  # noqa: E402
from budget import db as dbm  # noqa: E402
from budget import pipeline_db  # noqa: E402
from tests.test_db_pipeline import TOTAL, env  # noqa: E402,F401

ITEM = "수선유지비-열원정기점검"


# ── 키 정규화: 담당자 도구(pipeline.js simNorm)와 같은 키가 나와야 규칙이 맞는다 ──

@pytest.mark.parametrize("raw, key", [
    # 기대값은 Claude/src/pipeline.js 의 simNorm 실행 결과 그대로다.
    ("'25년 GT 29회 기성(정비)", "25년가스터빈기성정비"),
    ("2024년도 HRSG 3분기 점검", "배열회수보일러점검"),
    ("계량기 12월분 검침/수수료", "계량기분검침수수료"),
    ("비용역인식 25.3월 LTSA", "25.LTSA"),
    ("Ａ　가스터빈 · 보수", "Ａ가스터빈보수"),
])
def test_corr_key_matches_js_simnorm(raw, key):
    assert normalize.corr_key(raw) == key


def test_corr_key_gt_only_as_word():
    """GT 는 단어일 때만 가스터빈 — 영문 단어 속 GT 는 그대로(JS \\b 는 한글을 단어로 안 본다)."""
    assert normalize.corr_key("가스GT점검") == "가스가스터빈점검"
    assert normalize.corr_key("AGTB") == "AGTB"
    assert normalize.corr_key(None) == ""


# ── 업로드 파일 해석 ─────────────────────────────────────────────────────────

HDR = ["지사", "예산과목", "전표텍스트", "금액", "내가붙인사업명", "신뢰도", "검토필요", "올바른사업명", "계획사업명"]


def test_parse_rows_prefers_plan_name_and_reads_exclude():
    rows = [HDR,
            ["화성지사", ITEM, "정기점검 29회 기성", "", "", "", "", "집계표 이름", "계획본 이름"],
            ["화성지사", ITEM, "정기점검 부가세", "", "", "", "", "집계표 이름2", ""],
            ["", ITEM, "역분개 정정", "", "", "", "", "제외(역분개)", ""],
            ["화성지사", ITEM, "안 채운 줄", "", "", "", "", "", ""],
            ["화성지사", ITEM, "", "", "", "", "", "텍스트 없음", ""]]
    out = corr_rules.parse_rows(rows)
    rules = {(r["처지사"], r["과목"], r["텍스트키"]): r for r in out["rules"]}
    a = rules[("화성지사", ITEM, normalize.corr_key("정기점검 29회 기성"))]
    assert (a["동작"], a["사업명"], a["원사업명"]) == ("배정", "계획본 이름", "집계표 이름")
    b = rules[("화성지사", ITEM, normalize.corr_key("정기점검 부가세"))]
    assert b["사업명"] == "집계표 이름2"           # 대응 칸이 비면 올바른사업명 그대로
    c = rules[("", ITEM, normalize.corr_key("역분개 정정"))]
    assert c["동작"] == "제외" and c["사업명"] is None
    assert out["skipped"] == 2                      # 사업명 빈 줄·텍스트 빈 줄


def test_parse_rows_requires_columns():
    with pytest.raises(ValueError):
        corr_rules.parse_rows([["가", "나"], ["1", "2"]])


def test_parse_rows_later_row_wins_on_same_key():
    rows = [HDR,
            ["화성지사", ITEM, "점검 1회", "", "", "", "", "A", ""],
            ["화성지사", ITEM, "점검 2회", "", "", "", "", "B", ""]]  # 회차만 달라 같은 키
    out = corr_rules.parse_rows(rows)
    assert len(out["rules"]) == 1 and out["rules"][0]["사업명"] == "B"


# ── 매칭 엔진 ────────────────────────────────────────────────────────────────

def _erp(rows):
    df = pd.DataFrame([{"_erp_row": n, "계정코드": "60909002", "예산과목원문": ITEM, "연도": "2025",
                        "전표번호": f"D{n}", "금액원": amt * 1000, "금액천원": float(amt),
                        "사업명": text, "지사원문": dept} for n, (text, amt, dept) in enumerate(rows, 1)])
    df["과목정규"] = df["예산과목원문"]
    df["처지사정규"] = df["지사원문"]
    return df


def _plan():
    return pd.DataFrame([
        {"_row": 1, "예산과목": ITEM, "처지사": "화성지사", "사업명": "화성 정기점검 보수공사", "연예산": 9000.0},
        {"_row": 2, "예산과목": ITEM, "처지사": "화성지사", "사업명": "화성 배관 도색", "연예산": 9000.0},
        {"_row": 3, "예산과목": ITEM, "처지사": "대구지사", "사업명": "대구 정기점검", "연예산": 9000.0},
    ])


def _run(erp, rules=None, **kw):
    return matching.match_actuals(_plan(), erp, {ITEM}, {ITEM}, set(), threshold=80,
                                  corr_rules=rules, **kw)


def _row(res, name):
    return next(r for r in res["plan_rows"] if r["사업명"] == name)


def test_assign_rule_beats_similarity_and_learned():
    erp = _erp([("화성 정기점검 보수공사 3회", 1000, "화성지사")])
    key = (ITEM, normalize.learn_key("화성 정기점검 보수공사 3회"))
    rules = {("화성지사", ITEM, normalize.corr_key("화성 정기점검 보수공사 3회")):
             {"동작": "배정", "사업명": "화성 배관 도색"}}
    res = _run(erp, rules, learned={key: "화성 정기점검 보수공사"})
    assert _row(res, "화성 배관 도색")["실적금액"] == 1000.0
    assert _row(res, "화성 정기점검 보수공사")["실적금액"] == 0.0
    ann = res["erp_annotated"]
    assert ann["매칭근거"].iloc[0] == "보정 규칙"
    assert ann["매칭확신도"].iloc[0] == 1.0


def _assign(text, name, dept="화성지사"):
    return {(dept, ITEM, normalize.corr_key(text)): {"동작": "배정", "사업명": name}}


def test_assign_rule_with_unknown_name_makes_new_project():
    """계획에 같은·비슷한 사업이 없으면 규칙 이름 그대로 신규 사업 줄로 — 유사도로 아무 데나 붙이지 않는다."""
    erp = _erp([("화성 정기점검 보수공사 3회", 1000, "화성지사")])
    res = _run(erp, _assign("화성 정기점검 보수공사 3회", "화성 발전설비동 옥상방수 공사"))
    assert _row(res, "화성 정기점검 보수공사")["실적금액"] == 0.0
    assert [(r["사업명"], r["실적금액"]) for r in res["new_rows"]] == [("화성 발전설비동 옥상방수 공사", 1000.0)]
    assert res["erp_annotated"]["매칭근거"].iloc[0] == "보정 규칙(신규 사업)"


def test_assign_rule_ltsa_spelling_finds_plan_project():
    """장기유지보수계약 = LTSA 표기만 다른 같은 사업이면 계획 사업에 붙인다."""
    plan = pd.concat([_plan(), pd.DataFrame([{"_row": 4, "예산과목": ITEM, "처지사": "화성지사",
                                               "사업명": "화성 GT LTSA", "연예산": 9000.0}])])
    erp = _erp([("가스터빈 정비 기성", 1000, "화성지사")])
    res = matching.match_actuals(plan, erp, {ITEM}, {ITEM}, set(), threshold=80,
                                 corr_rules=_assign("가스터빈 정비 기성", "화성 GT 장기유지보수계약"))
    assert _row(res, "화성 GT LTSA")["실적금액"] == 1000.0
    assert res["new_rows"] == []


def test_assign_rule_ltsa_of_other_project_is_not_merged():
    """LTSA 가 들어갔다고 같은 사업이 아니다 — 앞 이름(발전소·호기)이 다르면 신규로 둔다."""
    plan = pd.concat([_plan(), pd.DataFrame([{"_row": 4, "예산과목": ITEM, "처지사": "화성지사",
                                               "사업명": "화성 1호기 LTSA", "연예산": 9000.0}])])
    erp = _erp([("정비 기성", 1000, "화성지사")])
    for name in ("대구 장기유지보수계약", "화성 2호기 장기유지보수계약"):
        res = matching.match_actuals(plan, erp, {ITEM}, {ITEM}, set(), threshold=80,
                                     corr_rules=_assign("정비 기성", name))
        assert _row(res, "화성 1호기 LTSA")["실적금액"] == 0.0, name
        assert [r["사업명"] for r in res["new_rows"]] == [name]


def test_assign_rule_near_identical_name_finds_plan_project():
    erp = _erp([("보수 3회", 1000, "화성지사")])
    res = _run(erp, _assign("보수 3회", "화성 정기점검 보수 공사분"))
    assert _row(res, "화성 정기점검 보수공사")["실적금액"] == 1000.0
    assert res["erp_annotated"]["매칭근거"].iloc[0] == "보정 규칙"


def test_rule_is_branch_specific():
    erp = _erp([("정기점검", 1000, "대구지사")])
    rules = {("화성지사", ITEM, normalize.corr_key("정기점검")): {"동작": "배정", "사업명": "화성 배관 도색"}}
    res = _run(erp, rules)
    assert _row(res, "대구 정기점검")["실적금액"] == 1000.0


def test_exclude_rule_drops_voucher_from_totals():
    erp = _erp([("화성 정기점검 보수공사", 1000, "화성지사"),
                ("역분개 정정 1회", 300, "화성지사"),
                ("역분개 정정 2회", 200, "대구지사")])
    rules = {("", ITEM, normalize.corr_key("역분개 정정")): {"동작": "제외", "사업명": None}}
    res = _run(erp, rules)
    total = sum(r["실적금액"] for r in res["plan_rows"]) + sum(r["실적금액"] for r in res["new_rows"])
    assert total == 1000.0                           # 빈 지사 규칙 = 모든 지사
    ex = res["excluded_by_reason"][matching.EXCL_RULE]
    assert ex["전표"] == 2 and round(ex["금액"]) == 500


def test_branch_exclude_rule_only_hits_that_branch():
    erp = _erp([("역분개", 300, "화성지사"), ("역분개", 200, "대구지사")])
    rules = {("화성지사", ITEM, normalize.corr_key("역분개")): {"동작": "제외", "사업명": None}}
    res = _run(erp, rules)
    assert res["excluded_by_reason"][matching.EXCL_RULE]["전표"] == 1
    assert _row(res, "대구 정기점검")["실적금액"] == 200.0


def test_manual_override_beats_exclude_rule():
    """사람이 재배정한 전표는 제외 규칙보다 우선한다."""
    erp = _erp([("역분개", 300, "화성지사")])
    rules = {("", ITEM, normalize.corr_key("역분개")): {"동작": "제외", "사업명": None}}
    res = _run(erp, rules, overrides={1: "화성 배관 도색"})
    assert _row(res, "화성 배관 도색")["실적금액"] == 300.0
    assert matching.EXCL_RULE not in res["excluded_by_reason"]


def test_no_rules_same_as_before():
    erp = _erp([("화성 정기점검 보수공사", 1000, "화성지사"), ("역분개", 300, "화성지사")])
    a, b = _run(erp), _run(erp, {})
    assert [r["실적금액"] for r in a["plan_rows"]] == [r["실적금액"] for r in b["plan_rows"]]


# ── 저장소 + DB 파이프라인 ───────────────────────────────────────────────────

def _rule(dept, text, name, action="배정"):
    return {"처지사": dept, "과목": ITEM, "텍스트키": normalize.corr_key(text),
            "동작": action, "사업명": name if action == "배정" else None,
            "원사업명": name, "원텍스트": text}


def test_store_replace_load_stats_clear(env):
    conn, _ = env
    dbm.replace_corr_rules(conn, [_rule("화성지사", "가", "A"), _rule("", "나", "제외", "제외")])
    assert dbm.corr_rule_stats(conn) == {"배정": 1, "제외": 1, "총계": 2}
    m = dbm.load_corr_rules(conn)
    assert m[("화성지사", ITEM, normalize.corr_key("가"))]["사업명"] == "A"
    dbm.replace_corr_rules(conn, [_rule("화성지사", "다", "C")])   # 통째로 갈아끼운다
    assert dbm.corr_rule_stats(conn)["총계"] == 1
    dbm.clear_corr_rules(conn)
    assert dbm.corr_rule_stats(conn)["총계"] == 0


def test_db_run_applies_rules(env):
    """D3(저유사 임의귀속)를 규칙으로 도색공사에, D1(정기점검)을 제외로."""
    conn, out = env
    dbm.replace_corr_rules(conn, [
        _rule("화성지사", "다른 무언가 공사", "화성 옥외배관 도색공사"),
        _rule("화성지사", "화성 정기점검 보수공사 1회", "제외", "제외"),
    ])
    res = pipeline_db.run_actual_db(conn, out, "2023", "손익")
    assert res["요약"]["총 실적(천원)"] == TOTAL - 8000
    detail = dbm.load_match_detail(conn, res["run_id"])
    d3 = detail[detail["전표번호"] == "D3"].iloc[0]
    assert d3["매칭사업명"] == "화성 옥외배관 도색공사" and d3["매칭확신도"] == 1.0


# ── API ──────────────────────────────────────────────────────────────────────

@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "")
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setattr(dbm, "DEFAULT_DB", str(tmp_path / "t.db"))
    import server
    from budget import auth as authm
    monkeypatch.setattr(server, "AUTH", authm.AuthConfig())
    from fastapi.testclient import TestClient
    return TestClient(server.app)


def _xlsx(rows):
    wb = openpyxl.Workbook()
    for r in rows:
        wb.active.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_api_upload_get_delete(client):
    data = _xlsx([HDR,
                  ["화성지사", ITEM, "점검 기성", "", "", "", "", "집계표명", "계획명"],
                  ["", ITEM, "역분개", "", "", "", "", "제외", ""],
                  ["화성지사", ITEM, "빈 줄", "", "", "", "", "", ""]])
    r = client.post("/api/corr-rules", files={"file": ("규칙.xlsx", data)})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["stats"] == {"배정": 1, "제외": 1, "총계": 2} and body["skipped"] == 1
    assert client.get("/api/corr-rules").json()["stats"]["총계"] == 2
    assert client.delete("/api/corr-rules").status_code == 200
    assert client.get("/api/corr-rules").json()["stats"]["총계"] == 0


def test_api_upload_rejects_bad_sheet(client):
    r = client.post("/api/corr-rules", files={"file": ("x.xlsx", _xlsx([["가"], ["나"]]))})
    assert r.status_code == 400


def test_api_get_never_lists_names(client):
    """조회는 건수만 — 사업명·전표텍스트를 화면 밖으로 내보내지 않는다."""
    client.post("/api/corr-rules", files={"file": ("r.xlsx", _xlsx(
        [HDR, ["화성지사", ITEM, "비밀 텍스트", "", "", "", "", "비밀 사업", ""]]))})
    assert "비밀" not in client.get("/api/corr-rules").text
