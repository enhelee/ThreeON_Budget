# -*- coding: utf-8 -*-
"""검토 대기(2026-10-27) — 사업 한 줄 단위로 이유를 모아 «검토 금액 × 위험 가중»으로 세우고,
커버율(상위 N건이 남은 검토 금액의 몇 %)·진행률·승인/사유/재배정 처리 상태를 준다.
"""
import os
import sys
import time

import pytest

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from budget import db as dbm, review_queue as rqm   # noqa: E402
from tests.test_upload_export_fixes import _analyzed, srv   # noqa: E402,F401


def _line(name, plan, actual, dept="화성지사", item="기계장치", budget="자본", gubun="계획집행"):
    return {"budget": budget, "처지사": dept, "예산과목": item, "사업명": name,
            "연예산": plan, "실적금액": actual, "구분": gubun}


def _key(name, dept="화성지사", item="기계장치", budget="자본"):
    return (budget, item, dept, name)


# ── 순수 계산 ──────────────────────────────────────────────────────────

def test_only_lines_with_a_reason_enter_the_queue():
    items = rqm.build_items([_line("정상", 100_000, 100_000), _line("조금 초과", 100_000, 115_000),
                             _line("미시행", 100_000, 0), _line("신규", 0, 30_000, gubun="신규")])
    assert [it["name"] for it in items] == ["미시행"]
    it = items[0]
    assert it["reasons"][0]["code"] == "variance" and it["amount"] == 100_000 and it["rank"] == 1
    assert it["dir"] == "under" and it["rate"] == 0.0 and it["needsNote"] is True


def test_priority_is_amount_times_risk_weight():
    """과다 귀속(×1.5)은 같은 금액의 단순 차이(×1.0)보다 앞에 선다 — 숫자 자체가 틀렸을 수 있다."""
    alerts = [{"kind": "과다 귀속", "budget": "자본", "branch": "화성지사", "item": "기계장치",
               "name": "과다", "text": "", "amount": 0}]
    items = rqm.build_items([_line("차이", 300_000, 100_000),          # 검토 금액 200,000
                             _line("과다", 50_000, 200_000)], alerts=alerts)   # 150,000 × 1.5 = 225,000
    assert [it["name"] for it in items] == ["과다", "차이"]
    assert items[0]["score"] == 225_000 and items[0]["amount"] == 150_000
    assert items[0]["reasons"][0]["label"] == "과다 귀속"


def test_lowconf_reason_and_same_money_not_counted_twice():
    basis = {_key("저확신"): {"total": 120_000, "lowconf": 90_000, "manual": 0}}
    items = rqm.build_items([_line("저확신", 100_000, 160_000)], basis=basis)
    codes = [r["code"] for r in items[0]["reasons"]]
    assert codes == ["variance", "lowconf"]
    assert items[0]["amount"] == 90_000                 # max(60,000, 90,000) — 합(150,000)이 아니다
    assert items[0]["score"] == round(90_000 * rqm.WEIGHTS["lowconf"])


def test_small_lowconf_is_ignored():
    basis = {_key("작음"): {"total": 5_000, "lowconf": rqm.LOWCONF_MIN - 1, "manual": 0}}
    assert rqm.build_items([_line("작음", 100_000, 100_000)], basis=basis) == []


def test_manual_reassign_share_gives_a_hint():
    basis = {_key("사람"): {"total": 300_000, "lowconf": 0, "manual": 240_000}}
    it = rqm.build_items([_line("사람", 100_000, 300_000)], basis=basis)[0]
    assert any("사람이 재배정한 전표" in c for c in it["ctx"])


def test_status_note_ack_stale_and_moved():
    lines = [_line("사유", 100_000, 0), _line("승인", 100_000, 0), _line("옛승인", 100_000, 0),
             _line("재배정", 100_000, 300_000), _line("남음", 100_000, 0)]
    notes = {_key("사유"): {"note": "차년도 이월"}}
    acks = {_key("승인"): {"actual": 0}, _key("옛승인"): {"actual": 55_000}}   # 승인 뒤 실적이 바뀜
    items = {it["name"]: it for it in rqm.build_items(lines, notes=notes, acks=acks, moved={_key("재배정")})}
    assert items["사유"]["status"] == "noted" and items["사유"]["resolved"]
    assert items["승인"]["status"] == "approved" and items["승인"]["resolved"]
    assert items["옛승인"]["status"] == "stale" and not items["옛승인"]["resolved"]
    assert items["재배정"]["status"] == "moved" and items["재배정"]["resolved"]
    assert items["남음"]["status"] == "open"


def test_lowconf_only_line_is_not_closed_by_a_note():
    """질문이 «귀속이 맞나»라서 사유로는 닫히지 않는다 — 승인이나 재배정으로 닫는다."""
    basis = {_key("귀속"): {"total": 100_000, "lowconf": 80_000, "manual": 0}}
    notes = {_key("귀속"): {"note": "설명"}}
    it = rqm.build_items([_line("귀속", 100_000, 100_000)], basis=basis, notes=notes)[0]
    assert it["needsNote"] is False and it["status"] == "open"


def test_open_items_first_and_ranked():
    lines = [_line("큰-처리", 1_000_000, 0), _line("중간", 500_000, 0), _line("작은", 100_000, 0)]
    items = rqm.build_items(lines, notes={_key("큰-처리"): {"note": "x"}})
    assert [(it["name"], it["rank"]) for it in items] == [("중간", 1), ("작은", 2), ("큰-처리", None)]


def test_summary_coverage_and_progress():
    lines = [_line(f"사업{i}", a, 0) for i, a in enumerate([700, 200, 50, 30, 20])]
    items = rqm.build_items(lines)
    sm = rqm.summarize(items)
    assert rqm.coverage_curve(items) == [0.7, 0.9, 0.95, 0.98, 1.0]
    assert sm["n80"] == 2 and sm["open"] == 5 and sm["progress"] == 0.0
    items = rqm.build_items(lines, notes={_key("사업0"): {"note": "x"}})
    sm = rqm.summarize(items)
    assert sm["progress"] == 0.7 and sm["amount_open"] == 300 and sm["open"] == 4
    assert sm["n80"] == 2                           # 남은 300 중 200+50 = 83%


def test_duplicate_names_are_merged():
    items = rqm.build_items([_line("동명", 100_000, 0), _line("동명", 50_000, 0)])
    assert len(items) == 1 and items[0]["plan"] == 150_000


def test_suggest_picks_a_clearly_closer_plan_project():
    vouchers = [{"erp_row_id": 1, "텍스트": "가스터빈 압축기 블레이드 세척 공사", "금액천원": 30_000},
                {"erp_row_id": 2, "텍스트": "", "금액천원": 10_000},
                {"erp_row_id": 3, "텍스트": "보호계전기 교체", "금액천원": 5_000}]
    cands = [{"name": "가스터빈 압축기 블레이드 세척", "plan": 50_000, "actual": 0},
             {"name": "건물 도장 공사", "plan": 10_000, "actual": 0}]
    out = rqm.suggest(vouchers, "보호계전기 교체 공사", cands)
    assert out[0]["suggest"]["target"] == "가스터빈 압축기 블레이드 세척"
    assert "유사도" in out[0]["suggest"]["why"] and "잔액" in out[0]["suggest"]["why"]
    assert out[1]["suggest"] is None                # 글자 없는 전표는 추천하지 않는다
    assert out[2]["suggest"] is None                # 지금 사업이 더 닮았다


@pytest.mark.parametrize("text,name,bad", [
    ("GT LTSA '25년 1월 비용인식", "공무_연료전지 LTSA", True),          # 설비가 다르다
    ("2025년판교정기점검보수준공", "2024년 판교지사 정기점검보수공사", True),   # 연도가 다르다
    ("GT LTSA '25년 1월 비용인식", "공무_가스터빈 LTSA(고정비)", False),    # 같은 설비(GT=가스터빈)
    ("정기점검 보험료 사후정산", "2025년 SRF 정기점검", False),            # 한쪽에만 적혀 있으면 판단 안 함
])
def test_conflicting_equipment_or_year_blocks_suggestion(text, name, bad):
    assert rqm.conflicts(text, name) is bad


def test_suggest_never_crosses_equipment():
    out = rqm.suggest([{"erp_row_id": 1, "텍스트": "GT LTSA 비용인식", "금액천원": 100}], "공무_가스터빈 LTSA(고정비)",
                      [{"name": "공무_연료전지 LTSA", "plan": 10_000, "actual": 0}])
    assert out[0]["suggest"] is None


def test_suggest_incoming_for_under_executed_line():
    sib = [{"erp_row_id": 9, "텍스트": "옥외배관 도색", "금액천원": 4_000, "from": "정기점검 보수공사"},
           {"erp_row_id": 8, "텍스트": "정기점검 보수", "금액천원": 9_000, "from": "정기점검 보수공사"}]
    got = rqm.suggest_incoming("옥외배관 도색공사", sib)
    assert [v["erp_row_id"] for v in got] == [9]


def test_no_literal_percent_in_sql_for_postgres():
    """PG(psycopg)는 매개변수가 있는 SQL 의 «%» 를 자리표시자로 읽는다 — LIKE 무늬는 매개변수로 넘긴다."""
    import inspect
    import re as _re
    src = inspect.getsource(dbm.basis_by_line) + inspect.getsource(dbm.moved_lines)
    assert not _re.search(r"LIKE\s+'[^']*%", src)


# ── 서버 ────────────────────────────────────────────────────────────────

def _queue(client, year="2023"):
    r = client.get(f"/api/review-queue?year={year}")
    assert r.status_code == 200, r.text
    return r.json()


def test_queue_api_lists_lines_and_brief(srv):
    _, client, _ = srv
    assert _queue(client)["analyzed"] is False
    _analyzed(client)
    d = _queue(client)
    assert d["analyzed"] and d["items"] and d["summary"]["open"] == len(d["items"])
    it = d["items"][0]
    for k in ("key", "budget", "branch", "item", "name", "plan", "actual", "amount", "score",
              "reasons", "status", "rank"):
        assert k in it
    brief = client.get("/api/review-queue?year=2023&brief=1").json()
    assert len(brief["items"]) <= 3 and brief["summary"] == d["summary"]


def _ack(client, it, ack=True, year="2023"):
    return client.put("/api/review-ack", json={"year": year, "budget": it["budget"], "예산과목": it["item"],
                                               "처지사": it["branch"], "사업명": it["name"], "ack": ack})


def test_ack_resolves_and_undo_reopens(srv):
    _, client, _ = srv
    _analyzed(client)
    it = _queue(client)["items"][0]
    r = _ack(client, it)
    assert r.status_code == 200 and r.json()["ack"]["actual"] == it["actual"]
    after = {x["key"]: x for x in _queue(client)["items"]}
    assert after[it["key"]]["status"] == "approved"
    assert _queue(client)["summary"]["progress"] > 0
    assert _ack(client, it, ack=False).json()["ack"] is None
    assert {x["key"]: x for x in _queue(client)["items"]}[it["key"]]["status"] == "open"


def test_ack_allowed_on_locked_year_and_unknown_line_404(srv):
    _, client, _ = srv
    _analyzed(client)
    it = _queue(client)["items"][0]
    assert client.post("/api/lock", json={"year": "2023"}).status_code == 200
    assert _ack(client, it).status_code == 200
    assert _ack(client, {**it, "name": "없는 사업"}).status_code == 404
    assert _ack(client, {**it, "budget": "기타"}).status_code == 400      # 미들웨어 검증


def test_variance_note_marks_item_noted(srv):
    _, client, _ = srv
    _analyzed(client)
    it = next(x for x in _queue(client)["items"] if x["needsNote"])
    client.put("/api/variance-note", json={"year": "2023", "budget": it["budget"], "예산과목": it["item"],
                                           "처지사": it["branch"], "사업명": it["name"], "note": "차년도 이월"})
    got = {x["key"]: x for x in _queue(client)["items"]}[it["key"]]
    assert got["status"] == "noted" and got["note"] == "차년도 이월"


def test_saved_override_marks_source_line_moved(srv):
    """재배정을 저장하면(분석 반영 전) 전표가 떠난 줄이 «재배정 대기»로 잡힌다."""
    _, client, _ = srv
    _analyzed(client)
    biz = client.get("/api/branch-detail?year=2023&branch=화성지사").json()["biz"]
    b = next(x for x in biz if x["전표"])
    key = (b["budget"], b["예산과목"], "화성지사", b["사업명"])
    conn = dbm.connect()
    try:
        run = dbm.latest_run(conn, "2023", b["budget"])
        rows = dbm.load_biz_lines(conn, run["id"]).to_dict("records")
        assert key not in dbm.moved_lines(conn, "2023", b["budget"], run, rows)
        time.sleep(1.1)        # 시각이 초 단위 — «미반영» 배지(_pending_data)와 같은 «초과» 비교라 한 초 띄운다
        r = client.post("/api/override", json={"year": "2023", "budget": b["budget"],
                                               "erp_row_ids": [b["전표"][0]["erp_row_id"]],
                                               "target_name": "새 사업"})
        assert r.status_code == 200
        moved = dbm.moved_lines(conn, "2023", b["budget"], run, rows)
        assert key in moved
        assert (b["budget"], b["예산과목"], "화성지사", "새 사업") in moved     # 받을 줄도
    finally:
        conn.close()
    # 줄이 큐에 있다면 상태도 moved — 큐 계산이 같은 키를 쓰는지
    items = rqm.build_items([{**x, "budget": b["budget"]} for x in rows if x["사업명"] == b["사업명"]],
                            moved={key})
    assert all(it["status"] == "moved" for it in items)


def test_suggest_api_shape(srv):
    _, client, _ = srv
    _analyzed(client)
    biz = client.get("/api/branch-detail?year=2023&branch=화성지사").json()["biz"]
    b = next(x for x in biz if x["전표"])
    r = client.get("/api/review-suggest", params={"year": "2023", "budget": b["budget"], "branch": "화성지사",
                                                  "item": b["예산과목"], "name": b["사업명"]})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["voucher_total"] == len(b["전표"]) and d["locked"] is False
    assert all("suggest" in v for v in d["nominate"])
    assert all(c["name"] != b["사업명"] for c in d["candidates"])
