# -*- coding: utf-8 -*-
"""연도별 기준정보 API — 조회·저장·연도 복사·마감 가드.

설정 화면(Task 5)이 붙는 계약이다. 연도 축이 여기서 새면 어느 해 기준으로
분석한 것인지 알 수 없게 되므로, «연도가 갈린다»는 사실을 라우트마다 고정한다.
"""
import os
import sys

import openpyxl
import pytest

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from budget import db as dbm   # noqa: E402


@pytest.fixture()
def client(tmp_path, monkeypatch):
    # 인증을 끈 사내망 모드 — 이 라우트들의 관심사는 인증이 아니라 연도 축이다.
    monkeypatch.setenv("APP_PASSWORD", "")
    monkeypatch.setenv("DATABASE_URL", "")       # 빈 문자열 = SQLite (실 DB 로 붙지 않게)
    monkeypatch.setattr(dbm, "DEFAULT_DB", str(tmp_path / "t.db"))
    import server
    from budget import auth as authm
    monkeypatch.setattr(server, "AUTH", authm.AuthConfig())
    from fastapi.testclient import TestClient
    return TestClient(server.app)


def _master_xlsx(path, header, rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(header)
    for r in rows:
        ws.append(r)
    wb.save(path)
    wb.close()
    return path


# ── 지사 구성 ────────────────────────────────────────────────────────────────

def test_get_depts_seeds_the_year(client):
    r = client.get("/api/config/depts?year=2025")
    assert r.status_code == 200
    rows = r.json()["rows"]
    assert {x["이름"]: x["그룹"] for x in rows}["양산지사"] == "중대형CHP"


def test_put_depts_persists_and_is_year_scoped(client):
    rows = client.get("/api/config/depts?year=2023").json()["rows"]
    for x in rows:
        if x["이름"] == "양산지사":
            x["그룹"] = "중대형CHP"
    assert client.put("/api/config/depts",
                      json={"year": "2023", "rows": rows}).status_code == 200

    g2023 = {x["이름"]: x["그룹"]
             for x in client.get("/api/config/depts?year=2023").json()["rows"]}
    g2025 = {x["이름"]: x["그룹"]
             for x in client.get("/api/config/depts?year=2025").json()["rows"]}
    assert g2023["양산지사"] == "중대형CHP"
    assert g2025["양산지사"] == "중대형CHP"      # 2025 는 원래 그렇다
    # 2023 만 바뀌었는지 다른 지사로 확인 — 저장이 옆 연도로 새지 않는다
    assert g2023["대구지사"] == "소형CHP" and g2025["대구지사"] == "중대형CHP"


# ── 과목 구성 ────────────────────────────────────────────────────────────────

def test_put_items_is_year_and_budget_scoped(client):
    rows = client.get("/api/config/items?year=2025&budget=자본").json()["rows"]
    rows.append({"과목": "신규자본과목", "대분류": "자산", "심의대상": False, "포함": True})
    assert client.put("/api/config/items",
                      json={"year": "2025", "budget": "자본",
                            "rows": rows}).status_code == 200

    def names(year, budget):
        return {x["과목"] for x in
                client.get(f"/api/config/items?year={year}&budget={budget}").json()["rows"]}

    assert "신규자본과목" in names("2025", "자본")
    assert "신규자본과목" not in names("2025", "손익")
    assert "신규자본과목" not in names("2023", "자본")


# ── 별칭 ─────────────────────────────────────────────────────────────────────

def test_alias_roundtrip_and_no_year_axis(client):
    """별칭은 연도 축이 없다 — 저장하면 어느 해 화면에서도 같은 값이 보인다."""
    base = client.get("/api/config/alias").json()
    assert base["dept"]["판교사업소"] == "판교지사"          # 시드가 병합돼 나온다

    merged = dict(base["dept"], 없는지사="화성지사")
    assert client.put("/api/config/alias",
                      json={"종류": "dept", "rows": merged}).status_code == 200
    assert client.get("/api/config/alias").json()["dept"]["없는지사"] == "화성지사"


def test_alias_reports_which_keys_are_seeded(client):
    """시드에서 온 열쇠를 알려 줘야 화면이 그 행을 잠글 수 있다.

    읽을 때마다 시드를 병합하므로 시드 별칭은 지워도 되살아난다. 지울 수 있는
    것처럼 보여 놓고 되살아나는 쪽이 더 나쁘다(사용자 결정 2026-09-19).
    """
    r = client.get("/api/config/alias").json()
    assert "판교사업소" in r["seeded"]["dept"]
    assert "수선유지비-열원보완개선및기타" in r["seeded"]["item"]

    # 사용자가 넣은 것은 시드가 아니다
    client.put("/api/config/alias", json={"종류": "dept", "rows": {"없는지사": "화성지사"}})
    r = client.get("/api/config/alias").json()
    assert r["dept"]["없는지사"] == "화성지사"
    assert "없는지사" not in r["seeded"]["dept"]
    # 시드를 DB 에 안 넣어도 읽을 때 병합돼 살아 있다
    assert r["dept"]["판교사업소"] == "판교지사"


# ── 마스터 조회 ──────────────────────────────────────────────────────────────

def test_master_upload_and_read_are_year_scoped(client, tmp_path):
    """업로드 경로가 연도를 안 받으면 year=NULL 행이 쌓이고 아무도 읽지 않는다."""
    f = _master_xlsx(tmp_path / "m.xlsx", ["부서코드", "부서명", "처지사"],
                     [["D1", "기술부", "화성지사"]])
    with open(f, "rb") as fh:
        r = client.post("/api/upload/master?kind=dept&year=2025",
                        files={"file": ("m.xlsx", fh.read())})
    assert r.status_code == 200, r.text
    assert client.get("/api/master/depts?year=2025").json()["rows"][0]["처지사"] == "화성지사"
    assert client.get("/api/master/depts?year=2023").json()["rows"] == []


def test_frontend_sends_year_on_master_upload():
    """프론트가 연도를 안 붙이면 업로드가 422 로 죽는다 — 실제로 그렇게 깨져 있었다.

    /api/upload/master 의 year 는 기본값 없는 필수 질의 인자다(Task 1).
    프론트는 테스트 대상이 아니므로 소스 문자열로 계약을 고정한다.
    """
    p = os.path.join(APP_DIR, "web", "src", "main.js")
    with open(p, encoding="utf-8") as f:
        src = f.read()
    assert "/api/upload/master?kind=${kind}&year=${state.year}" in src


# ── 연도 복사 ────────────────────────────────────────────────────────────────

def test_copy_year_clones_config_and_master(client, tmp_path):
    """새 연도는 직전 연도를 복사해 시작한다 — 매년 조금씩만 바뀌기 때문이다."""
    client.get("/api/config/depts?year=2025")
    client.get("/api/config/items?year=2025&budget=손익")
    f = _master_xlsx(tmp_path / "m.xlsx", ["부서코드", "부서명", "처지사"],
                     [["D1", "기술부", "화성지사"]])
    with open(f, "rb") as fh:
        client.post("/api/upload/master?kind=dept&year=2025",
                    files={"file": ("m.xlsx", fh.read())})

    r = client.post("/api/config/copy-year", json={"from_year": "2025", "to_year": "2026"})
    assert r.status_code == 200, r.text

    g = {x["이름"]: x["그룹"]
         for x in client.get("/api/config/depts?year=2026").json()["rows"]}
    assert g["양산지사"] == "중대형CHP"
    assert client.get("/api/master/depts?year=2026").json()["rows"][0]["부서코드"] == "D1"
    # 원본 연도는 그대로 남는다
    assert client.get("/api/master/depts?year=2025").json()["rows"]


def test_copy_year_allows_target_that_was_only_auto_seeded(client):
    """설정 화면을 한 번 여는 것만으로 그 해 구성이 심긴다.

    손대지 않은 그 시드까지 «이미 있음»으로 보고 막으면, 화면을 열어 봤다는
    이유만으로 연도 복사가 영영 막힌다 — 브라우저 실측으로 걸린 길이다.
    """
    rows = client.get("/api/config/depts?year=2025").json()["rows"]
    for x in rows:
        if x["이름"] == "화성지사":
            x["그룹"] = "DH"
    client.put("/api/config/depts", json={"year": "2025", "rows": rows})
    client.get("/api/config/depts?year=2026")          # 화면을 연 것과 같다 — 시드가 심긴다

    r = client.post("/api/config/copy-year", json={"from_year": "2025", "to_year": "2026"})
    assert r.status_code == 200, r.text
    g = {x["이름"]: x["그룹"]
         for x in client.get("/api/config/depts?year=2026").json()["rows"]}
    assert g["화성지사"] == "DH"                        # 시드가 아니라 2025 사본이다


def test_copy_year_refuses_to_clobber_an_existing_year(client):
    """이미 기준이 선 연도는 말없이 덮지 않는다.

    「＋연도」가 실수로 기존 연도를 가리켰을 때 공들여 맞춘 구성이 사라지는
    길을 막는다. 덮어쓰기는 overwrite 로 뜻을 밝혀야 한다.
    """
    rows = client.get("/api/config/depts?year=2026").json()["rows"]
    rows.append({"이름": "지켜야할지사", "그룹": "DH", "포함": True})   # 손댔다
    client.put("/api/config/depts", json={"year": "2026", "rows": rows})
    client.get("/api/config/depts?year=2025")

    r = client.post("/api/config/copy-year", json={"from_year": "2025", "to_year": "2026"})
    assert r.status_code == 409
    assert any(x["이름"] == "지켜야할지사"
               for x in client.get("/api/config/depts?year=2026").json()["rows"])


def test_copy_year_overwrites_target_without_leftovers(client):
    """overwrite 를 밝히면 통째로 갈아 끼운다 — 두 해가 섞이면 안 된다."""
    rows = client.get("/api/config/depts?year=2026").json()["rows"]
    rows.append({"이름": "없어질지사", "그룹": "DH", "포함": True})
    client.put("/api/config/depts", json={"year": "2026", "rows": rows})
    assert any(x["이름"] == "없어질지사"
               for x in client.get("/api/config/depts?year=2026").json()["rows"])

    client.get("/api/config/depts?year=2025")
    r = client.post("/api/config/copy-year",
                    json={"from_year": "2025", "to_year": "2026", "overwrite": True})
    assert r.status_code == 200
    assert not any(x["이름"] == "없어질지사"
                   for x in client.get("/api/config/depts?year=2026").json()["rows"])


# ── 마감 가드 ────────────────────────────────────────────────────────────────

def test_config_change_blocked_on_locked_year(client):
    """마감된 연도는 기준도 못 고친다 — 과거 결과가 조용히 바뀌지 않게."""
    client.get("/api/config/depts?year=2023")
    rows = client.get("/api/config/depts?year=2023").json()["rows"]
    assert client.post("/api/lock", json={"year": "2023"}).status_code == 200

    assert client.put("/api/config/depts",
                      json={"year": "2023", "rows": rows}).status_code == 423
    assert client.put("/api/config/items",
                      json={"year": "2023", "budget": "손익", "rows": []}).status_code == 423
    assert client.post("/api/config/copy-year",
                       json={"from_year": "2025", "to_year": "2023"}).status_code == 423
    # 읽기는 막지 않는다 — 마감본을 들여다보는 것까지 막을 이유가 없다
    assert client.get("/api/config/depts?year=2023").status_code == 200


# ── 분석 반영 배지 ───────────────────────────────────────────────────────────

def test_config_change_counts_as_pending(client):
    """구성 변경도 «결과에 반영되지 않은 변경»이다 — 재배정과 같은 배지에 잡힌다.

    알림을 두 갈래로 나누면 어느 것을 눌러야 하는지 헷갈린다.
    """
    client.get("/api/config/depts?year=2025")
    before = client.get("/api/pending?year=2025").json()["total"]

    rows = client.get("/api/config/depts?year=2025").json()["rows"]
    rows[0]["그룹"] = "DH"
    client.put("/api/config/depts", json={"year": "2025", "rows": rows})

    after = client.get("/api/pending?year=2025").json()
    assert after["total"] > before
    assert after["counts"].get("기준정보")


def test_pending_ignores_other_years_and_rejections(client):
    """다른 해를 고친 것과 거부된 요청은 이 해의 «미반영»이 아니다."""
    for y in ("2023", "2025"):
        client.get(f"/api/config/depts?year={y}")
    rows2023 = client.get("/api/config/depts?year=2023").json()["rows"]
    rows2023[0]["그룹"] = "DH"
    client.put("/api/config/depts", json={"year": "2023", "rows": rows2023})

    client.post("/api/lock", json={"year": "2025"})
    rows2025 = client.get("/api/config/depts?year=2025").json()["rows"]
    assert client.put("/api/config/depts",
                      json={"year": "2025", "rows": rows2025}).status_code == 423

    assert not client.get("/api/pending?year=2025").json()["counts"].get("기준정보")
    assert client.get("/api/pending?year=2023").json()["counts"]["기준정보"] >= 1


def test_pending_counts_copy_year_and_master_upload(client, tmp_path):
    """연도 복사와 마스터 업로드도 분석 결과를 바꾼다 — 같은 배지에 들어간다."""
    client.get("/api/config/depts?year=2025")
    client.post("/api/config/copy-year", json={"from_year": "2025", "to_year": "2026"})
    assert client.get("/api/pending?year=2026").json()["counts"]["기준정보"] >= 1

    f = _master_xlsx(tmp_path / "m.xlsx", ["부서코드", "부서명", "처지사"],
                     [["D1", "기술부", "화성지사"]])
    before = client.get("/api/pending?year=2023").json()["counts"].get("기준정보", 0)
    with open(f, "rb") as fh:
        client.post("/api/upload/master?kind=dept&year=2023",
                    files={"file": ("m.xlsx", fh.read())})
    assert client.get("/api/pending?year=2023").json()["counts"]["기준정보"] > before
