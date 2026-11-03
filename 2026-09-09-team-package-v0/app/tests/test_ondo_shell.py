# -*- coding: utf-8 -*-
"""ONDO 1단계 — 이름·어두운 사이드바·접기 띠의 구조 검사 (2026-10-27 grace 결정).

결정 요약
- 프로그램 이름은 ONDO(by ThreeON). 팀 이름 ThreeON 은 «by» 로 남긴다.
- CI 빨강(#FE0009)은 로고에만 — 버튼·포커스·링크 강조는 남색(navy)과 캐릭터 색.
- 사이드바는 어두운 얇은 띠(76px)가 기본이고 마우스를 올리면 잠깐 펼친다(10/26 방식).
  «메뉴 펼치기»로 펼친 채 고정할 수 있고, 고른 상태는 사람마다(localStorage) 기억한다.
- 메뉴마다 담당 캐릭터 색 점: 매칭이(예산 계획·실적 집계) · 검토미(분석·상세·검토 대기·통계) · 예측이(중장기).
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
        assert "ONDO" in text, f"{fn}: 표지는 ONDO"
    side_text = re.sub(r"<[^>]+>", "", side.split("export function renderSidebar", 1)[1].split("\nexport function", 1)[0])
    assert "by ThreeON" in side_text, "팀 이름 by ThreeON 은 사이드바에(맨 위 줄은 2026-11-03 단순화로 뺐다)"
    assert "ONDO" in _read(WEB, "index.html").split("<title>", 1)[1].split("</title>", 1)[0]


def test_every_work_menu_names_its_character():
    owners = dict(re.findall(r'view:\s*"(\w+)"[^}]*?char:\s*"(\w+)"', _menu_block()))
    expected = {"budget": "mt", "collect": "mt", "branches": "gt", "detail": "gt",
                "review": "gt", "stats": "gt", "standard": "yc", "stddetail": "yc", "forecast": "yc"}
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
    assert owners == {"budget": "hj", "collect": "mt", "branches": "gt", "review": "gt", "stats": "gt",
                      "standard": "yc", "forecast": "yc"}, owners


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


def test_menu_follows_three_axes():
    """2026-11-03 팀장: 업무는 세 축 — ① 예산 실적 집계 ② 표준화(+ 하위 «표준화 세부») ③ 중장기 예측."""
    menu = _menu_block()
    groups = re.findall(r'group:\s*"([^"]+)"', menu)
    assert groups[:3] == ["① 예산 실적 집계", "② 표준화", "③ 중장기 예측"], groups
    std = menu.split('"② 표준화"', 1)[1].split("group:", 1)[0]
    assert 'view: "standard"' in std and 'view: "stddetail"' in std and "sub: true" in std
    fc = _read(SRC, "views", "forecast.js")
    assert '["bench",' not in fc.split("const TABS", 1)[1].split("\n", 1)[0], "6번 탭에서 표준화 탭은 뺐다"
    router = _read(SRC, "router.js")
    assert '"forecast" && m[2] === "bench"' in router, "옛 #/forecast/bench 링크는 표준화 세부로"


def test_standard_overview_groups_hgpi_ti_and_shows_all_amounts():
    """2026-11-03 팀장: HGPI 와 TI 는 같은 등급(한 칸) · 손익·자본·총액을 바꿔 보지 않고 한 칸에 함께."""
    fc = _read(SRC, "views", "forecast.js")
    assert re.search(r'SAME_GRADES\s*=\s*\{"HGPI/TI":\s*\["HGPI",\s*"TI"\]\}', fc)
    assert "gradeKey(r.등급) === f.grade" in fc, "5+ 등급 거르기도 묶은 이름으로"
    std = _read(SRC, "views", "standard.js")
    assert '"HGPI/TI"' in std.split("const GRADE_ORDER", 1)[1].split("\n", 1)[0]
    assert "/ d" in std, "한 지사에 HGPI·TI 가 다 있으면 더하지 않고 평균"
    cell = _fn(std, "cellHtml")
    assert "c.총액" in cell and "c.손익" in cell and "c.자본" in cell, "칸 하나에 총액·손익·자본"
    assert "data-stdkind" not in std, "손익/자본/총액 바꾸기 버튼은 뺐다"


# ── 맨 위 줄 단순화(2026-11-03 grace): 9개 → 로고·ONDO·화면 제목·연도·이름 ─────────────
def test_header_is_simple():
    html = _read(WEB, "index.html")
    header = html.split("<header", 1)[1].split("</header>", 1)[0]
    assert "addYearBtn" not in header and "＋연도" not in header, "연도 추가 버튼은 연도 목록 맨 아래로"
    assert 'id="yearLock"' in header and 'id="operatorMenu"' in header and 'id="logoutBtn"' in header.split('id="operatorMenu"', 1)[1]
    brand = _read(SRC, "components", "sidebar.js").split("export function renderHeaderBrand", 1)[1].split("\nexport function", 1)[0]
    assert "by ThreeON" not in brand and "header-brand__mascot" not in brand and "발전플랜트" not in brand
    r = _read(SRC, "router.js")
    assert '"__add"' in r and "btn.hidden = locked" in r
    assert '=== "__add"' in _read(SRC, "main.js")


def test_lock_notice_links_to_settings_unlock():
    ch = _read(SRC, "components", "characters.js")
    assert 'data-action="go-unlock"' in ch.split("export function lockedSay", 1)[1]
    assert 'act === "go-unlock"' in _read(SRC, "main.js")


# ── 1단계 예산 계획 화면 쉽게(2026-11-03 grace) ─────────────────────────────
def test_plan_page_guides_first_time_users():
    plan = _read(SRC, "views", "plan.js")
    body = plan.split("export function renderBudget", 1)[1]
    stage = _read(SRC, "components", "stage.js")
    assert "stepGuide(" in body and "is-now" in stage, "세 단계 안내 — 지금 할 단계가 반짝"
    assert "올라간 계획 파일" in body and "지금 쓰는 파일" in stage and "데이터셋" not in body
    assert "slimDrop(" in body and 'drop: "plan"' in body and "drop-zone--slim" in stage, "얇은 업로드 칸, 끌어다 놓기"
    assert "yearPicker(" not in body, "화면 안 연도 칸은 맨 위 줄과 겹쳐 뺐다"
    assert 'tourButton("budget")' in body and "plan-hint" in stage
    assert "/api/datasets/${d.id}/download" in stage, "올라간 파일 원본 내려받기"
    assert 'nextStep({view: "collect"' in body, "다음 단계는 맨 아래 따로 큰 버튼"
    tour = _read(SRC, "components", "tour.js")
    assert "budget:" in tour and "collect:" in tour and "localStorage" in tour and "건너뛰기" in tour
    assert "maybeStartTour(" in _read(SRC, "router.js")
    main = _read(SRC, "main.js")
    assert 'act === "tour"' in main and '"drop"' in main


def test_collect_page_same_guide_and_visible_results_in_eok():
    col = _read(SRC, "views", "collect.js")
    body = col.split("export function renderCollect", 1)[1].split("\n// ───", 1)[0]
    assert "stepGuide(" in body and "slimDrop(" in body and "fileList(" in body and "yearPicker(" not in body
    assert "match-card" in body and "억원" in body and "천원</span>" not in body, "매칭 결과는 크게, 억원"
    assert 'nextStep({view: "detail"' in body and "다음 단계</p>" not in body, "다음 단계는 따로 큰 버튼"
    assert "데이터셋" not in body

def test_branches_page_has_tour():
    br = _read(SRC, "views", "branches.js")
    assert 'tourButton("branches"' in br and "br-scatter" in br and "br-filters" in br
    tour = _read(SRC, "components", "tour.js")
    assert "branches:" in tour and ".br-scatter" in tour


def test_stats_page_tour_explains_exports():
    st = _read(SRC, "views", "stats.js")
    assert 'tourButton("stats")' in st and "stats-exports" in st and "stats-table" in st
    tour = _read(SRC, "components", "tour.js").split("stats: [", 1)[1].split("],", 1)[0]
    for k in ('data-export="actual"', 'data-export="v1"', 'data-export="matched"'):
        assert k in tour, f"내보내기 버튼 설명 {k}"


def test_sub_menus_are_numbered():
    side = _read(SRC, "components", "sidebar.js")
    for tag, label in (("3-1", "지사 상세"), ("3-2", "검토 대기"), ("5-1", "표준화 세부")):
        assert f'tag: "{tag}", label: "{label}"' in side
    assert "검토 큐" not in side and '"3+"' not in side


def test_standard_explains_folded_and_fits_one_screen():
    """2026-11-03 grace: 표 설명은 접고 펴기 + 항목별 줄 나눔 · [전체보기]면 옆 스크롤 없이 한 화면."""
    std = _read(SRC, "views", "standard.js")
    body = _fn(std, "stdBody")
    assert '<details class="std-about">' in body and body.count("<li>") >= 4
    assert 'data-action="std-full"' in body, "전체보기 = 새 창"
    assert "window.open(" in _fn(std, "openStandardWindow")
    assert 'act === "std-full"' in _read(SRC, "main.js")
    css = _read(SRC, "styles", "custom.css")
    assert ".std-full .std-heat{table-layout:fixed}" in css
    assert ".std-tag{display:block;" in css, "편입 예정 딱지는 지사 이름 아래 줄"


def test_sidebar_menu_scrolls_on_its_own():
    """2026-11-03 grace: 화면이 낮으면 6번 메뉴까지 안 내려가고 본문만 내려가던 문제 — 메뉴만 따로 스크롤."""
    nav = _read(SRC, "components", "sidebar.js").split("<nav", 1)[1].split(">", 1)[0]
    assert "overflow-y-auto" in nav and "min-h-0" in nav and "overscroll-contain" in nav


def test_sub_menus_fold_under_parent():
    """2026-11-03 grace: 3-1·3-2·5-1 은 위 메뉴 ▾ 를 눌러 펼친다(스크롤 없이 짧게). 지금 화면이 하위면 펼쳐 둔다."""
    sb = _read(SRC, "components", "sidebar.js")
    assert "data-sb-sub" in sb and 'class="nav-subs"' in sb and "${navHtml(MENU)}" in sb
    assert "openActiveSub(state.view)" in _read(SRC, "router.js")
    assert "setSubOpen(sub.dataset.sbSub" in _read(SRC, "main.js")
    css = _read(SRC, "styles", "custom.css")
    assert "#sidebar .nav-subs{display:none}" in css and "#sidebar .nav-subs.is-open{display:block}" in css


def test_home_steps_follow_menu_and_character_colors():
    """2026-11-03 grace: 메인 알약 = 메뉴 1~6 이름 그대로 · 사이 › (색은 뺐다)."""
    home = _read(SRC, "views", "home.js")
    assert "MENU.filter(m => m.view && /^\\d$/.test(m.tag))" in home
    assert "home-step__arrow" in home and "home-step--" not in home, "색은 빼고 화살표만"


def test_tour_button_red_dot_until_clicked():
    """2026-11-03 grace 시안 3: 사용법 보기는 지금 모양, 그 화면에서 아직 안 눌렀으면 빨간 점."""
    tour = _read(SRC, "components", "tour.js")
    assert "ondo.tourBtn." in tour and '" is-new"' in tour
    for f in ("plan", "collect", "branches", "stats"):
        assert "tourButton(" in _read(SRC, "views", f + ".js"), f
    assert "markTourClicked(b)" in _read(SRC, "main.js")
    assert ".tour-btn.is-new::after" in _read(SRC, "styles", "custom.css")


def test_tour_skip_points_to_replay_button():
    """2026-11-03 grace: 둘러보기를 건너뛰면 [사용법 보기] 아래에 «나중에 여기서 다시 볼 수 있어요»."""
    tour = _read(SRC, "components", "tour.js")
    assert "laterHint(view)" in tour and "나중에 여기서 다시 볼 수 있어요" in tour
    assert '.addEventListener("click", skip)' in tour
    assert ".tour-later{" in _read(SRC, "styles", "custom.css")


def test_standard_page_has_tour():
    """2026-11-03 grace: 5 표준화에도 사용법 둘러보기 — 표 읽는 법 · 칸 누르면 5-1 · 전체보기(새 창)."""
    tour = _read(SRC, "components", "tour.js")
    std_tour = tour.split("  standard: [", 1)[1].split("],", 1)[0]
    assert ".std-heat thead" in std_tour and "5-1 표준화 세부" in std_tour and "std-full" in std_tour
    assert 'tourButton("standard")' in _read(SRC, "views", "standard.js")


def test_tour_text_breaks_per_sentence():
    """2026-11-03 grace: 둘러보기 말풍선은 문장마다 줄을 나누고, 낱말 중간에서 끊지 않는다."""
    assert '.replace(/([.?!]) +/g, "$1\\n")' in _read(SRC, "components", "tour.js")
    assert ".tour__text{white-space:pre-line;word-break:keep-all;" in _read(SRC, "styles", "custom.css")


def test_info_icon_opens_aligned_box_on_click():
    """2026-11-03 grace 시안 1: ⓘ 는 누르면 설명 상자 · 이름 칸 | 설명 칸 두 열로 줄을 맞춘다(줄이 바뀌어도 설명 시작선)."""
    fc = _read(SRC, "views", "forecast.js")
    assert "aria-label=\"설명\">ⓘ</span>" not in fc and "cursor-help" not in fc, "마우스 올려 기다리는 title 설명은 없앴다"
    assert "export function infoTip(" in fc and "infoTip(String(help)" in fc
    assert "closeInfo()" in _read(SRC, "main.js")
    css = _read(SRC, "styles", "custom.css")
    assert ".info-pop__list--kv{grid-template-columns:4.6rem minmax(0,1fr)" in css
    assert ".std-about__list li{display:grid;grid-template-columns:5.2rem minmax(0,1fr)" in css


def test_site_note_tag_is_short():
    """2026-11-03 grace: «2029년 준공 후 중대형CHP 편입 예정» 딱지는 «2029 편입 예정»으로 짧게(전체는 마우스 올리면)."""
    import subprocess, json
    std = _read(SRC, "views", "standard.js")
    line = [l for l in std.splitlines() if l.startswith("const shortNote")][0]
    js = line + '\nconsole.log(JSON.stringify([shortNote("2029년 준공 후 중대형CHP 편입 예정"), shortNote("기타 메모")]))'
    out = subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True).stdout
    assert json.loads(out) == ["2029 편입 예정", "기타 메모"]


def test_grade_plan_names_aligned_without_ditto():
    """2026-11-03 grace: 6 정비등급 양식 — «삼  송» 빈칸·〃 대신 지사 | 설비 두 열, 같은 지사 줄은 묶어 보이게."""
    fc = _fn(_read(SRC, "views", "forecast.js"), "gradePlanTable")
    assert 'text-tri">〃' not in fc and 'replace(/\\s+/g, "")' in fc and "gp-cont" in fc
    assert ".gp-name{display:grid;grid-template-columns:minmax(4.5rem,max-content) auto" in _read(SRC, "styles", "custom.css")


def test_grade_plan_paren_moves_to_unit():
    """2026-11-03 grace: «청 주(신규CHP)» → 청주 | 신규CHP (대구와 같은 양식), 설비 칸 바깥 괄호도 뗀다."""
    fc = _fn(_read(SRC, "views", "forecast.js"), "gradePlanTable")
    assert "const paren = !unit && site.match(" in fc and 'unit = unit.replace(/^\\((.*)\\)$/, "$1")' in fc


def test_forecast_page_has_tour():
    """2026-11-03 grace: 6 중장기 예측에도 사용법 둘러보기 — 기준연도 · 탭 · 가정 묶음 · 저장 · 지사 · 내려받기."""
    tour = _read(SRC, "components", "tour.js")
    fc_tour = tour.split("  forecast: [", 1)[1].split("\n  ],", 1)[0]
    for sel in ("[data-fcbase]", ".fc-tabs", ".fc-mtabs", "#fcSaveBtn", "[data-fcsite]", 'data-fcexport="longterm"'):
        assert sel in fc_tour, sel
    fc = _read(SRC, "views", "forecast.js")
    assert 'tourButton("forecast")' in fc and "fc-tabs" in fc and "fc-mtabs" in fc


def test_forecast_tour_explains_each_group():
    """2026-11-03 grace: 기준정보 묶음 9개를 둘러보기 한 단계에서 이름 | 설명 두 열로."""
    tour = _read(SRC, "components", "tour.js")
    step = tour.split('{sel: ".fc-mtabs"', 1)[1].split("]},", 1)[0]
    for name in ("참고 엑셀·대조", "정비등급", "고온부품", "설비용량·신규표준", "지사 연혁·구조변화",
                 "정기계약·CRI·투자", "본사 배분·임시사업", "지사 돌발사업", "학습 기간·물가 환산·백테스트"):
        assert f'["{name}", ' in step, name
    assert ".tour__list{display:grid;grid-template-columns:max-content minmax(0,1fr)" in _read(SRC, "styles", "custom.css")
