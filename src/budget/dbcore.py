# -*- coding: utf-8 -*-
"""DB 백엔드 전환 계층 — SQLite(기본) ↔ PostgreSQL(`DATABASE_URL`).

db.py는 sqlite3 DB-API 문법(`?` 자리표시자, AUTOINCREMENT, INSERT OR REPLACE, PRAGMA,
lastrowid)으로 쓰여 있다. PostgreSQL(Supabase·사내 서버)로 갈 때 db.py를 고치지 않고
이 계층이 SQL을 번역한다.

  DATABASE_URL 미설정          → sqlite3 연결 그대로 반환(기존 동작 100% 유지)
  DATABASE_URL=postgresql://… → psycopg 연결을 감싼 PgConnection 반환

번역 규칙(translate):
  ?                                   → %s
  INTEGER PRIMARY KEY AUTOINCREMENT   → BIGSERIAL PRIMARY KEY
  BLOB                                → BYTEA
  INSERT OR REPLACE INTO t VALUES(…)  → INSERT … ON CONFLICT (pk) DO UPDATE SET … (REPLACE_TABLES)
  INSERT OR IGNORE INTO …             → INSERT … ON CONFLICT DO NOTHING
  PRAGMA table_info(t)                → information_schema.columns 조회(r[1]=컬럼명 유지)
  PRAGMA journal_mode=WAL             → 무시
  INSERT INTO <id 테이블> (execute만)  → … RETURNING id → cursor.lastrowid 채움
파라미터의 numpy 스칼라/NaN은 Python 값/None으로 바꿔 넘긴다(psycopg는 numpy를 못 받는다).

⚠️ PostgreSQL 경로는 로컬에 PG 서버가 없어 단위 테스트(번역 규칙)만 검증됐다.
   Supabase 최초 접속 시 `py scripts/db_check.py`로 스키마 생성·조회를 확인할 것.
"""
import os
import re
import sqlite3

# INSERT OR REPLACE 대상 테이블: (PK 컬럼들, 전체 컬럼 순서) — db.py의 VALUES(?,…) 순서와 동일
REPLACE_TABLES = {
    "item_master": (("계정코드",), ("계정코드", "과목명", "주관부서코드", "주관부서명", "속성", "비고")),
    "dept_master": (("부서코드",), ("부서코드", "부서명", "처지사", "비고")),
    "year_lock": (("year",), ("year", "locked_at")),
    "learned_match": (("과목", "텍스트정규"), ("과목", "텍스트정규", "사업명", "source", "source_year", "created_at")),
}
# id BIGSERIAL을 가진 테이블 — 단건 INSERT 뒤 lastrowid가 필요하므로 RETURNING id를 붙인다
ID_TABLES = {
    "dataset", "plan_row", "erp_row", "override", "run", "manual_biz", "biz_delete", "biz_edit",
    "audit_log", "model_registry", "training_example", "training_snapshot",
}

_RE_AUTOINC = re.compile(r"INTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT", re.I)
_RE_REPLACE = re.compile(r"^\s*INSERT\s+OR\s+REPLACE\s+INTO\s+(\w+)\s*(.*)$", re.I | re.S)
_RE_IGNORE = re.compile(r"^\s*INSERT\s+OR\s+IGNORE\s+INTO\s+", re.I)
_RE_PRAGMA_INFO = re.compile(r"^\s*PRAGMA\s+table_info\((\w+)\)\s*$", re.I)
_RE_PRAGMA = re.compile(r"^\s*PRAGMA\b", re.I)
_RE_INSERT_TABLE = re.compile(r"^\s*INSERT\s+INTO\s+(\w+)", re.I)
_RE_BLOB = re.compile(r"\bBLOB\b")


def database_url():
    return (os.environ.get("DATABASE_URL") or "").strip()


def is_postgres_url(url):
    return bool(url) and url.lower().startswith(("postgres://", "postgresql://"))


def translate(sql, single=True):
    """sqlite SQL → PostgreSQL SQL. 반환 (sql, wants_lastrowid)."""
    m = _RE_PRAGMA_INFO.match(sql)
    if m:
        table = m.group(1).lower()
        return (
            "SELECT ordinal_position-1, column_name, data_type,"
            " CASE WHEN is_nullable='NO' THEN 1 ELSE 0 END, column_default, 0"
            " FROM information_schema.columns"
            f" WHERE table_schema=current_schema() AND table_name='{table}'"
            " ORDER BY ordinal_position", False)
    if _RE_PRAGMA.match(sql):
        return "SELECT 1", False

    out = _RE_AUTOINC.sub("BIGSERIAL PRIMARY KEY", sql)
    out = _RE_BLOB.sub("BYTEA", out)
    m = _RE_REPLACE.match(out)
    if m:
        table, rest = m.group(1), m.group(2)
        if table not in REPLACE_TABLES:
            raise ValueError(f"INSERT OR REPLACE 번역 규칙 없음: {table} (dbcore.REPLACE_TABLES에 추가)")
        pks, cols = REPLACE_TABLES[table]
        sets = ", ".join(f"{c}=EXCLUDED.{c}" for c in cols if c not in pks)
        out = (f"INSERT INTO {table} {rest.rstrip().rstrip(';')}"
               f" ON CONFLICT ({', '.join(pks)}) DO UPDATE SET {sets}")
    elif _RE_IGNORE.match(out):
        out = _RE_IGNORE.sub("INSERT INTO ", out).rstrip().rstrip(";") + " ON CONFLICT DO NOTHING"

    out = out.replace("?", "%s")
    wants_id = False
    m = _RE_INSERT_TABLE.match(out)
    if single and m and m.group(1).lower() in ID_TABLES and "RETURNING" not in out.upper():
        out = out.rstrip().rstrip(";") + " RETURNING id"
        wants_id = True
    return out, wants_id


def _py(v):
    """numpy 스칼라 → Python, NaN → None (psycopg 어댑터 호환)."""
    if v is None:
        return None
    item = getattr(v, "item", None)
    if item is not None and type(v).__module__ == "numpy":
        v = item()
    if isinstance(v, float) and v != v:
        return None
    return v


def _params(params):
    if params is None:
        return None
    if isinstance(params, dict):
        return {k: _py(v) for k, v in params.items()}
    return tuple(_py(v) for v in params)


class PgCursor:
    def __init__(self, raw):
        self._c = raw
        self.lastrowid = None

    def execute(self, sql, params=None):
        sql2, wants_id = translate(sql, single=True)
        self._c.execute(sql2, _params(params) if params else None)
        if wants_id:
            row = self._c.fetchone()
            self.lastrowid = row[0] if row else None
        return self

    def executemany(self, sql, seq):
        sql2, _ = translate(sql, single=False)
        self._c.executemany(sql2, [_params(p) for p in seq])
        return self

    def fetchone(self):
        return self._c.fetchone()

    def fetchall(self):
        return self._c.fetchall()

    def fetchmany(self, n=None):
        return self._c.fetchmany(n) if n else self._c.fetchmany()

    @property
    def rowcount(self):
        return self._c.rowcount

    @property
    def description(self):
        return self._c.description

    def close(self):
        self._c.close()

    def __iter__(self):
        return iter(self._c)


class PgConnection:
    """psycopg 연결 래퍼 — sqlite3.Connection과 같은 호출 방식 제공."""

    backend = "postgresql"

    def __init__(self, raw):
        self._raw = raw

    def cursor(self):
        return PgCursor(self._raw.cursor())

    def execute(self, sql, params=None):
        return self.cursor().execute(sql, params)

    def executemany(self, sql, seq):
        return self.cursor().executemany(sql, seq)

    def commit(self):
        self._raw.commit()

    def rollback(self):
        self._raw.rollback()

    def close(self):
        self._raw.close()


def connect(db_path=None, url=None):
    """DATABASE_URL이 PostgreSQL이면 PgConnection, 아니면 sqlite3 연결.

    db_path가 명시되면(테스트·스크립트) 항상 SQLite. url 인자는 명시 오버라이드.
    """
    url = url if url is not None else (None if db_path else database_url())
    if is_postgres_url(url):
        try:
            import psycopg
        except ImportError as exc:      # pragma: no cover
            raise RuntimeError("PostgreSQL 사용에는 `pip install psycopg[binary]`가 필요합니다.") from exc
        return PgConnection(psycopg.connect(url))
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def backend_name(conn):
    return getattr(conn, "backend", "sqlite")


def as_bytes(v):
    """BLOB/BYTEA 읽기 결과 → bytes (psycopg는 memoryview를 줄 수 있다)."""
    if v is None:
        return None
    return bytes(v) if not isinstance(v, bytes) else v
