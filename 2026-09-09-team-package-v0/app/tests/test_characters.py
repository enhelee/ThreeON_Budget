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


def test_sprite_defines_four_characters_once():
    for who in ("hj", "mt", "gt", "yc"):
        assert CHARS.count(f'<symbol id="ch-{who}"') == 1, f"캐릭터 «{who}» symbol 이 한 번만 있어야 합니다"
    # 그림은 characters.js 한 곳에만 — 화면 파일에 symbol 을 또 그리면 생김새가 갈라진다
    for root, _, files in os.walk(SRC):
        for f in files:
            if f.endswith(".js") and f != "characters.js":
                assert "<symbol id=" not in _read(root, f), f"{f}: 캐릭터 그림은 characters.js 의 symbol 만 씁니다"


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
    assert 'charSvg("mt", "sidebar-mascot", {head: true})' in _read(SRC, "components", "sidebar.js")
    assert 'charSvg("hj"' in _read(SRC, "components", "widgets.js"), "빈 화면에는 한장이"
    assert 'who: "mt"' in _read(SRC, "views", "collect.js"), "실적 집계에는 매칭이"
    assert 'who: "yc"' in _read(SRC, "views", "forecast.js"), "중장기 예측에는 예측이"
    main = _read(SRC, "main.js")
    assert main.index("injectCharacterSprite()") < main.index('$("#sidebar").innerHTML'), "그림을 먼저 심고 사이드바를 그립니다"
    assert "toggle-help" in main and "close-help" in main


def test_help_fab_lives_inside_app_shell():
    html = _read(APP, "web", "index.html")
    shell = html.split('id="appShell"', 1)[1].split('id="gate"', 1)[0]
    assert 'id="helpFab"' in shell, "도움말은 appShell 안 — 로그인 게이트에서는 같이 숨어야 합니다"
    css = _read(SRC, "styles", "custom.css")
    for cls in (".char-say", ".help-fab", ".help-bubble", ".empty-state__img", ".sidebar-mascot"):
        assert cls in css, f"custom.css 에 {cls} 가 없습니다"
