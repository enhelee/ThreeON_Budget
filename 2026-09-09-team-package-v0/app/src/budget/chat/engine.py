# -*- coding: utf-8 -*-
"""챗봇 규칙 엔진 — 질문 → 정규화 → 의도 → 답 카드(1단계: 사용법·화면 이동·진행 상황).

답의 숫자는 앱이 이미 가진 값(status_provider 가 DB 에서 읽은 것)만 쓴다. 문장은 정해 둔 틀이다.
나중에 사내 LLM 을 붙일 때는 ChatEngine 을 하나 더 만들어 «못 알아들은 질문 분류»와 «말투 다듬기»만
맡긴다(설계 7장) — 숫자는 계속 이 규칙 처리기가 낸다.

답 카드(dict):
  who      답하는 캐릭터 — hj 한장이 · mt 매칭이 · gt 검토미 · yc 예측이
  mood     표정 — default · wow(못 알아들음)
  text     결론 문장
  ctx      «○○으로 봤어요» — 해석한 맥락(없으면 빈칸)
  table    [[머리…], [행…], …] 또는 None
  links    [{"label", "hash", "focus"}] — 누르면 그 화면으로, focus(CSS 선택자)가 있으면 도착해서 그 버튼을 반짝인다
  go       주소 — «열어줘»처럼 이동을 시키는 말이면 화면이 버튼 없이 바로 옮긴다
  source   근거 한 줄(숫자를 쓴 답만)
  intent · score · engine("rule")
"""
import re

from . import kb

ENGINE_NAME = "rule"
MAX_LEN = 300

NAV_CUES = ("열어", "가자", "가줘", "이동", "보여줘", "보여줄래", "띄워", "켜줘", "으로가", "로가", "들어가")
HOWTO_CUES = ("어떻게", "방법", "하려면", "뭐야", "뭔가요", "뭐예요", "어디서", "언제", "왜", "알려", "하나요", "해야")
STATUS_CUES = ("어디까지", "진행상황", "진행상태", "다음할일", "뭐해야", "뭘해야", "남은일", "얼마나했", "다했")

STEP_LINK = {"plan": ("예산 계획으로", "#/plan", '[data-action="pick-plan"]'),
             "erp": ("실적 집계로", "#/collect", '[data-action="pick-erp"]'),
             "analyze": ("실적 집계로", "#/collect", "#analyzeBtn"),
             "apply": ("상세로", "#/detail", "#analyzeBtn"),
             "learn": ("설정 · 연도·학습으로", "#/settings", '[data-action="learn"]'),
             "lock": ("설정 · 연도·학습으로", "#/settings", '[data-action="lock-year"]'),
             "forecast": ("중장기 전망으로", "#/forecast", "[data-fcbase]")}


def normalize(text):
    """띄어쓰기·문장부호를 지우고 소문자로. «3+»의 + 는 남긴다."""
    t = (text or "").lower()
    t = re.sub(r"[\s.,!?~·…'\"«»()\[\]{}:;/\\-]+", "", t)
    return t


def find_year(text, base_year=None):
    """«2025», «25년», «올해·작년·내년» → 연도 문자열. 없으면 None."""
    m = re.search(r"(20\d{2})", text)
    if m:
        return m.group(1)
    m = re.search(r"(?<!\d)(\d{2})년", text)
    if m:
        return str(2000 + int(m.group(1)))
    if base_year and str(base_year).isdigit():
        b = int(base_year)
        n = normalize(text)
        if "작년" in n or "전년도" in n or "지난해" in n:
            return str(b - 1)
        if "내년" in n:
            return str(b + 1)
        if "올해" in n or "이번해" in n or "금년" in n:
            return str(b)
    return None


def _has(n, key):
    """key 가 글자면 «들어 있나», 묶음(tuple)이면 «조각이 모두 들어 있나»."""
    return all(k in n for k in key) if isinstance(key, tuple) else key in n


def _key_len(key):
    return sum(len(k) for k in key) if isinstance(key, tuple) else len(key)


def match_faq(n):
    """가장 잘 맞는 사용법 답과 점수(맞은 키워드 글자 수의 합). 없으면 (None, 0)."""
    best, best_score = None, 0
    for item in kb.FAQ:
        score = sum(_key_len(k) for k in item["keys"] if _has(n, k))
        if score > best_score:
            best, best_score = item, score
    return best, best_score


def match_screen(n):
    for hash_, name, keys in kb.SCREENS:
        if any(k in n for k in keys):
            return hash_, name
    return None, None


def ro(word):
    """«(으)로» — 받침이 없거나 ㄹ 받침이면 «로», 그 밖의 받침이면 «으로»(한글로 끝나지 않으면 «로»)."""
    last = (word or "").rstrip()[-1:]
    if not ("가" <= last <= "힣"):
        return f"{word}로"
    jong = (ord(last) - 0xAC00) % 28
    return f"{word}{'으로' if jong not in (0, 8) else '로'}"


def suggestions_for(view):
    return list(kb.SUGGEST.get(view or "home", kb.SUGGEST["home"]))


def _card(who, text, intent, score, links=(), ctx="", table=None, source="", mood="default"):
    return {"who": who, "mood": mood, "text": text, "ctx": ctx, "table": table,
            "links": [{"label": l[0], "hash": l[1], "focus": l[2] if len(l) > 2 else ""} for l in links],
            "source": source,
            "intent": intent, "score": score, "engine": ENGINE_NAME}


class ChatEngine:
    """엔진 교체 지점 — answer(question, context) → {"answer": 카드, "suggestions": [...]}."""
    name = "base"

    def answer(self, question, context=None):
        raise NotImplementedError


class RuleEngine(ChatEngine):
    name = ENGINE_NAME

    def __init__(self, status_provider=None):
        # status_provider(year) → {"year", "datasets", "runs", "pending", "locked"} | None
        #   서버가 넘긴다(DB 읽기만). 테스트는 가짜를 넘긴다.
        self.status_provider = status_provider

    def answer(self, question, context=None):
        ctx = context or {}
        view = ctx.get("view") or "home"
        q = (question or "").strip()[:MAX_LEN]
        n = normalize(q)
        sugg = suggestions_for(view)
        if not n:
            return {"answer": _card("mt", "궁금한 걸 적어 주세요. 아래 질문을 눌러도 돼요.", "empty", 0), "suggestions": sugg}

        faq, faq_score = match_faq(n)
        screen_hash, screen_name = match_screen(n)
        nav_cue = any(c in n for c in NAV_CUES)
        howto_cue = any(c in n for c in HOWTO_CUES)
        status_cue = any(c in n for c in STATUS_CUES)
        bare_screen = any(n == k for _, _, keys in kb.SCREENS for k in keys)   # «검토 큐»처럼 화면 이름만

        if status_cue:
            card = self._status(q, ctx)
        elif faq and howto_cue:
            card = self._help(faq, faq_score)
        elif screen_hash and (nav_cue or bare_screen):
            card = self._nav(screen_hash, screen_name)
        elif faq:
            card = self._help(faq, faq_score)
        elif screen_hash:
            card = self._nav(screen_hash, screen_name)
        else:
            card = self._fallback(n, view)
        return {"answer": card, "suggestions": sugg}

    # ── 처리기 ──────────────────────────────────────────────
    def _help(self, faq, score):
        return _card(faq["who"], faq["text"], "help.howto", score, faq["links"])

    def _nav(self, hash_, name):
        card = _card("mt", f"«{name}» 화면으로 갈게요.", "nav.goto", 1, [(f"{ro(name)} →", hash_)])
        card["go"] = hash_                       # 이동을 시키는 말 — 화면이 바로 옮긴다
        return card

    def _fallback(self, n, view):
        # 비슷한 사용법을 세 개까지 — 키워드 조각이 하나라도 걸리는 것
        near = []
        for item in kb.FAQ:
            if any(any(len(p) >= 2 and p in n for p in (k if isinstance(k, tuple) else (k[:2],))) for k in item["keys"]):
                near.append(item)
        links = [(_faq_title(i), "") for i in near[:3]]
        text = "아직 그 질문은 몰라요. 혹시 이거요?" if links else "아직 그 질문은 몰라요. 아래 질문처럼 물어봐 주세요."
        card = _card("mt", text, "fallback", 0, mood="wow")
        card["links"] = []
        card["ask"] = [t for t, _ in links]          # 누르면 그 질문을 다시 보낸다
        return card

    def _status(self, q, ctx):
        year = find_year(q, ctx.get("year")) or ctx.get("year") or None
        st = self.status_provider(year) if self.status_provider else None
        if not st or not st.get("year"):
            return _card("hj", "아직 올라온 자료가 없어요. 예산 계획부터 시작해요.", "status.progress", 1,
                         [STEP_LINK["plan"]])
        y = str(st["year"])
        ds = st.get("datasets") or []
        plan = next((d for d in ds if d.get("kind") == "plan"), None)
        erp = next((d for d in ds if d.get("kind") == "erp"), None)
        runs = st.get("runs") or {}
        pend = st.get("pending") or {}
        n_pend = int(pend.get("total") or 0)
        n_learn = int(pend.get("learn_pending") or 0)
        locked = bool(st.get("locked"))

        def when(r):
            return str(r)[:16].replace("T", " ") if r else ""

        rows = [["단계", "상태"],
                ["예산 계획", f"올림 · {int(plan.get('row_count') or 0):,}행" if plan else "아직"],
                ["실적(zrfm2)", f"올림 · {int(erp.get('row_count') or 0):,}행" if erp else "아직"],
                ["분석", " · ".join(f"{b} {when(runs[b])}" for b in ("손익", "자본") if b in runs) or "아직"],
                ["미반영 변경", f"{n_pend:,}건" if n_pend else "없음"],
                ["AI 학습 대기", f"{n_learn:,}건" if n_learn else "없음"],
                ["마감", "마감됨" if locked else "안 함"]]

        if not plan:
            step, nxt = "plan", "다음은 계획을 올릴 차례예요."
        elif not erp:
            step, nxt = "erp", "다음은 zrfm2 실적을 올릴 차례예요."
        elif not runs:
            step, nxt = "analyze", "다음은 «분석 실행»이에요."
        elif locked:
            step, nxt = "forecast", "마감까지 끝났어요. 이 연도는 중장기 전망의 입력으로 쓰여요."
        elif n_pend:
            step, nxt = "apply", f"고친 내용 {n_pend:,}건이 아직 분석에 반영 안 됐어요 — «분석 반영»을 눌러요."
        elif n_learn:
            step, nxt = "learn", f"학습 대기 {n_learn:,}건이 있어요 — 검토를 마쳤다면 «AI 학습»을 눌러요."
        else:
            step, nxt = "lock", "검토 큐를 마쳤다면 «연도 마감»을 하면 돼요."
        links = [STEP_LINK[step]]
        if step in ("apply", "learn", "lock") and not locked:
            links.append(("검토 큐로", "#/review", "[data-rq-card]"))
        return _card("hj", f"{y}년은 여기까지 했어요. {nxt}", "status.progress", 1, links,
                     ctx=f"{y}년으로 봤어요", table=rows, source=f"근거: {y}년 데이터셋·최신 분석·미반영 기록")


def _faq_title(item):
    """fallback 칩에 쓸 짧은 질문 — 첫 번째 링크 대신 의도를 묻는 말로."""
    return {
        "upload_plan": "계획은 어떻게 올려?", "analyze": "분석은 어떻게 해?", "review": "검토 큐는 어떻게 써?",
        "variance_note": "차이 사유는 어떻게 넣어?", "reassign": "재배정은 어떻게 해?", "learn": "AI 학습은 뭐야?",
        "lock": "마감은 어떻게 해?", "unlock": "마감 해제는 어떻게 해?", "export": "실적 집계표 어디서 받아?",
        "forecast_setup": "전망은 어떻게 해?", "forecast_empty": "표준화 결과가 비어", "plan_template": "계획 양식 받을 수 있어?", "year_config": "새 연도는 어떻게 만들어?", "login": "작업자 이름은 왜 넣어?",
        "history": "변경 이력은 어디서 봐?",
    }.get(item["id"], item["id"])
