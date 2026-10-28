# -*- coding: utf-8 -*-
"""ONDO 3단계 — 로그인 화면 B안(전체 화면 장면 + 떠 있는 카드) 구조 검사 (2026-10-28 grace 결정: A안 → B안).

- 화면 전체가 어두운 장면. 처음 ~3초 «ONDO» 글자가 점으로 모였다 흩어져 데이터 흐름이 되고,
  매칭이·검토미·예측이가 그 흐름을 받는다. 오른쪽에 반투명 흰 로그인 카드가 떠 있다(처음부터 입력 가능).
- 소개는 장면이 하므로 카드는 로고·ONDO·입력 칸·입장만. «ONDO» 의 ON 은 CI 빨강(워드마크 = 로고).
- 누르거나 키를 치면 인트로를 건너뛴다. 움직임 줄이기 설정·좁은 화면은 애니메이션 없이 마지막 장면만.
- 로그인하면 애니메이션을 완전히 멈춘다(작업 화면이 느려지지 않게).
- 운영 수치(금액·건수·집행률)는 한 글자도 넣지 않는다(게이트 원칙).
"""
import os
import re

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(APP, "web", "src")


def _read(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as f:
        return f.read()


GATE = _read(SRC, "views", "gate.js")


def _render_block():
    """renderGate() 의 화면 글자 — 왼쪽 장면은 scene() 이 그려 ${scene()} 자리에 들어간다."""
    body = GATE.split("export function renderGate", 1)[1].split("\nexport function", 1)[0]
    scene = GATE.split("function scene()", 1)[1].split("\nexport function", 1)[0]
    assert "${scene()}" in body
    return body.replace("${scene()}", scene)


def test_gate_is_full_scene_with_floating_login_card():
    body = _render_block()
    assert "gate-scene" in body and "gate-panel" in body, "왼쪽 장면 + 오른쪽 로그인 카드"
    assert body.index("gate-scene") < body.index("gate-panel")
    panel = body.split("gate-panel", 1)[1]
    assert 'id="gateForm"' in panel and 'id="gateName"' in panel and 'id="gatePw"' in panel, "로그인 칸은 오른쪽 카드에 그대로"
    assert "<canvas" in body.split("gate-panel", 1)[0], "인트로·데이터 흐름은 왼쪽 canvas"


def test_scene_uses_3d_characters_and_ondo_copy():
    scene = _render_block().split("gate-panel", 1)[0]
    assert "CHAR_IMG" in scene, "캐릭터는 챗봇과 같은 입체 그림"
    for who in ("mt", "gt", "yc"):
        assert f'"{who}"' in GATE, f"장면에 {who}"
    assert "지금 몇 도인가요?" in scene and "10년 뒤 예보까지" in scene


def test_scene_shows_no_operating_numbers():
    scene = re.sub(r"<[^>]+>", " ", _render_block().split("gate-panel", 1)[0])
    assert not re.search(r"\d{1,3}(,\d{3})+|\d+(\.\d+)?\s*%|\d+\s*(건|천원|억)", scene), "게이트 장면에 금액·건수·집행률 금지"


def test_intro_can_skip_respects_reduced_motion_and_stops_after_login():
    intro = _read(SRC, "components", "gate_intro.js")
    assert "export function startIntro" in intro and "export function stopIntro" in intro
    assert "prefers-reduced-motion" in intro, "움직임 줄이기 설정이면 애니메이션 없이"
    assert "cancelAnimationFrame" in intro and "removeEventListener" in intro, "멈출 때 그리기·이벤트를 모두 걷는다"
    assert re.search(r"pointerdown|keydown", intro), "누르거나 키를 치면 건너뛰기"
    show = GATE.split("export function showGate", 1)[1].split("\nexport function", 1)[0]
    hide = GATE.split("export function hideGate", 1)[1].split("\nexport function", 1)[0]
    assert "startIntro(" in show and "stopIntro(" in hide, "게이트를 띄울 때 시작, 로그인하면 멈춤"


def test_gate_styles_exist():
    css = _read(SRC, "styles", "custom.css")
    for cls in (".gate-scene", ".gate-panel", ".gate-char"):
        assert cls in css, f"custom.css 에 {cls}"
    scene = css.split(".gate-scene{", 1)[1].split("}", 1)[0]
    assert "var(--navy)" in scene
    assert "position:fixed" in scene and "inset:0" in scene, "B안: 장면이 화면 전체를 덮는다"


def test_card_is_simple_login_only():
    panel = _render_block().split("gate-panel", 1)[1]
    for gone in ("stageFlow", "10개년", "section-help"):
        assert gone not in panel, f"카드에서 {gone} 는 뺐다(소개는 장면 몫)"
    assert "ondo-word" in panel and "<b>ON</b>DO" in panel


def test_on_of_ondo_is_ci_red_everywhere():
    css = _read(SRC, "styles", "custom.css")
    assert re.search(r"\.ondo-word b\{[^}]*color:var\(--brand\)", css), "워드마크 ON 은 CI 빨강"
    side = _read(SRC, "components", "sidebar.js")
    assert side.count("ondo-word") >= 2, "사이드바·머리 워드마크도 같은 클래스"
    intro = _read(SRC, "components", "gate_intro.js")
    assert "RED" in intro and "? RED" in intro, "인트로 점 글자의 ON 도 빨강"
    left = intro.split("function logoTargets", 1)[1].split("\n  }", 1)[0]
    assert "W * 0.3" in left or "cx" in left, "B안: 글자는 카드 왼쪽 빈 곳 가운데"


def test_favicon_is_thermometer_svg():
    html = _read(APP, "web", "index.html")
    assert 'rel="icon"' in html and "favicon.svg" in html, "탭 아이콘(온도계, 2026-10-28 grace 3번)"
    svg = _read(SRC, "assets", "favicon.svg")
    assert "#9DB3E0" in svg and "#E58F79" in svg and "#0B1020" in svg, "수은은 파랑→산호(10/28 grace — CI 빨강은 탭에서 너무 셌다)"


def test_gate_matches_main_palette_and_fades_into_main():
    """오프닝 → 메인이 이어지게(10/28): 장면 색은 메인 팔레트(파랑·산호), 로그인하면 밝게 풀리며 메인이 떠오른다."""
    css = _read(SRC, "styles", "custom.css")
    scene = css.split(".gate-scene{", 1)[1].split("}", 1)[0]
    assert "62,230,196" not in scene and "113,140,191" in scene, "빛 번짐은 메인 파랑·산호"
    assert "gate--leave" in css and "app-enter" in css and "prefers-reduced-motion" in css.split("gate--leave", 1)[1]
    hide = GATE.split("export function hideGate", 1)[1].split("\nexport function", 1)[0]
    assert "gate--leave" in hide and "app-enter" in hide


def test_flow_is_rich_but_capped():
    """흐름 점이 허전하지 않게(10/28) — 양을 늘리되 상한을 둬서 느려지지 않게."""
    intro = _read(SRC, "components", "gate_intro.js")
    assert "flow.length < 1400" in intro and "lighter" in intro and "destination-out" in intro


def test_flow_speed_and_soft_twinkle():
    intro = _read(SRC, "components", "gate_intro.js")
    assert "rnd(0.00032, 0.0005)" in intro, "흐름 점 조금 더 빠르게(10/28)"
    assert "0.75 + 0.25 * Math.sin" in intro, "반짝임은 은은하게"


def test_busy_overlay_is_thermometer_with_character():
    """4단계 로딩(10/28 가안): 온도계 수은이 파랑→산호로 차오르고, 옆에 그 일을 맡은 캐릭터 + 문구. 조잡하지 않게 카드 하나."""
    html = _read(APP, "web", "index.html")
    busy = html.split('id="busy"', 1)[1].split("</div>\n  </div>", 1)[0]
    assert "loader-thermo" in busy and 'id="busyChar"' in busy and 'id="busyText"' in busy
    fb = _read(SRC, "components", "feedback.js")
    assert "CHAR_IMG" in fb and "busyChar" in fb
    css = _read(SRC, "styles", "custom.css")
    assert "@keyframes loaderFill" in css and "prefers-reduced-motion" in css.split("@keyframes loaderFill", 1)[1]


def test_home_year_buttons_keep_scroll():
    js = _read(SRC, "main.js")
    gy = js.split('closest("[data-goyear]")', 1)[1].split("return; }", 1)[0]
    assert "scrollY" in gy, "메인 연도 버튼을 눌러도 맨 위로 튀지 않게(10/28 grace)"


def test_chat_title_is_ondo():
    chat = _read(SRC, "components", "chat.js")
    assert "ONDO 탐험대" in chat and "ThreeON 탐험대" not in chat
