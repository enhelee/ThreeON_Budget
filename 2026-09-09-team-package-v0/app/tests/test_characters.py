# -*- coding: utf-8 -*-
"""ThreeON 캐릭터(한장이·매칭이·검토미·예측이)를 화면에 심은 구조의 검사.

그림은 브라우저에서만 보이지만 «그림이 한 곳에만 정의돼 있는가», «도움말이 모든 메뉴에
있는가», «검토미의 기준선이 확신도 배지와 같은가»는 파일만 읽어도 안다.
"""
import os
import re

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(APP, "web", "src")


def _read(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as f:
        return f.read()


CHARS = _read(SRC, "components", "characters.js")


def test_characters_are_the_3d_set_only():
    """2026-10-27: 옛 벡터(<symbol>) 캐릭터를 걷어 내고 입체 v2 그림(char_images.js) 한 벌만 쓴다.
    안내 줄·빈 화면·사이드바 머리까지 같은 그림이어야 «새 캐릭터로 안 바뀐 곳»이 안 생긴다."""
    assert "<symbol" not in CHARS and "injectCharacterSprite" not in CHARS, "옛 벡터 sprite 가 남아 있습니다"
    assert "CHAR_IMG" in CHARS.split("export function charImg", 1)[1].split("\nexport function", 1)[0]
    for root, _, files in os.walk(SRC):
        for f in files:
            if f.endswith(".js"):
                body = _read(root, f)
                assert "<symbol id=" not in body and "charSvg(" not in body, f"{f}: 옛 벡터 캐릭터 호출"
                assert "#ch-" not in body, f"{f}: 옛 sprite 참조(<use href=\"#ch-…\">)"


def test_help_covers_every_menu_view():
    menu_views = set(re.findall(r'view:\s*"(\w+)"', _read(SRC, "components", "sidebar.js").split("export const STAGES")[0]))
    help_block = CHARS.split("export const HELP", 1)[1].split("export function helpFabHtml", 1)[0]
    help_views = set(re.findall(r"^\s{2}(\w+):\s*\[", help_block, re.M))
    assert menu_views and menu_views <= help_views, f"도움말이 없는 메뉴: {sorted(menu_views - help_views)}"
    for v in help_views:
        steps = re.search(rf"^\s{{2}}{v}:\s*\[(.*?)\]", help_block, re.M | re.S).group(1)
        assert len(re.findall(r'"[^"]+"', steps)) == 3, f"도움말 «{v}» 은 세 줄입니다"


def test_review_threshold_matches_conf_badge():
    """검토미가 고르는 기준(0.80 미만)과 표의 «검토 필요» 배지 기준이 어긋나면 숫자가 서로 다르게 보인다."""
    detail = _read(SRC, "views", "detail.js")
    badges = _read(SRC, "components", "badges.js")
    assert "n >= 0.8" in badges
    assert re.search(r"isLowConf\s*=.*<\s*0\.8\b", detail), "isLowConf 는 확신도 0.8 미만"
    assert 'b.구분 === "계획집행"' in detail.split("isLowConf", 1)[1].split("\n", 1)[0]
    assert "reviewBannerHtml()" in detail and "toggle-lowconf" in detail


def test_placements_wired():
    assert 'charImg("mt", "sidebar-mascot", {head: true})' in _read(SRC, "components", "sidebar.js")
    assert 'charImg("hj"' in _read(SRC, "components", "widgets.js"), "빈 화면에는 한장이"
    assert 'who: "mt"' in _read(SRC, "views", "collect.js"), "실적 집계에는 매칭이"
    assert 'who: "yc"' in _read(SRC, "views", "forecast.js"), "중장기 예측에는 예측이"
    main = _read(SRC, "main.js")
    assert "toggle-help" in main and "close-help" in main


def test_help_fab_lives_inside_app_shell():
    html = _read(APP, "web", "index.html")
    shell = html.split('id="appShell"', 1)[1].split('id="gate"', 1)[0]
    assert 'id="helpFab"' in shell, "도움말은 appShell 안 — 로그인 게이트에서는 같이 숨어야 합니다"
    css = _read(SRC, "styles", "custom.css")
    for cls in (".char-say", ".help-fab", ".help-bubble", ".empty-state__img", ".sidebar-mascot"):
        assert cls in css, f"custom.css 에 {cls} 가 없습니다"


def test_character_names_follow_the_three_axes():
    """2026-11-04 grace: 캐릭터 이름을 발표의 세 축에 맞춘다 — 매칭이 → 실적이, 검토미 → 표준이(예측이·한장이 그대로).
    화면에 나오는 글자(이름표·인사·로그인 소개·대화 패널)에 옛 이름이 남으면 발표 영상과 앱이 달라 보인다."""
    assert 'NAMES = {hj: "한장이", mt: "실적이", gt: "표준이", yc: "예측이"}' in CHARS
    shown = ["components/characters.js", "components/fab_intro.js", "components/chat.js", "views/gate.js", "views/collect.js"]
    for rel in shown:
        body = "\n".join(l for l in _read(SRC, *rel.split("/")).splitlines() if not l.lstrip().startswith(("//", "*", "/*")))
        assert "매칭이" not in body and "검토미" not in body, f"{rel}: 화면 글자에 옛 이름"
