# -*- coding: utf-8 -*-
"""배포 구성(Caddyfile · supervisord · entrypoint)의 구조 검사.

이 파일들은 컨테이너 안에서만 실행되므로 개발 PC(Docker 불가)에서는 돌려볼 수 없다.
그래서 «돌려보지 않아도 알 수 있는 실수»만 여기서 잡는다 — 실제로 배포를 두 번
깨뜨렸던 종류다(변경이력 2026-09-10: sed 가 범위를 잘못 잡아 닫는 괄호가 고아로 남음).

이 테스트가 Caddy 실행을 대신하지는 못한다. 문법 전체와 forward_auth 의 실제 동작은
Caddy 바이너리나 배포에서 확인해야 한다.
"""
import os
import re

DEPLOY = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "deploy")


def _read(name):
    with open(os.path.join(DEPLOY, name), encoding="utf-8") as f:
        return f.read()


def _strip_comments(text):
    return "\n".join(l.split("#", 1)[0] for l in text.split("\n"))


def test_caddyfile_braces_are_balanced():
    """고아 중괄호 = Caddy 기동 실패 = 배포 실패. 실제로 겪은 사고다."""
    body = _strip_comments(_read("Caddyfile"))
    assert body.count("{") == body.count("}"), "Caddyfile 중괄호 짝이 맞지 않습니다"


def test_forecast_is_guarded_by_forward_auth_not_basic_auth():
    """로그인 1회 — /forecast 는 앱 세션으로 열린다(기본인증 팝업 없음)."""
    body = _read("Caddyfile")
    block = re.search(r"handle /forecast\*\s*\{(.*?)\n\}", body, re.S)
    assert block, "Caddyfile 에 /forecast 블록이 없습니다"
    inner = _strip_comments(block.group(1))
    assert "forward_auth" in inner
    assert "basic_auth" not in inner, "기본인증이 남아 있으면 로그인이 2회가 된다"
    assert "reverse_proxy 127.0.0.1:8501" in inner


def test_forward_auth_target_is_verify_not_status():
    """가장 조용한 사고 경로 — /api/auth/status 는 비로그인에도 200 이라 전부 통과시킨다.

    설계서 §6.1 이 status 를 지목했으나 실제 응답을 보면 쓸 수 없다.
    (같은 내용을 API 쪽에서도 고정한다: test_auth_registry.test_forward_auth_target_is_401_until_login)
    """
    inner = _strip_comments(_read("Caddyfile"))
    assert "uri /api/auth/verify" in inner
    assert "uri /api/auth/status" not in inner


def test_no_dangling_import_of_removed_snippet():
    """import 대상이 없으면 Caddy 는 기동하지 못한다. entrypoint 도 더는 만들지 않는다."""
    caddyfile = _read("Caddyfile")
    entrypoint = _read("entrypoint.sh")
    assert "forecast_auth.caddy" not in _strip_comments(caddyfile)
    assert "AUTH_SNIPPET" not in entrypoint
    assert "hash-password" not in entrypoint


def test_caddy_upstreams_match_processes_supervisord_starts():
    """Caddy 가 가리키는 포트를 실제로 띄우는 프로세스가 있어야 한다."""
    ports = set(re.findall(r"reverse_proxy 127\.0\.0\.1:(\d+)", _read("Caddyfile")))
    ports |= set(re.findall(r"forward_auth 127\.0\.0\.1:(\d+)", _read("Caddyfile")))
    sup = _read("supervisord.conf")
    for p in ports:
        assert f"--port {p}" in sup or f"--server.port={p}" in sup, \
            f"Caddy 가 {p} 로 보내는데 supervisord 가 그 포트를 띄우지 않습니다"
