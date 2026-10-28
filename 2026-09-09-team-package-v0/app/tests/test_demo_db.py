# -*- coding: utf-8 -*-
"""시연용 더미 DB(scripts/make_demo_db.py) — 하나의 치환표 · 일반 낱말 보호 · 업체명 · 금액 계수 · 전표번호."""
import importlib.util
import os
import sqlite3

from budget import db as dbm

_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts", "make_demo_db.py")
_spec = importlib.util.spec_from_file_location("make_demo_db", _PATH)
M = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(M)


def _db(tmp_path):
    conn = sqlite3.connect(str(tmp_path / "s.db"))
    dbm.init_db(conn)
    for i, (name, group) in enumerate([("플랜트기술처", "본사"), ("화성지사", "중대형CHP"), ("용인지사", "DH"),
                                       ("대구지사", "소형CHP")]):
        conn.execute("INSERT INTO dept_config(year,이름,그룹,포함,순서) VALUES('2025',?,?,1,?)", (name, group, i))
    conn.execute("INSERT INTO audit_log(at,operator,method,path,status,detail) VALUES('t','홍길순','PUT','/x',200,'')")
    conn.commit()
    return conn


def test_mapping_codes_sites_keeps_hq_and_pseudonymizes(tmp_path):
    m = M.build_mapping(_db(tmp_path), seed=1)
    pairs = dict(m["pairs"])
    assert pairs["화성지사"] == "지사A" and pairs["화성"] == "지사A"       # 지명도 같은 코드 — 지사로 정규화되게
    assert pairs["용인지사"] == "지사B" and pairs["대구지사"] == "지사C"
    assert "플랜트기술처" not in pairs                                   # 본사 처 이름은 그대로(본사 배분 규칙)
    assert all(0.8 <= k <= 1.2 for k in m["factor"].values())
    assert m["operators"] == {"홍길순": "작업자1"}
    assert M.build_mapping(_db_same(tmp_path), seed=1)["factor"] == m["factor"]      # 같은 seed = 같은 계수


def _db_same(tmp_path):
    p = tmp_path / "again"
    p.mkdir()
    return _db(p)


def test_text_protects_ordinary_words_and_replaces_vendors():
    t = M.make_text_fn({"pairs": [("용인지사", "지사B"), ("용인", "지사B"), ("대구", "지사C")]})
    assert t("5월 비용인식(용인)") == "5월 비용인식(지사B)"          # «비용인식»의 «용인»은 지명이 아니다
    assert t("DB확대구축용역") == "DB확대구축용역"
    assert t("대구지사 (주)한빛 ABB GEAR") == "지사C지사 (주)업체 제조사아 GEAR"
    assert t("한빛(주) 정기점검") == "업체(주) 정기점검"
    assert t(None) is None and t("") == ""


def test_transform_scales_by_site_and_renumbers_vouchers(tmp_path):
    conn = _db(tmp_path)
    conn.execute("INSERT INTO dataset(id,kind,year,label,uploaded_at) VALUES(1,'plan','2025','화성.xlsx','t')")
    conn.execute("INSERT INTO dataset(id,kind,year,label,uploaded_at) VALUES(2,'erp','2025','zrfm2','t')")
    conn.execute("INSERT INTO plan_row(dataset_id,처지사,예산과목,사업명,연예산) VALUES(1,'화성지사','기계장치','화성 펌프 교체',1000)")
    for i, (no, amt) in enumerate([("A1", 400_000.0), ("A1", 100_000.0), ("B9", 300_000.0)]):
        conn.execute("INSERT INTO erp_row(id,dataset_id,예산과목원문,연도,전표번호,금액원,금액천원,사업명,지사원문,거래처코드)"
                     " VALUES(?,2,'기계장치','2025',?,?,?,'화성 펌프 교체','화성','V001')", (i + 1, no, amt, amt / 1000))
    conn.commit()
    m = M.build_mapping(conn, seed=3)
    M.transform(conn, m)
    k = m["factor"]["화성지사"]
    plan = conn.execute("SELECT 처지사, 사업명, 연예산 FROM plan_row").fetchone()
    assert plan[0] == "지사A" and plan[1] == "지사A 펌프 교체" and abs(plan[2] - 1000 * k) < 1e-6
    rows = conn.execute("SELECT 전표번호, 금액원, 금액천원, 거래처코드, 지사원문 FROM erp_row ORDER BY id").fetchall()
    assert rows[0][0] == rows[1][0] != rows[2][0]                    # 같은 번호는 같은 새 번호
    assert all(r[3] is None and r[4] == "지사A" for r in rows)
    assert abs(rows[0][1] - round(400_000 * k)) < 1 and abs(rows[0][2] - rows[0][1] / 1000) < 1e-9
    assert M.leftovers(conn, m) == {}
