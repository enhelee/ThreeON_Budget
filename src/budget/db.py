# -*- coding: utf-8 -*-
"""보안 저장소(SQLite) — 업로드 원자료를 DB로 흡수하고 분석은 DB에서 수행.

보안 원칙:
- 업로드된 계획/zrfm2 파일은 **행 단위로 DB에 저장 후 원본 파일을 남기지 않는다**
  (임시파일은 흡수 직후 삭제 — 호출측 책임, app.py 참조).
- 프론트엔드는 DB의 분석 결과만 표출하고, 수정(전표 재배정)은 override로 기록한다.
- DB 파일은 `budget_app/data/budget.db` 하나 — 반출 통제·백업이 파일 1개로 끝난다.
"""
import json
import os
import sqlite3
from datetime import datetime

import pandas as pd

from . import loaders, erp_loader, dbcore, ml_registry

APP_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# DATA_DIR 환경변수(배포 시 볼륨 경로) → 기본 budget_app/data
DATA_DIR = os.environ.get("DATA_DIR") or os.path.join(APP_DIR, "data")
DEFAULT_DB = os.path.join(DATA_DIR, "budget.db")

PLAN_COLS = loaders.PLAN_COLUMNS            # 10열
ERP_COLS = [c for c in erp_loader.ERP_COLUMNS if c != "_erp_row"]


def connect(db_path=None):
    """DB 연결. db_path 지정 → SQLite 파일(테스트·스크립트).
    미지정 → DATABASE_URL이 PostgreSQL이면 그 서버, 아니면 DATA_DIR/budget.db(SQLite)."""
    if db_path is None and dbcore.is_postgres_url(dbcore.database_url()):
        conn = dbcore.connect()
    else:
        path = db_path or DEFAULT_DB
        os.makedirs(os.path.dirname(path), exist_ok=True)
        conn = dbcore.connect(db_path=path)
    init_db(conn)
    return conn


def init_db(conn):
    cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS dataset(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        kind TEXT NOT NULL,              -- 'plan' | 'erp'
        year TEXT NOT NULL,
        label TEXT,
        uploaded_at TEXT NOT NULL,
        row_count INTEGER,
        total_amount REAL)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS plan_row(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        dataset_id INTEGER NOT NULL REFERENCES dataset(id),
        주관부서명 TEXT, 부서코드 TEXT, 처지사 TEXT, 부서부 TEXT, 속성 TEXT,
        예산코드 TEXT, 예산과목 TEXT, 사업명 TEXT, 산출내역 TEXT, 연예산 REAL,
        src_row INTEGER)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS erp_row(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        dataset_id INTEGER NOT NULL REFERENCES dataset(id),
        계정코드 TEXT, 예산과목원문 TEXT, 연도 TEXT, 전표번호 TEXT,
        금액원 REAL, 금액천원 REAL, 사업명 TEXT, 지사원문 TEXT, 부서부원문 TEXT,
        전기일 TEXT, 사업장코드 TEXT, 거래처코드 TEXT,
        src_row INTEGER)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS override(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        year TEXT NOT NULL, budget TEXT NOT NULL,
        erp_row_id INTEGER NOT NULL,     -- erp_row.id
        target_name TEXT NOT NULL,       -- 배정할 사업명(계획 사업명 또는 신규 이름)
        memo TEXT,
        created_at TEXT NOT NULL)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS run(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        year TEXT NOT NULL, budget TEXT NOT NULL,
        created_at TEXT NOT NULL,
        summary_json TEXT)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS match_line(
        run_id INTEGER NOT NULL REFERENCES run(id),
        erp_row_id INTEGER NOT NULL,
        과목정규 TEXT, 처지사정규 TEXT, 매칭사업명 TEXT, 매칭확신도 REAL, 구분 TEXT,
        매칭행 INTEGER)""")           # 매칭행=귀속 계획행 번호(동명 사업 구분)
    cur.execute("""CREATE TABLE IF NOT EXISTS biz_line(
        run_id INTEGER NOT NULL REFERENCES run(id),
        budget TEXT NOT NULL,            -- '손익' | '자본'
        예산과목 TEXT, 속성 TEXT, 주관부서명 TEXT, 처지사 TEXT, 부서부 TEXT,
        사업명 TEXT, 연예산 REAL, 실적금액 REAL, 구분 TEXT, 매칭확신도 REAL,
        매칭전표수 INTEGER, 저유사전표수 INTEGER, 임의귀속전표수 INTEGER,
        src_row INTEGER)""")
    # 스키마 마이그레이션(기존 DB): 없는 컬럼 추가
    def _ensure_col(table, col, decl):
        cols = {r[1] for r in cur.execute(f"PRAGMA table_info({table})")}
        if col not in cols:
            cur.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")
    _ensure_col("match_line", "매칭행", "INTEGER")
    _ensure_col("biz_line", "src_row", "INTEGER")
    _ensure_col("override", "target_dept", "TEXT")   # 타지사 이동(크로스 재배정)
    cur.execute("""CREATE TABLE IF NOT EXISTS learned_match(
        과목 TEXT NOT NULL,               -- 과목정규
        텍스트정규 TEXT NOT NULL,         -- ERP 전표 텍스트 정규화(공백·따옴표 제거)
        사업명 TEXT NOT NULL,             -- 확정된 귀속 사업명
        source TEXT,                      -- '수동확정'(재배정) | '자동확정'
        source_year TEXT,
        created_at TEXT,
        PRIMARY KEY (과목, 텍스트정규))""")
    cur.execute("""CREATE TABLE IF NOT EXISTS item_master(
        계정코드 TEXT PRIMARY KEY,
        과목명 TEXT NOT NULL,
        주관부서코드 TEXT, 주관부서명 TEXT, 속성 TEXT, 비고 TEXT)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS dept_master(
        부서코드 TEXT PRIMARY KEY,
        부서명 TEXT NOT NULL,
        처지사 TEXT, 비고 TEXT)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS year_lock(
        year TEXT PRIMARY KEY,
        locked_at TEXT NOT NULL)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS manual_biz(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        year TEXT NOT NULL, budget TEXT NOT NULL,
        예산과목 TEXT NOT NULL, 처지사 TEXT NOT NULL, 사업명 TEXT NOT NULL,
        속성 TEXT, 주관부서명 TEXT, 부서부 TEXT, 연예산 REAL,
        created_at TEXT NOT NULL)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS biz_delete(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        year TEXT NOT NULL, budget TEXT NOT NULL,
        예산과목 TEXT, 처지사 TEXT, 사업명 TEXT,   -- 삭제 대상 사업(현재 이름)
        memo TEXT,
        created_at TEXT NOT NULL)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS biz_edit(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        year TEXT NOT NULL, budget TEXT NOT NULL,
        예산과목 TEXT, 처지사 TEXT, 사업명 TEXT,   -- 대상 사업 식별(현재 이름)
        fields_json TEXT NOT NULL,                 -- {"속성": "...", "사업명": "...", ...}
        created_at TEXT NOT NULL)""")
    cur.execute("CREATE INDEX IF NOT EXISTS ix_plan_ds ON plan_row(dataset_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS ix_erp_ds ON erp_row(dataset_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS ix_ml_run ON match_line(run_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS ix_bl_run ON biz_line(run_id)")
    # 감사 로그(수정 이력) — 공용 비밀번호 체계에서 '누가 언제 무엇을' 남기는 유일한 기록(auth.py)
    cur.execute("""CREATE TABLE IF NOT EXISTS audit_log(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        at TEXT NOT NULL,
        operator TEXT,                   -- 로그인 때 입력한 작업자 이름
        method TEXT NOT NULL, path TEXT NOT NULL,
        status INTEGER,
        detail TEXT)""")
    cur.execute("CREATE INDEX IF NOT EXISTS ix_audit_at ON audit_log(at)")
    conn.commit()
    ml_registry.init_tables(conn)        # 모델 레지스트리·학습데이터 표


def add_audit(conn, operator, method, path, status, detail=None):
    conn.execute("INSERT INTO audit_log(at,operator,method,path,status,detail) VALUES(?,?,?,?,?,?)",
                 (_now(), operator, method, path, int(status) if status is not None else None, detail))
    conn.commit()


def list_audit(conn, limit=100, operator=None):
    q = "SELECT id,at,operator,method,path,status,detail FROM audit_log"
    p = []
    if operator:
        q += " WHERE operator=?"
        p.append(operator)
    q += " ORDER BY id DESC LIMIT ?"
    p.append(int(limit))
    cols = ["id", "at", "operator", "method", "path", "status", "detail"]
    return [dict(zip(cols, r)) for r in conn.execute(q, tuple(p)).fetchall()]


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ---------------------------------------------------------------------------
# 흡수(ingest) — 파일 → DB. 호출측은 성공 후 임시파일을 삭제할 것.
# ---------------------------------------------------------------------------

def ingest_plan(conn, path, year, label=None):
    df = loaders.load_business_plan(path)
    cur = conn.cursor()
    total = float(pd.to_numeric(df["연예산"], errors="coerce").fillna(0).sum())
    cur.execute("INSERT INTO dataset(kind,year,label,uploaded_at,row_count,total_amount)"
                " VALUES('plan',?,?,?,?,?)",
                (str(year), label or os.path.basename(path), _now(), len(df), total))
    ds_id = cur.lastrowid
    rows = []
    for _, r in df.iterrows():
        rows.append((ds_id, *[None if pd.isna(r[c]) else r[c] for c in PLAN_COLS],
                     int(r["_row"])))
    cur.executemany(
        f"INSERT INTO plan_row(dataset_id,{','.join(PLAN_COLS)},src_row)"
        f" VALUES({','.join('?' * (len(PLAN_COLS) + 2))})", rows)
    conn.commit()
    return {"dataset_id": ds_id, "rows": len(df), "total": total}


def ingest_erp(conn, path, year, label=None):
    df = erp_loader.load_erp(path)
    cur = conn.cursor()
    total = float(pd.to_numeric(df["금액천원"], errors="coerce").fillna(0).sum())
    cur.execute("INSERT INTO dataset(kind,year,label,uploaded_at,row_count,total_amount)"
                " VALUES('erp',?,?,?,?,?)",
                (str(year), label or os.path.basename(path), _now(), len(df), total))
    ds_id = cur.lastrowid
    rows = []
    for _, r in df.iterrows():
        rows.append((ds_id, *[None if pd.isna(r[c]) else r[c] for c in ERP_COLS],
                     int(r["_erp_row"])))
    cur.executemany(
        f"INSERT INTO erp_row(dataset_id,{','.join(ERP_COLS)},src_row)"
        f" VALUES({','.join('?' * (len(ERP_COLS) + 2))})", rows)
    conn.commit()
    return {"dataset_id": ds_id, "rows": len(df), "total": total}


def list_datasets(conn, year=None):
    q = ("SELECT id,kind,year,label,uploaded_at,row_count,total_amount FROM dataset"
         + (" WHERE year=?" if year else "") + " ORDER BY id DESC")
    cur = conn.execute(q, (str(year),) if year else ())
    cols = ["id", "kind", "year", "label", "uploaded_at", "row_count", "total_amount"]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def delete_dataset(conn, dataset_id):
    conn.execute("DELETE FROM plan_row WHERE dataset_id=?", (dataset_id,))
    conn.execute("DELETE FROM erp_row WHERE dataset_id=?", (dataset_id,))
    conn.execute("DELETE FROM dataset WHERE id=?", (dataset_id,))
    conn.commit()


def _latest_dataset_id(conn, kind, year):
    cur = conn.execute(
        "SELECT id FROM dataset WHERE kind=? AND year=? ORDER BY id DESC LIMIT 1",
        (kind, str(year)))
    row = cur.fetchone()
    return row[0] if row else None


# ---------------------------------------------------------------------------
# 조회 — 분석 파이프라인 입력 DataFrame (loaders/erp_loader와 동일 스키마)
# ---------------------------------------------------------------------------

def load_plan_df(conn, year):
    ds = _latest_dataset_id(conn, "plan", year)
    if ds is None:
        return None
    df = pd.read_sql_query(
        f"SELECT {','.join(PLAN_COLS)}, src_row AS _row FROM plan_row"
        " WHERE dataset_id=? ORDER BY id", conn, params=(ds,))
    return df


def load_erp_df(conn, year):
    ds = _latest_dataset_id(conn, "erp", year)
    if ds is None:
        return None
    df = pd.read_sql_query(
        f"SELECT id AS _erp_row, {','.join(ERP_COLS)} FROM erp_row"
        " WHERE dataset_id=? ORDER BY id", conn, params=(ds,))
    # 스키마 순서를 erp_loader와 동일하게
    return df[[c for c in erp_loader.ERP_COLUMNS]]


# ---------------------------------------------------------------------------
# 오버라이드(전표 재배정) / 실행 이력
# ---------------------------------------------------------------------------

def add_override(conn, year, budget, erp_row_id, target_name, memo=None,
                 target_dept=None):
    conn.execute(
        "INSERT INTO override(year,budget,erp_row_id,target_name,memo,created_at,"
        "target_dept) VALUES(?,?,?,?,?,?,?)",
        (str(year), budget, int(erp_row_id), target_name, memo, _now(), target_dept))
    conn.commit()


def list_overrides(conn, year, budget):
    cur = conn.execute(
        "SELECT id,erp_row_id,target_name,memo,created_at,target_dept FROM override"
        " WHERE year=? AND budget=? ORDER BY id", (str(year), budget))
    cols = ["id", "erp_row_id", "target_name", "memo", "created_at", "target_dept"]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def override_map(conn, year, budget):
    """{erp_row_id -> {"사업명": ..., "처지사": ...|None}} — 최신이 이긴다."""
    out = {}
    for ov in list_overrides(conn, year, budget):
        out[int(ov["erp_row_id"])] = {"사업명": ov["target_name"],
                                      "처지사": ov.get("target_dept")}
    return out


def delete_override(conn, override_id):
    conn.execute("DELETE FROM override WHERE id=?", (override_id,))
    conn.commit()


def save_run(conn, year, budget, summary, erp_annotated):
    cur = conn.cursor()
    cur.execute("INSERT INTO run(year,budget,created_at,summary_json) VALUES(?,?,?,?)",
                (str(year), budget, _now(), json.dumps(summary, ensure_ascii=False)))
    run_id = cur.lastrowid
    rows = []
    for _, r in erp_annotated.iterrows():
        conf = r.get("매칭확신도")
        mrow = r.get("매칭행")
        rows.append((run_id, int(r["_erp_row"]),
                     r.get("과목정규"), r.get("처지사정규"), r.get("매칭사업명"),
                     None if conf is None or pd.isna(conf) else float(conf),
                     r.get("구분"),
                     None if mrow is None or pd.isna(mrow) else int(mrow)))
    cur.executemany("INSERT INTO match_line VALUES(?,?,?,?,?,?,?,?)", rows)
    conn.commit()
    return run_id


def _f(v):
    """숫자 필드 정규화(NaN → None)."""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if f != f else f


def save_biz_lines(conn, run_id, budget, plan_rows, new_rows):
    """분석 결과의 사업 단위 행(계획행+신규행)을 DB에 저장 — 웹 상세화면 소스."""
    rows = []
    for r in plan_rows:
        src = _f(r.get("_row"))
        rows.append((run_id, budget, r.get("예산과목"), r.get("속성"), r.get("주관부서명"),
                     r.get("처지사"), r.get("부서부"), r.get("사업명"),
                     _f(r.get("연예산")), round(r.get("실적금액", 0.0)), r.get("구분"),
                     _f(r.get("매칭확신도")), r.get("매칭전표수", 0),
                     r.get("저유사전표수", 0), r.get("임의귀속전표수", 0),
                     None if src is None else int(src)))
    for r in new_rows:
        rows.append((run_id, budget, r.get("예산과목"), r.get("속성"), None,
                     r.get("처지사"), r.get("부서부"), r.get("사업명"),
                     0.0, round(r.get("실적금액", 0.0)), r.get("구분", "신규"),
                     None, r.get("전표건수", 0), 0, 0, None))
    conn.executemany(
        "INSERT INTO biz_line VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    conn.commit()


def load_biz_lines(conn, run_id):
    return pd.read_sql_query(
        "SELECT * FROM biz_line WHERE run_id=? ORDER BY 처지사, 예산과목, 실적금액 DESC",
        conn, params=(run_id,))


def latest_run(conn, year, budget):
    cur = conn.execute(
        "SELECT id,created_at,summary_json FROM run WHERE year=? AND budget=?"
        " ORDER BY id DESC LIMIT 1", (str(year), budget))
    row = cur.fetchone()
    if not row:
        return None
    return {"id": row[0], "created_at": row[1],
            "summary": json.loads(row[2]) if row[2] else {}}


# ---------------------------------------------------------------------------
# 마스터 (예산과목·부서코드) — 사용자 제공 기준정보의 DB화
# ---------------------------------------------------------------------------

VALID_ATTRS = ("일반", "제조", "건가", "자산")


def ingest_item_master(conn, path):
    """예산과목.xlsx [예산코드] 시트 → item_master. (계정코드, 과목명, 속성 등)"""
    import openpyxl
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb[wb.sheetnames[0]]
    cur = conn.cursor()
    n = 0
    for r in range(2, ws.max_row + 1):
        code, name = ws.cell(r, 1).value, ws.cell(r, 2).value
        if code is None or name is None:
            continue
        cur.execute("INSERT OR REPLACE INTO item_master VALUES(?,?,?,?,?,?)",
                    (str(code).strip(), str(name).strip(),
                     None if ws.cell(r, 3).value is None else str(ws.cell(r, 3).value).strip(),
                     ws.cell(r, 4).value, ws.cell(r, 5).value, ws.cell(r, 6).value))
        n += 1
    wb.close()
    conn.commit()
    return n


def ingest_dept_master(conn, path):
    """부서코드.xlsx [부서코드] 시트 → dept_master. (부서코드, 부서명, 처지사)"""
    import openpyxl
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb[wb.sheetnames[0]]
    cur = conn.cursor()
    n = 0
    for r in range(2, ws.max_row + 1):
        code, name = ws.cell(r, 1).value, ws.cell(r, 2).value
        if code is None or name is None:
            continue
        cur.execute("INSERT OR REPLACE INTO dept_master VALUES(?,?,?,?)",
                    (str(code).strip(), str(name).strip(),
                     ws.cell(r, 3).value, ws.cell(r, 4).value))
        n += 1
    wb.close()
    conn.commit()
    return n


def load_item_attr_map(conn):
    """{과목명 -> 속성(단일)} — 복합 표기('일반/제조')는 첫 값 사용."""
    out = {}
    for name, attr in conn.execute("SELECT 과목명, 속성 FROM item_master"):
        if not attr:
            continue
        first = str(attr).split("/")[0].strip()
        if first in VALID_ATTRS:
            out[str(name)] = first
    return out


def load_code_to_item(conn):
    """{계정코드 -> 과목명} — ERP 계정코드 정규화용."""
    return {str(c): str(n) for c, n in
            conn.execute("SELECT 계정코드, 과목명 FROM item_master")}


def load_deptcode_map(conn):
    """{부서코드 -> 처지사} — 계획행 처지사 보정용(부서코드 마스터)."""
    return {str(c): str(d) for c, d in
            conn.execute("SELECT 부서코드, 처지사 FROM dept_master WHERE 처지사 IS NOT NULL")}


def master_stats(conn):
    item = conn.execute("SELECT COUNT(*) FROM item_master").fetchone()[0]
    dept = conn.execute("SELECT COUNT(*) FROM dept_master").fetchone()[0]
    return {"예산과목": item, "부서코드": dept}


# ---------------------------------------------------------------------------
# 수동 사업 추가 — 계획본에 없는 사업을 관리자가 직접 등록
# ---------------------------------------------------------------------------

def add_manual_biz(conn, year, budget, item, dept, name, attr=None,
                   owner=None, part=None, plan_amt=None):
    cur = conn.execute(
        "INSERT INTO manual_biz(year,budget,예산과목,처지사,사업명,속성,주관부서명,"
        "부서부,연예산,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
        (str(year), budget, item, dept, name, attr, owner, part,
         float(plan_amt) if plan_amt else 0.0, _now()))
    conn.commit()
    return cur.lastrowid


def list_manual_biz(conn, year, budget=None):
    q = ("SELECT id,budget,예산과목,처지사,사업명,속성,주관부서명,부서부,연예산,created_at"
         " FROM manual_biz WHERE year=?" + (" AND budget=?" if budget else "")
         + " ORDER BY id")
    cur = conn.execute(q, (str(year), budget) if budget else (str(year),))
    cols = ["id", "budget", "예산과목", "처지사", "사업명", "속성", "주관부서명",
            "부서부", "연예산", "created_at"]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def delete_manual_biz(conn, biz_id):
    conn.execute("DELETE FROM manual_biz WHERE id=?", (biz_id,))
    conn.commit()


# ---------------------------------------------------------------------------
# 연도 마감(잠금) — 완료 연도의 데이터 변경 차단
# ---------------------------------------------------------------------------

def lock_year(conn, year):
    conn.execute("INSERT OR REPLACE INTO year_lock VALUES(?,?)", (str(year), _now()))
    conn.commit()


def unlock_year(conn, year):
    conn.execute("DELETE FROM year_lock WHERE year=?", (str(year),))
    conn.commit()


def is_locked(conn, year):
    return conn.execute("SELECT 1 FROM year_lock WHERE year=?",
                        (str(year),)).fetchone() is not None


def locked_years(conn):
    return {r[0]: r[1] for r in
            conn.execute("SELECT year, locked_at FROM year_lock ORDER BY year")}


# ---------------------------------------------------------------------------
# 학습 — 완료된 분석(수동 재배정 포함)에서 텍스트→사업 매핑을 축적
# ---------------------------------------------------------------------------

def norm_text(s):
    """학습 키용 텍스트 정규화(normalize.text_key와 동일 기준)."""
    from . import normalize
    return normalize.text_key(s)


def learn_from_year(conn, year):
    """해당 연도의 최신 실행(손익·자본) 확정 결과를 학습 DB에 반영.

    - 계획집행/신규로 귀속된 전표의 (과목, 텍스트정규) → 사업명 을 저장.
    - 수동 재배정(override) 전표는 source='수동확정'으로 우선 저장(사람 확정).
    - 같은 키는 최신 학습이 덮어쓴다(사람 확정 > 자동 확정).
    반환: {"자동확정": n, "수동확정": m}
    """
    counts = {"자동확정": 0, "수동확정": 0}
    cur = conn.cursor()
    for budget in ("손익", "자본"):
        run = latest_run(conn, year, budget)
        if not run:
            continue
        manual_ids = {int(o["erp_row_id"]) for o in list_overrides(conn, year, budget)}
        detail = load_match_detail(conn, run["id"])
        rows = []
        for _, r in detail.iterrows():
            if r["구분"] not in ("계획집행", "신규"):
                continue
            key = norm_text(r["전표텍스트"])
            if not key or not r["과목정규"]:
                continue
            name = str(r["매칭사업명"] or "")
            if name.startswith("[신규] "):
                name = name[len("[신규] "):]
            if not name:
                continue
            src = "수동확정" if int(r["erp_row_id"]) in manual_ids else "자동확정"
            rows.append((r["과목정규"], key, name, src))
        # 자동확정 먼저, 수동확정 나중(같은 키면 사람 확정이 이긴다)
        for want in ("자동확정", "수동확정"):
            for item, key, name, src in rows:
                if src != want:
                    continue
                cur.execute(
                    "INSERT OR REPLACE INTO learned_match VALUES(?,?,?,?,?,?)",
                    (item, key, name, src, str(year), _now()))
                counts[src] += 1
    conn.commit()
    return counts


def learn_from_override(conn, year, budget, erp_row_ids, target_name):
    """수동 재배정 저장 즉시 해당 전표의 텍스트→사업명 매핑을 학습(수동확정).

    사람이 확정한 것이므로 버튼 없이 자동 축적된다. 과목은 최신 실행의
    match_line(과목정규)에서, 없으면 erp_row의 예산과목원문으로 대체.
    """
    run = latest_run(conn, year, budget)
    cur = conn.cursor()
    n = 0
    for rid in erp_row_ids:
        item = None
        if run:
            r = cur.execute(
                "SELECT 과목정규 FROM match_line WHERE run_id=? AND erp_row_id=?",
                (run["id"], int(rid))).fetchone()
            item = r[0] if r else None
        row = cur.execute(
            "SELECT 예산과목원문, 사업명 FROM erp_row WHERE id=?", (int(rid),)).fetchone()
        if not row:
            continue
        item = item or row[0]
        key = norm_text(row[1])
        if not item or not key:
            continue
        cur.execute("INSERT OR REPLACE INTO learned_match VALUES(?,?,?,?,?,?)",
                    (item, key, target_name, "수동확정", str(year), _now()))
        n += 1
    conn.commit()
    return n


def load_learned(conn):
    """{(과목, 텍스트정규) -> 사업명} — matching이 유사도보다 우선 적용."""
    cur = conn.execute("SELECT 과목, 텍스트정규, 사업명 FROM learned_match")
    return {(r[0], r[1]): r[2] for r in cur.fetchall()}


def learned_stats(conn):
    cur = conn.execute(
        "SELECT source, COUNT(*) FROM learned_match GROUP BY source")
    out = dict(cur.fetchall())
    out["총계"] = sum(out.values())
    return out


def count_learn_pending(conn, year):
    """아직 학습되지 않은 '사람 확정 재배정' 건수.

    재배정 저장 시 자동 학습을 떼어냈으므로(설정 탭 [AI 학습] 버튼으로 분리),
    학습 대기 = override 중 (과목, 텍스트정규)가 learned_match에 없는 것.
    """
    n = 0
    for budget in ("손익", "자본"):
        run = latest_run(conn, year, budget)
        rows = conn.execute(
            "SELECT o.erp_row_id, o.target_name, e.예산과목원문, e.사업명"
            " FROM override o JOIN erp_row e ON e.id = o.erp_row_id"
            " WHERE o.year=? AND o.budget=?", (str(year), budget)).fetchall()
        for rid, target, item_raw, text in rows:
            item = None
            if run:
                r = conn.execute(
                    "SELECT 과목정규 FROM match_line WHERE run_id=? AND erp_row_id=?",
                    (run["id"], int(rid))).fetchone()
                item = r[0] if r else None
            item = item or item_raw
            key = norm_text(text)
            if not item or not key:
                continue          # 텍스트 없는 전표는 학습 대상 아님
            hit = conn.execute(
                "SELECT 사업명 FROM learned_match WHERE 과목=? AND 텍스트정규=?",
                (item, key)).fetchone()
            if not hit or hit[0] != target:
                n += 1
    return n


def clear_learned(conn):
    conn.execute("DELETE FROM learned_match")
    conn.commit()


# ---------------------------------------------------------------------------
# 사업 내용 수정(biz_edit) — 관리자가 속성·사업명 등을 직접 고쳐 저장
# ---------------------------------------------------------------------------

def add_biz_edit(conn, year, budget, item, dept, name, fields):
    conn.execute(
        "INSERT INTO biz_edit(year,budget,예산과목,처지사,사업명,fields_json,created_at)"
        " VALUES(?,?,?,?,?,?,?)",
        (str(year), budget, item, dept, name,
         json.dumps(fields, ensure_ascii=False), _now()))
    conn.commit()


def list_biz_edits(conn, year, budget=None):
    q = ("SELECT id,budget,예산과목,처지사,사업명,fields_json,created_at FROM biz_edit"
         " WHERE year=?" + (" AND budget=?" if budget else "") + " ORDER BY id")
    cur = conn.execute(q, (str(year), budget) if budget else (str(year),))
    cols = ["id", "budget", "예산과목", "처지사", "사업명", "fields_json", "created_at"]
    out = []
    for r in cur.fetchall():
        d = dict(zip(cols, r))
        d["fields"] = json.loads(d.pop("fields_json"))
        out.append(d)
    return out


def delete_biz_edit(conn, edit_id):
    conn.execute("DELETE FROM biz_edit WHERE id=?", (edit_id,))
    conn.commit()


def add_biz_delete(conn, year, budget, item, dept, name, memo=None):
    """사업 삭제(=분석 대상에서 제외) 기록. 원본을 지우지 않으므로 이력을 지우면 복구된다."""
    conn.execute(
        "INSERT INTO biz_delete(year,budget,예산과목,처지사,사업명,memo,created_at)"
        " VALUES(?,?,?,?,?,?,?)",
        (str(year), budget, item, dept, name, memo, _now()))
    conn.commit()


def list_biz_deletes(conn, year, budget=None):
    q = ("SELECT id,budget,예산과목,처지사,사업명,memo,created_at FROM biz_delete"
         " WHERE year=?" + (" AND budget=?" if budget else "") + " ORDER BY id")
    cur = conn.execute(q, (str(year), budget) if budget else (str(year),))
    cols = ["id", "budget", "예산과목", "처지사", "사업명", "memo", "created_at"]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def delete_biz_delete(conn, del_id):
    conn.execute("DELETE FROM biz_delete WHERE id=?", (del_id,))
    conn.commit()


def rename_biz_references(conn, year, budget, item, dept, old_name, new_name):
    """사업명 변경 시 그 사업을 '이름으로' 가리키는 기록을 함께 옮긴다.

    이걸 하지 않으면 재배정(override)·학습(learned_match)이 옛 이름을 계속 가리켜,
    재분석 때 그 이름의 계획행이 없으므로 동명의 신규 사업이 따로 생긴다(중복 행).
    override는 과목·지사를 갖고 있지 않으므로 최신 실행의 match_line으로 범위를 좁힌다.
    manual_biz는 건드리지 않는다 — 이름 변경은 biz_edit가 매 분석 때 적용하므로,
    원본 이름을 바꾸면 그 biz_edit(옛 이름 키)가 더 이상 매칭되지 않아 속성 등 나머지
    수정까지 함께 사라진다.
    """
    if not old_name or not new_name or old_name == new_name:
        return {"override": 0, "learned": 0}
    run = latest_run(conn, year, budget)
    ov = 0
    if run:
        cur = conn.execute(
            "UPDATE override SET target_name=? WHERE year=? AND budget=? AND target_name=?"
            " AND erp_row_id IN (SELECT erp_row_id FROM match_line WHERE run_id=?"
            "                    AND 과목정규=? AND 처지사정규=?)",
            (new_name, str(year), budget, old_name, run["id"], item, dept))
        ov = cur.rowcount
    cur = conn.execute("UPDATE learned_match SET 사업명=? WHERE 과목=? AND 사업명=?",
                       (new_name, item, old_name))
    lm = cur.rowcount
    conn.commit()
    return {"override": ov, "learned": lm}


def patch_latest_run_biz(conn, year, budget, item, dept, name, fields):
    """최신 실행의 biz_line(및 사업명 변경 시 match_line 라벨)을 즉시 수정 —
    재분석 없이 화면에 바로 반영하기 위한 패치. 영구 반영은 biz_edit가 담당."""
    run = latest_run(conn, year, budget)
    if not run:
        return 0
    sets, vals = [], []
    for k in ("속성", "사업명", "주관부서명", "부서부", "처지사", "연예산", "예산과목"):
        if k in fields:
            sets.append(f"{k}=?")
            vals.append(fields[k] if fields[k] != "" else None)
    if not sets:
        return 0
    vals += [run["id"], budget, item, dept, name]
    cur = conn.execute(
        f"UPDATE biz_line SET {', '.join(sets)} WHERE run_id=? AND budget=?"
        " AND 예산과목=? AND 처지사=? AND 사업명=?", vals)
    n = cur.rowcount
    new_name = fields.get("사업명")
    if new_name and new_name != name:
        conn.execute(
            "UPDATE match_line SET 매칭사업명=? WHERE run_id=? AND 과목정규=?"
            " AND 처지사정규=? AND 매칭사업명=?",
            (new_name, run["id"], item, dept, name))
        conn.execute(
            "UPDATE match_line SET 매칭사업명=? WHERE run_id=? AND 과목정규=?"
            " AND 처지사정규=? AND 매칭사업명=?",
            (f"[신규] {new_name}", run["id"], item, dept, f"[신규] {name}"))
    # 지사 이동은 귀속 전표(match_line)도 같이 옮겨야 전표 트리가 어긋나지 않는다.
    #   영구 반영은 biz_edit(계획행) + override(전표)로 재분석이 담당한다.
    new_dept = fields.get("처지사")
    if new_dept and new_dept != dept:
        for label in (new_name or name, f"[신규] {new_name or name}"):
            conn.execute(
                "UPDATE match_line SET 처지사정규=? WHERE run_id=? AND 과목정규=?"
                " AND 처지사정규=? AND 매칭사업명=?",
                (new_dept, run["id"], item, dept, label))
    conn.commit()
    return n


def load_match_detail(conn, run_id):
    """트리 검토용: 매칭 결과 + ERP 전표 원장 조인."""
    return pd.read_sql_query(
        """SELECT m.erp_row_id, m.과목정규, m.처지사정규, m.매칭사업명, m.매칭확신도, m.구분,
                  m.매칭행,
                  e.전표번호, e.사업명 AS 전표텍스트, e.금액천원, e.금액원, e.전기일,
                  e.지사원문, e.부서부원문
           FROM match_line m JOIN erp_row e ON e.id = m.erp_row_id
           WHERE m.run_id=? ORDER BY m.과목정규, m.처지사정규, m.매칭사업명, e.id""",
        conn, params=(run_id,))
