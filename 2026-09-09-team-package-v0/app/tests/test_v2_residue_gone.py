# -*- coding: utf-8 -*-
"""동료 전망 앱(v2)과 파일로 주고받던 잔재가 되돌아오지 않게 고정한다 (Phase 7).

v2 는 6-8 에서 이 앱에 흡수·삭제됐다. 그 뒤에도 남아 있던 «v2 로 넘기는» 코드 —
/api/export-team(결과 JSON·CSV 3종)·/api/export-status(마지막으로 넘긴 시각)·spec_io·
v2_model_sync — 는 소비자가 없는 죽은 코드였다(사용자 결정 2026-09-20). 죽은 코드는
«이건 뭐지»를 만들고, 다음 사람이 살려 쓰려다 시간을 잃는다.
"""
import os
import sys

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if APP not in sys.path:
    sys.path.insert(0, APP)


def _read(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as f:
        return f.read()


def test_team_export_routes_are_gone():
    src = _read(APP, "server.py")
    assert "/api/export-team" not in src
    assert "/api/export-status" not in src
    assert "export_team_bundle" not in src and "team_bundle_paths" not in src


def test_spec_io_and_v2_sync_are_gone():
    assert not os.path.exists(os.path.join(APP, "src", "budget", "spec_io.py"))
    assert not os.path.exists(os.path.join(APP, "scripts", "v2_model_sync.py"))
    for f in os.listdir(os.path.join(APP, "src", "budget")):
        if f.endswith(".py"):
            assert "spec_io" not in _read(APP, "src", "budget", f), f


def test_frontend_has_no_team_export_ui():
    web = os.path.join(APP, "web", "src")
    for root, _, files in os.walk(web):
        for f in files:
            if f.endswith(".js"):
                body = _read(root, f)
                assert "team-export" not in body and "teamExport" not in body, f
                assert "exportStatus" not in body and "export-status" not in body, f


def test_matched_csv_is_still_downloadable_per_budget():
    """지운 것은 v2 묶음뿐이다 — 전표 단위 matched CSV 는 /api/export?kind=matched 로 계속."""
    src = _read(APP, "server.py")
    assert '"matched": f"matched_{year}_{budget}.csv"' in src
