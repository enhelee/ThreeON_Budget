# -*- coding: utf-8 -*-
"""마감 해제 구간 — 사유 기록 · 해제 상태 노출 · 재마감 요약.

마감된 연도의 숫자는 대외 보고에 쓰인 값이다. 버튼 하나로 열리고, 열린 사실이
설정 화면 안쪽에만 있으면 열린 줄 모르고 며칠이 지나간다. 해제부터 재마감까지를
사유·배너·요약으로 감싸는 것이 이 테스트가 고정하는 계약이다.
"""
import os
import sys

import pytest

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from budget import db as dbm   # noqa: E402


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


def test_unlock_requires_reason(client):
    """사유 없이 여는 길을 막는다 — 나중에 «왜 2023년 숫자가 달라졌지»에 답해야 한다."""
    client.post("/api/lock", json={"year": "2023"})
    r = client.request("DELETE", "/api/lock/2023", json={"reason": "   "})
    assert r.status_code == 400
    assert client.get("/api/lock-state?year=2023").json()["locked"] is True


def test_unlock_records_reason_and_exposes_open_state(client):
    """열려 있다는 사실이 어느 화면에서든 드러나야 한다 — 배너의 근거가 이 필드다."""
    client.post("/api/lock", json={"year": "2023"})
    r = client.request("DELETE", "/api/lock/2023",
                       json={"reason": "2023년 양산지사 그룹 정정"})
    assert r.status_code == 200

    st = client.get("/api/lock-state?year=2023").json()
    assert st["locked"] is False
    assert st["unlocked_at"]
    assert "양산지사" in st["reason"]
    # 상태 응답에도 실려야 배너가 다른 연도를 보는 중에도 뜬다
    assert client.get("/api/status?year=2025").json()["lock_state"]["2023"]["unlocked_at"]


def test_unlocked_year_accepts_changes_again(client):
    """해제의 목적은 고치는 것이다 — 열면 기준정보 저장이 다시 통해야 한다."""
    client.get("/api/config/depts?year=2023")
    client.post("/api/lock", json={"year": "2023"})
    rows = client.get("/api/config/depts?year=2023").json()["rows"]
    assert client.put("/api/config/depts",
                      json={"year": "2023", "rows": rows}).status_code == 423

    client.request("DELETE", "/api/lock/2023", json={"reason": "정정"})
    assert client.put("/api/config/depts",
                      json={"year": "2023", "rows": rows}).status_code == 200


def test_relock_reports_what_changed_while_open(client):
    """재마감은 «열린 동안 무엇이 바뀌었는지»를 보여주고 닫는다."""
    client.get("/api/config/depts?year=2023")
    client.post("/api/lock", json={"year": "2023"})
    client.request("DELETE", "/api/lock/2023", json={"reason": "정정"})

    rows = client.get("/api/config/depts?year=2023").json()["rows"]
    rows[0]["그룹"] = "DH"
    client.put("/api/config/depts", json={"year": "2023", "rows": rows})

    r = client.post("/api/lock", json={"year": "2023"})
    assert r.status_code == 200
    assert r.json()["changes"]["구성"] >= 1
    assert client.get("/api/lock-state?year=2023").json() == {
        "locked": True, "unlocked_at": None, "reason": None, "by": None}


def test_relock_does_not_count_other_years_or_rejections(client):
    """열린 연도의 변경만 센다. 거부된 요청(423)은 «바뀐 것»이 아니다."""
    for y in ("2023", "2025"):
        client.get(f"/api/config/depts?year={y}")
    client.post("/api/lock", json={"year": "2023"})
    client.post("/api/lock", json={"year": "2025"})
    client.request("DELETE", "/api/lock/2023", json={"reason": "정정"})

    rows2025 = client.get("/api/config/depts?year=2025").json()["rows"]
    assert client.put("/api/config/depts",
                      json={"year": "2025", "rows": rows2025}).status_code == 423

    assert client.post("/api/lock", json={"year": "2023"}).json()["changes"] == {}


def test_lock_without_prior_unlock_reports_no_changes(client):
    """한 번도 연 적 없는 연도를 마감하는 평소 경로는 그대로다."""
    r = client.post("/api/lock", json={"year": "2024"})
    assert r.status_code == 200 and r.json()["changes"] == {}
