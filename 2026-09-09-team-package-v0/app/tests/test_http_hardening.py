# -*- coding: utf-8 -*-
"""Caddy 가 내던 HTTP 속성을 앱이 직접 낸다 (Phase 6-8).

6-8 에서 Caddy 가 사라진다. Caddy 는 프록시만 한 게 아니라 응답에 세 가지를 얹고
있었다 — 보안 헤더 3종 · gzip · /assets 영구 캐시. 프록시가 사라지면 이것들도 같이
사라지는데 **화면은 멀쩡히 뜬다**. 그래서 눈으로는 못 잡는다.

옛 Caddyfile 이 하던 선언(삭제 전 원문):
    header {
        X-Content-Type-Options nosniff
        X-Frame-Options SAMEORIGIN
        Referrer-Policy strict-origin-when-cross-origin
    }
    encode gzip
    handle /assets/* { header Cache-Control "public, max-age=31536000, immutable" }

여기서 고정해 두면 다음 사람이 미들웨어를 지웠을 때 테스트가 먼저 말해 준다.
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


@pytest.fixture()
def asset_url():
    """`/assets/` 는 Vite 빌드 산출물이라 저장소에 없다 — 검사용 파일을 잠깐 놓는다.

    gzip 임계값(1KB)을 넘기려고 넉넉히 채운다. 마운트가 `check_dir=False` 라
    server 를 언제 import 했든 이 파일이 바로 보인다.
    """
    d = os.path.join(APP_DIR, "static", "assets")
    os.makedirs(d, exist_ok=True)
    name = "_hardening_probe.css"
    path = os.path.join(d, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write("/* %s */\n" % ("x" * 4000))
    try:
        yield "/assets/" + name
    finally:
        os.remove(path)


# ── 보안 헤더 3종 ────────────────────────────────────────────────────────

def test_security_headers_are_on_every_response(client):
    """Caddy 의 `header {}` 블록은 전 경로에 걸려 있었다 — 앱도 그래야 한다."""
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.headers.get("x-content-type-options") == "nosniff"
    assert r.headers.get("x-frame-options") == "SAMEORIGIN"
    assert r.headers.get("referrer-policy") == "strict-origin-when-cross-origin"


def test_security_headers_are_on_error_responses_too(client):
    """오류 응답이 헤더 없이 나가면 그 경로만 무방비가 된다."""
    r = client.get("/api/definitely-not-a-route")
    assert r.status_code == 404
    assert r.headers.get("x-content-type-options") == "nosniff"


# ── /assets 영구 캐시 ────────────────────────────────────────────────────

def test_hashed_assets_are_cached_forever(client, asset_url):
    """파일명에 해시가 붙으므로 영구 캐시가 안전하다 — 이게 없으면 매 방문이 재다운로드다."""
    r = client.get(asset_url)
    assert r.status_code == 200
    assert r.headers.get("cache-control") == "public, max-age=31536000, immutable"


def test_index_html_is_still_no_cache(client):
    """가장 비싼 회귀 — index.html 이 캐시에 묶이면 프론트 수정이 사용자에게 영원히 안 닿는다.

    /assets 캐시 규칙을 넓게 잡다가 index.html 까지 삼키는 일이 실제로 일어날 수 있다.
    (실측 사고 2026-09-15: Cache-Control 부재 → 브라우저가 자체 판단으로 캐시,
     서버 번들은 새것인데 화면은 옛 동작.)
    """
    r = client.get("/")
    assert r.status_code == 200
    assert "no-cache" in r.headers.get("cache-control", "")
    assert "immutable" not in r.headers.get("cache-control", "")


# ── gzip ─────────────────────────────────────────────────────────────────

def test_large_responses_are_gzipped(client, asset_url):
    """Caddy 의 `encode gzip` 자리. 번들·JSON 응답 크기가 몇 배로 늘어나는 것을 막는다."""
    r = client.get(asset_url, headers={"Accept-Encoding": "gzip"})
    assert r.status_code == 200
    assert r.headers.get("content-encoding") == "gzip"


def test_small_responses_are_not_gzipped(client):
    """작은 응답까지 압축하면 CPU 만 쓰고 오히려 커진다 — 임계값이 살아 있는지."""
    r = client.get("/healthz", headers={"Accept-Encoding": "gzip"})
    assert r.headers.get("content-encoding") != "gzip"
