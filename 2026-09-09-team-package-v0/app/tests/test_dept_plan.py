# -*- coding: utf-8 -*-
"""부서별 계획 올리기(2026-11-25) — 처·지사 파일만 올리면 한 계획으로 취합되고, 안 낸 부서가 보인다."""
import os
import sys

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from tests.test_upload_export_fixes import HDR_2324, XLSX, _row2324, _xlsx_bytes, srv   # noqa: E402,F401


def _file(dept, *amts):
    return _xlsx_bytes(HDR_2324, [_row2324(dept, "수선유지비-열원정기점검", f"{dept} 사업{i}", a)
                                  for i, a in enumerate(amts)])


def _up(client, *files, year="2023"):
    return client.post(f"/api/upload/plan-dept?year={year}",
                       files=[("file", (name, data, XLSX)) for name, data in files])


def _plans(client):
    return [d for d in client.get("/api/status?year=2023").json()["datasets"] if d["kind"] == "plan"]


def test_dept_files_merge_into_one_plan_and_list_missing(srv):
    _, client, _ = srv
    r = _up(client, ("화성.xlsx", _file("화성지사", 100, 200)), ("파주.xlsx", _file("파주지사", 50)))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["rows"] == 3 and body["total"] == 350
    assert {s["부서"] for s in body["saved"]} == {"화성지사", "파주지사"}
    assert "화성지사" not in body["missing"] and "동탄지사" in body["missing"]
    assert body["submitted"] == 2 and body["expected"] == len(body["missing"]) + 2

    st = client.get("/api/plan-depts?year=2023").json()
    assert st["current_is_merged"] and st["files"] == 2
    hw = next(d for d in st["depts"] if d["부서"] == "화성지사")
    assert hw["제출"] and hw["files"][0]["row_count"] == 2
    assert not next(d for d in st["depts"] if d["부서"] == "동탄지사")["제출"]

    # 다음 부서가 내면 다시 합치고, 앞 취합본은 지워 하나만 남는다
    assert _up(client, ("동탄.xlsx", _file("동탄지사", 10))).json()["rows"] == 4
    plans = _plans(client)
    assert len(plans) == 1 and plans[0]["label"].startswith("[부서별 취합] 3개 부서")


def test_same_dept_same_name_replaces_other_name_adds(srv):
    _, client, _ = srv
    _up(client, ("화성_손익.xlsx", _file("화성지사", 100)))
    assert _up(client, ("화성_손익.xlsx", _file("화성지사", 300))).json()["total"] == 300
    assert _up(client, ("화성_자본.xlsx", _file("화성지사", 7))).json()["total"] == 307
    hw = next(d for d in client.get("/api/plan-depts?year=2023").json()["depts"] if d["부서"] == "화성지사")
    assert sorted(f["filename"] for f in hw["files"]) == ["화성_손익.xlsx", "화성_자본.xlsx"]


def test_delete_file_rebuilds_and_last_delete_removes_merged_plan(srv):
    _, client, _ = srv
    _up(client, ("화성.xlsx", _file("화성지사", 100)), ("파주.xlsx", _file("파주지사", 50)))
    st = client.get("/api/plan-depts?year=2023").json()
    ids = {d["부서"]: d["files"][0]["id"] for d in st["depts"] if d["files"]}
    assert client.delete(f"/api/plan-depts/{ids['파주지사']}").status_code == 200
    plans = _plans(client)
    assert len(plans) == 1 and plans[0]["total_amount"] == 100
    assert client.delete(f"/api/plan-depts/{ids['화성지사']}").status_code == 200
    assert _plans(client) == []
    assert client.delete(f"/api/plan-depts/{ids['화성지사']}").status_code == 404


def test_direct_merged_upload_is_not_deleted_by_dept_rebuild(srv):
    _, client, _ = srv
    _up(client, ("화성.xlsx", _file("화성지사", 100)))
    assert client.post("/api/upload/plan?year=2023",
                       files=[("file", ("취합.xlsx", _file("화성지사", 999), XLSX))]).status_code == 200
    assert not client.get("/api/plan-depts?year=2023").json()["current_is_merged"]
    _up(client, ("파주.xlsx", _file("파주지사", 50)))
    labels = [d["label"] for d in _plans(client)]
    assert "취합.xlsx" in labels and labels[0].startswith("[부서별 취합]") and len(labels) == 3


def test_file_with_other_dept_rows_counts_both(srv):
    _, client, _ = srv
    data = _xlsx_bytes(HDR_2324, [_row2324("플랜트기술처", "수선유지비-열원정기점검", "a", 5),
                                  _row2324("플랜트기술처", "수선유지비-열원정기점검", "b", 5),
                                  _row2324("동탄지사", "수선유지비-열원정기점검", "c", 5)])
    body = _up(client, ("기술처.xlsx", data)).json()
    assert body["saved"][0]["부서"] == "플랜트기술처"
    dt = next(d for d in client.get("/api/plan-depts?year=2023").json()["depts"] if d["부서"] == "동탄지사")
    assert dt["제출"] and dt["다른파일"] and not dt["files"]


def test_bad_file_and_locked_year_are_refused(srv):
    server, client, _ = srv
    empty = _xlsx_bytes(HDR_2324, [])
    r = _up(client, ("빈.xlsx", empty))
    assert r.status_code == 400 and "빈.xlsx" in r.json()["detail"]
    _up(client, ("화성.xlsx", _file("화성지사", 100)))
    assert client.post("/api/lock", json={"year": "2023"}).status_code == 200
    assert _up(client, ("파주.xlsx", _file("파주지사", 50))).status_code == 423
    fid = client.get("/api/plan-depts?year=2023").json()["depts"]
    fid = next(d for d in fid if d["files"])["files"][0]["id"]
    assert client.delete(f"/api/plan-depts/{fid}").status_code == 423
