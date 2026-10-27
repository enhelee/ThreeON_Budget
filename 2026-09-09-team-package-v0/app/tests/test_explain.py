# -*- coding: utf-8 -*-
"""근거 설명 자동 초안(2026-10-27, 경진대회 B) — 검토 큐 한 줄의 사실을 문장으로, 원인은 «추정»으로만."""
import os
import sys

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from budget import explain as E   # noqa: E402
from tests.test_upload_export_fixes import _analyzed, srv   # noqa: E402,F401


def _v(text, amt, conf=0.9, basis="사업명 유사"):
    return {"텍스트": text, "금액천원": amt, "확신도": conf, "근거": basis}


def test_money_units():
    assert E.money(339_400) == "3.4억 원"
    assert E.money(87_000) == "87백만 원"
    assert E.money(75) == "75천원"
    assert E.money(-164_000) == "−1.6억 원"


def test_over_executed_line_facts_and_draft():
    vs = [_v("2025년 정기점검 3회 기성", 200_000), _v("정기점검 자재 구매", 100_000),
          _v("소모품", 30_000), _v(float("nan"), 9_000, conf=None, basis=None)]
    prev = {"name": "2024년 정기점검", "actual": 150_000.0, "plan": 0.0, "sim": 0.9}
    r = E.build({"plan": 100_000, "actual": 339_000}, vs, prev)
    assert r["facts"][0] == "계획 1.0억 원 대비 3.4억 원 집행(339%, 2.4억 원 초과)."
    assert "전표 4건 중 상위 3건" in r["facts"][1] and "nan" not in r["facts"][1]
    assert "실적의 97%" in r["facts"][1]
    assert "대비 2.3배" in r["facts"][2]
    assert r["facts"][3].startswith("매칭 근거: 사업명 유사 3건")
    assert "매칭 근거" not in r["draft"]            # 사유 초안에는 «어떻게 붙었나»를 넣지 않는다
    assert "추정 원인: 기성(분할) 대금 집행" in r["draft"]
    assert len(r["draft"]) <= E.DRAFT_MAX


def test_not_executed_and_lowconf_mix_hint():
    r = E.build({"plan": 50_000, "actual": 0}, [], None)
    assert r["facts"] == ["미시행 — 계획 50백만 원 전액이 집행되지 않았다."]
    assert r["hints"] == []
    vs = [_v("다른 공사 준공", 190_000, conf=0.3, basis="임의 귀속(유사도 낮음)")]
    r = E.build({"plan": 5_000, "actual": 190_000}, vs, None)
    assert any(h.startswith("다른 사업 전표 혼입 가능") for h in r["hints"])
    assert r["facts"][1].startswith("전표 1건: «다른 공사 준공»")


def test_offsetting_vouchers_hint():
    vs = [_v("정기점검", 164_000), _v("정기점검", -164_000), _v("정기점검", 164_000)]
    r = E.build({"plan": 40_000, "actual": 164_000}, vs, None)
    assert any(h.startswith("취소·재전기 전표 포함") for h in r["hints"])


def test_prev_match_ignores_year_but_not_equipment():
    rows = [{"사업명": "2024년 화성 정기점검보수공사(제어분야)", "실적금액": 10, "연예산": 10},
            {"사업명": "2024년 화성 정기점검보수공사(GT분야)", "실적금액": 7, "연예산": 5},
            {"사업명": "2024년 화성 정기점검보수공사(GT분야)", "실적금액": 3, "연예산": 5}]
    m = E.prev_match("2025년 화성 정기점검보수공사(GT분야)", rows)
    assert m["name"] == "2024년 화성 정기점검보수공사(GT분야)" and m["actual"] == 10
    assert E.prev_match("2025년 화성 정기점검보수공사(SRF분야)", rows[:1]) is None   # 설비 다름
    assert E.prev_match("전혀 다른 사업", rows) is None


def test_explain_api(srv):
    _, client, _ = srv
    _analyzed(client)
    biz = client.get("/api/branch-detail?year=2023&branch=화성지사").json()["biz"]
    b = next(x for x in biz if x["전표"])
    q = {"year": "2023", "budget": b["budget"], "branch": "화성지사", "item": b["예산과목"], "name": b["사업명"]}
    r = client.get("/api/review-explain", params=q)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["facts"] and isinstance(d["hints"], list) and d["draft"]
    assert "prev" in d                      # 2022 분석이 없으면 None
    r = client.get("/api/review-explain", params={**q, "name": "없는 사업"})
    assert r.status_code == 404
