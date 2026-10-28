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
    assert "nav-dot" not in _read(SRC, "components", "sidebar.js"), "메뉴 색 점은 뺐다(10/28 색 줄이기)"


def test_sidebar_starts_as_rail_and_remembers_pin():
    side = _read(SRC, "components", "sidebar.js")
    assert "data-sb-fold" in side, "사이드바 아래 접기·펼치기 버튼"
    js = _read(SRC, "main.js")
    assert '"ondo.sidebar"' in js, "접기 선택은 localStorage «ondo.sidebar» 로 기억"
    assert re.search(r'===\s*"open"', js), "저장값이 open 일 때만 펼친 채로 시작(기본은 접힌 띠)"
    assert "sb-open" in js, "펼침 고정 상태 표시(html.sb-open)"
    css = _read(SRC, "styles", "custom.css")
    assert ".sb-open #appShell" in css, "펼침 고정이면 본문이 사이드바 폭만큼 비켜야 합니다"


def test_sidebar_is_light_rail_without_character_colors():
    """10/28 피드백: 남색 사이드바 + 밝은 본문은 «다크·화이트 모드가 섞인 느낌» → 연회색 사이드바로 통일."""
    css = _read(SRC, "styles", "custom.css")
    app = _read(SRC, "styles", "app.css")
    assert re.search(r"--navy:\s*#0B1020", app, re.I), "app.css :root 에 --navy(글자·강조색)"
    sb = css.split("/* ONDO 사이드바", 1)[1].split("/* 표지", 1)[0]
    assert re.search(r"#sidebar\{[^}]*background:var\(--rail\)", sb), "사이드바 바탕은 연회색(--rail)"
    for c in ("--char-mt", "--char-gt", "--char-yc", "var(--navy)}"):
        assert c not in sb.replace("color:var(--navy)}", ""), f"사이드바에 {c} 없음(캐릭터 색은 그림에만)"


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

def test_page_background_is_soft_gray_and_cards_stay_white():
    cfg = _read(WEB, "tailwind.config.js")
    assert re.search(r'\bpage:\s*"#F4F6FA"', cfg, re.I), "tailwind 토큰 page(연회색 바탕)"
    app = _read(SRC, "styles", "app.css")
    body = app.split("body {", 1)[1].split("}", 1)[0]
    assert "bg-page" in body and "bg-base" not in body, "본문 바탕은 연회색, 카드(.panel)는 흰색 그대로"
    assert "bg-base" in app.split(".panel {", 1)[1].split("}", 1)[0]


def test_home_banner_is_light_with_temperature_gauge_and_characters():
    home = _read(SRC, "views", "home.js")
    strip = home.split("function headerStrip()", 1)[1].split("\n}\n", 1)[0]
    assert "home-hero" in strip and "예산의 온도를 읽다" in strip
    assert "home-hero__gauge" in strip, "배너의 예산 온도 막대(숫자 없음, 이름 뜻 그림)"
    assert "CHAR_IMG[id].full" in strip and 'alt="${NAMES[id]}"' in strip, "캐릭터 그림은 챗봇과 같은 char_images.js"
    assert '["mt", "gt", "yc"]' in strip, "배너에 매칭이·검토미·예측이"
    assert not os.path.isdir(os.path.join(WEB, "public", "assets", "characters")), "그림은 한 벌(src/assets/characters webp)만"
    css = _read(SRC, "styles", "custom.css")
    hero = css.split(".home-hero{", 1)[1].split("}", 1)[0]
    assert "var(--navy)" not in hero and "#fff" in hero, "배너는 흰 카드(남색 덩어리는 로그인 화면에만)"
    assert "prefers-reduced-motion" in css.split(".home-hero{", 1)[1], "캐릭터 둥실 움직임은 움직임 줄이기 설정에서 멈춘다"


# ── 메인 카드도 시안처럼(2026-10-27 grace: 지금 내용은 그대로, 조화만) ─────────────
# 그래프 모양은 그대로, 색만 차분하게(2026-10-28 grace·팀: 쨍한 파랑·주황이 남색 배너·캐릭터 색 옆에서 튀었다).
#   계획 = 연한 남색(배경처럼 물러난 기준), 실적 = 차분한 산호(검토미 산호 계열). 막대마다 숫자·범례가 붙어 있어 구별은 글자로도 된다.

def test_banner_lists_work_steps_as_links():
    strip = _read(SRC, "views", "home.js").split("function headerStrip()", 1)[1].split("\n}\n", 1)[0]
    assert "home-hero__steps" in strip and "data-view" in strip, "배너 안 업무 단계 알약(누르면 이동)"


def test_status_cards_have_no_character_color_lines():
    home = _read(SRC, "views", "home.js")
    assert re.search(r"function card\(title, badge, body\)", home), "카드 위 캐릭터 색 선은 뺐다(10/28 색 줄이기)"
    assert "metric-card--" not in home + _read(SRC, "styles", "custom.css")


def test_stage_cards_show_their_character():
    home = _read(SRC, "views", "home.js")
    stage = home.split("function stageCards()", 1)[1].split("\n}\n", 1)[0]
    assert "CHAR_IMG[" in stage and "stage-card__char" in stage, "업무 단계 카드마다 담당 캐릭터 그림"
    side = _read(SRC, "components", "sidebar.js")
    owners = dict(re.findall(r'view: "(\w+)", title:[^}]*?char: "(\w+)"', side.split("export const STAGES", 1)[1]))
    assert owners == {"budget": "hj", "collect": "mt", "branches": "gt", "review": "gt", "stats": "gt", "forecast": "yc"}, owners


def test_chart_plan_light_navy_and_actual_soft_coral():
    css = _read(SRC, "styles", "custom.css")
    for k, v in (("plan", "#B8C4DD"), ("act", "#D9826B")):
        assert f".yr-bar--{k}{{background:{v}}}" in css and f".yr-dot--{k}{{background:{v}}}" in css, f"{k} 막대·점은 {v}"
    assert "#2F6FDB" not in css and "#D2601A" not in css, "예전 쨍한 파랑·주황이 남아 있습니다"


# ── 팀장 검토의견 반영(2026-10-28 UI/검토의견.xlsx) ─────────────────────────────
# ① 3개년: 계획·실적을 한 막대에(계획 위에 실적), 손익·자본·합계 따로 ② 연도별 요약 = «3개년 실적비교» 표(연도 가로·계획/실적·실적률)
# ③ 전망 = 손익+자본 누적 막대 ④ 손익·자본 카드를 누르면 예산과목별로 펼침 ⑤ 카드에서 연도 고르기

def _fn(src, name):
    return src.split(f"function {name}(", 1)[1].split("\nfunction ", 1)[0].split("\nexport function", 1)[0]


def test_review_multi_year_bars_split_budget_types_in_one_bar():
    home = _read(SRC, "views", "home.js")
    body = _fn(home, "multiYearPanels")
    assert 'BT = ["손익", "자본", "합계"]' in home and "BT.map" in body, "손익·자본·합계 따로"
    assert "yr-one" in body, "계획 막대 위에 실적 막대를 겹친 한 줄(.yr-one)"


def test_review_summary_is_three_year_comparison_table():
    body = _fn(_read(SRC, "views", "home.js"), "summaryTable")
    assert "colspan" in body and "homeRateBadge" in body and "합계" in body and "억원" in body


def test_review_forecast_is_stacked_by_budget_type():
    home = _read(SRC, "views", "home.js")
    body = _fn(home, "forecastPanel")
    assert "구분" in body and "#718CBF" in body and "#ADB7C9" in body, "손익(파랑)·자본(회청) 누적 — 확정 팔레트"
    pf = _read(APP, "src", "budget", "pipeline_forecast.py")
    assert '"구분"' in pf and "def capital_items" in pf, "전망 합계 행에 손익/자본 구분"


def test_review_cards_expand_by_account_and_pick_year():
    home = _read(SRC, "views", "home.js")
    assert "data-homeacct" in home and "acctPanel" in home, "손익·자본 카드를 누르면 과목별 펼침"
    assert "yearPickCard" in home and "data-goyear" in _fn(home, "yearPickCard"), "카드에서 연도 고르기"
    js = _read(SRC, "main.js")
    assert "data-homeacct" in js and "/api/stats?year=" in js


def test_stats_amounts_ignore_missing_plan():
    """계획 없이 집행된 줄(연예산 NaN)이 과목 계획 합계를 통째로 NaN 으로 만들지 않는다(10/28 발견)."""
    import math
    import sys
    sys.path.insert(0, APP)
    import server
    assert server._amt(float("nan")) == 0 and server._amt(None) == 0 and server._amt(5) == 5
    body = _read(APP, "server.py").split('@app.get("/api/stats")', 1)[1].split("@app.get(", 1)[0]
    assert '"] or 0' not in body, "/api/stats 의 금액 합계는 _amt() 로"
    assert not math.isnan(sum(server._amt(v) for v in (1.0, float("nan"), 2.0)))


def test_main_chart_palette_tokens():
    css = _read(SRC, "styles", "custom.css")
    for k, v in (("--chart-profit", "#718CBF"), ("--chart-capital", "#ADB7C9"), ("--chart-total", "#E58F79"),
                 ("--status-good", "#31876F"), ("--status-warning", "#A77A27"), ("--status-poor", "#B65E53")):
        assert f"{k}:{v}" in css, f"{k} = {v}(10/28 확정 팔레트)"


def test_home_rate_badge_thresholds():
    """메인 집행률 배지(10/28 grace): 90% 이상 초록 · 미만 노랑 · 100% 초과 빨강. 다른 탭은 80~120% 그대로."""
    b = _read(SRC, "components", "badges.js")
    fn = b.split("export function homeRateBadge", 1)[1].split("\n}", 1)[0]
    assert "r > 100" in fn and "r >= 90" in fn
    home = _read(SRC, "views", "home.js")
    assert "homeRateBadge(" in home and "rateBadge(" not in home.replace("homeRateBadge(", "")
