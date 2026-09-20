# -*- coding: utf-8 -*-
"""한난 디자인 시스템 적용(Phase 8)의 구조 검사.

색·글꼴은 브라우저에서만 보이지만, «어느 이름이 정의돼 있는가»와 «옛 팔레트가 남았는가»는
파일만 읽어도 안다. 회귀는 조용히 온다 — 새 화면에 blue-600 을 한 줄 쓰면 아무 테스트도
안 깨지고 화면만 옛날로 돌아간다. 그래서 잔존 0 을 여기서 고정한다.
"""
import os
import re

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(APP, "web")


def _read(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as f:
        return f.read()


# ── Task 1: 토큰·글꼴·로고 ─────────────────────────────────────────────

def test_tailwind_defines_hannan_tokens():
    cfg = _read(WEB, "tailwind.config.js")
    for name in ("ink", "sub", "line", "subtle", "brand", "ok", "warn", "err", "info", "overlay"):
        assert re.search(rf"\b{name}\b\s*:", cfg), f"tailwind.config.js 에 색 토큰 «{name}» 이 없습니다"
    assert "#FE0009" in cfg.upper(), "브랜드 빨강은 CI 매뉴얼 공식값 #FE0009 여야 합니다"
    assert "#ED1C2B" not in cfg.upper(), "#ED1C2B 는 시안의 추출값 — 쓰지 않습니다"
    for r in ("card", "visual", "control"):
        assert re.search(rf"\b{r}\b\s*:", cfg), f"borderRadius «{r}» 이 없습니다"
    assert "hanan" in cfg, "fontFamily «hanan» 이 없습니다"


def test_css_root_declares_brand_and_font_face():
    css = _read(WEB, "src", "styles", "app.css")
    assert "--BRAND: #FE0009" in css.upper().replace("--BRAND:#", "--BRAND: #"), "app.css :root 의 --brand 는 #FE0009"
    assert "@font-face" in css and "HananCha" in css and "font-display: swap" in css
    assert "/assets/fonts/HananCha-v1.woff2" in css
    assert "prefers-reduced-motion" in css


def test_font_subset_and_logo_are_shipped():
    font = os.path.join(WEB, "public", "assets", "fonts", "HananCha-v1.woff2")
    assert os.path.isfile(font), "한난체 서브셋 woff2 가 없습니다 — py scripts/make_hanan_font.py <HANAN.TTF>"
    assert 50_000 < os.path.getsize(font) < 400_000, "서브셋 크기가 이상합니다(2,350자+ASCII 면 100~300KB)"
    with open(font, "rb") as f:
        assert f.read(4) == b"wOF2"
    svg = _read(WEB, "public", "assets", "kdhc-signature-ko.svg")
    assert "<svg" in svg and "viewBox" in svg


# ── Task 2: 공통 컴포넌트 ────────────────────────────────────────────

def test_shared_css_uses_tokens_not_legacy_palette():
    """app.css·custom.css 에 옛 팔레트가 남으면 컴포넌트 절반이 파랑으로 돌아간다."""
    legacy = re.compile(r"\b(bg|text|border|ring|divide)-(blue|slate|emerald|amber|red|rose|indigo|gray)-\d+")
    for name in ("app.css", "custom.css"):
        body = _read(WEB, "src", "styles", name)
        hits = sorted(set(legacy.findall(body)))
        assert not hits, f"{name} 에 옛 팔레트 유틸리티: {hits}"
    custom = _read(WEB, "src", "styles", "custom.css")
    for hexv in ("#2563eb", "#1d4ed8", "#3730a3", "#eef2ff", "#dbeafe"):
        assert hexv not in custom.lower(), f"custom.css 에 옛 파랑 {hexv} 가 남아 있습니다"


def test_primary_button_follows_sample_rule():
    """검정 바탕 + 흰 글자 + 브랜드 빨강 테두리 + 캡슐 + 44px. 빨강 바탕은 금지."""
    css = _read(WEB, "src", "styles", "app.css")
    block = css.split(".btn-primary {", 1)[1].split("}", 1)[0]          # 단독 블록(색·테두리)
    assert "bg-ink" in block and "text-white" in block and "border-brand" in block
    shared = css.split(".btn-primary,", 1)[1].split("}", 1)[0]           # 공유 블록(형태)
    assert "rounded-full" in shared and "min-h-[44px]" in shared
    assert "bg-brand" not in block, "브랜드 빨강을 버튼 바탕으로 쓰면 흰 글자 대비가 4.5 미만입니다"


# ── Task 3: 셸 ────────────────────────────────────────────────────────

def test_shell_has_skip_link_header_height_and_drawer_aria():
    html = _read(WEB, "index.html")
    assert 'lang="ko"' in html
    assert 'class="skip-link"' in html and 'href="#page"' in html and "본문 바로가기" in html
    assert "min-h-[72px]" in html, "헤더는 72px(시안)"
    assert 'aria-expanded="false"' in html and 'aria-controls="sidebar"' in html
    assert "backdrop-blur" not in html, "시안 헤더는 불투명 흰색"


def test_sidebar_and_gate_use_official_signature():
    for f in (os.path.join(WEB, "src", "components", "sidebar.js"), os.path.join(WEB, "src", "views", "gate.js")):
        body = _read(f)
        assert "/assets/kdhc-signature-ko.svg" in body, f"{os.path.basename(f)}: 공식 시그니처 SVG"
        assert 'alt="한국지역난방공사"' in body, f"{os.path.basename(f)}: 로고 대체 텍스트"
        assert "ThreeON" in body, f"{os.path.basename(f)}: 팀 이름 ThreeON 표기(로고 아래)"


def test_drawer_handles_escape_and_returns_focus():
    js = _read(WEB, "src", "main.js")
    assert '"Escape"' in js, "드로어는 Escape 로 닫혀야 합니다"
    assert "aria-expanded" in js
    assert "menuReturnEl" in js and ".focus()" in js, "닫힌 뒤 메뉴 버튼으로 포커스가 돌아와야 합니다"
    assert '"Tab"' in js, "열려 있는 동안 Tab 은 드로어 안에서 순환"


# ── Task 4: 옛 팔레트 잔존 0 ─────────────────────────────────────────

LEGACY = re.compile(r"\b(?:hover:|focus:|sm:|lg:|md:)?(?:bg|text|border|ring|accent|divide|from|to)-(?:blue|slate|emerald|amber|red|rose|indigo|gray|green|yellow)-\d+(?:/\d+)?\b")


def test_no_legacy_palette_anywhere_in_frontend_source():
    """새 화면에 blue-600 한 줄이 들어와도 아무 테스트도 안 깨진다 — 여기서 깨진다."""
    hits = {}
    for root, _, files in os.walk(os.path.join(WEB, "src")):
        for f in files:
            if f.endswith(".js"):
                found = sorted(set(LEGACY.findall(_read(root, f))))
                if found:
                    hits[f] = found
    found = sorted(set(LEGACY.findall(_read(WEB, "index.html"))))
    if found:
        hits["index.html"] = found
    assert not hits, "옛 팔레트 유틸리티가 남아 있습니다: " + repr(hits)


def test_no_card_shadows_left():
    """시안: 일반 카드는 그림자 없음. 떠 있는 것(토스트·바쁨)만 shadow-float."""
    src = ""
    for root, _, files in os.walk(os.path.join(WEB, "src")):
        for f in files:
            if f.endswith(".js"):
                src += _read(root, f)
    src += _read(WEB, "index.html")
    assert not re.search(r"\bshadow-(sm|md|lg|xl)\b|\bshadow\b(?!-float)", src), "shadow-* 유틸리티가 남아 있습니다"
