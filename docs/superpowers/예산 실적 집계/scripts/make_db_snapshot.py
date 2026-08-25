# -*- coding: utf-8 -*-
"""budget.db 내용을 문서화 — docs/DB_스냅샷.md 생성.

다른 컴퓨터에서 Claude Code가 DB 구조·현재 데이터를 파악할 수 있도록
스키마 + 행수 + 소형 테이블 전체 + 대형 테이블 요약을 덤프한다.
실행: budget_app 디렉토리에서  py scripts/make_db_snapshot.py
"""
import io
import json
import os
import sqlite3
import sys
from datetime import datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(APP, "data", "budget.db")
OUT = os.path.join(APP, "docs", "DB_스냅샷.md")

conn = sqlite3.connect(DB)
L = []
w = L.append

w(f"# budget.db 스냅샷\n")
w(f"> 생성: {datetime.now():%Y-%m-%d %H:%M} · 파일: `budget_app/data/budget.db` "
  f"({os.path.getsize(DB)/1e6:.1f}MB)\n")
w("> 이 파일은 `scripts/make_db_snapshot.py`로 재생성할 수 있습니다.\n")

# ── 스키마 ──────────────────────────────────────────────────────────────
w("\n## 1. 스키마 (전체 테이블)\n")
for (name, sql) in conn.execute(
        "SELECT name, sql FROM sqlite_master WHERE type='table' "
        "AND name != 'sqlite_sequence' ORDER BY name"):
    n = conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
    w(f"\n### `{name}` — {n:,}행\n")
    w("```sql\n" + sql.strip() + "\n```\n")

# ── 데이터셋 ────────────────────────────────────────────────────────────
w("\n## 2. 업로드 데이터셋 (dataset)\n")
w("| id | kind | year | label | 행수 | 총액 | 업로드 |\n|---|---|---|---|---|---|---|\n")
for r in conn.execute("SELECT id,kind,year,label,row_count,total_amount,uploaded_at"
                      " FROM dataset ORDER BY id"):
    w(f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} | {r[4]:,} | {r[5]:,.0f} | {r[6]} |\n")
w("\n> 같은 (kind, year)가 여럿이면 **id가 가장 큰 것(최신)** 이 분석에 사용됩니다.\n")

# ── 최신 실행 요약 ──────────────────────────────────────────────────────
w("\n## 3. 최신 분석 실행 (run — 연도×구분별 최신)\n")
for (year,) in conn.execute("SELECT DISTINCT year FROM run ORDER BY year"):
    for (budget,) in conn.execute(
            "SELECT DISTINCT budget FROM run WHERE year=? ORDER BY budget", (year,)):
        row = conn.execute(
            "SELECT id, created_at, summary_json FROM run WHERE year=? AND budget=?"
            " ORDER BY id DESC LIMIT 1", (year, budget)).fetchone()
        s = json.loads(row[2]) if row[2] else {}
        w(f"\n### {year}년 {budget} (run #{row[0]}, {row[1]})\n")
        w("| 항목 | 값 |\n|---|---|\n")
        for k, v in s.items():
            w(f"| {k} | {v:,} |\n" if isinstance(v, (int, float)) and v is not None
              else f"| {k} | {v} |\n")
total_runs = conn.execute("SELECT COUNT(*) FROM run").fetchone()[0]
w(f"\n> 전체 실행 이력 {total_runs}건 중 최신만 표시. 과거 run의 match_line/biz_line은 "
  "`scripts/db_정리.py`로 정리 가능(최신만 유지, 원본 데이터는 영향 없음).\n")

# ── 수동 데이터(사용자 확정) ────────────────────────────────────────────
w("\n## 4. 사용자 확정 데이터 (이관 시 핵심 — 반드시 보존)\n")

w("\n### override (수동 재배정) — 전체\n")
w("| id | year | budget | erp_row_id | 배정 사업명 | 이동 지사 | 일시 |\n"
  "|---|---|---|---|---|---|---|\n")
for r in conn.execute("SELECT id,year,budget,erp_row_id,target_name,target_dept,"
                      "created_at FROM override ORDER BY id"):
    w(f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} | {r[4]} | {r[5] or '-'} | {r[6]} |\n")

for tbl, title in (("manual_biz", "manual_biz (수동 추가 사업)"),
                   ("biz_edit", "biz_edit (사업 내용 수정 — 사업명·속성·부서·처지사·연예산·예산과목)"),
                   ("biz_delete", "biz_delete (사업 삭제 = 분석 제외, 이력 삭제로 복구)"),
                   ("year_lock", "year_lock (연도 마감)")):
    n = conn.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
    w(f"\n### {title} — {n}건\n")
    if n:
        cur = conn.execute(f"SELECT * FROM {tbl}")
        cols = [d[0] for d in cur.description]
        w("| " + " | ".join(cols) + " |\n|" + "---|" * len(cols) + "\n")
        for r in cur.fetchall():
            w("| " + " | ".join(str(x) if x is not None else "-" for x in r) + " |\n")

w("\n### learned_match (학습 DB) — 요약\n")
w("| source | 건수 |\n|---|---|\n")
for r in conn.execute("SELECT source, COUNT(*) FROM learned_match GROUP BY source"):
    w(f"| {r[0]} | {r[1]:,} |\n")
w("\n**사람 확정(수동확정) 전체 목록** — 자동확정은 재분석+일괄학습으로 재생성 가능:\n\n")
w("| 과목 | 텍스트정규 | 배정 사업명 | 연도 |\n|---|---|---|---|\n")
for r in conn.execute("SELECT 과목, 텍스트정규, 사업명, source_year FROM learned_match"
                      " WHERE source='수동확정' ORDER BY 과목, 텍스트정규"):
    w(f"| {r[0]} | {r[1][:40]} | {r[2]} | {r[3]} |\n")

# ── 마스터 ──────────────────────────────────────────────────────────────
w("\n## 5. 기준정보 마스터 (원본: 바탕화면 예산과목.xlsx / 부서코드.xlsx)\n")
w(f"\n- item_master(예산과목): "
  f"{conn.execute('SELECT COUNT(*) FROM item_master').fetchone()[0]}건 "
  "(계정코드→과목명·속성)\n")
w(f"- dept_master(부서코드): "
  f"{conn.execute('SELECT COUNT(*) FROM dept_master').fetchone()[0]}건 "
  "(부서코드→부서명·처지사)\n")
w("\n분석에 쓰는 시드 과목의 마스터 속성:\n\n| 계정코드 | 과목명 | 속성 |\n|---|---|---|\n")
for r in conn.execute("""SELECT 계정코드, 과목명, 속성 FROM item_master WHERE 과목명 IN (
    '수선유지비-건물/구축물','수선유지비-열원정기점검','수선유지비-열원경상정비',
    '수선유지비-열원정기유지보수','수선유지비-열원보완및개선','지급수수료-열원점검수수료',
    '건물','구축물','기계장치','공구와기구-열원시설공기구','저장품-열원(보수)',
    '건설중인자산-재생고온부품','건설중인자산-자산화예비품','외주비-열원정기점검',
    '외주비-열원공사비','재료비-열원자재비','외주비-열원기술용역비') ORDER BY 계정코드"""):
    w(f"| {r[0]} | {r[1]} | {r[2]} |\n")

# ── 검증 기준치 ─────────────────────────────────────────────────────────
w("\n## 6. 검증 기준치 (이관 후 재분석 시 이 수치가 재현되어야 함)\n")
w("""
| 연도 | 구분 | 총 실적(천원) | 미반영 | 비고 |
|---|---|---|---|---|
| 2023 | 손익 | 72,164,026~28 (±2 반올림) | 0 | 본사 미매핑 39건 재배정 반영 |
| 2023 | 자본 | 55,820,726 | 0 | |
| 2025 | 손익 | 98,554,802 | 0 | 본사 미매핑 30건 재배정 반영 |
| 2025 | 자본 | 49,709,178 | 0 | |

불변식: **손익+자본+미반영 = ERP 전체** (2023: 127,984,754 / 2025: 148,263,979, 천원, 행별 반올림 ±수천원)
""")
conn.close()

os.makedirs(os.path.dirname(OUT), exist_ok=True)
io.open(OUT, "w", encoding="utf-8").write("".join(L))
print("생성:", OUT, f"({os.path.getsize(OUT)/1024:.0f}KB)")
