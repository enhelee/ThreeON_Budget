# -*- coding: utf-8 -*-
"""dbcore — SQLite → PostgreSQL SQL 번역 규칙 (PG 서버 없이 검증 가능한 부분)."""
import numpy as np
import pytest

from budget import dbcore


def test_placeholders_and_autoincrement():
    sql, wants = dbcore.translate(
        "CREATE TABLE IF NOT EXISTS t(id INTEGER PRIMARY KEY AUTOINCREMENT, x TEXT, b BLOB, amt REAL)")
    assert "BIGSERIAL PRIMARY KEY" in sql and "AUTOINCREMENT" not in sql
    assert "BYTEA" in sql and " BLOB" not in sql
    # PG REAL(float4)은 8자리 원 금액을 깨뜨린다 → DOUBLE PRECISION (실서버 검증에서 발견)
    assert "amt DOUBLE PRECISION" in sql and " REAL" not in sql
    assert wants is False
    sql, _ = dbcore.translate("SELECT id FROM dataset WHERE kind=? AND year=?")
    assert sql == "SELECT id FROM dataset WHERE kind=%s AND year=%s"


def test_insert_returning_id_only_for_id_tables_and_single():
    sql, wants = dbcore.translate("INSERT INTO run(year,budget,created_at,summary_json) VALUES(?,?,?,?)")
    assert sql.endswith("RETURNING id") and wants is True
    sql, wants = dbcore.translate("INSERT INTO match_line VALUES(?,?,?,?,?,?,?,?)")
    assert "RETURNING" not in sql and wants is False            # id 없는 테이블
    sql, wants = dbcore.translate("INSERT INTO run(year) VALUES(?)", single=False)
    assert "RETURNING" not in sql and wants is False            # executemany 경로


def test_insert_or_replace_becomes_on_conflict():
    sql, _ = dbcore.translate("INSERT OR REPLACE INTO learned_match VALUES(?,?,?,?,?,?)")
    assert sql.startswith("INSERT INTO learned_match VALUES(%s,%s,%s,%s,%s,%s)")
    assert "ON CONFLICT (과목, 텍스트정규) DO UPDATE SET 사업명=EXCLUDED.사업명" in sql
    assert "source_year=EXCLUDED.source_year" in sql and "과목=EXCLUDED.과목" not in sql
    sql, _ = dbcore.translate("INSERT OR REPLACE INTO year_lock VALUES(?,?)")
    assert "ON CONFLICT (year) DO UPDATE SET locked_at=EXCLUDED.locked_at" in sql
    with pytest.raises(ValueError):
        dbcore.translate("INSERT OR REPLACE INTO unknown_t VALUES(?)")
    sql, _ = dbcore.translate("INSERT OR IGNORE INTO year_lock VALUES(?,?)")
    assert sql.endswith("ON CONFLICT DO NOTHING")


def test_pragma_translation():
    sql, _ = dbcore.translate("PRAGMA table_info(match_line)")
    assert "information_schema.columns" in sql and "table_name='match_line'" in sql
    assert sql.strip().startswith("SELECT ordinal_position-1, column_name")   # r[1] = 컬럼명 유지
    sql, _ = dbcore.translate("PRAGMA journal_mode=WAL")
    assert sql == "SELECT 1"


def test_params_convert_numpy_and_nan():
    out = dbcore._params((np.int64(3), np.float64(2.5), float("nan"), "x", None))
    assert out == (3, 2.5, None, "x", None)
    assert type(out[0]) is int and type(out[1]) is float


def test_sqlite_default_when_no_url(monkeypatch, tmp_path):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    conn = dbcore.connect(db_path=str(tmp_path / "a.db"))
    assert dbcore.backend_name(conn) == "sqlite"
    conn.execute("CREATE TABLE t(x)")
    conn.close()
    assert dbcore.is_postgres_url("postgresql://u:p@h/db") and not dbcore.is_postgres_url("")
