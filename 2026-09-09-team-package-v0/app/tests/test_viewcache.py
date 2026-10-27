# -*- coding: utf-8 -*-
"""계산 결과 캐시(viewcache, 2026-10-27) — 숫자와 무관한 쓰기는 캐시를 비우지 않고, 숫자를 바꾸는 쓰기는 비운다.
같은 계산이 동시에 와도 한 번만 계산한다. 예열은 캐시를 채운다. 화면 공통 API 의 질의 수는 줄어든 그대로.

운영 점검(2026-10-27): 전망 첫 계산 28초가 자주 다시 났다 — 로그인·차이 사유 저장까지 감사 로그에 남아
캐시 버전을 바꿨기 때문. /api/forecast/base-years 질의 41번, /api/nav-state 26번.
"""
import os
import re
import sys
import threading
import time

import pytest

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from budget import db as dbm, viewcache   # noqa: E402
from tests.test_forecast_api import client   # noqa: E402,F401
from tests.test_perf_budget import seeded, _timing   # noqa: E402,F401
from tests.test_db_pipeline import env   # noqa: E402,F401


def test_version_ignores_session_notes_and_rejected_writes(tmp_path):
    conn = dbm.connect(str(tmp_path / "v.db"))
    dbm.add_audit(conn, "a", "PUT", "/api/forecast/state/factors", 200, "")
    base = viewcache.data_version(conn)
    assert base > 0
    for path, status in (("/api/login", 200), ("/api/logout", 200), ("/api/variance-note", 200),
                         ("/api/review-ack", 200), ("/api/override", 423)):
        dbm.add_audit(conn, "a", "POST", path, status, "")
    assert viewcache.data_version(conn) == base                      # 숫자는 그대로
    # 검토 큐는 사유·승인으로 상태가 바뀐다 — 그 버전에는 들어간다(로그인만 뺀다)
    assert viewcache.data_version(conn, ignore=viewcache.SESSION_PATHS) > base
    dbm.add_audit(conn, "a", "POST", "/api/override", 200, "")
    assert viewcache.data_version(conn) > base                       # 재배정은 숫자를 바꾼다
    conn.close()


def test_same_key_computes_once_under_concurrency():
    viewcache.clear()
    calls = []

    def slow():
        calls.append(1)
        time.sleep(0.2)
        return {"v": 1}

    out = []
    ts = [threading.Thread(target=lambda: out.append(viewcache.get_or_compute(("t", "k"), 7, slow)))
          for _ in range(4)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert len(calls) == 1 and out == [{"v": 1}] * 4
    assert viewcache.get_or_compute(("t", "k"), 8, slow) == {"v": 1} and len(calls) == 2   # 버전이 바뀌면 다시


def test_forecast_cache_survives_login_and_notes(client, monkeypatch):
    from budget import pipeline_forecast as pf
    viewcache.clear()
    calls = []
    orig = pf.run_forecast
    monkeypatch.setattr(pf, "run_forecast", lambda c, by: calls.append(by) or orig(c, by))
    client.get("/api/forecast/table?base_year=2026")
    conn = dbm.connect()
    dbm.add_audit(conn, "홍길동", "POST", "/api/login", 200, "로그인")
    dbm.add_audit(conn, "홍길동", "PUT", "/api/variance-note", 200, "")
    conn.close()
    client.get("/api/forecast/table?base_year=2026")
    assert len(calls) == 1                     # 로그인·사유 저장으로는 다시 계산하지 않는다


def test_base_years_and_nav_state_query_counts(seeded):
    client, *_ = seeded
    q, c = _timing(client.get("/api/forecast/base-years"))
    assert c == 1 and q <= 3, f"base-years 질의 {q}회"          # 예전 41회(표마다 DISTINCT ×2)
    q, c = _timing(client.get("/api/nav-state?year=2023"))
    assert c == 1 and q <= 10, f"nav-state 질의 {q}회"           # 예전 26회


def test_learn_pending_counts_unchanged(seeded):
    """학습 대기 계산을 질의 3번으로 묶었다 — 값은 예전과 같아야 한다(재배정 2건, 학습 전)."""
    client, conn, *_ = seeded
    assert dbm.count_learn_pending(conn, "2023") == client.get("/api/pending?year=2023").json()["learn_pending"]
    assert dbm.count_learn_pending(conn, "2023") == 2
    assert dbm.count_learn_pending(conn, "2099") == 0


def test_warm_fills_forecast_and_review_caches(seeded):
    import server
    from budget import api_forecast, pipeline_forecast as pf
    viewcache.clear()
    server._warm_once()
    conn = dbm.connect()
    try:
        by = str(pf.default_base_year(conn))
        ver = viewcache.data_version(conn)
        assert viewcache.cached(("forecast", "table", by), ver) is not None
        assert viewcache.cached(("forecast", "benchmark", by), ver) is not None
        rver = viewcache.data_version(conn, ignore=viewcache.SESSION_PATHS)
        assert viewcache.cached(("review", "2023"), rver) is not None
    finally:
        conn.close()
