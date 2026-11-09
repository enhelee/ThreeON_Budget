# -*- coding: utf-8 -*-
"""가짜 데이터(demo_data/)를 실행 중인 앱에 넣는다 — 화면에서 손으로 올리는 순서 그대로 API 로.

  python scripts/load_demo.py [http://localhost:8010]

순서: 기준정보 마스터 → 보정 규칙 → 연도마다(2016~2025) 계획·전표 업로드 → 분석 → 학습 → 마감
      → 2026 계획 업로드 → 중장기 전망 기준정보(정비등급·정기계약·투자계획·물가지수).
마감한 해의 실적이 표준화·중장기 전망의 입력이 된다. 비밀번호(APP_PASSWORD)를 켠 서버면
DEMO_PASSWORD 환경변수로 로그인한다. 빈 DB 에만 넣는다 — 자료가 하나라도 있는 서버(운영 등)면 아무것도 하지 않고 멈춘다.
"""
import http.cookiejar
import json
import os
import sys
import time
import urllib.request
import uuid

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(APP, "demo_data")
BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8010").rstrip("/")
OPENER = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))


def call(method, path, body=None, files=None):
    headers = {}
    data = None
    if files:
        boundary = uuid.uuid4().hex
        chunks = []
        for name, fpath in files:
            with open(fpath, "rb") as f:
                chunks.append(
                    f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"; "
                    f"filename=\"{os.path.basename(fpath)}\"\r\nContent-Type: application/octet-stream\r\n\r\n"
                    .encode() + f.read() + b"\r\n")
        data = b"".join(chunks) + f"--{boundary}--\r\n".encode()
        headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
    elif body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(BASE + path, data=data, method=method, headers=headers)
    try:
        with OPENER.open(req, timeout=600) as r:
            return json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        raise SystemExit(f"{method} {path} 실패 {e.code}: {e.read().decode()[:300]}")


def step(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def main():
    if call("GET", "/api/auth/status").get("enabled") and os.environ.get("DEMO_PASSWORD"):
        call("POST", "/api/login", {"password": os.environ["DEMO_PASSWORD"], "name": "시연데이터"})
    if call("GET", "/api/datasets"):
        raise SystemExit("이 서버에는 이미 올린 자료가 있습니다 — 실데이터와 섞이지 않게 빈 DB 에서만 넣습니다.")
    f = lambda n: os.path.join(DATA, n)
    step("기준정보 마스터(예산과목·부서코드)")
    call("POST", "/api/upload/master?kind=item&year=2016", files=[("file", f("마스터_예산과목.xlsx"))])
    call("POST", "/api/upload/master?kind=dept&year=2016", files=[("file", f("마스터_부서코드.xlsx"))])
    step("보정 규칙")
    call("POST", "/api/corr-rules", files=[("file", f("보정규칙.xlsx"))])
    for y in [str(y) for y in range(2016, 2026)]:
        step(f"{y} 계획·전표 업로드")
        call("POST", f"/api/upload/plan?year={y}", files=[("file", f(f"{y}_계획_양식1.xlsx"))])
        call("POST", f"/api/upload/erp?year={y}", files=[("file", f(f"{y}_zrfm2.xlsx"))])
        step(f"{y} 분석")
        res = call("POST", "/api/analyze", {"year": y})
        for b, v in res.items():
            s = v["요약"]
            print(f"    {b}: 총 실적 {s.get('총 실적(천원)', 0) / 1e5:,.1f}억 · 신규 {s.get('신규 실적(천원)', 0) / 1e5:,.1f}억")
        step(f"{y} 학습 · 마감")
        call("POST", "/api/learn", {"year": y})
        call("POST", "/api/lock", {"year": y})
    step("2026 계획 업로드(전망 기준연도)")
    call("POST", "/api/upload/plan?year=2026", files=[("file", f("2026_계획_양식1.xlsx"))])
    step("중장기 전망 기준정보")
    with open(f("전망_기준정보.json"), encoding="utf-8") as fh:
        fc = json.load(fh)
    by = fc["base_year"]
    call("PUT", "/api/forecast/state/grades", {"base_year": by, "rows": fc["grades"]})
    for table in ("regular-contract", "investment-plan", "price-index"):
        call("PUT", f"/api/forecast/state/{table}", {"base_year": by, "rows": fc[table.replace("-", "_")]})
    t = call("GET", f"/api/forecast/table?base_year={by}")
    step(f"완료 — 전망 표 지사 {len(t.get('tables', {}))}곳")


if __name__ == "__main__":
    main()
