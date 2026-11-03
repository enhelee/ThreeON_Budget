# -*- coding: utf-8 -*-
"""챗봇 사업 실적 묻기(chat/facts.py) — 가짜 사업 줄로. 숫자는 줄 값 그대로·합계만."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from budget.chat import engine as ce, facts   # noqa: E402


def L(y, d, name, plan, act, item="수선유지비"):
    return {"연도": y, "예산": "손익", "처지사": d, "예산과목": item, "사업명": name, "연예산": plan, "실적금액": act}


DATA = {"lines": [
    L("2025", "파주지사", "#1 GT 정기점검 보수공사", 300000, 280000),
    L("2025", "파주지사", "#2 GT 정기점검 보수공사", 200000, 0),
    L("2025", "파주지사", "건물 도장", 5000, 4800),
    L("2024", "파주지사", "#1 GT 정기점검 보수공사", 250000, 260000),
    L("2023", "파주지사", "배열회수보일러 보수", 90000, 85000),
    L("2025", "동탄지사", "가스터빈 정기점검", 400000, 390000),
    L("2025", "파주지사", "LTSA 장기유지보수계약", 700000, 650000),
], "depts": ["파주지사", "동탄지사"]}


def eng():
    return ce.RuleEngine(facts_provider=lambda: DATA)


def ask(q, year="2025"):
    return eng().answer(q, {"view": "home", "year": year})["answer"]


def test_parse_question():
    q = "25년도에 파주지사 정기점검 보수 얼마 들었어"
    assert facts.find_years(q) == ["2025"]
    assert facts.find_dept(q, DATA["depts"]) == "파주지사"
    assert facts.keywords(q, "파주지사") == ["정기점검", "보수"]
    assert facts.find_dept("파주 터빈 점검 비용?", DATA["depts"]) == "파주지사"
    assert facts.find_years("작년에 얼마", "2025") == ["2024"]


def test_cost_sums_matching_lines_of_that_year_and_branch():
    a = ask("25년도에 파주지사 정기점검 보수 얼마 들었어")
    assert a["intent"] == "fact.cost"
    assert "2건" in a["text"] and "2.8억원" in a["text"]           # 280000 + 0 천원
    assert len(a["table"]) == 3 and a["table"][1][1] == "#1 GT 정기점검 보수공사"
    assert "지사" not in a["table"][0]                                 # 지사를 정해 물으면 지사 칸 없음
    assert "2025" in a["source"]


def test_turbine_means_gt_too():
    a = ask("파주지사 터빈 점검할때 쓰인 비용?")
    assert a["intent"] == "fact.cost"
    names = {r[1] for r in a["table"][1:]}
    assert names == {"#1 GT 정기점검 보수공사", "#2 GT 정기점검 보수공사"}
    assert "2024" in a["text"] and "2025" in a["text"]            # 연도를 안 말하면 모든 연도 + 연도별


def test_all_words_must_match_no_guessing():
    a = ask("파주지사 냉각탑 보수 얼마 들었어")
    assert a["intent"] == "fact.cost" and a["table"] is None and "못 찾았어요" in a["text"]
    assert a["mood"] == "wow"


def test_history_lists_years_with_actual_spend():
    a = ask("파주지사에서 몇년도에 정기점검 한적 있어?")
    assert a["intent"] == "fact.history"
    assert "2025년, 2024년" in a["text"]
    assert all(int(r[-1].replace(",", "")) > 0 for r in a["table"][1:])   # 실적 0 인 계획만 있는 줄은 «한 적» 아님


def test_history_whole_branch_without_words_is_per_year_summary():
    a = ask("파주지사 무슨 공사 한적 있어?")
    assert a["intent"] == "fact.history"
    assert [r[0] for r in a["table"][1:]] == ["2025", "2024", "2023"]
    assert a["table"][1][1] == "3건"                                  # 2025 실적 있는 줄 3개(실적 0 은 뺌)


def test_cost_without_words_lists_biggest_of_the_year():
    a = ask("어떤 공사에 얼마 들었어?")
    assert a["intent"] == "fact.cost" and a["table"][1][2] == "LTSA 장기유지보수계약"
    assert {r[0] for r in a["table"][1:]} == {"2025"}                  # 연도를 안 말하면 지금 연도


def test_not_found_tells_counts_per_word():
    a = ask("파주지사 냉각탑 보수 얼마 들었어")
    assert "«냉각탑» 0건" in a["text"] and "«보수» " in a["text"]


def test_ltsa_spelling():
    a = ask("파주 장기유지보수 비용 얼마야")
    assert a["table"] and a["table"][1][1] == "LTSA 장기유지보수계약"


def test_other_questions_unchanged():
    assert ask("마감은 어떻게 해?")["intent"] == "help.howto"
    assert ask("검토 큐 열어줘")["intent"] == "nav.goto"
    assert ask("올해 어디까지 했어?")["intent"] == "status.progress"


def test_no_provider_or_no_data_falls_back():
    a = ce.RuleEngine().answer("파주지사 정기점검 얼마 들었어", {"view": "home"})["answer"]
    assert a["intent"] != "fact.cost"
    a = ce.RuleEngine(facts_provider=lambda: None).answer("파주지사 정기점검 얼마 들었어", {"view": "home"})["answer"]
    assert a["intent"] != "fact.cost"


def test_won_format():
    assert facts.won(280000) == "2.8억원"
    assert facts.won(8400) == "840만원"
    assert facts.won(5) == "5천원"
