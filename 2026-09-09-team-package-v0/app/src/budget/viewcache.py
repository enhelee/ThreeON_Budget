# -*- coding: utf-8 -*-
"""계산 결과 캐시 — 무거운 화면 계산(전망 표·표준화·검토 대기)을 «자료가 바뀌지 않았으면» 다시 쓴다.

«바뀌었는가»의 근거는 감사 로그(audit_log)의 최신 id 다. 이 앱의 모든 쓰기(POST/PUT/PATCH/DELETE /api/*)는
응답 전에 감사 로그를 남기므로(AuthAuditMiddleware) 쓰기가 있으면 버전이 바뀐다.

2026-10-27 바꾼 것(운영 점검: 전망 첫 계산 28초가 자주 다시 났다)
  - 숫자와 무관한 기록은 버전에서 뺀다 — 로그인·로그아웃은 감사 로그에 남아 로그인할 때마다 전망 캐시가
    비워졌고, 차이 사유·검토 승인도 전망 숫자를 바꾸지 않는다. 거절된 요청(4xx·5xx)도 바뀐 것이 없다.
  - 유효 시간 10분 → 6시간. 버전 키가 있어 오래 둬도 옛 값이 아니다(시간 제한은 감사 기록이 실패한 드문
    경우의 안전판일 뿐).
  - 같은 키를 두 요청이 동시에 계산하지 않는다(키별 잠금) — 예열 중 들어온 요청은 기다렸다가 같은 결과를 쓴다.
프로세스 메모리에만 둔다(배포·재시작 때 비워짐 → server 의 예열이 다시 채운다).
"""
import threading
import time

from . import db as dbm

TTL = 6 * 3600
MAX_ENTRIES = 32

# 숫자에 영향이 없는 쓰기 — 버전 계산에서 뺀다
SESSION_PATHS = ("/api/login", "/api/logout")
NOTE_PATHS = ("/api/variance-note", "/api/review-ack")

_CACHE = {}
_GUARD = threading.Lock()
_KEY_LOCKS = {}


def data_version(conn, ignore=SESSION_PATHS + NOTE_PATHS):
    """숫자를 바꿀 수 있는 마지막 쓰기의 감사 로그 id(없으면 0)."""
    # MAX() 대신 «id 역순 첫 줄» — 감사 로그가 커져도 기본키를 거꾸로 읽다 첫 해당 줄에서 멈춘다.
    ph = ",".join("?" for _ in ignore)
    sql = "SELECT id FROM audit_log WHERE (status IS NULL OR status < 400)"
    if ignore:
        sql += f" AND path NOT IN ({ph})"
    row = conn.execute(sql + " ORDER BY id DESC LIMIT 1", tuple(ignore)).fetchone()
    return row[0] if row else 0


def _db_id():
    # DB 가 바뀌면(테스트의 임시 DB · 지역 이전 후 새 DATABASE_URL) 다른 답이다.
    return dbm.dbcore.database_url() or dbm.DEFAULT_DB


def get_or_compute(key, version, compute, ttl=TTL):
    """(key, version) 이 같고 ttl 안이면 저장된 값, 아니면 계산해 저장. 같은 key 는 한 번에 하나만 계산한다."""
    full = (_db_id(),) + tuple(key)
    hit = _CACHE.get(full)
    if hit and hit[0] == version and time.monotonic() - hit[1] < ttl:
        return hit[2]
    with _GUARD:
        lk = _KEY_LOCKS.setdefault(full, threading.Lock())
    with lk:
        hit = _CACHE.get(full)                 # 기다리는 동안 다른 요청이 채웠을 수 있다
        if hit and hit[0] == version and time.monotonic() - hit[1] < ttl:
            return hit[2]
        out = compute()
        with _GUARD:
            if len(_CACHE) >= MAX_ENTRIES and full not in _CACHE:
                _CACHE.pop(min(_CACHE, key=lambda k: _CACHE[k][1]))
            _CACHE[full] = (version, time.monotonic(), out)
        return out


def cached(key, version):
    """저장돼 있고 버전이 같으면 그 값, 아니면 None(계산하지 않는다)."""
    hit = _CACHE.get((_db_id(),) + tuple(key))
    return hit[2] if hit and hit[0] == version and time.monotonic() - hit[1] < TTL else None


def clear():
    with _GUARD:
        _CACHE.clear()
