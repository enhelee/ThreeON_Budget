# -*- coding: utf-8 -*-
"""운영 서버 깨우기 — 발표 10분 전에 실행(경진대회 D, 시연 서버의 예비).

무료 호스팅은 한동안 요청이 없으면 잠든다. 첫 요청에 30~60초가 걸리고, 깬 뒤에도 서버가 뒤에서
전망·검토 큐 계산을 미리 채우는 데(예열) 1~2분이 더 든다. `/healthz?db=1` 을 DB 응답까지 확인될
때까지 부르고, 예열 시간을 기다린 뒤 «준비됨»을 알린다. 로그인 정보는 쓰지 않는다.

사용: python scripts/wake_prod.py [주소]   (기본 https://threeon-budget.onrender.com)
"""
import json
import sys
import time
import urllib.request

URL = (sys.argv[1] if len(sys.argv) > 1 else "https://threeon-budget.onrender.com").rstrip("/")
WARM_WAIT = 150          # 예열(server._warm_loop) 첫 바퀴를 기다리는 시간(초)


def ping():
    t = time.time()
    with urllib.request.urlopen(f"{URL}/healthz?db=1", timeout=90) as r:
        body = json.loads(r.read().decode("utf-8"))
    return body, time.time() - t


def main():
    print(f"{URL} 깨우는 중…")
    for i in range(20):
        try:
            body, sec = ping()
            if body.get("ok") and body.get("db_ok", True):
                print(f"응답 {sec:.1f}초 · 커밋 {body.get('commit')} · DB {body.get('db')}")
                break
            print(f"아직 준비 안 됨: {body}")
        except Exception as e:                  # 잠든 서버는 첫 요청이 끊기기도 한다
            print(f"{i + 1}번째 시도 실패({e.__class__.__name__}) — 10초 뒤 다시")
        time.sleep(10)
    else:
        sys.exit("서버가 깨지 않았습니다 — 시연 서버(run_demo.py)나 녹화본으로 진행하세요.")
    print(f"예열을 {WARM_WAIT}초 기다립니다(전망·검토 큐 계산)…")
    for left in range(WARM_WAIT, 0, -30):
        time.sleep(min(30, left))
        try:
            _, sec = ping()
            print(f"  살아 있음({sec:.1f}초) · 남은 {max(left - 30, 0)}초")
        except Exception as e:
            print(f"  응답 없음({e.__class__.__name__})")
    print("준비됨 — 브라우저에서 로그인해 메인 → 검토 큐 → 5번 화면을 한 번씩 열어 두세요.")


if __name__ == "__main__":
    main()
