# -*- coding: utf-8 -*-
"""budget.db 용량 정리 — 과거 분석 실행 이력 삭제(연도×구분별 최신 run만 유지).

원본 데이터(plan_row/erp_row)·사용자 확정(override/manual_biz/biz_edit/learned_match)
·마스터·마감은 절대 건드리지 않는다. 삭제되는 것은 재분석으로 언제든 재생성되는
중간 산출(match_line/biz_line/과거 run)뿐이다.
실행: budget_app 디렉토리에서  py scripts/db_정리.py
"""
import io
import os
import sqlite3
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(APP, "data", "budget.db")

conn = sqlite3.connect(DB)
before = os.path.getsize(DB) / 1e6

keep = [r[0] for r in conn.execute(
    "SELECT MAX(id) FROM run GROUP BY year, budget")]
ph = ",".join("?" * len(keep))
n_run = conn.execute(f"DELETE FROM run WHERE id NOT IN ({ph})", keep).rowcount
n_ml = conn.execute(f"DELETE FROM match_line WHERE run_id NOT IN ({ph})", keep).rowcount
n_bl = conn.execute(f"DELETE FROM biz_line WHERE run_id NOT IN ({ph})", keep).rowcount
conn.commit()
conn.execute("VACUUM")
conn.close()

after = os.path.getsize(DB) / 1e6
print(f"정리 완료: run {n_run}건 / match_line {n_ml:,}행 / biz_line {n_bl:,}행 삭제")
print(f"유지된 최신 run: {sorted(keep)}")
print(f"DB 크기: {before:.1f}MB → {after:.1f}MB")
