# -*- coding: utf-8 -*-
"""한글(hwpx) 보고서 — 집행성과분석(2월용) 양식 채우기."""
import io
import os
import re
import sys
import zipfile

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from budget import report_hwpx as rh   # noqa: E402
from tests.test_upload_export_fixes import _analyzed, srv   # noqa: E402,F401

TEMPLATE = os.path.join(APP_DIR, "templates", "report_perf_template.hwpx")


def _inputs():
    """손으로 만든 입력값(억원) — 2025년 보고서 모양."""
    items = {b: [{"label": label, "배정": 10.0, "실적": 9.0} for label, _ in rows] for b, rows in rh.PERF_ITEMS.items()}
    items["손익"][0] = {"label": "건물/구축물", "배정": 56.94, "실적": 85.44}       # 초과 집행 → 잔액 △
    groups = {b: {g: {"배정": 100.0, "실적": 90.0} for g in rh.GROUPS} for b in ("손익", "자본")}
    raw = {"three": {"2023": {"손익": {"배정": 829, "실적": 719}, "자본": {"배정": 796, "실적": 692}},
                     "2024": {"손익": {"배정": 910, "실적": 825}, "자본": {"배정": 424, "실적": 383}}},
           "items": items, "groups": groups, "group_counts": {"중대형CHP": 9, "소형CHP": 3, "DH": 7},
           "prev_group_share": {"중대형CHP": 70, "소형CHP": 15, "DH": 14, "본사": 1}}
    inp = rh.normalize_inputs(raw, "2025")
    inp["texts"] = rh.auto_texts(inp)
    return inp


def _render(inp):
    with open(TEMPLATE, "rb") as f:
        return rh.render_perf_hwpx(f.read(), inp)


def test_template_in_repo_has_no_amounts():
    """저장소 양식에는 서식만 — 금액·원인 문장이 남아 있으면 실데이터 유출이다."""
    with open(TEMPLATE, "rb") as f:
        text = rh.section_text(f.read())
    assert not re.search(r"\d+억|\d{2,}(\.\d)?%|\d{1,3},\d{3}", text)
    assert "원인" in text and "(과목)" in text
    hpf = zipfile.ZipFile(TEMPLATE).read("Contents/content.hpf").decode("utf-8")
    assert re.search(r'name="creator" content="text">(?=<)', hpf)                   # 작성자 속성도 비운다


def test_numbers_land_in_the_cells():
    text = rh.section_text(_render(_inputs()))
    assert "56.9" in text and "85.4" in text and "△28.5" in text and "150.1" in text   # 표6 건물/구축물
    assert "829" in text and "87%" in text                                            # 표2 2023년 손익
    assert "중대형" in text and "CHP(9)" in text and "(7)" in text                    # 지사 수(줄바꿈 칸)
    assert "2026. 02." in text and "25년 열원 유지보수 예산집행 성과분석" in text


def test_sentences_and_bullets_follow_the_inputs():
    inp = _inputs()
    inp["texts"]["son_bullets"] = [{"label": "건물/구축물", "body": "도장·누수 공사 증가"},
                                   {"label": "경상정비", "body": "물가변동 계약 미시행"}]
    inp["texts"]["ja_bullets"] = [{"label": "기계장치", "body": "공사 연기"}]
    text = rh.section_text(_render(inp))
    assert "(건물/구축물) 도장·누수 공사 증가" in text and "(경상정비) 물가변동 계약 미시행" in text
    assert "(기계장치) 공사 연기  끝." in text
    assert text.count("○") == 1 + 2 + 1                       # 지사 유형 1(자동) + 손익 2 + 자본 1
    assert "원인\n" not in text and "(과목)" not in text      # 양식 자리표시가 남지 않는다
    assert "‘25년 열원시설 손익예산" in text and "억원(△" in text          # 전년보다 줄면 △


def test_empty_bullets_drop_and_end_mark_moves_to_head():
    inp = _inputs()
    for k in ("s2_bullets", "son_bullets", "ja_bullets"):
        inp["texts"][k] = []
    text = rh.section_text(_render(inp))
    assert "○" not in text
    assert text.rstrip().endswith("끝.")


def test_output_is_a_valid_hwpx_package():
    out = _render(_inputs())
    z = zipfile.ZipFile(io.BytesIO(out))
    first = z.infolist()[0]
    assert first.filename == "mimetype" and first.compress_type == zipfile.ZIP_STORED
    assert z.read("mimetype") == b"application/hwp+zip"
    sec = z.read("Contents/section0.xml").decode("utf-8")
    assert sec.startswith("<?xml") and 'xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph"' in sec[:3000]
    assert z.read("Preview/PrvImage.png") == rh.BLANK_PNG


def test_normalize_rejects_shape_changes():
    inp = rh.normalize_inputs({"items": {"손익": [{"label": "없는 과목", "배정": 1, "실적": 1}]},
                               "texts": {"box1": "<script>" + "x" * 2000}}, "2025")
    assert [x["label"] for x in inp["items"]["손익"]] == [label for label, _ in rh.PERF_ITEMS["손익"]]
    assert all(x["배정"] == 0 for x in inp["items"]["손익"])
    assert len(inp["texts"]["box1"]) == rh.TEXT_MAX


def test_rounding_is_half_up():
    assert rh.n0(2.5) == "3" and rh.n1(0.25) == "0.3" and rh.tri(-28.45, rh.n1) == "△28.5"


def test_api_builds_inputs_and_downloads_hwpx(srv):
    _, client, _ = srv
    _analyzed(client)
    inp = client.get("/api/report/perf?year=2023").json()
    assert inp["year"] == "2023" and set(inp["items"]) == {"손익", "자본"}
    tot = sum(x["실적"] for b in ("손익", "자본") for x in inp["items"][b])
    st = client.get("/api/stats?year=2023").json()["budgets"]
    assert abs(tot - sum(i["실적"] for d in st.values() for i in d["items"]) / rh.EOK) < 1e-3
    r = client.post("/api/report/perf/texts", json={"year": "2023", "inputs": inp})
    assert r.status_code == 200 and "son_head" in r.json()
    r = client.post("/api/report/perf/hwpx", json={"year": "2023", "inputs": inp})
    assert r.status_code == 200
    assert "hwpx" in r.headers["content-disposition"]
    assert "23년 열원 유지보수" in rh.section_text(r.content)
    assert client.post("/api/report/perf/hwpx", json={"year": "20x3", "inputs": {}}).status_code == 400


def _preview(inp):
    with open(TEMPLATE, "rb") as f:
        return rh.preview_perf_html(f.read(), inp)


def test_preview_marks_editable_and_computed_cells():
    html = _preview(_inputs())
    assert 'class="rp-page"' in html and "<table" in html and "data:image/" in html   # 종이·표·로고
    for path in ("items.손익.0.배정", "three.2023.손익.실적", "groups.자본.DH.배정", "group_counts.중대형CHP",
                 "texts.box1", "texts.son_head", "date"):
        assert f'data-path="{path}"' in html, path
    assert 'data-path="three.2025.' not in html            # 올해 3개년 칸은 과목표 합(계산)
    assert html.count("rp-calc") > 40                        # 합계·잔액·실적률·점유율


def test_preview_bullets_have_tools_and_keep_empty_lines():
    inp = _inputs()
    inp["texts"]["son_bullets"] = [{"label": "경상정비", "body": ""}]
    html = _preview(inp)
    assert 'data-path="texts.son_bullets.0.label"' in html and 'data-path="texts.son_bullets.0.body"' in html
    assert 'data-rp-act="del-bullet" data-k="son_bullets" data-i="0"' in html
    assert 'data-rp-act="add-bullet" data-k="ja_bullets"' in html
    assert "(과목)" not in html


def test_normalize_splits_label_and_drops_end_mark():
    inp = rh.normalize_inputs({"texts": {"son_bullets": [{"label": "", "body": "(경상정비) 물가변동"}],
                                         "ja_bullets": [{"label": "(기계장치)", "body": "공사 연기  끝."}]}}, "2025")
    assert inp["texts"]["son_bullets"] == [{"label": "경상정비", "body": "물가변동"}]
    assert inp["texts"]["ja_bullets"] == [{"label": "기계장치", "body": "공사 연기"}]


def test_preview_never_emits_runaway_sizes():
    """한글의 «미지정»(4294967295) 여백이 5,700만 px 칸 여백이 되어 문서가 통째로 깨졌다(2026-10-28 라이브)."""
    from budget import hwpx_html, report_plan as rp
    assert hwpx_html.px("4294967295") == round(-1 / 75, 2)
    for path, build in ((TEMPLATE, _preview), (os.path.join(APP_DIR, "templates", "report_plan_template.hwpx"), None)):
        if build:
            html = build(_inputs())
        else:
            with open(path, "rb") as f:
                html = rp.preview_plan_html(f.read(), rp.normalize_inputs({}, "2025") | {"texts": rp.auto_texts(rp.normalize_inputs({}, "2025"))})
        sizes = [float(v) for v in re.findall(r"(-?\d+(?:\.\d+)?)px", html)]
        assert sizes and max(sizes) < 2000 and min(sizes) > -500
