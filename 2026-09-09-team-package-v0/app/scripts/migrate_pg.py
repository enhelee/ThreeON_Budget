# -*- coding: utf-8 -*-
"""PostgreSQL → PostgreSQL 이전(같은 앱 스키마) — Supabase 지역 이전용.

왜: 운영 앱은 Render 싱가포르, DB 는 Supabase 서울(ap-northeast-2)이라 질의 한 번이
~75ms 왕복이다(2026-10-15 실측). DB 를 앱과 같은 지역(ap-southeast-1)의 새 프로젝트로
옮기고 Render 의 DATABASE_URL 만 바꾼다. 원본은 읽기 전용으로만 연다 — 되돌리기는
DATABASE_URL 을 원래 값으로 돌리는 것.

연결 문자열은 화면·로그에 찍지 않는다(호스트만). 파일 하나에 둔다(.gitignore 의 `.env.*`):

    app/.env.migrate
        TARGET_DATABASE_URL=postgresql://…ap-southeast-1.pooler.supabase.com:5432/postgres?sslmode=require
        # SOURCE_DATABASE_URL=…   (생략하면 app/.env 의 DATABASE_URL — 지금 운영 DB)

사용(app 폴더에서):
    py scripts/migrate_pg.py check            # 양쪽 접속·버전·표·행 수·왕복 시간(쓰기 없음)
    py scripts/migrate_pg.py copy             # 대상에 표 생성 → 전 표 COPY → 시퀀스 맞춤 → verify
    py scripts/migrate_pg.py copy --replace   # 대상에 이미 행이 있으면 비우고 다시(리허설 반복용)
    py scripts/migrate_pg.py verify           # 표마다 행 수 + 내용 해시 비교(쓰기 없음)

copy 는 대상 하나의 트랜잭션이다 — 중간에 실패하면 대상은 copy 전 상태로 남는다.
"""
import argparse
import os
import sys
import time
import urllib.parse

sys.stdout.reconfigure(encoding="utf-8")
APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(APP, "src"))

import psycopg   # noqa: E402

from budget import dbcore   # noqa: E402

ENV_FILE = os.path.join(APP, ".env.migrate")


def load_urls(path=ENV_FILE):
    vals = {}
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                vals[k.strip()] = v.strip().strip('"').strip("'")
    src = os.environ.get("SOURCE_DATABASE_URL") or vals.get("SOURCE_DATABASE_URL")
    if not src:                          # 없으면 지금 앱이 쓰는 주소(app/.env 의 DATABASE_URL)가 원본
        env = os.path.join(APP, ".env")
        if os.path.exists(env):
            for line in open(env, encoding="utf-8"):
                if line.strip().startswith("DATABASE_URL="):
                    src = line.split("=", 1)[1].strip().strip('"').strip("'")
    dst = os.environ.get("TARGET_DATABASE_URL") or vals.get("TARGET_DATABASE_URL")
    if not src or not dst:
        sys.exit(f"SOURCE_DATABASE_URL·TARGET_DATABASE_URL 이 필요합니다 ({path} 또는 환경변수).")
    if urllib.parse.urlsplit(src).hostname == urllib.parse.urlsplit(dst).hostname and \
            urllib.parse.urlsplit(src).username == urllib.parse.urlsplit(dst).username:
        sys.exit("원본과 대상이 같은 DB 입니다 — 중단.")
    return src, dst


def host(url):
    u = urllib.parse.urlsplit(url)
    return f"{u.hostname}:{u.port or 5432}"


def connect(url, read_only=False):
    conn = psycopg.connect(url, prepare_threshold=None)
    if read_only:
        conn.read_only = True            # 원본 보호 — 이 연결로는 어떤 쓰기도 서버가 거부한다
    return conn


def app_tables(conn):
    rows = conn.execute(
        "SELECT table_name FROM information_schema.tables"
        " WHERE table_schema=current_schema() AND table_type='BASE TABLE' ORDER BY table_name").fetchall()
    return [r[0] for r in rows]


def columns(conn, table):
    return [r[0] for r in conn.execute(
        "SELECT column_name FROM information_schema.columns"
        " WHERE table_schema=current_schema() AND table_name=%s ORDER BY ordinal_position", (table,))]


def count(conn, table):
    return conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]


def fingerprint(conn, table, cols):
    """행 수 + 순서 무관 내용 해시(행 텍스트 md5 의 합). 큰 표도 서버 메모리를 거의 안 쓴다."""
    collist = ", ".join(f'"{c}"' for c in cols)
    n, h = conn.execute(
        f"SELECT COUNT(*), COALESCE(SUM(('x' || substr(md5(ROW({collist})::text), 1, 15))::bit(60)::bigint), 0)"
        f' FROM "{table}"').fetchone()
    return n, int(h)


def fk_order(conn, tables):
    """참조되는 표가 먼저 오게(외래키) — COPY 중 FK 위반을 피한다."""
    deps = {t: set() for t in tables}
    for child, parent in conn.execute(
            "SELECT c.conrelid::regclass::text, c.confrelid::regclass::text FROM pg_constraint c"
            " WHERE c.contype='f' AND c.connamespace = current_schema()::regnamespace"):
        child, parent = child.strip('"'), parent.strip('"')
        if child in deps and parent in deps and child != parent:
            deps[child].add(parent)
    out, seen = [], set()

    def visit(t):
        if t in seen:
            return
        seen.add(t)
        for p in sorted(deps[t]):
            visit(p)
        out.append(t)
    for t in sorted(tables):
        visit(t)
    return out


def rtt_ms(conn, n=10):
    t = time.perf_counter()
    for _ in range(n):
        conn.execute("SELECT 1").fetchone()
    return (time.perf_counter() - t) * 1000 / n


def cmd_check(src_url, dst_url):
    with connect(src_url, read_only=True) as s, connect(dst_url) as d:
        for name, url, c in (("원본", src_url, s), ("대상", dst_url, d)):
            ver = c.execute("SHOW server_version").fetchone()[0]
            print(f"{name}: {host(url)}  PostgreSQL {ver}  왕복(이 PC 기준) {rtt_ms(c):.0f}ms")
        st, dt = app_tables(s), app_tables(d)
        print(f"\n원본 표 {len(st)}개 · 대상 표 {len(dt)}개")
        print(f"{'표':24} {'원본 행':>10} {'대상 행':>10}")
        for t in st:
            print(f"{t:24} {count(s, t):>10,} {count(d, t) if t in dt else '-':>10}")
        missing = sorted(set(st) - set(dt))
        if missing:
            print(f"\n대상에 아직 없는 표 {len(missing)}개 — copy 가 앱 스키마로 만든다.")


def create_schema(dst_raw):
    """대상에 앱 스키마 생성 — 앱이 처음 뜰 때와 같은 init_db(같은 표·열·인덱스·제약)."""
    from budget import db as dbm
    dbm.init_db(dbcore.PgConnection(dst_raw))


def cmd_copy(src_url, dst_url, replace=False):
    with connect(src_url, read_only=True) as s, connect(dst_url) as d:
        create_schema(d)                 # 같은 트랜잭션 — 실패하면 표 생성까지 되돌아간다
        st, dt = app_tables(s), set(app_tables(d))
        missing = sorted(set(st) - dt)
        if missing:
            sys.exit(f"대상 스키마에 없는 원본 표: {missing} — 앱 버전이 다릅니다. 중단(대상 변경 없음).")
        nonempty = [t for t in st if count(d, t)]
        if nonempty and not replace:
            sys.exit(f"대상에 이미 행이 있습니다: {nonempty} — 리허설을 다시 하려면 --replace. 중단.")
        order = fk_order(d, st)
        if replace:
            d.execute("TRUNCATE " + ", ".join(f'"{t}"' for t in order) + " RESTART IDENTITY CASCADE")
        t0 = time.perf_counter()
        for t in order:
            cols = [c for c in columns(s, t)]
            dcols = set(columns(d, t))
            lost = [c for c in cols if c not in dcols]
            if lost:
                sys.exit(f"{t}: 대상에 없는 열 {lost} — 중단(대상 변경 없음).")
            collist = ", ".join(f'"{c}"' for c in cols)
            n = 0
            t1 = time.perf_counter()
            with s.cursor().copy(f'COPY "{t}" ({collist}) TO STDOUT') as cin, \
                    d.cursor().copy(f'COPY "{t}" ({collist}) FROM STDIN') as cout:
                for chunk in cin:
                    cout.write(chunk)
                    n += len(chunk)
            print(f"  {t:24} {count(d, t):>10,}행  {n / 1e6:6.1f}MB  {time.perf_counter() - t1:5.1f}s")
        # BIGSERIAL 시퀀스를 max(id) 로 — 안 맞추면 앱의 첫 INSERT 가 기존 id 와 부딪힌다
        for t in order:
            if "id" in columns(d, t):
                seq = d.execute("SELECT pg_get_serial_sequence(%s, 'id')", (t,)).fetchone()[0]
                if seq:
                    d.execute(f"SELECT setval('{seq}', COALESCE((SELECT MAX(id) FROM \"{t}\"), 1),"
                              f" (SELECT MAX(id) FROM \"{t}\") IS NOT NULL)")
        d.commit()
        print(f"\n복사 완료 {time.perf_counter() - t0:.0f}초 — 검증합니다.\n")
    return cmd_verify(src_url, dst_url)


def cmd_verify(src_url, dst_url):
    bad = 0
    with connect(src_url, read_only=True) as s, connect(dst_url, read_only=True) as d:
        dt = set(app_tables(d))
        print(f"{'표':24} {'원본 행':>10} {'대상 행':>10}  내용")
        for t in app_tables(s):
            cols = columns(s, t)
            a = fingerprint(s, t, cols)
            b = fingerprint(d, t, cols) if t in dt else (None, None)
            ok = a == b
            bad += not ok
            print(f"{t:24} {a[0]:>10,} {b[0] if b[0] is not None else '-':>10}  {'같음' if ok else '★ 다름'}")
        # 시퀀스가 max(id) 이상인지 — 앱의 다음 INSERT 가 안전한지
        for t in app_tables(d):
            if "id" in columns(d, t):
                seq = d.execute("SELECT pg_get_serial_sequence(%s, 'id')", (t,)).fetchone()[0]
                if seq:
                    last = d.execute(f"SELECT last_value FROM {seq}").fetchone()[0]
                    mx = d.execute(f'SELECT COALESCE(MAX(id), 0) FROM "{t}"').fetchone()[0]
                    if last < mx:
                        bad += 1
                        print(f"★ {t}: 시퀀스 {last} < max(id) {mx}")
    print("\n결과:", "모두 같음 ✅" if not bad else f"불일치 {bad}건 ❌")
    return 0 if not bad else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["check", "copy", "verify"])
    ap.add_argument("--replace", action="store_true", help="대상의 기존 행을 비우고 다시 복사(리허설 반복)")
    ap.add_argument("--env-file", default=ENV_FILE)
    a = ap.parse_args()
    src, dst = load_urls(a.env_file)
    print(f"원본 {host(src)} (읽기 전용) → 대상 {host(dst)}\n")
    if a.cmd == "check":
        cmd_check(src, dst)
        return 0
    if a.cmd == "copy":
        return cmd_copy(src, dst, replace=a.replace)
    return cmd_verify(src, dst)


if __name__ == "__main__":
    sys.exit(main())
