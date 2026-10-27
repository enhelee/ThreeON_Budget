# -*- coding: utf-8 -*-
"""시연 서버 — 더미 DB(SQLite)로 이 PC 에서 앱을 띄운다(경진대회 D).

발표장에서 운영 서버(무료 호스팅)를 쓰면 첫 접속에 30~60초 콜드 스타트가 걸리고, 실데이터가 화면에 나온다.
이 PC 에서 더미 DB 로 띄우면 둘 다 없다. 운영 DB 로 새지 않게 DATABASE_URL·APP_PASSWORD 를 «빈 값»으로
먼저 넣는다(.env 는 이미 있는 값을 덮지 않는다). 계산 캐시는 서버가 뜨자마자 미리 채운다(CACHE_WARM=1).

사용: python scripts/run_demo.py [더미 폴더] [포트]
      더미 폴더 기본값 = 저장소 바깥 «시연용_더미DB»(scripts/make_demo_db.py 가 만든 곳)
"""
import os
import sys
import webbrowser

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DATA = os.path.normpath(os.path.join(APP_DIR, "..", "..", "..", "시연용_더미DB"))


def main():
    data = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DATA
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 8020
    db = os.path.join(data, "budget.db")
    if not os.path.exists(db):
        sys.exit(f"더미 DB 가 없습니다: {db}\n먼저 scripts/make_demo_db.py 로 만드세요.")
    os.environ["DATABASE_URL"] = ""          # 운영 PostgreSQL 로 붙지 않게(빈 값 = SQLite)
    os.environ["APP_PASSWORD"] = ""          # 시연은 로그인 없이
    os.environ["DATA_DIR"] = data
    os.environ["CACHE_WARM"] = "1"           # 전망·검토 큐 계산을 미리
    os.chdir(APP_DIR)
    sys.path.insert(0, APP_DIR)
    sys.path.insert(0, os.path.join(APP_DIR, "src"))
    import uvicorn
    print(f"시연 서버: http://localhost:{port}  (더미 DB {db})")
    webbrowser.open(f"http://localhost:{port}")
    uvicorn.run("server:app", host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
