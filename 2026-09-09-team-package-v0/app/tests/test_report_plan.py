# -*- coding: utf-8 -*-
"""한글(hwpx) 보고서 — [붙임2] 집행실적 및 계획(5월용) 양식 채우기."""
import os
import re
import sys
import zipfile
from urllib.parse import unquote

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from budget import report_hwpx as rh, report_plan as rp   # noqa: E402
from tests.test_upload_export_fixes import _analyzed, srv   # noqa: E402,F401

TEMPLATE = os.path.join(APP_DIR, "templates", "report_plan_template.hwpx")


def _inputs():
    """손으로 만든 입력값(억원) — 2025년, 모든 과목 3개년 실적 100·110·121, 배정 = 실적 + 10, 다음해 배정 130."""
    matrix = {}
    for b, rows in rp.PLAN_ROWS.items():
        matrix[b] = [{"key": key, "v": {"2023": {"배정": 110, "실적": 100}, "2024": {"배정": 120, "실적": 110},
                                        "2025": {"배정": 131, "실적": 121}, "2026": {"배정": 130}}}
                     for key, *_ in rows]
    raw = {"matrix": matrix, "grades": {"2025": {"화성": "MI", "판교": "MI"}, "2026": {"파주": "TI", "광교": "HGPI"}}}
    inp = rp.normalize_inputs(raw, "2025")
    inp["texts"] = rp.auto_texts(inp)
    return inp


def _render(inp):
    with open(TEMPLATE, "rb") as f:
        return rh.section_text(rp.render_plan_hwpx(f.read(), inp))


def test_template_in_repo_has_no_amounts():
    with open(TEMPLATE, "rb") as f:
        text = rh.section_text(f.read())
    assert not re.search(r"\d+억|\d{2,}(\.\d)?%|\d{1,3},\d{3}|MI|HGPI", text)
    hpf = zipfile.ZipFile(TEMPLATE).read("Contents/content.hpf").decode("utf-8")
    assert re.search(r'name="creator" content="text"(/>|>(?=<))', hpf)


def test_one_number_feeds_every_table():
    """정기점검 2025 실적 121 — 3개년표(표8)·집행표(표11)에 같이, 손익 합계(8행)는 표7·10에."""
    text = _render(_inputs())
    assert "121 (17%)" in text                    # 표8: 손익 8과목 중 6과목이 표에 — 점유율은 표 안 합계 기준
    assert "+11 <+10.0%>" in text                 # 전년대비 증감
    assert "131\n121\n△10\n92%" in text            # 표11 정기점검: 배정·실적·차액(실적−배정)·집행율
    assert "1,048\n968" in text                    # 표7 2025 손익(8과목) 배정·실적
    assert "「‘25년～‘26년 열원시설」" in text and "’26년도 유지보수 배정예산" in text


def test_override_changes_only_the_three_year_table():
    inp = _inputs()
    inp["over"]["2023.자본.배정"] = 796
    text = _render(inp)
    assert "796" in text


def test_grades_and_sentences():
    text = _render(_inputs())
    assert "’25년도 화성, 판교 대정비 시행" in text
    assert "파주, 광교 등 2개지사 B급(TI, HGPI) 예정" in text
    assert "(실적분석) 전년대비 수선유지비" in text
    assert "(과목)" not in text and "원인\n" not in text


def test_bullets_and_continuations():
    inp = _inputs()
    inp["texts"]["g3"] = [{"label": "정기점검", "body": "MI 시행으로 증가"}]
    inp["texts"]["g4"] = []
    text = _render(inp)
    assert "(정기점검) MI 시행으로 증가" in text
    assert text.count("○") == 3 + 1 + 2 + 4            # (실적분석)3 + g3 1 + g7 2 + 정적 «○ 손익/자본예산» 4
    assert text.rstrip().endswith("끝.")


def test_preview_marks_matrix_cells():
    with open(TEMPLATE, "rb") as f:
        html = rp.preview_plan_html(f.read(), _inputs())
    for path in ("matrix.손익.0.v.2025.실적", "matrix.자본.9.v.2026.배정", "over.2024.자본.실적", "grades.2025.화성",
                 "texts.a3", "texts.h1", "texts.g7.0.label"):
        assert f'data-path="{path}"' in html, path
    assert 'data-rp-act="add-bullet" data-k="g4"' in html


def test_api_plan_kind(srv):
    _, client, _ = srv
    _analyzed(client)
    inp = client.get("/api/report/plan?year=2023").json()
    assert inp["year"] == "2023" and set(inp["matrix"]) == {"손익", "자본"}
    r = client.post("/api/report/plan/preview", json={"year": "2023", "inputs": inp})
    assert r.status_code == 200 and "rp-page" in r.json()["html"]
    r = client.post("/api/report/plan/hwpx", json={"year": "2023", "inputs": inp})
    assert r.status_code == 200 and "붙임2" in unquote(r.headers["content-disposition"])
    text = rh.section_text(r.content)
    assert "「‘23년～‘24년 열원시설」" in text and "’24년도 유지보수 배정예산" in text and "‘24년 유지보수 예산 계획" in text
    assert client.get("/api/report/xx?year=2023").status_code == 404
