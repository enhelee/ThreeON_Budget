# -*- coding: utf-8 -*-
"""DB 연결·스키마 점검 — SQLite/PostgreSQL(Supabase) 어느 쪽이든 .env 설정대로 접속해 확인.

  py scripts/db_check.py            현재 설정(.env DATABASE_URL 또는 SQLite)으로 접속·표 생성·조회
  py scripts/db_check.py --migrate  로컬 SQLite(data/budget.db)의 모든 표를 PostgreSQL로 복사(최초 이전용)

PostgreSQL 최초 접속 시 이 스크립트가 통과해야 서버를 띄운다(dbcore 번역 규칙의 실서버 검증).
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(APP, "src"))

from budget import auth as authm            # noqa: E402
authm.load_dotenv_if_present(APP)
from budget import db as dbm, dbcore        # noqa: E402

TABLES = ["dataset", "plan_row", "erp_row", "override", "run", "match_line", "biz_line", "learned_match",
          "item_master", "dept_master", "year_lock", "manual_biz", "biz_delete", "biz_edit", "audit_log",
          "model_registry", "training_example", "training_snapshot"]


def check(conn):
    print("backend:", dbcore.backend_name(conn))
    for t in TABLES:
        n = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(f"  {t:18s} {n:>8,}")
    conn.execute("INSERT INTO audit_log(at,operator,method,path,status,detail) VALUES(?,?,?,?,?,?)",
                 (dbm._now(), "db_check", "CHECK", "/scripts/db_check", 200, "연결 점검"))
    conn.commit()
    print("write OK (audit_log)")


def migrate(src_path, dst_conn):
    import sqlite3
    src = sqlite3.connect(src_path)
    for t in TABLES:
        cols = [r[1] for r in src.execute(f"PRAGMA table_info({t})")]
        rows = src.execute(f"SELECT {','.join(cols)} FROM {t}").fetchall()
        if not rows:
            continue
        # PostgreSQL BIGSERIAL 표에 id를 명시 삽입 → 이후 시퀀스 보정
        ph = ",".join("?" * len(cols))
        dst_conn.executemany(f"INSERT INTO {t}({','.join(cols)}) VALUES({ph})", rows)
        if "id" in cols and dbcore.backend_name(dst_conn) == "postgresql":
            dst_conn.execute(f"SELECT setval(pg_get_serial_sequence('{t}','id'), (SELECT MAX(id) FROM {t}))")
        dst_conn.commit()
        print(f"  {t}: {len(rows):,}행 복사")
    src.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--migrate", action="store_true", help="로컬 SQLite → 현재 DATABASE_URL(PostgreSQL)로 전체 복사")
    a = ap.parse_args()
    conn = dbm.connect()
    try:
        if a.migrate:
            if dbcore.backend_name(conn) != "postgresql":
                print("DATABASE_URL이 PostgreSQL이 아닙니다 — 이전 대상이 없습니다.")
                return 2
            src = os.path.join(APP, "data", "budget.db")
            print("source:", src)
            migrate(src, conn)
        check(conn)
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
