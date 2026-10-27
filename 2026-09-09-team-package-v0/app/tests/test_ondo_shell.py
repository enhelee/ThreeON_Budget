# -*- coding: utf-8 -*-
"""ONDO 1단계 — 이름·어두운 사이드바·접기 띠의 구조 검사 (2026-10-27 grace 결정).

결정 요약
- 프로그램 이름은 ONDO(by ThreeON). 팀 이름 ThreeON 은 «by» 로 남긴다.
- CI 빨강(#FE0009)은 로고에만 — 버튼·포커스·링크 강조는 남색(navy)과 캐릭터 색.
- 사이드바는 어두운 얇은 띠(76px)가 기본이고 마우스를 올리면 잠깐 펼친다(10/26 방식).
  «메뉴 펼치기»로 펼친 채 고정할 수 있고, 고른 상태는 사람마다(localStorage) 기억한다.
- 메뉴마다 담당 캐릭터 색 점: 매칭이(예산 계획·실적 집계) · 검토미(분석·상세·검토 큐·통계) · 예측이(중장기).
"""
import os
import re

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(APP, "web")
SRC = os.path.join(WEB, "src")


def _read(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as f:
        return f.read()


def _menu_block():
    return _read(SRC, "components", "sidebar.js").split("export const MENU", 1)[1].split("]", 1)[0]


def test_product_name_is_ondo_by_threeon():
    side = _read(SRC, "components", "sidebar.js")
    for fn in ("renderSidebar", "renderHeaderBrand"):
        body = side.split(f"export function {fn}", 1)[1].split("\nexport function", 1)[0]
        text = re.sub(r"<[^>]+>", "", body)                      # <b>ON</b>DO 처럼 나눠 칠해도 글자는 ONDO
        assert "ONDO" in text and "by ThreeON" in text, f"{fn}: 표지는 ONDO by ThreeON"
    assert "ONDO" in _read(WEB, "index.html").split("<title>", 1)[1].split("</title>", 1)[0]


def test_every_work_menu_names_its_character():
    owners = dict(re.findall(r'view:\s*"(\w+)"[^}]*?char:\s*"(\w+)"', _menu_block()))
    expected = {"budget": "mt", "collect": "mt", "branches": "gt", "detail": "gt",
                "review": "gt", "stats": "gt", "forecast": "yc"}
    assert owners == expected, f"메뉴별 담당 캐릭터가 다릅니다: {owners}"
    assert "nav-dot" in _read(SRC, "components", "sidebar.js"), "메뉴 버튼에 캐릭터 색 점(.nav-dot)"


def test_sidebar_starts_as_rail_and_remembers_pin():
    side = _read(SRC, "components", "sidebar.js")
    assert "data-sb-fold" in side, "사이드바 아래 접기·펼치기 버튼"
    js = _read(SRC, "main.js")
    assert '"ondo.sidebar"' in js, "접기 선택은 localStorage «ondo.sidebar» 로 기억"
    assert re.search(r'===\s*"open"', js), "저장값이 open 일 때만 펼친 채로 시작(기본은 접힌 띠)"
    assert "sb-open" in js, "펼침 고정 상태 표시(html.sb-open)"
    css = _read(SRC, "styles", "custom.css")
    assert ".sb-open #appShell" in css, "펼침 고정이면 본문이 사이드바 폭만큼 비켜야 합니다"


def test_sidebar_is_dark_navy_with_three_color_edge():
    css = _read(SRC, "styles", "custom.css")
    app = _read(SRC, "styles", "app.css")
    assert re.search(r"--navy:\s*#0B1020", app, re.I), "app.css :root 에 --navy"
    sb = css.split("/* ONDO 사이드바", 1)[1]
    assert "var(--navy)" in sb, "사이드바 바탕은 남색"
    for c in ("--char-mt", "--char-gt", "--char-yc"):
        assert c in sb, f"사이드바 3색 선·점에 {c}"


def test_brand_red_stays_only_in_logo():
    app = _read(SRC, "styles", "app.css")
    block = app.split(".btn-primary {", 1)[1].split("}", 1)[0]
    assert "brand" not in block, "주 버튼에 CI 빨강을 쓰지 않습니다(남색)"
    assert "bg-navy" in block and "text-white" in block
    focus = app.split(":focus-visible {", 1)[1].split("}", 1)[0]
    assert "--brand" not in focus, "키보드 포커스 테두리도 빨강 대신 남색"
    marker = app.split(".nav-button-active::before {", 1)[1].split("}", 1)[0]
    assert "brand" not in marker
    src = _read(WEB, "index.html")
    for root, _, files in os.walk(SRC):
        for f in files:
            if f.endswith(".js"):
                src += _read(root, f)
    left = sorted(set(re.findall(r"\b(?:hover:)?(?:bg|text|border|accent)-brand\b", src)))
    assert not left, f"화면 코드에 CI 빨강 유틸리티가 남았습니다: {left}"


# ── 시안 맞춤: 본문 연회색 바탕 + 메인 남색 배너(2026-10-27 grace 요청) ──────────────
# 남색 사이드바 옆에 새하얀 본문만 있으면 따로 논다 — 바탕을 연회색으로, 메인 맨 위에 남색 배너를 둬서 잇는다.

CHAR_DIR = os.path.join(WEB, "public", "assets", "characters")


def test_page_background_is_soft_gray_and_cards_stay_white():
    cfg = _read(WEB, "tailwind.config.js")
    assert re.search(r'\bpage:\s*"#F4F6FA"', cfg, re.I), "tailwind 토큰 page(연회색 바탕)"
    app = _read(SRC, "styles", "app.css")
    body = app.split("body {", 1)[1].split("}", 1)[0]
    assert "bg-page" in body and "bg-base" not in body, "본문 바탕은 연회색, 카드(.panel)는 흰색 그대로"
    assert "bg-base" in app.split(".panel {", 1)[1].split("}", 1)[0]


def test_home_banner_is_navy_with_three_characters():
    home = _read(SRC, "views", "home.js")
    strip = home.split("function headerStrip()", 1)[1].split("\n}\n", 1)[0]
    assert "home-hero" in strip, "메인 맨 위 배너는 .home-hero(남색)"
    assert "예산의 온도를 읽다" in strip
    assert '/assets/characters/${id}.png" alt="${name}"' in strip, "캐릭터 그림은 이름을 대체 텍스트로"
    for cid, name in (("mt", "매칭이"), ("gt", "검토미"), ("yc", "예측이")):
        assert f'["{cid}", "{name}"]' in strip, f"배너에 {name}"
        png = os.path.join(CHAR_DIR, f"{cid}.png")
        assert os.path.isfile(png), f"{cid}.png 가 없습니다"
        assert os.path.getsize(png) < 160_000, f"{cid}.png 가 너무 큽니다(배너용은 작게 줄여 넣는다)"
    css = _read(SRC, "styles", "custom.css")
    hero = css.split(".home-hero{", 1)[1].split("}", 1)[0]
    assert "var(--navy)" in hero
    assert "prefers-reduced-motion" in css.split(".home-hero{", 1)[1], "캐릭터 둥실 움직임은 움직임 줄이기 설정에서 멈춘다"
