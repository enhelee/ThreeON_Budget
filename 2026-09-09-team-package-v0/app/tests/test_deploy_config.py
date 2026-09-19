# -*- coding: utf-8 -*-
"""배포 구성(Dockerfile · entrypoint · compose)의 구조 검사.

이 파일들은 컨테이너 안에서만 실행되므로 개발 PC(Docker 불가)에서는 돌려볼 수 없다.
그래서 «돌려보지 않아도 알 수 있는 실수»만 여기서 잡는다 — 실제로 배포를 두 번
깨뜨렸던 종류다(변경이력 2026-09-10: sed 가 범위를 잘못 잡아 닫는 괄호가 고아로 남음).

Phase 6-8 에서 Caddy·supervisord·Streamlit 이 사라졌다. 프로세스는 uvicorn 하나다.
그래서 이 파일의 절반(Caddyfile 문법·forward_auth·업스트림 포트·양식 복사)은 검사할
대상이 없어져 삭제했고, 대신 **그 삭제가 되돌아오지 않게** 하는 검사와 «uvicorn 이
혼자 서 있을 때 반드시 맞아야 하는 것»을 넣었다. 후자는 틀리면 배포가 통째로 죽는데
이 PC 에서는 Docker 가 없어 실행으로 잡을 수 없다 — 이 테스트가 유일한 그물이다.
"""
import os

DEPLOY = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "deploy")


def _read(name):
    with open(os.path.join(DEPLOY, name), encoding="utf-8") as f:
        return f.read()


def _strip_comments(text):
    return "\n".join(l.split("#", 1)[0] for l in text.split("\n"))


# ── Phase 6-8 — 프로세스 하나(uvicorn) ───────────────────────────────────

def test_caddy_and_supervisor_configs_are_gone():
    """삭제가 되돌아오면 «프로세스 하나»라는 완료 기준이 조용히 깨진다."""
    for name in ("Caddyfile", "supervisord.conf"):
        assert not os.path.exists(os.path.join(DEPLOY, name)), \
            f"{name} 이 남아 있습니다 — 6-8 에서 삭제한 파일입니다"


def test_entrypoint_execs_uvicorn_directly():
    """supervisord 없이 uvicorn 이 PID 1 이 된다 — exec 여야 신호가 앱까지 닿는다."""
    body = _strip_comments(_read("entrypoint.sh"))
    assert "supervisord" not in body, "supervisord 는 6-8 에서 사라졌습니다"
    assert "streamlit" not in body.lower()
    last = [l for l in body.strip().split("\n") if l.strip()][-1]
    assert last.startswith("exec "), "exec 가 아니면 SIGTERM 이 uvicorn 에 닿지 않습니다"
    assert "uvicorn" in last


def test_uvicorn_binds_the_public_port():
    """가장 비싼 실수 — 앞에 아무도 없으므로 127.0.0.1 로 묶으면 배포가 통째로 죽는다.

    Caddy 가 있던 동안에는 uvicorn 이 127.0.0.1:8010 이 맞았다(Caddy 만 접속했다).
    Caddy 를 지우면서 이 줄을 그대로 두면 컨테이너는 «정상 기동»하고 헬스체크만 실패한다.
    """
    body = _strip_comments(_read("entrypoint.sh"))
    assert "--host 0.0.0.0" in body, "0.0.0.0 으로 열지 않으면 밖에서 아무도 닿지 못합니다"
    assert "127.0.0.1" not in body
    assert "PORT" in body, "$PORT 를 쓰지 않으면 PaaS 가 지정한 포트를 놓칩니다"
    assert "8010" not in body, "8010 은 Caddy 뒤에 숨어 있을 때 쓰던 내부 포트입니다"


def test_uvicorn_trusts_proxy_headers():
    """TLS 는 Render·사내 프록시가 종단한다 — 이게 없으면 앱이 요청을 http 로 보고
    COOKIE_SECURE=1 쿠키를 거부당하거나 리다이렉트를 http 로 만든다."""
    body = _strip_comments(_read("entrypoint.sh"))
    assert "--proxy-headers" in body
    assert "--forwarded-allow-ips" in body


def test_server_header_is_suppressed():
    """Caddyfile 의 `-Server` 자리. 서버 종류·버전을 굳이 알리지 않는다."""
    assert "--no-server-header" in _strip_comments(_read("entrypoint.sh"))


def test_dockerfile_has_no_caddy_supervisor_or_forecast():
    """이미지에서 셋을 빼는 것이 6-8 의 결과물이다.

    Caddy 내려받기(RUN curl github.com/caddyserver/...)가 사라지면서, 사내 TLS 프록시
    환경에서 GitHub 릴리스 자산을 못 받아 빌드가 깨지던 위험도 함께 사라졌다.
    """
    body = _strip_comments(_read("Dockerfile"))   # 주석의 이력 설명은 허용, 명령만 본다
    low = body.lower()
    assert "caddy" not in low
    assert "supervisor" not in low
    assert "COPY forecast/" not in body, "v2 앱은 6-8 에서 저장소에서 사라졌습니다"
    assert "FORECAST_DATA_DIR" not in body


def test_runtime_workdir_is_app_dir():
    """supervisord 의 `directory=/srv/app` 자리 — 마지막 WORKDIR 이 /srv/app 이어야 한다.

    앱은 경로를 __file__·환경변수로 풀어 지금은 CWD 에 안 기대지만, 흡수한 v2 계산부는
    CWD 상대경로로 양식을 읽다 터진 이력이 있다(2026-09-15). 실행 폴더를 예전과 같게 둔다.
    """
    lines = [l.strip() for l in _strip_comments(_read("Dockerfile")).splitlines()]
    workdirs = [l for l in lines if l.startswith("WORKDIR ")]
    assert workdirs and workdirs[-1] == "WORKDIR /srv/app", workdirs


def test_deploy_requirements_have_no_streamlit():
    """전망 앱이 사라졌으니 이미지에 Streamlit 을 넣을 이유가 없다(설치 시간·크기)."""
    assert "streamlit" not in _read("requirements.txt").lower()


def test_pandas_pin_survives_streamlit_removal():
    """고정 이유는 Streamlit 이었지만 budget_app 이 그 조합에서 검증됐다.

    ⚠ pandas 3.0 은 기본 str dtype 이 달라 classify/plan_summary/excel_plan_writer 의
    결측 처리가 바뀐다(pd.isna 가드 설계). 푸는 것은 별건이다 — 같이 풀지 않는다.
    """
    assert "pandas==2.2.3" in _read("requirements.txt")


def test_compose_has_no_forecast_volume():
    """v2 앱이 CWD 에 쓰던 CSV·모델을 담던 볼륨. 상태는 이제 DB 에 있다."""
    body = _read("docker-compose.yml")
    assert "forecast_data" not in body
    assert "/data/forecast" not in body
    assert "budget_data" in body, "budget 볼륨까지 지우면 SQLite 모드가 비영속이 됩니다"


# ── 앞선 Phase 에서 지킨 것들 (대상이 남아 있는 것만) ────────────────────

def test_no_dangling_auth_snippet_in_entrypoint():
    """basic_auth 폐지(Phase 4) — 기동 시 bcrypt 해시를 만들던 조각은 없어야 한다."""
    entrypoint = _read("entrypoint.sh")
    assert "AUTH_SNIPPET" not in entrypoint
    assert "hash-password" not in entrypoint
    assert "forecast_auth.caddy" not in entrypoint


def test_intro_site_is_gone():
    """소개·문서 사이트(/site)는 SPA 가 흡수했다 — 서빙 경로가 남아 있으면 안 된다."""
    assert "/srv/site" not in _read("Dockerfile")
    server = os.path.join(os.path.dirname(DEPLOY), "app", "server.py")
    with open(server, encoding="utf-8") as f:
        src = f.read()
    assert "SITE_DIR" not in src and '"/site' not in src


def test_config_dir_is_gone():
    """구성은 DB 에 산다 — 파일 경로가 남아 있으면 진실이 두 곳에 생긴다.

    Phase 5 에서 넣었던 «구성 JSON 복사»는 복사할 대상이 저장소에도 이미지에도
    없어(.gitignore·.dockerignore 양쪽에 걸려 있었다) 아무 일도 하지 않는
    코드였다. 연도별 기준정보를 DB 로 옮기며 함께 걷어냈다.
    """
    assert "CONFIG_DIR" not in _read("Dockerfile")
    entrypoint = _read("entrypoint.sh")
    assert "CONFIG_DIR" not in entrypoint
    assert "/srv/app/config" not in entrypoint
    server = os.path.join(os.path.dirname(DEPLOY), "app", "server.py")
    with open(server, encoding="utf-8") as f:
        assert "CONFIG_DIR" not in f.read()


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


def test_old_app_path_redirect_is_pythons_job():
    """/app/ 301 은 파이썬이 낸다 — Caddy 가 사라져도 그대로다.

    Caddy 시절 두 번 틀렸던 자리다(handle_path 가 접두어를 떼어 301 을 무력화 ·
    Caddy redir 의 «/» 가 매처로 파싱되어 빈 200). 그래서 파이썬으로 옮겼고,
    이제는 그 라우트가 유일한 구현이다(test_export_status.test_old_app_path_returns_301).
    """
    server = os.path.join(os.path.dirname(DEPLOY), "app", "server.py")
    with open(server, encoding="utf-8") as f:
        src = f.read()
    assert "def app_redirect" in src and "301" in src
