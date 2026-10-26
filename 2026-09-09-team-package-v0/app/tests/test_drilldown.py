# -*- coding: utf-8 -*-
"""드릴다운(2026-10-22) — 통계 과목 숫자 → 지사별 → 상세 전표, 전표마다 «매칭 근거»."""
import os
import sys

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from tests.test_upload_export_fixes import _analyzed, srv   # noqa: E402,F401

KNOWN = {"재배정", "재배정(신규 사업)", "학습", "학습(신규 사업)", "계획 없음(신규)",
         "규칙(크리티칼 용역)", "유사도 미달(신규)", "총액 기준(자재류)", "사업명 유사",
         "임의 귀속(유사도 낮음)", "유일한 계획 사업"}


def _vouchers(client, branch="화성지사"):
    biz = client.get(f"/api/branch-detail?year=2023&branch={branch}").json()["biz"]
    return biz, [v for b in biz for v in b["전표"]]


def test_every_attributed_voucher_has_a_basis(srv):
    _, client, _ = srv
    _analyzed(client)
    _, vs = _vouchers(client)
    assert vs
    for v in vs:
        assert v["근거"] in KNOWN, v


def test_override_shows_as_reassignment(srv):
    _, client, _ = srv
    _analyzed(client)
    biz, _ = _vouchers(client)
    src = next(b for b in biz if b["전표"])
    moved = src["전표"][0]
    r = client.post("/api/override", json={"year": "2023", "budget": src["budget"],
                                           "erp_row_ids": [moved["erp_row_id"]],
                                           "target_name": "드릴다운 검증용 사업"})
    assert r.status_code == 200
    assert client.post("/api/analyze", json={"year": "2023"}).status_code == 200
    _, vs2 = _vouchers(client)
    assert next(v for v in vs2 if v["erp_row_id"] == moved["erp_row_id"])["근거"].startswith("재배정")


def test_stats_items_carry_branch_breakdown(srv):
    _, client, _ = srv
    _analyzed(client)
    st = client.get("/api/stats?year=2023").json()["budgets"]
    for data in st.values():
        for it in data["items"]:
            assert sum(b["실적"] for b in it["지사"]) == it["실적"]
            assert sum(b["계획"] for b in it["지사"]) == it["계획"]
            assert sum(b["사업수"] for b in it["지사"]) == it["사업수"]


def test_basis_fallback_for_runs_before_the_column():
    import server
    assert server._basis_fallback(None, "계획집행") is None
    assert server._basis_fallback(0.99, "계획집행") == "학습(추정)"
    assert server._basis_fallback(1.0, "계획집행") == "재배정·규칙·자재류(추정)"
    assert server._basis_fallback(0.5, "계획집행") == "유사도 낮음(추정)"
    assert server._basis_fallback(0.0, "신규") == "신규(추정)"
