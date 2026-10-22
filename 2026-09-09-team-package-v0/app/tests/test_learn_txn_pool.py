# -*- coding: utf-8 -*-
"""종합 검토(2026-10-22) 2단계 — 학습 확신도 기준 · 실행 저장 원자성 · 재배정 일괄 저장 · PG 연결 재사용."""
import os
import sys
import types

import pandas as pd
import pytest

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from budget import db as dbm, dbcore, pipeline_db   # noqa: E402


# ── 학습: 확신도 낮은 자동 귀속은 배우지 않는다 ─────────────────────────────

def _learn_with(monkeypatch, conn, detail, overrides=()):
    monkeypatch.setattr(dbm, "latest_run", lambda c, y, b: {"id": 1} if b == "손익" else None)
    monkeypatch.setattr(dbm, "load_match_detail", lambda c, rid: pd.DataFrame(detail))
    monkeypatch.setattr(dbm, "list_overrides",
                        lambda c, y, b: [{"erp_row_id": i} for i in overrides])
    return dbm.learn_from_year(conn, "2025")


def test_low_confidence_auto_match_not_learned(tmp_path, monkeypatch):
    conn = dbm.connect(str(tmp_path / "l.db"))
    detail = [
        {"구분": "계획집행", "전표텍스트": "강남 HRSG TUBE 교체", "과목정규": "수선유지비",
         "매칭사업명": "RO 베셀 교체", "매칭확신도": 0.41, "erp_row_id": 1},
        {"구분": "계획집행", "전표텍스트": "화성 GT 점검", "과목정규": "수선유지비",
         "매칭사업명": "화성 GT 정기점검", "매칭확신도": 0.93, "erp_row_id": 2},
        # 사람이 고친 전표는 확신도와 무관하게 배운다
        {"구분": "계획집행", "전표텍스트": "동탄 배관 보수", "과목정규": "수선유지비",
         "매칭사업명": "동탄 배관 정비", "매칭확신도": 0.30, "erp_row_id": 3},
    ]
    counts = _learn_with(monkeypatch, conn, detail, overrides=[3])
    assert counts["저확신제외"] == 1
    assert counts["자동확정"] == 1 and counts["수동확정"] == 1
    got = dict(conn.execute("SELECT 텍스트정규, source FROM learned_match").fetchall())
    assert dbm.norm_text("강남 HRSG TUBE 교체") not in got
    assert got[dbm.norm_text("동탄 배관 보수")] == "수동확정"
    conn.close()


def test_threshold_matches_detail_screen_rule():
    """상세 화면 범례 «0.80↑ 자동확정»과 같은 기준이어야 화면·학습 설명이 어긋나지 않는다."""
    assert dbm.LEARN_MIN_CONF == 0.80


# ── 실행 저장: run·match_line·biz_line 한 트랜잭션 ──────────────────────────

def test_run_save_rolls_back_when_biz_lines_fail(tmp_path, monkeypatch):
    """biz_line 저장이 실패하면 run·match_line 도 남지 않아야 한다(«사업 행 없는 최신 실행» 방지)."""
    conn = dbm.connect(str(tmp_path / "r.db"))
    fake_res = {"요약": {}, "erp_annotated": pd.DataFrame(), "plan_rows": [], "new_rows": []}

    def boom(*a, **k):
        raise RuntimeError("biz_line 저장 실패")

    monkeypatch.setattr(dbm, "load_plan_df", lambda c, y: pd.DataFrame({"x": [1]}))
    monkeypatch.setattr(dbm, "load_erp_df", lambda c, y: pd.DataFrame({"x": [1]}))
    monkeypatch.setattr(pipeline_db.pipeline_actual, "run_actual_frames", lambda *a, **k: fake_res)
    monkeypatch.setattr(dbm, "save_biz_lines", boom)
    with pytest.raises(RuntimeError):
        pipeline_db.run_actual_db(conn, str(tmp_path), "2025", "손익", make_files=False)
    assert conn.execute("SELECT COUNT(*) FROM run").fetchone()[0] == 0
    conn.close()


def test_save_run_commit_flag_defers_commit(tmp_path):
    path = str(tmp_path / "c.db")
    conn = dbm.connect(path)
    dbm.save_run(conn, "2025", "손익", {}, pd.DataFrame(), commit=False)
    other = dbm.connect(path)
    assert other.execute("SELECT COUNT(*) FROM run").fetchone()[0] == 0   # 아직 안 보인다
    conn.commit()
    assert other.execute("SELECT COUNT(*) FROM run").fetchone()[0] == 1
    other.close(); conn.close()


def test_add_overrides_inserts_all_at_once(tmp_path):
    conn = dbm.connect(str(tmp_path / "o.db"))
    dbm.add_overrides(conn, "2025", "손익", [11, 12, 13], "화성 정기점검", memo="일괄")
    rows = dbm.list_overrides(conn, "2025", "손익")
    assert [int(r["erp_row_id"]) for r in rows] == [11, 12, 13]
    assert len({r["created_at"] for r in rows}) == 1
    conn.close()


# ── PG 연결 재사용 ────────────────────────────────────────────────────────

class _FakeRaw:
    made = 0

    def __init__(self):
        _FakeRaw.made += 1
        self.closed = False
        self.read_only = False
        self.rollbacks = 0
        self.pings = 0

    def execute(self, sql, *a):
        if sql == "SELECT 1":
            self.pings += 1
        return types.SimpleNamespace(fetchone=lambda: (1,))

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed = True


@pytest.fixture()
def fake_pg(monkeypatch):
    _FakeRaw.made = 0
    mod = types.SimpleNamespace(connect=lambda url, **k: _FakeRaw())
    monkeypatch.setitem(sys.modules, "psycopg", mod)
    monkeypatch.setenv("PG_POOL_SIZE", "2")
    dbcore.pool_clear()
    yield "postgresql://u:p@h/db"
    dbcore.pool_clear()


def test_pool_reuses_connection_after_close(fake_pg):
    c1 = dbcore.connect(url=fake_pg)
    raw = c1._raw
    c1.close()
    assert raw.rollbacks == 1 and not raw.closed        # 정리하고 돌려받음
    c2 = dbcore.connect(url=fake_pg)
    assert c2._raw is raw and _FakeRaw.made == 1
    c2.close()
    c2.close()                                           # 두 번 닫아도 풀에 한 번만
    assert len(dbcore._POOL) == 1


def test_pool_size_cap_and_disable(fake_pg, monkeypatch):
    conns = [dbcore.connect(url=fake_pg) for _ in range(3)]
    raws = [c._raw for c in conns]
    for c in conns:
        c.close()
    assert len(dbcore._POOL) == 2 and raws[2].closed     # 넘치는 연결은 닫는다
    dbcore.pool_clear()
    monkeypatch.setenv("PG_POOL_SIZE", "0")
    c = dbcore.connect(url=fake_pg)
    raw = c._raw
    c.close()
    assert raw.closed and not dbcore._POOL


def test_pool_drops_read_only_and_dead_connections(fake_pg, monkeypatch):
    c = dbcore.connect(url=fake_pg)
    c._raw.read_only = True                              # prune_history 미리보기
    raw = c._raw
    c.close()
    assert raw.closed and not dbcore._POOL
    c = dbcore.connect(url=fake_pg)
    raw = c._raw
    c.close()
    raw.closed = True                                    # 서버가 끊음
    c = dbcore.connect(url=fake_pg)
    assert c._raw is not raw
    c.close()


def test_pool_pings_idle_connection(fake_pg, monkeypatch):
    c = dbcore.connect(url=fake_pg)
    raw = c._raw
    c.close()
    url, r, _t = dbcore._POOL[0]
    dbcore._POOL[0] = (url, r, 0.0)                      # 오래 놀았던 것으로
    c = dbcore.connect(url=fake_pg)
    assert c._raw is raw and raw.pings == 1
    c.close()
