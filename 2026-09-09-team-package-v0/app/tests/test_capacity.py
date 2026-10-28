# -*- coding: utf-8 -*-
"""용량 환산 표준금액(2026-10-28) — 신규 발전설비 지사의 등급별 표준금액을 기준 지사 용량 규칙으로.

규칙: 한 해 합계 = 고정분 F + 등급별 단가 k × MW (F·k[간이] = 간이 해 회귀, 나머지 = (평균 − F)/MW 중앙값),
과목별 = 기준 지사의 그 등급 해 과목 비중. 정비제외 해 = F 만.
"""
import pandas as pd
import pytest

from budget import capacity

ACC1, ACC2 = "수선유지비-열원경상정비", "수선유지비-열원정기점검"
HOT = "건설중인자산-재생고온부품"          # 고온부품 계획으로 따로 잡히는 과목 — 모형에서 뺀다


def _actuals(rows):
    return pd.DataFrame(rows, columns=["사업장", "연도", "예산과목", "금액"])


def _world():
    """기준 지사 둘(100·500MW): 간이 해 = 20억 + 0.2억/MW, MI 해 = 20억 + 0.6억/MW. 과목 비중 7:3."""
    refs = {"가지사": 100, "나지사": 500}
    acts, grades = [], []
    for site, mw in refs.items():
        for y, g in ((2021, "간이"), (2022, "간이"), (2023, "MI")):
            total = (20 + (0.2 if g == "간이" else 0.6) * mw) * 1e5
            acts += [(site, y, ACC1, total * 0.7), (site, y, ACC2, total * 0.3), (site, y, HOT, 999e5)]
            grades.append((site, y, g))
    return refs, _actuals(acts), pd.DataFrame(grades, columns=["사업장", "연도", "등급"])


def test_fit_recovers_fixed_and_unit_cost():
    refs, acts, grades = _world()
    m = capacity.fit_model(acts, grades, refs)
    assert m["fixed"] == pytest.approx(20e5)
    assert m["k"]["간이"] == pytest.approx(0.2e5)
    assert m["k"]["MI"] == pytest.approx(0.6e5)
    assert m["shares"]["MI"] == pytest.approx({ACC1: 0.7, ACC2: 0.3})      # 고온부품 과목은 비중에 없다


def test_target_rows_scale_by_capacity_and_split_by_share():
    refs, acts, grades = _world()
    m = capacity.fit_model(acts, grades, refs)
    rows = capacity.standard_rows(m, "다지사", {"mw": 270, "start": 2024, "excluded": {2027}})
    tot = rows.groupby("등급")["표준금액"].sum()
    assert tot["간이"] == pytest.approx((20 + 0.2 * 270) * 1e5)
    assert tot["MI"] == pytest.approx((20 + 0.6 * 270) * 1e5)
    assert tot["표준"] == pytest.approx(tot["간이"])
    assert tot[capacity.EXCLUDED] == pytest.approx(20e5)                    # 정비제외 = 고정분만
    mi = rows[rows["등급"] == "MI"].set_index("예산과목")["표준금액"]
    assert mi[ACC1] / mi.sum() == pytest.approx(0.7)
    assert set(rows["방식출처"]) == {"용량규칙"}


def test_apply_replaces_only_target_rows_and_keeps_manual():
    refs, acts, grades = _world()
    rules = pd.DataFrame([("가지사", "기준", None, 100, "", ""), ("나지사", "기준", None, 500, "", ""),
                          ("다지사", "대상", 2024, 270, "", "")], columns=capacity.RULE_COLS)
    std = pd.DataFrame([
        {"사업장": "가지사", "예산과목": ACC1, "등급": "간이", "표준금액": 1.0, "방식출처": "자동추천"},
        {"사업장": "다지사", "예산과목": ACC1, "등급": "간이", "표준금액": 2.0, "방식출처": "자동추천"},
        {"사업장": "다지사", "예산과목": ACC2, "등급": "MI", "표준금액": 3.0, "방식출처": "수동수정"},
    ])
    out, model, targets = capacity.apply_capacity(std, acts, grades, capacity.default_capacity(), rules)
    assert set(targets) == {"다지사"}
    keep = out[out["사업장"] == "가지사"]
    assert list(keep["표준금액"]) == [1.0]                                   # 기준 지사는 그대로
    d = out[out["사업장"] == "다지사"].set_index(["예산과목", "등급"])["표준금액"]
    assert d[(ACC2, "MI")] == 3.0                                           # 수동수정이 이긴다
    assert d[(ACC1, "간이")] == pytest.approx((20 + 0.2 * 270) * 1e5 * 0.7)


def test_defaults_match_user_capacity_file():
    cap = capacity.default_capacity()
    assert capacity.site_mw(cap, "화성지사") == 512
    assert capacity.site_mw(cap, "수원사업소") == 136                         # 개체 후(가장 늦게 준공)
    _, targets = capacity._clean_rules(capacity.default_rules(), cap)
    assert targets["수원사업소"]["excluded"] == {2027, 2028}
    assert {s: t["start"] for s, t in targets.items()} == {"양산지사": 2023, "대구지사": 2024, "청주지사": 2025, "수원사업소": 2029}
    ev = capacity.usage_events(capacity.default_rules(), cap)
    assert set(zip(ev["사업장"], ev["연도"])) == {("양산지사", 2023), ("대구지사", 2024), ("청주지사", 2025), ("수원사업소", 2029)}
