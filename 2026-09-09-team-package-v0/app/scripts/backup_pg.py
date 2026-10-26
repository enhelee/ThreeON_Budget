# -*- coding: utf-8 -*-
"""운영 PostgreSQL 백업·복원 — 표마다 CSV(gzip) + manifest.json.

왜: 2026-10 기준 자동 백업이 없었다(Supabase 무료 플랜). 이 스크립트를 이 PC 작업 스케줄러로
주 1회 돌린다. 원본은 read_only 연결로만 읽는다. 주 1회 DB 를 읽는 것은 무료 프로젝트가
«미사용»으로 일시정지되는 것을 막는 데도 도움이 될 것으로 본다(정책 기준은 미확인).

백업 폴더(기본: 문서\\ThreeON_DB백업\\YYYY-MM-DD_HHMM\\):
    <표>.csv.gz   COPY … TO STDOUT (FORMAT csv, HEADER) — 열 이름 포함
    manifest.json 표별 행 수·내용 해시(migrate_pg.fingerprint 와 같은 계산)·열 목록·DB 버전
⚠ 실데이터다 — 저장소 안에 두지 않는다(기본 위치가 저장소 밖인 이유).

사용(app 폴더에서):
    py scripts/backup_pg.py backup                 # app/.env 의 DATABASE_URL(운영)을 백업
    py scripts/backup_pg.py check <폴더>           # 파일 행 수 == manifest 인지(DB 접속 없음)
    py scripts/backup_pg.py restore <폴더>         # TARGET_DATABASE_URL(app/.env.migrate) 의
                                                   #  «빈» DB 로 복원 → 해시까지 검증
연결 문자열은 출력하지 않는다(호스트만).
"""
import argparse
import csv
import datetime as dt
import gzip
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(APP, "src"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import migrate_pg as mp   # noqa: E402

DEFAULT_ROOT = os.path.join(os.path.expanduser("~"), "Documents", "ThreeON_DB백업")


def _env_value(path, key):
    if not os.path.exists(path):
        return None
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if line.startswith(key + "="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def source_url():
    url = os.environ.get("BACKUP_DATABASE_URL") or _env_value(os.path.join(APP, ".env"), "DATABASE_URL")
    if not url or not url.lower().startswith(("postgres://", "postgresql://")):
        sys.exit("백업할 PostgreSQL 주소가 없습니다(app/.env 의 DATABASE_URL 또는 BACKUP_DATABASE_URL).")
    return url


def cmd_backup(root):
    url = source_url()
    stamp = dt.datetime.now().strftime("%Y-%m-%d_%H%M")
    out = os.path.join(root, stamp)
    os.makedirs(out, exist_ok=False)
    manifest = {"created_at": dt.datetime.now().isoformat(timespec="seconds"),
                "source_host": mp.host(url), "tables": {}}
    with mp.connect(url, read_only=True) as s:
        manifest["server_version"] = s.execute("SHOW server_version").fetchone()[0]
        total = 0
        for t in mp.app_tables(s):
            cols = mp.columns(s, t)
            n, h = mp.fingerprint(s, t, cols)
            collist = ", ".join(f'"{c}"' for c in cols)
            path = os.path.join(out, f"{t}.csv.gz")
            with gzip.open(path, "wb") as f, \
                    s.cursor().copy(f'COPY "{t}" ({collist}) TO STDOUT (FORMAT csv, HEADER)') as cp:
                for chunk in cp:
                    f.write(chunk)
            manifest["tables"][t] = {"rows": n, "hash": str(h), "columns": cols}
            total += n
            print(f"  {t:24} {n:>9,}행  {os.path.getsize(path) / 1e6:6.2f}MB")
    with open(os.path.join(out, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)
    bad = cmd_check(out, quiet=True)
    print(f"\n백업 완료: {out}  ({len(manifest['tables'])}개 표 · {total:,}행)"
          + ("  파일 검사 ✅" if not bad else f"  파일 검사 불일치 {bad}건 ❌"))
    return 1 if bad else 0


def _file_rows(path):
    with gzip.open(path, "rt", encoding="utf-8", newline="") as f:
        return sum(1 for _ in csv.reader(f)) - 1      # 머리글 제외 · 셀 안 줄바꿈도 한 행으로


def cmd_check(folder, quiet=False):
    m = json.load(open(os.path.join(folder, "manifest.json"), encoding="utf-8"))
    bad = 0
    for t, info in m["tables"].items():
        n = _file_rows(os.path.join(folder, f"{t}.csv.gz"))
        if n != info["rows"]:
            bad += 1
            print(f"★ {t}: 파일 {n}행 ≠ manifest {info['rows']}행")
        elif not quiet:
            print(f"  {t:24} {n:>9,}행 같음")
    if not quiet:
        print("결과:", "모두 같음 ✅" if not bad else f"불일치 {bad}건 ❌")
    return bad


def cmd_restore(folder):
    """빈 대상 DB 에 복원 — 한 트랜잭션. 행이 있는 DB 에는 하지 않는다(덮어쓰기 사고 방지)."""
    m = json.load(open(os.path.join(folder, "manifest.json"), encoding="utf-8"))
    dst = os.environ.get("TARGET_DATABASE_URL") or _env_value(mp.ENV_FILE, "TARGET_DATABASE_URL")
    if not dst:
        sys.exit("복원 대상 TARGET_DATABASE_URL 이 없습니다(app/.env.migrate 또는 환경변수).")
    if mp.host(dst) == m["source_host"] and dst == source_url():
        sys.exit("복원 대상이 운영 DB 와 같습니다 — 중단.")
    print(f"복원: {folder} → {mp.host(dst)}")
    with mp.connect(dst) as d:
        mp.create_schema(d)
        tables = list(m["tables"])
        nonempty = [t for t in tables if t in mp.app_tables(d) and mp.count(d, t)]
        if nonempty:
            sys.exit(f"대상에 이미 행이 있습니다: {nonempty} — 빈 DB 에만 복원합니다. 중단(변경 없음).")
        for t in mp.fk_order(d, tables):
            cols = m["tables"][t]["columns"]
            collist = ", ".join(f'"{c}"' for c in cols)
            with gzip.open(os.path.join(folder, f"{t}.csv.gz"), "rb") as f, \
                    d.cursor().copy(f'COPY "{t}" ({collist}) FROM STDIN (FORMAT csv, HEADER)') as cp:
                while chunk := f.read(1 << 20):
                    cp.write(chunk)
        for t in tables:
            if "id" in m["tables"][t]["columns"]:
                seq = d.execute("SELECT pg_get_serial_sequence(%s, 'id')", (t,)).fetchone()[0]
                if seq:
                    d.execute(f"SELECT setval('{seq}', COALESCE((SELECT MAX(id) FROM \"{t}\"), 1),"
                              f" (SELECT MAX(id) FROM \"{t}\") IS NOT NULL)")
        bad = 0
        for t, info in m["tables"].items():
            n, h = mp.fingerprint(d, t, info["columns"])
            ok = n == info["rows"] and str(h) == info["hash"]
            bad += not ok
            print(f"  {t:24} {n:>9,}행  {'같음' if ok else '★ 다름'}")
        if bad:
            d.rollback()
            print(f"\n불일치 {bad}건 — 되돌림(대상 변경 없음) ❌")
            return 1
        d.commit()
    print("\n복원 완료 · 행 수와 내용 해시 모두 백업과 같음 ✅")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["backup", "check", "restore"])
    ap.add_argument("folder", nargs="?", help="check·restore 할 백업 폴더")
    ap.add_argument("--root", default=DEFAULT_ROOT, help="backup 이 만들 폴더의 상위 경로")
    a = ap.parse_args()
    if a.cmd == "backup":
        return cmd_backup(a.root)
    if not a.folder:
        sys.exit("백업 폴더를 지정하세요.")
    if a.cmd == "check":
        return 1 if cmd_check(a.folder) else 0
    return cmd_restore(a.folder)


if __name__ == "__main__":
    sys.exit(main())
