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


def test_forward_auth_strips_websocket_upgrade_headers():
    """전망 앱은 WebSocket 으로 산다 — 인증 부속 요청에 업그레이드 헤더가 남으면 앱이 죽는다.

    forward_auth 는 원래 요청의 헤더를 그대로 달고 /api/auth/verify 로 묻는다.
    거기에 Connection: Upgrade / Upgrade: websocket 이 남아 있으면 uvicorn 이 그것을
    WebSocket 접속 시도로 읽고, 그 경로엔 WS 라우트가 없으니 403 으로 거절한다.
    forward_auth 는 2xx 가 아니면 통과시키지 않으므로 진짜 WebSocket 도 함께 끊긴다.

    실측(2026-09-15 배포): wss://.../forecast/_stcore/stream 핸드셰이크 403,
    서버 로그 "WebSocket /api/auth/verify" 403 — 같은 경로의 일반 GET 은 204 였다.
    화면은 HTML 까지만 뜨고 스켈레톤에서 멈췄다.
    """
    body = _read("Caddyfile")
    block = re.search(r"handle /forecast\*\s*\{(.*?)\n\}", body, re.S)
    assert block, "Caddyfile 에 /forecast 블록이 없습니다"
    inner = _strip_comments(block.group(1))
    auth = re.search(r"forward_auth[^\n]*\{(.*?)\n\t\}", inner, re.S)
    assert auth, "forward_auth 블록을 찾지 못했습니다"
    for field in ("-Connection", "-Upgrade"):
        assert f"header_up {field}" in auth.group(1), \
            f"인증 부속 요청에서 {field[1:]} 헤더를 떼지 않으면 전망 앱의 WebSocket 이 403 으로 끊깁니다"


def test_entrypoint_copies_builtin_templates_into_forecast_workdir():
    """전망 앱은 내장 양식을 상대경로로 읽는다 — 실행 폴더에 없으면 화면이 터진다.

    supervisord 가 FORECAST_DATA_DIR 에서 실행하므로 코드 폴더(/srv/forecast)의 양식이
    보이지 않는다. 실측(2026-09-15 배포):
      FileNotFoundError: 'builtin_template_중장기예산.xlsx'
        longterm_forecast_template.py:168 load_workbook(template_path)
    """
    entrypoint = _read("entrypoint.sh")
    assert "builtin_template_*.xlsx" in entrypoint, \
        "내장 양식을 실행 폴더로 복사하지 않으면 중장기 예산 화면이 FileNotFoundError 로 터집니다"
    assert "FORECAST_DATA_DIR" in entrypoint

    # 복사할 원본이 실제로 저장소에 있어야 한다.
    forecast_dir = os.path.join(os.path.dirname(DEPLOY), "forecast")
    tpls = [f for f in os.listdir(forecast_dir) if f.startswith("builtin_template_")]
    assert tpls, "forecast/ 에 내장 양식이 없습니다"


# ── Phase 5 — 배포 단순화 이후 지켜야 할 것들 ────────────────────────────

def test_old_app_path_redirects_instead_of_proxying():
    """/app/ 은 301 로 루트에 보내야 한다 — 팀원 북마크를 지키면서 주소를 하나로 모은다.

    예전에는 handle_path 로 «/app» 을 떼고 프록시했는데, 그러면 FastAPI 가 그 요청을
    «/» 로 보게 되어 SPA 를 그냥 돌려줬다. 301 이 나가지 않아 주소창이 /app/ 에 머물렀다.
    실측(2026-09-15 배포): GET /app/ -> 200 (301 이어야 했다).
    """
    body = _strip_comments(_read("Caddyfile"))
    assert "handle_path /app/*" not in body, "handle_path 는 접두어를 떼어 301 을 무력화합니다"
    block = re.search(r"handle /app\*\s*\{(.*?)\n\}", body, re.S)
    assert block and "redir / permanent" in block.group(1)


def test_intro_site_is_gone():
    """소개·문서 사이트(/site)는 SPA 가 흡수했다 — 서빙 경로가 남아 있으면 안 된다."""
    assert "/srv/site" not in _strip_comments(_read("Caddyfile"))
    assert "/srv/site" not in _read("Dockerfile")
    server = os.path.join(os.path.dirname(DEPLOY), "app", "server.py")
    with open(server, encoding="utf-8") as f:
        src = f.read()
    assert "SITE_DIR" not in src and '"/site' not in src


def test_entrypoint_seeds_config_json_into_config_dir():
    """구성 JSON 이 CONFIG_DIR 에 없으면 앱이 시드 기본값으로 시작한다.

    이미지의 구성은 /srv/app/config 에 있고 앱은 CONFIG_DIR 에서 읽는다.
    Render 무료 플랜은 /data 가 배포마다 초기화되므로, 이 복사가 없으면
    저장소에 정리해 둔 연도별 지사·과목 구성이 배포된 앱에 영영 반영되지 않는다.
    """
    entrypoint = _read("entrypoint.sh")
    assert "/srv/app/config/*.json" in entrypoint
    assert "CONFIG_DIR" in entrypoint


def test_dead_env_vars_are_removed():
    """basic_auth 폐지(Phase 4)·/site 삭제(Phase 5)로 죽은 값들.

    남겨 두면 "기본인증이 아직 있나?" 하는 오해를 부른다.
    """
    dockerfile = _read("Dockerfile")
    assert "BASIC_USER" not in dockerfile
    assert "SITE_DIR" not in dockerfile
    render = os.path.join(os.path.dirname(os.path.dirname(DEPLOY)), "render.yaml")
    if os.path.isfile(render):
        with open(render, encoding="utf-8") as f:
            blueprint = f.read()
        assert "BASIC_USER" not in blueprint
        assert "APP_REV" in blueprint, "메인 헤더 리비전이 dev 로 찍힙니다"
