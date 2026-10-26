# -*- coding: utf-8 -*-
"""이상 알림(2026-10-22) — 급증·예산 초과·음수 실적·미매칭 비중 규칙과 /api/alerts."""
import os
import sys

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from budget import alerts as al   # noqa: E402
from tests.test_upload_export_fixes import _analyzed, srv   # noqa: E402,F401


def L(branch, item, plan, actual, gubun="계획집행", budget="손익", name="사업"):
    return {"budget": budget, "처지사": branch, "예산과목": item, "사업명": name,
            "연예산": plan, "실적금액": actual, "구분": gubun}


def kinds(found, kind):
    return [a for a in found if a["kind"] == kind]


def test_over_budget_grouped_by_branch_item():
    found = al.compute_alerts([L("화성", "정기점검", 100_000, 90_000, name="a"),
                               L("화성", "정기점검", 0, 80_000, gubun="신규", name="b"),
                               L("동탄", "정기점검", 100_000, 105_000)])
    over = kinds(found, "예산 초과")
    assert [(a["branch"], a["amount"], a["severity"]) for a in over] == [("화성", 70_000, "높음")]
    # 동탄 5,000 초과는 OVER_MIN(10,000) 미만이라 빠진다


def test_spike_vs_previous_year():
    cur = [L("화성", "정기점검", 0, 300_000), L("동탄", "정기점검", 0, 120_000),
           L("판교", "정기점검", 0, 60_000)]
    prev = [L("화성", "정기점검", 0, 100_000), L("동탄", "정기점검", 0, 100_000)]
    spikes = {a["branch"]: a for a in kinds(al.compute_alerts(cur, prev), "급증")}
    assert spikes["화성"]["amount"] == 200_000 and "3.0배" in spikes["화성"]["text"]
    assert "동탄" not in spikes                      # 1.2배 — 2배 미만
    assert "전년 실적 없음" in spikes["판교"]["text"]   # 전년 0 → 올해 5천만 이상
    assert not kinds(al.compute_alerts(cur, None), "급증")   # 전년 자료가 없으면 규칙 자체를 건너뛴다


def test_negative_actual_per_business_line():
    found = al.compute_alerts([L("강남", "안전지적사항", 0, -133_000, gubun="신규", name="계정대체"),
                               L("강남", "정기점검", 0, -500)])
    neg = kinds(found, "음수 실적")
    assert len(neg) == 1 and neg[0]["name"] == "계정대체" and neg[0]["severity"] == "높음"


def test_unmatched_share_per_budget_and_branch():
    lines = [L("본사", "정기점검", 1_000_000, 500_000),
             L("화성", "정기점검", 0, 200_000, gubun="신규"),
             L("동탄", "정기점검", 100_000, 100_000)]
    found = kinds(al.compute_alerts(lines, None, {"손익": 100_000}), "미매칭 비중")
    overall = [a for a in found if a["branch"] is None]
    assert len(overall) == 1 and overall[0]["amount"] == 300_000        # 신규 20만 + 미매핑 10만
    assert overall[0]["severity"] == "높음"                              # 300/900 = 33%
    assert any(a["branch"] == "화성" for a in found)                     # 지사 실적 전부가 신규


def test_order_high_first_then_amount():
    found = al.compute_alerts([L("A", "x", 100_000, 120_000),            # 초과 2만 → 보통
                               L("B", "x", 100_000, 400_000),            # 초과 30만 → 높음
                               L("C", "x", 100_000, 200_000)])           # 초과 10만 → 높음
    assert [a["branch"] for a in found] == ["B", "C", "A"]
    sm = al.summarize(found)
    assert sm == {"total": 3, "high": 2, "counts": {"급증": 0, "예산 초과": 3, "음수 실적": 0, "미매칭 비중": 0}}


def test_api_empty_year_and_analyzed_year(srv):
    _, client, _ = srv
    r = client.get("/api/alerts?year=2024").json()
    assert r["alerts"] == [] and r["summary"]["total"] == 0
    _analyzed(client)
    r = client.get("/api/alerts?year=2023")
    assert r.status_code == 200
    body = r.json()
    assert body["prev_year"] is None                         # 2022 분석 없음 → 급증 규칙 건너뜀
    assert body["summary"]["total"] == len(body["alerts"])
    for a in body["alerts"]:
        assert a["kind"] in al.KINDS and a["severity"] in ("높음", "보통")


def test_api_rejects_bad_year(srv):
    _, client, _ = srv
    assert client.get("/api/alerts?year=abcd").status_code == 400
