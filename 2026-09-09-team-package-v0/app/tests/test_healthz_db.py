# -*- coding: utf-8 -*-
"""/healthz?db=1 — Supabase 무료 프로젝트 일시정지 방지용 «DB 한 번 읽기».

기본 /healthz 는 DB 를 안 건드린다(배포 확인용, 빠르게). 주기 호출(keepalive 워크플로)이
DB 활동을 남기려면 ?db=1 이 실제로 쿼리를 보내야 하고, 실패하면 503 이어야 워크플로가 빨개진다.
로그인 없이 열리는 주소라 실패 사유(연결 문자열·호스트)는 응답에 실리면 안 된다.
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
    monkeypatch.setenv("DATABASE_URL", "")       # 빈 문자열 = SQLite (실 DB 로 붙지 않게)
    monkeypatch.setattr(dbm, "DEFAULT_DB", str(tmp_path / "t.db"))
    import server
    from budget import auth as authm
    monkeypatch.setattr(server, "AUTH", authm.AuthConfig())
    from fastapi.testclient import TestClient
    return TestClient(server.app)


def test_plain_healthz_does_not_touch_db(client, monkeypatch):
    import server

    def boom():
        raise AssertionError("기본 /healthz 가 DB 에 붙었다")
    monkeypatch.setattr(server, "_conn", boom)
    r = client.get("/healthz")
    assert r.status_code == 200 and "db_ok" not in r.json()


def test_db_flag_runs_a_query(client, monkeypatch):
    import server
    seen = []
    real = server._conn

    def spy():
        conn = real()
        orig = conn.execute

        class Wrap:
            def execute(self, sql, *a):
                seen.append(sql)
                return orig(sql, *a)

            def close(self):
                conn.close()
        return Wrap()
    monkeypatch.setattr(server, "_conn", spy)
    r = client.get("/healthz?db=1")
    assert r.status_code == 200
    assert r.json()["ok"] is True and r.json()["db_ok"] is True
    assert seen == ["SELECT 1"]


def test_db_failure_is_503_without_details(client, monkeypatch):
    import server

    def down():
        raise RuntimeError("postgresql://user:secret@db.example.supabase.co:5432/postgres 연결 실패")
    monkeypatch.setattr(server, "_conn", down)
    r = client.get("/healthz?db=1")
    assert r.status_code == 503
    assert r.json()["ok"] is False and r.json()["db_ok"] is False
    assert "secret" not in r.text and "supabase" not in r.text


def test_db_flag_is_public(tmp_path, monkeypatch):
    """인증이 켜져 있어도 열린다 — 워크플로는 로그인하지 않는다."""
    monkeypatch.setenv("APP_PASSWORD", "pw")
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setattr(dbm, "DEFAULT_DB", str(tmp_path / "t.db"))
    import server
    from budget import auth as authm
    monkeypatch.setattr(server, "AUTH", authm.AuthConfig())
    from fastapi.testclient import TestClient
    r = TestClient(server.app).get("/healthz?db=1")
    assert r.status_code == 200 and r.json()["db_ok"] is True
