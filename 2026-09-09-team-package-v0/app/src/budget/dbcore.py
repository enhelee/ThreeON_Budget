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
  REAL                                → DOUBLE PRECISION (PG REAL은 float4 → 금액 정밀도 손실, 실측으로 확인)
  INSERT OR REPLACE INTO t VALUES(…)  → INSERT … ON CONFLICT (pk) DO UPDATE SET … (REPLACE_TABLES)
  INSERT OR IGNORE INTO …             → INSERT … ON CONFLICT DO NOTHING
  PRAGMA table_info(t)                → information_schema.columns 조회(r[1]=컬럼명 유지)
  PRAGMA journal_mode=WAL             → 무시
  INSERT INTO <id 테이블> (execute만)  → … RETURNING id → cursor.lastrowid 채움
파라미터의 numpy 스칼라/NaN은 Python 값/None으로 바꿔 넘긴다(psycopg는 numpy를 못 받는다).

⚠️ PostgreSQL 경로는 로컬에 PG 서버가 없어 단위 테스트(번역 규칙)만 검증됐다.
   Supabase 최초 접속 시 `py scripts/db_check.py`로 스키마 생성·조회를 확인할 것.
"""
import contextvars
import os
import re
import sqlite3
import threading
import time

# ── 요청별 DB 사용량(Server-Timing 헤더의 근거) ─────────────────────────────
# 운영 DB(서울)와 앱(싱가포르)이 떨어져 있어 «느린 이유»의 대부분이 연결·질의 왕복이다
# (2026-10-15 실측: 연결 ~0.5s, 질의당 ~75ms). 미들웨어가 요청마다 begin_request_stats() 로
# 빈 집계를 열면, 그 요청 안의 연결·질의가 여기에 더해진다. 집계가 없으면(스크립트·테스트) 무동작.
_REQUEST_STATS = contextvars.ContextVar("db_request_stats", default=None)


def begin_request_stats():
    stats = {"conn": 0, "conn_ms": 0.0, "q": 0, "q_ms": 0.0}
    _REQUEST_STATS.set(stats)
    return stats


def _note(kind, started):
    stats = _REQUEST_STATS.get()
    if stats is not None:
        stats[kind] += 1
        stats[kind + "_ms"] += (time.perf_counter() - started) * 1000


def track_sqlite(conn):
    """SQLite 연결의 질의 수를 요청 집계에 더한다(시간은 못 잰다 — 로컬이라 의미도 작다)."""
    stats = _REQUEST_STATS.get()
    if stats is None or not hasattr(conn, "set_trace_callback"):
        return
    stats["conn"] += 1

    def count(_sql):
        stats["q"] += 1
    conn.set_trace_callback(count)


# INSERT OR REPLACE 대상 테이블: (PK 컬럼들, 전체 컬럼 순서) — db.py의 VALUES(?,…) 순서와 동일
REPLACE_TABLES = {
    "item_master": (("year", "계정코드"),
                    ("year", "계정코드", "과목명", "주관부서코드", "주관부서명", "속성", "비고")),
    "dept_master": (("year", "부서코드"), ("year", "부서코드", "부서명", "처지사", "비고")),
    "year_lock": (("year",), ("year", "locked_at")),
    "learned_match": (("과목", "텍스트정규"), ("과목", "텍스트정규", "사업명", "source", "source_year", "created_at")),
}
# id BIGSERIAL을 가진 테이블 — 단건 INSERT 뒤 lastrowid가 필요하므로 RETURNING id를 붙인다
ID_TABLES = {
    "dataset", "plan_row", "erp_row", "override", "run", "manual_biz", "biz_delete", "biz_edit",
    "audit_log", "model_registry", "training_example", "training_snapshot",
    "hq_temp", "forecast_surprise",          # 전망 상태(6-5) — 자연키 없는 두 표
}

_RE_AUTOINC = re.compile(r"INTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT", re.I)
_RE_REPLACE = re.compile(r"^\s*INSERT\s+OR\s+REPLACE\s+INTO\s+(\w+)\s*(.*)$", re.I | re.S)
_RE_IGNORE = re.compile(r"^\s*INSERT\s+OR\s+IGNORE\s+INTO\s+", re.I)
_RE_PRAGMA_INFO = re.compile(r"^\s*PRAGMA\s+table_info\((\w+)\)\s*$", re.I)
_RE_PRAGMA = re.compile(r"^\s*PRAGMA\b", re.I)
_RE_INSERT_TABLE = re.compile(r"^\s*INSERT\s+INTO\s+(\w+)", re.I)
_RE_BLOB = re.compile(r"\bBLOB\b")
# ⚠ PostgreSQL의 REAL은 4바이트(유효숫자 ~7자리)라 8자리 원 단위 금액이 깨진다(실측: 손익 −50원, 자본 +144원).
#   SQLite의 REAL은 8바이트이므로 DOUBLE PRECISION으로 번역해야 두 백엔드 결과가 같다.
_RE_REAL = re.compile(r"\bREAL\b")


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
    out = _RE_REAL.sub("DOUBLE PRECISION", out)
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
        t = time.perf_counter()
        self._c.execute(sql2, _params(params) if params else None)
        _note("q", t)
        if wants_id:
            row = self._c.fetchone()
            self.lastrowid = row[0] if row else None
        return self

    def executemany(self, sql, seq):
        sql2, _ = translate(sql, single=False)
        t = time.perf_counter()
        self._c.executemany(sql2, [_params(p) for p in seq])
        _note("q", t)
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


# ── PG 연결 재사용(작은 풀) ──────────────────────────────────────────────
# 요청마다 psycopg.connect 하면 운영(Render 싱가포르 ↔ Supabase)에서 연결 한 번이 ~0.42초다
# (Server-Timing conn, 2026-10-22 실측). 화면 하나가 API 3~15개를 부르므로 그만큼 곱해진다.
# close() 때 트랜잭션을 정리한 연결을 돌려받아 다음 요청이 쓴다. 외부 의존성(psycopg_pool)
# 없이 리스트 하나로 — 서버는 uvicorn 한 프로세스다. PG_POOL_SIZE=0 이면 예전처럼 매번 연결.
_POOL = []                 # [(url, raw, 돌려받은 시각)] — 뒤가 최근(LIFO)
_POOL_LOCK = threading.Lock()
_POOL_PING_AFTER = 30.0    # 이만큼 놀던 연결은 SELECT 1 로 살아 있는지 보고 쓴다


def _pool_size():
    try:
        return max(0, int(os.environ.get("PG_POOL_SIZE", "4")))
    except ValueError:
        return 0


def _pool_take(url):
    while True:
        with _POOL_LOCK:
            idx = next((i for i in range(len(_POOL) - 1, -1, -1) if _POOL[i][0] == url), None)
            if idx is None:
                return None
            _, raw, since = _POOL.pop(idx)
        if raw.closed:
            continue
        if time.time() - since > _POOL_PING_AFTER:
            try:
                raw.execute("SELECT 1").fetchone()
                raw.rollback()
            except Exception:
                try:
                    raw.close()
                except Exception:
                    pass
                continue
        return raw


def _pool_give(url, raw):
    """정리된 연결만 돌려받는다. 실패·읽기전용·가득 참이면 닫는다."""
    try:
        if raw.closed or getattr(raw, "read_only", False):
            raw.close()
            return
        raw.rollback()       # 커밋 안 된 읽기 트랜잭션·실패 트랜잭션을 정리
        with _POOL_LOCK:
            if len(_POOL) < _pool_size():
                _POOL.append((url, raw, time.time()))
                return
    except Exception:
        pass
    try:
        raw.close()
    except Exception:
        pass


def pool_clear():
    """테스트·종료용 — 놀고 있는 연결을 모두 닫는다."""
    with _POOL_LOCK:
        items = list(_POOL)
        _POOL.clear()
    for _, raw, _t in items:
        try:
            raw.close()
        except Exception:
            pass


class PgConnection:
    """psycopg 연결 래퍼 — sqlite3.Connection과 같은 호출 방식 제공."""

    backend = "postgresql"

    def __init__(self, raw, pool_url=None):
        self._raw = raw
        self._pool_url = pool_url     # 있으면 close() 가 풀로 돌려준다

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
        raw, self._raw = self._raw, None
        if raw is None:               # 두 번 닫아도 같은 연결을 풀에 두 번 넣지 않게
            return
        if self._pool_url and _pool_size():
            _pool_give(self._pool_url, raw)
        else:
            raw.close()


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
        # prepare_threshold=None: 서버측 prepared statement 사용 안 함.
        # Supavisor transaction 모드(6543)는 prepared statement를 지원하지 않아
        # psycopg 기본값(5회 후 자동 prepare)이면 오류가 난다. session 모드(5432)에서도 무해.
        if _pool_size():
            raw = _pool_take(url)
            if raw is not None:
                return PgConnection(raw, pool_url=url)
        t = time.perf_counter()
        raw = psycopg.connect(url, prepare_threshold=None)
        _note("conn", t)
        return PgConnection(raw, pool_url=url)
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
