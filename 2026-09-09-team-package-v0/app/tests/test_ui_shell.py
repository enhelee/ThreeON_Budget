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
