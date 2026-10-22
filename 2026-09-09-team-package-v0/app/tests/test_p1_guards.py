# -*- coding: utf-8 -*-
"""종합 검토(2026-10-22) P1 빠른 수정 묶음 — 되돌아가지 않게 고정한다.

① id 로 지우는 라우트도 마감 연도면 423  ② 로그인 실패 횟수 제한(429)
③ /openapi.json 비공개  ④ 업로드 크기 상한(413)·xlsx 아닌 파일 400
⑤ 자동 학습이 사람이 확정한 학습을 덮지 않음
"""
import io
import os
import sys
import zipfile

import pandas as pd
import pytest

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from budget import auth as authm   # noqa: E402
from budget import db as dbm       # noqa: E402
from budget import uploads         # noqa: E402

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _client(tmp_path, monkeypatch, password=""):
    monkeypatch.setenv("APP_PASSWORD", password)
    monkeypatch.setenv("SECRET_KEY", "x" * 40)
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setattr(dbm, "DEFAULT_DB", str(tmp_path / "t.db"))
    import server
    monkeypatch.setattr(server, "AUTH", authm.AuthConfig())
    from fastapi.testclient import TestClient
    return TestClient(server.app)


@pytest.fixture()
def client(tmp_path, monkeypatch):
    return _client(tmp_path, monkeypatch)


# ── ① 마감 우회 ──────────────────────────────────────────────────────────

def _seed_rows(year):
    conn = dbm.connect()
    try:
        dbm.add_override(conn, year, "손익", 1, "화성 정기점검")
        dbm.add_biz_edit(conn, year, "손익", "수선유지비", "화성지사", "사업A", {"속성": "x"})
        dbm.add_biz_delete(conn, year, "손익", "수선유지비", "화성지사", "사업B")
        biz = dbm.add_manual_biz(conn, year, "손익", "수선유지비", "화성지사", "사업C")
        ids = {t: conn.execute(f"SELECT MAX(id) FROM {t}").fetchone()[0]
               for t in ("override", "biz_edit", "biz_delete", "manual_biz")}
        return ids, biz
    finally:
        conn.close()


ROUTES = {"override": "/api/override/{}", "biz_edit": "/api/biz-edit/{}",
          "biz_delete": "/api/biz-delete/{}", "manual_biz": "/api/manual-biz/{}"}


def test_delete_by_id_blocked_on_locked_year(client):
    """마감 연도의 지시를 «지우는» 것으로 결과를 바꿀 수 없어야 한다."""
    ids, _ = _seed_rows("2023")
    assert client.post("/api/lock", json={"year": "2023"}).status_code == 200
    for table, url in ROUTES.items():
        r = client.delete(url.format(ids[table]))
        assert r.status_code == 423, (table, r.text)
    conn = dbm.connect()
    try:
        for table, rid in ids.items():
            assert conn.execute(f"SELECT 1 FROM {table} WHERE id=?", (rid,)).fetchone(), table
    finally:
        conn.close()


def test_delete_by_id_allowed_on_open_year(client):
    ids, _ = _seed_rows("2025")
    for table, url in ROUTES.items():
        assert client.delete(url.format(ids[table])).status_code == 200, table
    # 없는 id 는 예전처럼 조용히 통과(멱등)
    assert client.delete("/api/override/999999").status_code == 200


# ── ② 로그인 레이트리밋 ───────────────────────────────────────────────────

def test_login_rate_limited_after_repeated_failures(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch, password="team-secret")
    hdr = {"X-Forwarded-For": "1.2.3.4"}
    for _ in range(5):
        assert c.post("/api/login", json={"password": "wrong", "name": "QA"},
                      headers=hdr).status_code == 401
    r = c.post("/api/login", json={"password": "team-secret", "name": "QA"}, headers=hdr)
    assert r.status_code == 429                  # 차단 중엔 맞는 비밀번호도 확인하지 않는다
    assert int(r.headers["Retry-After"]) > 0
    # 다른 접속지는 영향 없음
    assert c.post("/api/login", json={"password": "team-secret", "name": "QA"},
                  headers={"X-Forwarded-For": "5.6.7.8"}).status_code == 200


def test_rate_limit_key_ignores_spoofed_left_hops(tmp_path, monkeypatch):
    """X-Forwarded-For 왼쪽은 클라이언트가 바꿀 수 있다 — 바꿔도 같은 키여야 한다."""
    c = _client(tmp_path, monkeypatch, password="team-secret")
    for i in range(5):
        c.post("/api/login", json={"password": "wrong", "name": "QA"},
               headers={"X-Forwarded-For": f"10.0.0.{i}, 9.9.9.9"})
    r = c.post("/api/login", json={"password": "wrong", "name": "QA"},
               headers={"X-Forwarded-For": "10.0.0.99, 9.9.9.9"})
    assert r.status_code == 429


def test_limiter_window_and_success_reset():
    lim = authm.LoginLimiter(max_fails=2, window=60, global_max=100)
    lim.fail("a", now=0); lim.fail("a", now=10)
    assert lim.retry_after("a", now=20) == 41
    assert lim.retry_after("a", now=61) == 0      # 첫 실패가 창을 벗어남
    lim.fail("b", now=0)
    lim.success("b")
    lim.fail("b", now=1)
    assert lim.retry_after("b", now=2) == 0
    g = authm.LoginLimiter(max_fails=100, window=60, global_max=3)
    for i in range(3):
        g.fail(f"ip{i}", now=i)
    assert g.retry_after("new", now=5) > 0        # 전체 상한은 처음 보는 접속지도 막는다


# ── ③ openapi ────────────────────────────────────────────────────────────

def test_openapi_schema_not_public(client):
    assert client.get("/openapi.json").status_code == 404


# ── ④ 업로드 상한 ─────────────────────────────────────────────────────────

def test_upload_too_large_is_413(client, monkeypatch):
    monkeypatch.setattr(uploads, "MAX_UPLOAD_BYTES", 1000)
    r = client.post("/api/upload/erp?year=2025",
                    files={"file": ("big.xlsx", b"x" * 5000, XLSX)})
    assert r.status_code == 413, r.text


def test_upload_not_xlsx_is_400(client):
    r = client.post("/api/upload/plan?year=2025",
                    files=[("file", ("a.xlsx", b"not a zip", XLSX))])
    assert r.status_code == 400 and "xlsx" in r.json()["detail"]


def test_upload_zip_bomb_is_413(client, monkeypatch):
    monkeypatch.setattr(uploads, "MAX_XLSX_UNZIPPED", 10_000)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("xl/big.xml", "0" * 100_000)
    r = client.post("/api/upload/erp?year=2025",
                    files={"file": ("bomb.xlsx", buf.getvalue(), XLSX)})
    assert r.status_code == 413, r.text


def test_upload_on_locked_year_keeps_423(client):
    """예전엔 except Exception 이 423 을 400 «흡수 실패»로 뭉갰다."""
    client.post("/api/lock", json={"year": "2023"})
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("x.xml", "<a/>")
    r = client.post("/api/upload/erp?year=2023",
                    files={"file": ("z.xlsx", buf.getvalue(), XLSX)})
    assert r.status_code == 423, r.text


# ── ⑤ 학습: 사람 확정 보호 ───────────────────────────────────────────────

def test_auto_learning_does_not_overwrite_manual(tmp_path, monkeypatch):
    conn = dbm.connect(str(tmp_path / "l.db"))
    key = dbm.norm_text("강남 HRSG TUBE 교체")
    conn.execute("INSERT INTO learned_match VALUES(?,?,?,?,?,?)",
                 ("수선유지비", key, "강남 HRSG 정비", "수동확정", "2024", "2024-12-31 00:00:00"))
    conn.commit()
    detail = pd.DataFrame([
        {"구분": "계획집행", "전표텍스트": "강남 HRSG TUBE 교체", "과목정규": "수선유지비",
         "매칭사업명": "RO 베셀 교체", "매칭확신도": 0.95, "erp_row_id": 1},
        {"구분": "계획집행", "전표텍스트": "화성 GT 점검", "과목정규": "수선유지비",
         "매칭사업명": "화성 GT 정기점검", "매칭확신도": 0.95, "erp_row_id": 2},
    ])
    monkeypatch.setattr(dbm, "latest_run", lambda c, y, b: {"id": 1} if b == "손익" else None)
    monkeypatch.setattr(dbm, "load_match_detail", lambda c, rid: detail)
    monkeypatch.setattr(dbm, "list_overrides", lambda c, y, b: [])
    counts = dbm.learn_from_year(conn, "2025")
    assert counts["수동확정보호"] == 1 and counts["자동확정"] == 1
    got = dict(conn.execute("SELECT 텍스트정규, 사업명 FROM learned_match").fetchall())
    assert got[key] == "강남 HRSG 정비"
    assert got[dbm.norm_text("화성 GT 점검")] == "화성 GT 정기점검"
    conn.close()
