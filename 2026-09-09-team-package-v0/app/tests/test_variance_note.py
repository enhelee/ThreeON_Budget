# -*- coding: utf-8 -*-
"""차이 사유(2026-10-22) — 집행률이 계획 대비 ±20%p 를 벗어난 사업에 사유를 권장한다.

판정(경계 포함 안 함) · 저장/삭제 · 상세·지사 목록 노출 · 마감 연도 허용 · 이름 변경 시 따라감.
"""
import os
import sys

import pytest

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from budget import db as dbm   # noqa: E402
from tests.test_upload_export_fixes import _analyzed, srv   # noqa: E402,F401


@pytest.mark.parametrize("plan,actual,expected", [
    (100, 100, False), (100, 80, False), (100, 120, False),     # 경계는 대상 아님
    (100, 79.9, True), (100, 120.1, True),
    (100, 0, True),                                              # 미시행(불용)도 설명 대상
    (0, 500, False), (None, 500, False),                         # 계획 없는 신규는 집행률이 없다
])
def test_is_variance_band(plan, actual, expected):
    assert dbm.is_variance(plan, actual) is expected


def test_note_set_replace_and_delete(tmp_path):
    conn = dbm.connect(str(tmp_path / "v.db"))
    key = ("2025", "손익", "수선유지비", "화성지사", "정기점검")
    assert dbm.set_variance_note(conn, *key, "  일정 이월  ", operator="홍길동") == "일정 이월"
    dbm.set_variance_note(conn, *key, "긴급 보수 추가", operator="김검토")
    got = dbm.variance_notes(conn, "2025")
    assert got[key[1:]]["note"] == "긴급 보수 추가" and got[key[1:]]["operator"] == "김검토"
    assert dbm.set_variance_note(conn, *key, "   ") is None
    assert dbm.variance_notes(conn, "2025") == {}
    conn.close()


def test_rename_moves_note(tmp_path):
    conn = dbm.connect(str(tmp_path / "r.db"))
    dbm.set_variance_note(conn, "2025", "손익", "수선유지비", "화성지사", "옛이름", "사유")
    dbm.rename_biz_references(conn, "2025", "손익", "수선유지비", "화성지사", "옛이름", "새이름")
    assert ("손익", "수선유지비", "화성지사", "새이름") in dbm.variance_notes(conn, "2025")
    conn.close()


def _variance_row(client):
    biz = client.get("/api/branch-detail?year=2023&branch=화성지사").json()["biz"]
    assert all("편차" in b and "사유" in b for b in biz)
    for b in biz:
        assert b["편차"] is dbm.is_variance(b["연예산"], b["실적"])
    flagged = [b for b in biz if b["편차"]]
    assert flagged, "시험 자료에 ±20%p 를 벗어난 사업이 있어야 한다"
    return flagged[0]


def _put(client, b, note, year="2023"):
    return client.put("/api/variance-note", json={
        "year": year, "budget": b["budget"], "예산과목": b["예산과목"],
        "처지사": "화성지사", "사업명": b["사업명"], "note": note})


def test_note_roundtrip_through_detail_and_branch_list(srv):
    _, client, _ = srv
    _analyzed(client)
    b = _variance_row(client)
    row = next(r for r in client.get("/api/branches?year=2023").json()["rows"] if r["branch"] == "화성지사")
    assert row["variance"] >= 1 and row["varianceNoted"] == 0

    r = _put(client, b, "정기점검 일정 이월")
    assert r.status_code == 200 and r.json()["note"] == "정기점검 일정 이월"
    again = next(x for x in client.get("/api/branch-detail?year=2023&branch=화성지사").json()["biz"]
                 if x["사업명"] == b["사업명"] and x["budget"] == b["budget"])
    assert again["사유"] == "정기점검 일정 이월"
    row = next(r for r in client.get("/api/branches?year=2023").json()["rows"] if r["branch"] == "화성지사")
    assert row["varianceNoted"] == 1

    assert _put(client, b, "").json()["note"] is None


def test_note_allowed_on_locked_year(srv):
    """사유는 숫자를 바꾸지 않는다 — 보통 마감 뒤 보고 때 쓰므로 막지 않는다."""
    _, client, _ = srv
    _analyzed(client)
    b = _variance_row(client)
    assert client.post("/api/lock", json={"year": "2023"}).status_code == 200
    assert _put(client, b, "마감 후 보고용 설명").status_code == 200


def test_note_validation(srv):
    _, client, _ = srv
    b = {"budget": "손익", "예산과목": "수선유지비", "사업명": "x"}
    assert _put(client, b, "가" * 501).status_code == 400
    assert _put(client, {**b, "budget": "기타"}, "사유").status_code == 400     # 미들웨어 검증
    assert _put(client, b, "사유", year="20x5").status_code == 400
