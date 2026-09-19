# -*- coding: utf-8 -*-
"""사내 이관 패키지(deploy/onprem · .env.example · 가이드)의 구조 검사 (Phase 6-9).

이 PC 에는 Docker 가 없다. 스크립트가 실제로 도는지는 사용자 측 Docker PC 에서 처음
확인된다. 그래서 여기서는 «돌려보지 않아도 알 수 있는 실수»만 잡는다 —
오프라인 서버에서 빌드를 시도하는 것, 커밋 해시를 안 넘겨 /healthz 가 비는 것,
.env.example 에 죽은 키가 남아 팀원이 없는 변수를 채우는 것.
"""
import os
import re

PKG = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEPLOY = os.path.join(PKG, "deploy")
ONPREM = os.path.join(DEPLOY, "onprem")
APP = os.path.join(PKG, "app")


def _read(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as f:
        return f.read()


def _strip_comments(text, marker="#"):
    return "\n".join(l.split(marker, 1)[0] for l in text.split("\n"))


SCRIPTS = ["build_image", "load_and_run", "check"]


# ── 스크립트 6개 ─────────────────────────────────────────────────────────

def test_scripts_exist_in_both_flavors():
    """서버 OS 가 미정이라 Linux(.sh)·Windows(.ps1) 두 벌을 같은 이름으로 둔다."""
    for name in SCRIPTS:
        for ext in (".sh", ".ps1"):
            assert os.path.isfile(os.path.join(ONPREM, name + ext)), f"{name}{ext} 이 없습니다"


def test_shell_scripts_fail_fast():
    """`set -eu` 가 없으면 중간 실패를 지나쳐 «올라온 것처럼» 보인다."""
    for name in SCRIPTS:
        body = _read(ONPREM, name + ".sh")
        assert body.startswith("#!/usr/bin/env bash"), f"{name}.sh: bash 셔뱅"
        assert re.search(r"^set -eu", body, re.M), f"{name}.sh: set -eu 가 없습니다"


def test_powershell_scripts_fail_fast():
    for name in SCRIPTS:
        body = _read(ONPREM, name + ".ps1")
        assert '$ErrorActionPreference = "Stop"' in body, f"{name}.ps1: Stop 이 아니면 오류를 지나칩니다"


def test_server_side_never_builds():
    """가장 비싼 실수 — 인터넷 없는 서버에서 빌드가 걸리면 조용히 오래 실패한다."""
    for ext in (".sh", ".ps1"):
        body = _strip_comments(_read(ONPREM, "load_and_run" + ext))
        assert "--no-build" in body, f"load_and_run{ext}: compose up 에 --no-build 가 없습니다"
        assert "docker build" not in body, f"load_and_run{ext}: 서버에서 빌드하면 안 됩니다"
        assert "docker load" in body


def test_build_passes_commit_into_image():
    """/healthz 의 commit 은 사내에서도 찍혀야 한다 — 배포 판별의 유일한 근거다.

    Render 는 RENDER_GIT_COMMIT 을 자동으로 넣어 주지만 사내 이미지는 아무도 안 넣는다.
    빌드 인자로 넘기고 Dockerfile 이 ENV 로 굳힌다.
    """
    for ext in (".sh", ".ps1"):
        body = _strip_comments(_read(ONPREM, "build_image" + ext))
        assert "--build-arg APP_COMMIT=" in body, f"build_image{ext}: APP_COMMIT 을 넘기지 않습니다"
        assert "docker save" in body
    dockerfile = _strip_comments(_read(DEPLOY, "Dockerfile"))
    assert re.search(r"^ARG APP_COMMIT", dockerfile, re.M), "Dockerfile: ARG APP_COMMIT"
    assert "APP_COMMIT=${APP_COMMIT}" in dockerfile, "Dockerfile: ENV 로 굳히지 않으면 런타임에 사라집니다"


def test_scripts_agree_on_image_name():
    """build 가 만드는 이름·compose 가 찾는 이름·load 가 다는 태그가 같아야 한다."""
    compose = _strip_comments(_read(DEPLOY, "docker-compose.yml"))
    assert "image: threeon-budget:latest" in compose
    for name in ("build_image", "load_and_run"):
        for ext in (".sh", ".ps1"):
            assert "threeon-budget" in _strip_comments(_read(ONPREM, name + ext)), f"{name}{ext}"


def test_compose_never_pulls_from_registry():
    """오프라인 서버가 이미지를 못 찾으면 레지스트리를 뒤지다 시간을 끈다 — 바로 실패해야 한다."""
    compose = _strip_comments(_read(DEPLOY, "docker-compose.yml"))
    assert "pull_policy: never" in compose


# ── .env.example ─────────────────────────────────────────────────────────

def _env_example_keys():
    keys = set()
    for line in _read(PKG, ".env.example").split("\n"):
        m = re.match(r"^([A-Z_][A-Z0-9_]*)=", line.strip())
        if m:
            keys.add(m.group(1))
    return keys


def _keys_read_by_code():
    src = ""
    src += _read(APP, "server.py")
    for f in os.listdir(os.path.join(APP, "src", "budget")):
        if f.endswith(".py"):
            src += _read(APP, "src", "budget", f)
    return set(re.findall(r"environ(?:\.get)?\(\s*['\"]([A-Z_][A-Z0-9_]*)['\"]", src)) \
        | set(re.findall(r"getenv\(\s*['\"]([A-Z_][A-Z0-9_]*)['\"]", src))


def _keys_read_by_compose():
    return set(re.findall(r"\$\{([A-Z_][A-Z0-9_]*)[:?]", _read(DEPLOY, "docker-compose.yml")))


def test_env_example_has_no_dead_keys():
    """죽은 키가 남으면 팀원이 «이 값도 채워야 하나» 하고 없는 변수를 채운다.

    FORECAST_URL(6-6 에서 iframe 과 함께 소멸)·BASIC_USER(Phase 4 basic_auth 폐지)·
    APP_ENV(읽는 코드가 없다)가 실제로 남아 있었다.
    """
    documented = _env_example_keys()
    readable = _keys_read_by_code() | _keys_read_by_compose()
    dead = documented - readable
    assert not dead, f".env.example 에 아무도 읽지 않는 키가 있습니다: {sorted(dead)}"


def test_env_example_documents_every_secret_the_app_needs():
    """반대로 앱이 읽는 비밀·설정이 예시에 없으면 사내 첫 세팅 때 코드를 읽어야 한다."""
    documented = _env_example_keys()
    # 플랫폼이 넣는 값(RENDER_GIT_COMMIT · APP_COMMIT)과 컨테이너가 정하는 값(PORT · DATA_DIR ·
    # OUT_DIR)은 사람이 .env 에 쓰는 것이 아니다.
    must = {"APP_PASSWORD", "SECRET_KEY", "SESSION_HOURS", "COOKIE_SECURE", "DATABASE_URL",
            "APP_REV", "HOST_PORT", "PG_PASSWORD"}
    missing = must - documented
    assert not missing, f".env.example 에 빠진 키: {sorted(missing)}"


def test_env_example_explains_both_locations():
    """로컬은 app/.env, Docker 는 패키지 루트 .env — 다른 자리라 명시하지 않으면 헤맨다."""
    body = _read(PKG, ".env.example")
    assert "app/.env" in body and "compose" in body.lower()


# ── 가이드 ───────────────────────────────────────────────────────────────

def test_onprem_guide_covers_the_whole_path():
    guide = _read(PKG, "docs", "사내이관_가이드.md")
    for needle in ("build_image", "docker load", "load_and_run", "--no-build", "/healthz",
                   "check.", "롤백", "백업", "COOKIE_SECURE"):
        assert needle in guide, f"사내이관_가이드.md 에 «{needle}» 절이 없습니다"


def test_old_deploy_guide_points_to_the_new_one():
    """사내 절차가 두 문서에 있으면 한쪽이 썩는다 — 배포가이드 §3 은 링크만."""
    old = _read(PKG, "docs", "배포가이드.md")
    assert "사내이관_가이드.md" in old
    sec = old.split("## 3.", 1)[1].split("## 4.", 1)[0]
    assert "docker save" not in sec and "streamlit" not in sec.lower(), \
        "배포가이드 §3 에 옛 절차(Caddy·Streamlit 시절)가 남아 있습니다"
