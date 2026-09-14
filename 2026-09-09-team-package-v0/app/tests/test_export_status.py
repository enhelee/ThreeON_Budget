# -*- coding: utf-8 -*-
"""메인 대시보드(Phase 3)가 서버에서 끌어오는 두 값.

1) GET /api/export-status — '이음새' 박스의 마지막 내보내기 연도·시각
2) GET /healthz 의 rev — 헤더 스트립에 찍히는 리비전 문자열

/api/export-team 은 GET 이라 audit_log 에 남지 않으므로, 내보낸 시각의 근거는
OUT_DIR 에 실제로 떨어진 파일의 수정시각이다. 이 테스트는 그 규칙을 고정한다.
"""
import io
import os
import sys
import time

import pytest

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from budget import db as dbm, pipeline_db   # noqa: E402


@pytest.fixture()
def client(tmp_path, monkeypatch):
    # 인증을 끈 사내망 모드로 띄운다 — 이 라우트의 관심사는 인증이 아니라 파일 시각이다.
    monkeypatch.setenv("APP_PASSWORD", "")
    monkeypatch.setenv("DATABASE_URL", "")       # 빈 문자열 = SQLite (개발자 실 DB 로 붙지 않게)
    monkeypatch.setattr(dbm, "DEFAULT_DB", str(tmp_path / "t.db"))
    import server
    from budget import auth as authm
    monkeypatch.setattr(server, "AUTH", authm.AuthConfig())
    out = tmp_path / "output"
    out.mkdir()
    monkeypatch.setattr(server, "OUT_DIR", str(out))
    from fastapi.testclient import TestClient
    return TestClient(server.app), out


def _bundle(out_dir, year, kind="json"):
    name = pipeline_db.TEAM_BUNDLE_FILES[kind].format(y=year)
    path = os.path.join(str(out_dir), name)
    io.open(path, "w", encoding="utf-8").write("{}")
    return path


def test_no_export_yet(client):
    c, _ = client
    r = c.get("/api/export-status").json()
    assert r["last"] is None and r["exports"] == []


def test_last_export_is_the_newest_year_bundle(client):
    c, out = client
    _bundle(out, "2023")
    time.sleep(1.1)                      # 수정시각이 초 단위 문자열이라 1초 이상 벌린다
    _bundle(out, "2025")
    r = c.get("/api/export-status").json()
    assert r["last"]["year"] == "2025"
    assert len(r["last"]["at"]) == 19    # "YYYY-MM-DD HH:MM:SS"
    assert [h["year"] for h in r["exports"]] == ["2023", "2025"]


def test_year_param_reports_each_bundle_file(client):
    c, out = client
    _bundle(out, "2025", "json")
    r = c.get("/api/export-status?year=2025").json()
    assert r["year"] == "2025"
    assert r["files"]["json"] is not None
    assert r["files"]["matched"] is None      # 아직 만들지 않은 산출물은 None


def test_unrelated_files_are_ignored(client):
    c, out = client
    io.open(os.path.join(str(out), "팀연계_삭제본_사업실적연결.json"), "w", encoding="utf-8").write("{}")
    r = c.get("/api/export-status").json()
    assert r["last"] is None               # 연도 4자리가 아니면 집계하지 않는다


def test_healthz_reports_revision(client, monkeypatch):
    """헤더 스트립의 rev 는 APP_REV 환경변수를 그대로 보여준다(미설정이면 dev)."""
    c, _ = client
    import server
    assert c.get("/healthz").json()["rev"] == server.APP_REV
    monkeypatch.setattr(server, "APP_REV", "rev15")
    assert c.get("/healthz").json()["rev"] == "rev15"
