# -*- coding: utf-8 -*-
"""캐릭터 챗봇 1단계 — 규칙 엔진(사용법·화면 이동·진행 상황)과 /api/chat.

지키는 것: ① 화면에 띄우는 추천 질문은 전부 알아듣는다 ② 이동 주소가 router.js 와 맞다
③ 진행 상황 숫자는 DB 에서 읽은 값만 ④ 챗봇은 읽기만 한다 — 감사 로그·계산 캐시를 건드리지 않는다.
"""
import os
import re
import sys

import pytest

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(APP_DIR, "src")
for p in (APP_DIR, SRC):
    if p not in sys.path:
        sys.path.insert(0, p)

from budget import db as dbm   # noqa: E402
from budget.chat import engine as ce, kb   # noqa: E402


def ask(q, view="home", year="2025", provider=None):
    return ce.RuleEngine(status_provider=provider).answer(q, {"view": view, "year": year})["answer"]


def test_normalize_and_year():
    assert ce.normalize("  검토 큐, 열어 줘!") == "검토큐열어줘"
    assert ce.find_year("25년 동탄") == "2025"
    assert ce.find_year("2024 손익") == "2024"
    assert ce.find_year("작년 실적", "2025") == "2024"
    assert ce.find_year("올해 어디까지", "2025") == "2025"
    assert ce.find_year("실적", "2025") is None


@pytest.mark.parametrize("q,intent,faq_or_hash", [
    ("마감은 어떻게 해?", "help.howto", "#/settings"),
    ("마감 해제는 어떻게 해?", "help.howto", "unlock"),
    ("계획은 어떻게 올려?", "help.howto", "#/plan"),
    ("분석은 어떻게 해?", "help.howto", "#/collect"),
    ("재배정은 어떻게 해?", "help.howto", "#/detail"),
    ("분석 반영은 언제 눌러?", "help.howto", "#/detail"),
    ("단축키 알려줘", "help.howto", "#/review"),
    ("차이 사유는 어떻게 넣어?", "help.howto", "#/review"),
    ("실적 집계표 어디서 받아?", "help.howto", "#/stats"),
    ("전망은 어떻게 해?", "help.howto", "#/forecast"),
    ("표준화 결과가 비어", "help.howto", "#/settings"),
    ("AI 학습은 뭐야?", "help.howto", "#/settings"),
    ("새 연도는 어떻게 만들어?", "help.howto", "#/settings/master"),
    ("예산 계획 양식 다운받을 수 있어?", "help.howto", "plan_template"),
    ("계획 양식 받을 수 있어?", "help.howto", "plan_template"),
    ("검토 큐 열어줘", "nav.goto", "#/review"),
    ("변경 이력 보여줘", "nav.goto", "#/settings/history"),
    ("전년 대비 보여줘", "nav.goto", "#/stats/compare"),
    ("3+ 상세 열어줘", "nav.goto", "#/detail"),
    ("표준화 열어줘", "nav.goto", "#/forecast/bench"),
    ("실적 집계로 가자", "nav.goto", "#/collect"),
    ("검토 큐", "nav.goto", "#/review"),
    # 말로 물을 때(음성 → 글자) 흔한 높임·띄어쓰기 — «가 주세요»·«보여 주세요»
    ("검토 큐로 가 주세요", "nav.goto", "#/review"),
    ("중장기 전망 보여 주세요", "nav.goto", "#/forecast/table"),
    ("메인으로 가 줘", "nav.goto", "#/home"),
    ("올해 어디까지 했어?", "status.progress", None),
])
def test_intents(q, intent, faq_or_hash):
    a = ask(q)
    assert a["intent"] == intent, (q, a)
    if faq_or_hash and faq_or_hash.startswith("#/"):
        assert faq_or_hash in [l["hash"] for l in a["links"]], (q, a["links"])
    elif faq_or_hash:
        assert a["text"] == next(f["text"] for f in kb.FAQ if f["id"] == faq_or_hash)


def test_unknown_question_falls_back_with_mood():
    a = ask("오늘 점심 뭐 먹지")
    assert a["intent"] == "fallback" and a["mood"] == "wow"


def test_every_suggestion_is_understood():
    """패널에 띄우는 추천 질문이 «몰라요»로 끝나면 첫인상이 깨진다."""
    for view, qs in kb.SUGGEST.items():
        for q in qs:
            assert ask(q, view=view)["intent"] != "fallback", (view, q)


def test_fallback_chips_are_understood():
    """«혹시 이거요?» 칩을 누르면 그 질문이 다시 간다 — 칩도 알아들어야 한다."""
    for item in kb.FAQ:
        title = ce._faq_title(item)
        assert ask(title)["intent"] != "fallback", title


def test_screen_hashes_match_router():
    src = open(os.path.join(APP_DIR, "web", "src", "router.js"), encoding="utf-8").read()
    view_hash = dict(re.findall(r'(\w+): "(\w+)"', src.split("const VIEW_HASH = {", 1)[1].split("};", 1)[0]))
    known = set(view_hash.values())
    for hash_, _, _ in kb.SCREENS:
        parts = hash_[2:].split("/")
        assert parts[0] in known, hash_
    for item in kb.FAQ:
        for link in item["links"]:
            h = link[1]
            assert h[2:].split("/")[0] in known, (item["id"], h)


def test_status_uses_provider_values_only():
    calls = []

    def provider(year):
        calls.append(year)
        return {"year": "2025",
                "datasets": [{"kind": "plan", "row_count": 1700}, {"kind": "erp", "row_count": 24000}],
                "runs": {"손익": "2026-10-27T10:00:00", "자본": "2026-10-27T10:01:00"},
                "pending": {"total": 3, "learn_pending": 78}, "locked": False}
    a = ask("올해 어디까지 했어?", provider=provider)
    assert calls == ["2025"]
    flat = " ".join(" ".join(r) for r in a["table"])
    assert "1,700행" in flat and "24,000행" in flat and "3건" in flat and "78건" in flat
    assert "분석 반영" in a["text"] and a["links"][0]["hash"] == "#/detail"
    assert a["who"] == "hj" and a["ctx"] == "2025년으로 봤어요"


def test_status_next_steps():
    def make(**kw):
        base = {"year": "2025", "datasets": [], "runs": {}, "pending": {}, "locked": False}
        base.update(kw)
        return lambda y: base
    assert ask("어디까지 했어", provider=make())["links"][0]["hash"] == "#/plan"
    assert ask("어디까지 했어", provider=make(datasets=[{"kind": "plan"}]))["links"][0]["hash"] == "#/collect"
    done = make(datasets=[{"kind": "plan"}, {"kind": "erp"}], runs={"손익": "x"}, locked=True)
    assert ask("어디까지 했어", provider=done)["links"][0]["hash"] == "#/forecast"
    assert ask("어디까지 했어", provider=lambda y: None)["links"][0]["hash"] == "#/plan"


def test_chat_package_is_read_only():
    """챗봇 모듈은 DB 에 쓰지 않는다 — 쓰는 길은 서버가 넘기는 읽기 함수뿐."""
    d = os.path.join(SRC, "budget", "chat")
    for name in os.listdir(d):
        if name.endswith(".py"):
            s = open(os.path.join(d, name), encoding="utf-8").read()
            for bad in ("INSERT", "UPDATE ", "DELETE", "commit(", "import db", "from .. import"):
                assert bad not in s, (name, bad)


# ── API ────────────────────────────────────────────────────
@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "")
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setattr(dbm, "DEFAULT_DB", str(tmp_path / "t.db"))
    import server
    from budget import auth as authm
    monkeypatch.setattr(server, "AUTH", authm.AuthConfig())
    from fastapi.testclient import TestClient
    return TestClient(server.app)


def _audit_count():
    conn = dbm.connect()
    try:
        return conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
    finally:
        conn.close()


def test_api_chat_answers_and_is_not_audited(client):
    before = _audit_count()
    r = client.post("/api/chat", json={"question": "검토 큐 열어줘", "context": {"view": "review", "year": "2025"}})
    assert r.status_code == 200
    body = r.json()
    assert body["answer"]["intent"] == "nav.goto" and body["answer"]["engine"] == "rule"
    assert body["suggestions"] == kb.SUGGEST["review"]
    assert _audit_count() == before          # 질문 원문을 남기지 않고, 계산 캐시 버전도 그대로


def test_api_chat_status_on_empty_db(client):
    r = client.post("/api/chat", json={"question": "올해 어디까지 했어?", "context": {"view": "home"}})
    assert r.status_code == 200
    assert "아직 올라온 자료가 없어요" in r.json()["answer"]["text"]


def test_api_chat_ignores_bad_context_and_limits_length(client):
    r = client.post("/api/chat", json={"question": "어디까지 했어", "context": {"view": "<x>", "year": "../1"}})
    assert r.status_code == 200 and r.json()["suggestions"] == kb.SUGGEST["home"]
    assert client.post("/api/chat", json={"question": "가" * 301}).status_code == 400


def test_api_chat_suggestions(client):
    assert client.get("/api/chat/suggestions?view=stats").json()["suggestions"] == kb.SUGGEST["stats"]
    assert client.get("/api/chat/suggestions?view=nope").json()["suggestions"] == kb.SUGGEST["home"]


def test_no_menu_numbers_in_answers():
    """사이드바 번호(«4 통계», «3+ 상세»)는 대화에서 읽기 어색하다 — 화면 이름만 쓴다(10/27 사용자 의견)."""
    import re as _re
    texts = [f["text"] for f in kb.FAQ] + [link[0] for f in kb.FAQ for link in f["links"]] + [n for _, n, _ in kb.SCREENS]
    for t in texts:
        assert not _re.search(r"(^|[\s«(])[1-5]\+? (예산|실적|통계|표준화|중장기|상세)", t), t


def test_ops_questions_removed():
    assert not {"slow", "stale"} & {f["id"] for f in kb.FAQ}


def test_nav_moves_right_away_and_help_points_at_button():
    nav = ask("검토 큐 열어줘")
    assert nav["go"] == "#/review"
    lock = ask("마감은 어떻게 해?")
    assert "go" not in lock                                  # 사용법은 버튼만 — 사람이 누를 때 간다
    assert lock["links"][0]["focus"] == '[data-action="lock-year"]'


def test_focus_selectors_exist_in_screen_code():
    """짚어 줄 버튼이 화면 코드에 실제로 있어야 한다 — 화면을 고치면서 사라지면 여기서 먼저 알린다."""
    web = os.path.join(APP_DIR, "web")
    src = "".join(open(os.path.join(dp, f), encoding="utf-8").read()
                  for dp, _, fs in os.walk(os.path.join(web, "src")) for f in fs if f.endswith(".js"))
    src += open(os.path.join(web, "index.html"), encoding="utf-8").read()
    sels = {link[2] for f in kb.FAQ for link in f["links"] if len(link) > 2}
    sels |= {v[2] for v in ce.STEP_LINK.values()} | {"[data-rq-card]"}
    for sel in sels:
        for one in (x.strip() for x in sel.split(",")):
            m = re.match(r'\[data-([a-z-]+)(?:="([^"]+)")?\]$|#(\w+)$', one)
            assert m, one
            if m.group(3):
                assert f'id="{m.group(3)}"' in src, one
            elif m.group(2):
                assert f'data-{m.group(1)}="{m.group(2)}"' in src, one
            else:
                assert f"data-{m.group(1)}" in src, one


# ── 말로 묻기: 음성 인식이 한 글자 틀리게 받아 적어도 앱 낱말로 고쳐 알아듣는다(2026-11-03) ──
@pytest.mark.parametrize("heard,want", [
    ("검토키로 가죠", "검토큐로가죠"),
    ("말감은 어떻게 해?", "마감은어떻게해"),
    ("중장기 전망 보여주세요.", "중장기전망보여주세요"),
])
def test_voice_fix_snaps_to_app_words(heard, want):
    assert ce.voice_fix(ce.normalize(heard)) == want


@pytest.mark.parametrize("q", ["오늘 날씨 어때", "작년이랑 비교해줘", "동탄 지사 보여줘", "고마워"])
def test_voice_fix_leaves_unrelated_words(q):
    assert ce.voice_fix(ce.normalize(q)) == ce.normalize(q)


def test_voice_question_navigates_and_answers():
    eng = ce.RuleEngine()
    nav = eng.answer("검토키로 가죠", {"view": "home", "voice": True})["answer"]
    assert nav["intent"] == "nav.goto" and nav["go"] == "#/review"
    howto = eng.answer("말감은 어떻게 해?", {"view": "home", "voice": True})["answer"]
    assert howto["intent"] == "help.howto"
    # 글자로 친 질문은 고치지 않는다(사람이 친 글자는 그대로)
    typed = eng.answer("말감은 어떻게 해?", {"view": "home"})["answer"]
    assert typed["text"] != howto["text"]


def test_api_voice_flag_fixes_misheard_words(client):
    r = client.post("/api/chat", json={"question": "검토키로 가죠", "context": {"view": "home", "voice": True}})
    assert r.json()["answer"].get("go") == "#/review"
