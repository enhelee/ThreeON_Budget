# -*- coding: utf-8 -*-
"""이력 정리(scripts/prune_history.py) — 지워도 화면·분석 결과가 한 글자도 바뀌지 않아야 한다.

남기는 것: (연도, 손익|자본)별 최신 실행 · (계획|ERP, 연도)별 최신 데이터셋. 화면이 읽는 것은
이 둘뿐이다. 재배정이 지울 ERP 행을 가리키면 아무것도 지우지 않는다.
"""
import os
import sys

import pytest

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (APP_DIR, os.path.join(APP_DIR, "scripts")):
    if p not in sys.path:
        sys.path.insert(0, p)

import prune_history as ph   # noqa: E402
from budget import db as dbm, pipeline_db   # noqa: E402
from tests.test_db_pipeline import env   # noqa: E402,F401


@pytest.fixture()
def grown(env, tmp_path, monkeypatch):
    """같은 자료를 두 번 올리고(대체된 데이터셋) 분석을 세 번(옛 실행 2회분) 돌린 DB."""
    conn, out = env
    plan_ds = dbm.list_datasets(conn)
    plan_path = erp_path = None
    for f in os.listdir(tmp_path):
        if f.endswith(".xlsx") and "계획" in f:
            plan_path = str(tmp_path / f)
        if f.upper().endswith(".XLSX") and "zrfm2" in f:
            erp_path = str(tmp_path / f)
    dbm.ingest_plan(conn, plan_path, "2023")
    dbm.ingest_erp(conn, erp_path, "2023")
    for _ in range(3):
        pipeline_db.run_actual_db(conn, out, "2023", "손익", make_files=False)
    assert len(dbm.list_datasets(conn)) == len(plan_ds) + 2

    monkeypatch.setenv("APP_PASSWORD", "")
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setattr(dbm, "DEFAULT_DB", str(tmp_path / "budget.db"))
    import server
    from budget import auth as authm
    monkeypatch.setattr(server, "AUTH", authm.AuthConfig())
    from fastapi.testclient import TestClient
    return conn, TestClient(server.app), out


SCREENS = ["/api/nav-state?year=2023", "/api/status?year=2023", "/api/branches?year=2023",
           "/api/branch-detail?year=2023&branch=화성지사", "/api/stats?year=2023",
           "/api/overview", "/api/overrides?year=2023"]


def _snap(client):
    out = {}
    for u in SCREENS:
        j = client.get(u).json()
        if u.startswith("/api/status"):
            j.pop("datasets", None)          # 업로드 이력 목록 자체는 줄어드는 게 맞다
        out[u] = j
    return out


def test_prune_removes_only_unused_history_and_screens_stay_identical(grown):
    conn, client, out = grown
    before = _snap(client)
    p = ph.plan(conn)
    assert p["problems"] == []
    assert p["delete"]["run"] == 2 and p["delete"]["dataset"] == 2
    assert p["delete"]["match_line"] > 0 and p["delete"]["erp_row"] > 0

    ph.apply(conn, p)
    after = ph.plan(conn)
    assert sum(after["delete"].values()) == 0                 # 더 지울 것이 없다
    assert _snap(client) == before                            # 화면 결과는 그대로
    pipeline_db.run_actual_db(conn, out, "2023", "손익", make_files=False)   # 다음 분석도 정상


def test_prune_refuses_when_override_points_to_old_erp_row(grown):
    conn, _client, _out = grown
    old_ds = min(d["id"] for d in dbm.list_datasets(conn) if d["kind"] == "erp")
    old_row = conn.execute("SELECT id FROM erp_row WHERE dataset_id=? LIMIT 1", (old_ds,)).fetchone()[0]
    dbm.add_override(conn, "2023", "손익", old_row, "화성 정기점검 보수공사")
    p = ph.plan(conn)
    assert p["problems"]
    with pytest.raises(RuntimeError):
        ph.apply(conn, p)
    assert ph.plan(conn)["delete"]["erp_row"] > 0             # 아무것도 지우지 않았다


def test_backup_must_match_current_counts(grown, tmp_path):
    conn, _, out = grown
    import json
    folder = tmp_path / "bk"
    folder.mkdir()
    counts = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ("run", "erp_row")}
    (folder / "manifest.json").write_text(json.dumps({"tables": {t: {"rows": n} for t, n in counts.items()}}),
                                          encoding="utf-8")
    assert ph.backup_matches(conn, str(folder)) == []
    pipeline_db.run_actual_db(conn, out, "2023", "손익", make_files=False)   # 백업 뒤 변경
    assert ph.backup_matches(conn, str(folder))                # 낡은 백업은 거절
