# -*- coding: utf-8 -*-
"""연도·예산 구분 입력 검증 — 2026-09-20 QA P1 재발 방지.

연도는 모든 화면이 HTML 에 그대로 찍고 OUT_DIR 아래 폴더 이름도 된다. 서버가 아무 문자열이나
받으면 로그인한 누구나 `?year=<img onerror=…>` 한 번으로 전 사용자 화면에 스크립트를 심고,
`/api/lock {"year":"../../x"}` 로 OUT_DIR 밖에 폴더를 만들 수 있었다.
"""
import os
import sys

import pytest

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from budget import db as dbm   # noqa: E402

XSS = '<img src=x onerror="window.__qa=1">'


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


@pytest.mark.parametrize("url", [
    f"/api/status?year={XSS}",
    "/api/pending?year=2025x",
    "/api/branches?year=",
    "/api/forecast/table?base_year=../../x",
    "/api/config/items?year=2025&budget=<b>",
])
def test_bad_query_rejected(client, url):
    r = client.get(url)
    assert r.status_code == 400
    assert "연도" in r.json()["detail"] or "예산 구분" in r.json()["detail"]


def test_upload_with_script_year_is_rejected_and_nothing_stored(client):
    """QA 재현 경로 그대로 — 업로드 연도에 스크립트. 거절되고 DB 에 흔적이 없어야 한다."""
    r = client.post(f"/api/upload/plan?year={XSS}",
                    files={"files": ("p.xlsx", b"not-an-xlsx", "application/octet-stream")})
    assert r.status_code == 400
    years = [y["year"] for y in client.get("/api/overview").json()["years"]]
    assert all(len(y) == 4 and y.isdigit() for y in years)


@pytest.mark.parametrize("body", [{"year": "../../x"}, {"year": XSS}, {"year": 2025.5}])
def test_lock_body_rejected(client, body, tmp_path):
    r = client.post("/api/lock", json=body)
    assert r.status_code == 400
    assert client.get("/api/lock-state").status_code == 200


def test_lock_path_year_rejected(client):
    r = client.request("DELETE", "/api/lock/..%2F..%2Fx", json={"reason": "정정"})
    assert r.status_code in (400, 404)       # 경로 분해 방식과 무관하게 처리되지 않아야 한다
    r = client.request("DELETE", "/api/lock/20x5", json={"reason": "정정"})
    assert r.status_code == 400


def test_bad_budget_in_json_rejected(client):
    r = client.post("/api/override", json={"year": "2025", "budget": "기타", "erp_row_ids": [1],
                                           "target_name": "x"})
    assert r.status_code == 400


def test_valid_values_pass(client):
    assert client.get("/api/status?year=2025").status_code == 200
    assert client.get("/api/config/items?year=2025&budget=손익").status_code == 200
    assert client.get("/api/forecast/table").status_code == 200          # base_year 생략 = 서버 기본값
    assert client.post("/api/lock", json={"year": "2023"}).status_code == 200
