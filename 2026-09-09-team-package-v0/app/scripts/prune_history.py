# -*- coding: utf-8 -*-
"""쓰지 않는 이력 정리 — 옛 분석 실행분 · 대체된 업로드 데이터셋.

왜: 분석·업로드는 매번 새 행을 쌓기만 한다. 화면·분석·내보내기·전망이 읽는 것은
  · 분석 결과: (연도, 손익|자본)마다 «가장 최근 실행» 하나 (db.latest_run)
  · 원자료:   (계획|ERP, 연도)마다 «가장 최근 데이터셋» 하나 (db._latest_dataset_id)
뿐이다. 2026-10-18 운영 DB 는 44만 행 중 72%(옛 실행 22회분 29.7만 행 · 대체된 데이터셋 4개
2.4만 행)가 이 둘에 해당하지 않았다.

지키는 것(하나라도 걸리면 아무것도 지우지 않고 멈춘다):
  · 재배정(override)이 가리키는 ERP 행은 지우지 않는다.
  · 남길 최신 실행의 매칭 결과가 가리키는 ERP 행은 지우지 않는다.
  · --apply 는 «방금 뜬» 백업(backup_pg.py)을 요구한다 — 그 백업의 표별 행 수가 지금 DB 와
    같아야 한다. 지운 것을 되살릴 길이 그 백업이다.
  · 한 트랜잭션 — 중간에 실패하면 그대로.
  · 지운 내역을 같은 트랜잭션으로 audit_log 에 남긴다(작업자 «스크립트(prune_history)», 경로
    /scripts/prune_history) — 설정 «변경 이력»에 보이고, 전망 결과 캐시도 바로 다시 계산된다.

사용(app 폴더에서):
    python scripts/prune_history.py                      # 미리보기(지우지 않음) — 운영(app/.env)
    python scripts/prune_history.py --apply --backup <백업폴더>
    python scripts/prune_history.py --db data/budget.db   # SQLite 파일(로컬 사본·테스트)
"""
import argparse
import json
import os
import sys

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(APP, "src"))

from budget import db as dbm, dbcore   # noqa: E402

CHILD_OF_RUN = ("match_line", "biz_line")
CHILD_OF_DATASET = ("plan_row", "erp_row")


def _ph(ids):
    return ",".join("?" for _ in ids)


def _scalar(conn, sql, params=()):
    return conn.execute(sql, tuple(params)).fetchone()[0]


def plan(conn):
    """지울 것과 남길 것을 센다. 지우지 않는다. 안전 조건이 깨지면 problems 에 이유를 담는다."""
    keep_runs = [r[0] for r in conn.execute("SELECT MAX(id) FROM run GROUP BY year, budget").fetchall()]
    keep_ds = [r[0] for r in conn.execute("SELECT MAX(id) FROM dataset GROUP BY kind, year").fetchall()]
    out = {"keep_runs": keep_runs, "keep_datasets": keep_ds, "delete": {}, "problems": []}
    if keep_runs:
        out["delete"]["run"] = _scalar(conn, f"SELECT COUNT(*) FROM run WHERE id NOT IN ({_ph(keep_runs)})", keep_runs)
        for t in CHILD_OF_RUN:
            out["delete"][t] = _scalar(conn, f"SELECT COUNT(*) FROM {t} WHERE run_id NOT IN ({_ph(keep_runs)})", keep_runs)
    if keep_ds:
        out["delete"]["dataset"] = _scalar(conn, f"SELECT COUNT(*) FROM dataset WHERE id NOT IN ({_ph(keep_ds)})", keep_ds)
        for t in CHILD_OF_DATASET:
            out["delete"][t] = _scalar(conn, f"SELECT COUNT(*) FROM {t} WHERE dataset_id NOT IN ({_ph(keep_ds)})", keep_ds)
        n = _scalar(conn, "SELECT COUNT(*) FROM override o JOIN erp_row e ON e.id = o.erp_row_id"
                          f" WHERE e.dataset_id NOT IN ({_ph(keep_ds)})", keep_ds)
        if n:
            out["problems"].append(f"재배정 {n}건이 지울 ERP 행을 가리킵니다")
        if keep_runs:
            n = _scalar(conn, "SELECT COUNT(*) FROM match_line m JOIN erp_row e ON e.id = m.erp_row_id"
                              f" WHERE m.run_id IN ({_ph(keep_runs)}) AND e.dataset_id NOT IN ({_ph(keep_ds)})",
                        keep_runs + keep_ds)
            if n:
                out["problems"].append(f"최신 분석 결과 {n}행이 지울 ERP 행을 가리킵니다")
    return out


AUDIT_OPERATOR = "스크립트(prune_history)"
AUDIT_PATH = "/scripts/prune_history"


def apply(conn, p, operator=AUDIT_OPERATOR, note=""):
    """plan() 결과대로 지운다 — 자식 표부터, 한 트랜잭션.

    지운 사실을 audit_log 에 같은 트랜잭션으로 남긴다. ① 설정 화면 «변경 이력»에서 팀이 언제·무엇을
    정리했는지 본다(공용 비밀번호 체계에서 수정 이력의 근거가 audit_log 다). ② 전망 결과 캐시의
    데이터 버전이 audit_log 최신 id 라서, 기록이 남아야 캐시가 바로 다시 계산된다(2026-10-19 첫 정리는
    기록 없이 돌아 캐시가 10분 TTL 까지 옛값을 냈다). db.add_audit 는 스스로 commit 하므로 쓰지 않는다.
    """
    if p["problems"]:
        raise RuntimeError("안전 조건 위반: " + " · ".join(p["problems"]))
    kr, kd = p["keep_runs"], p["keep_datasets"]
    try:
        if kr:
            for t in CHILD_OF_RUN:
                conn.execute(f"DELETE FROM {t} WHERE run_id NOT IN ({_ph(kr)})", tuple(kr))
            conn.execute(f"DELETE FROM run WHERE id NOT IN ({_ph(kr)})", tuple(kr))
        if kd:
            for t in CHILD_OF_DATASET:
                conn.execute(f"DELETE FROM {t} WHERE dataset_id NOT IN ({_ph(kd)})", tuple(kd))
            conn.execute(f"DELETE FROM dataset WHERE id NOT IN ({_ph(kd)})", tuple(kd))
        detail = "이력 정리 — " + ", ".join(f"{t} {n:,}" for t, n in p["delete"].items() if n) \
                 + f" (합계 {sum(p['delete'].values()):,}행)" + (f" · {note}" if note else "")
        conn.execute("INSERT INTO audit_log(at,operator,method,path,status,detail) VALUES(?,?,?,?,?,?)",
                     (dbm._now(), operator, "SCRIPT", AUDIT_PATH, 200, detail))
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def backup_matches(conn, folder):
    """백업 manifest 의 표별 행 수가 지금 DB 와 같은지 — 같아야 «방금 뜬» 백업이다."""
    m = json.load(open(os.path.join(folder, "manifest.json"), encoding="utf-8"))
    diffs = []
    for t, info in m["tables"].items():
        try:
            n = _scalar(conn, f"SELECT COUNT(*) FROM {t}")
        except Exception:
            continue
        if n != info["rows"]:
            diffs.append(f"{t}: 백업 {info['rows']} / 지금 {n}")
    return diffs


def _connect(db_path):
    if db_path:
        return dbcore.connect(db_path=db_path)
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        env = os.path.join(APP, ".env")
        if os.path.exists(env):
            for line in open(env, encoding="utf-8"):
                if line.strip().startswith("DATABASE_URL="):
                    url = line.split("=", 1)[1].strip().strip('"').strip("'")
    if not dbcore.is_postgres_url(url):
        sys.exit("대상 DB 가 없습니다 — --db <sqlite 파일> 또는 app/.env 의 DATABASE_URL.")
    return dbcore.connect(url=url)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", help="SQLite 파일(생략하면 app/.env 의 운영 PostgreSQL)")
    ap.add_argument("--apply", action="store_true", help="실제로 지운다(없으면 미리보기)")
    ap.add_argument("--backup", help="--apply 에 필요: 방금 뜬 backup_pg.py 백업 폴더")
    a = ap.parse_args()
    conn = _connect(a.db)
    if not a.apply and hasattr(conn, "_raw"):
        conn._raw.read_only = True       # 미리보기는 PostgreSQL 에 읽기 전용으로만 붙는다
    try:
        p = plan(conn)
        print(f"남길 최신 실행 {len(p['keep_runs'])}개 · 최신 데이터셋 {len(p['keep_datasets'])}개")
        print("지울 행:", ", ".join(f"{t} {n:,}" for t, n in p["delete"].items()),
              f"(합계 {sum(p['delete'].values()):,})")
        if p["problems"]:
            print("❌ 안전 조건 위반 — 지우지 않습니다:", " · ".join(p["problems"]))
            return 1
        if not a.apply:
            print("미리보기입니다 — 지우려면 --apply --backup <백업폴더>")
            return 0
        if not a.backup:
            sys.exit("--apply 에는 --backup <방금 뜬 백업 폴더> 가 필요합니다.")
        diffs = backup_matches(conn, a.backup)
        if diffs:
            print("❌ 백업이 지금 DB 와 다릅니다(새로 백업하세요):", "; ".join(diffs))
            return 1
        apply(conn, p, note=f"백업 {os.path.basename(os.path.normpath(a.backup))}")
        after = plan(conn)
        print("✅ 정리 완료 — 남은 정리 대상:", sum(after["delete"].values()), "행")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
