# -*- coding: utf-8 -*-
"""메인 대시보드가 서버에서 끌어오는 값과 루트 경로 규칙.

1) GET /healthz 의 rev — 헤더 스트립에 찍히는 리비전 문자열
2) index.html 은 매번 재검증(no-cache) · /app/ 은 301

(예전에 여기 있던 /api/export-status — 팀 연계 파일을 마지막으로 넘긴 시각 — 는 v2 앱과 함께
 Phase 7 에서 사라졌다. 부재는 test_v2_residue_gone.py 가 고정한다.)
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


def test_healthz_reports_revision(client, monkeypatch):
    """헤더 스트립의 rev 는 APP_REV 환경변수를 그대로 보여준다(미설정이면 dev)."""
    c, _ = client
    import server
    assert c.get("/healthz").json()["rev"] == server.APP_REV
    monkeypatch.setattr(server, "APP_REV", "rev15")
    assert c.get("/healthz").json()["rev"] == "rev15"


def test_index_html_is_revalidated_every_time(client, tmp_path, monkeypatch):
    """index.html 이 캐시에 묶이면 프론트 수정이 사용자에게 영영 닿지 않는다.

    자산은 파일명에 해시가 붙어 영구 캐시가 안전하지만, 그 파일명을 가리키는 것이
    index.html 이다. 이 파일만은 매번 확인해야 한다(no-cache = 저장하되 재검증).

    실측(2026-09-15 배포): 서버 번들에는 수정이 들어 있는데 화면은 옛 동작 그대로였다.
    응답에 Cache-Control 이 없어 브라우저가 자체 판단으로 캐시한 결과였다.
    """
    c, _ = client
    import server
    page = os.path.join(server.WEB_DIR, "index.html")
    if not os.path.isfile(page):
        pytest.skip("프론트 빌드 산출물이 없습니다 (npm run build)")
    r = c.get("/")
    assert r.status_code == 200
    assert "no-cache" in r.headers.get("cache-control", "")


def test_old_app_path_returns_301(client):
    """옛 주소 /app · /app/... 는 루트로 301 — 팀원 북마크를 지킨다.

    Caddy 는 이 경로를 접두어 그대로 넘겨 주므로(handle_path 아님), 301 을 내는 것은
    이 파이썬 라우트다. 실측(2026-09-15): Caddy 의 redir 로 처리하려다 «/» 가 매처로
    파싱되어 빈 200 이 나갔다 — 그래서 판단을 테스트 가능한 쪽에 둔다.
    """
    c, _ = client
    for path in ("/app", "/app/", "/app/anything"):
        r = c.get(path, follow_redirects=False)
        assert r.status_code == 301, f"{path} 가 301 이 아닙니다"
        assert r.headers["location"] == "/"
