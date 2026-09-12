# -*- coding: utf-8 -*-
"""공용 비밀번호 로그인 + 감사 로그 + 모델 레지스트리/학습데이터 API."""
import io
import os
import sys

import pandas as pd
import pytest

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from budget import db as dbm, ml_registry, auth as authm   # noqa: E402


PG_TEST_URL = os.environ.get("PG_TEST_URL")   # 설정 시 이 테스트들을 실제 PostgreSQL에서 실행(dbcore 번역 검증)


def _reset_pg_tables(url):
    from budget import dbcore
    conn = dbcore.connect(url=url)
    dbm.init_db(conn)
    for t in ("audit_log", "model_registry", "training_example", "training_snapshot"):
        conn.execute(f"DELETE FROM {t}")
    conn.commit()
    conn.close()


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "team-secret")
    monkeypatch.setenv("SECRET_KEY", "x" * 40)
    if PG_TEST_URL:
        monkeypatch.setenv("DATABASE_URL", PG_TEST_URL)
        _reset_pg_tables(PG_TEST_URL)
    else:
        # 삭제가 아니라 빈 문자열로 둔다. server.py 는 import 시점에
        # load_dotenv_if_present(APP_DIR) 로 app/.env 를 읽는데, override=False 는
        # "키가 이미 있으면 건드리지 않는다"는 뜻이라 지워버리면 개발자의 실제
        # DATABASE_URL 이 되살아나 테스트가 운영 PostgreSQL 에 붙어 행을 쓴다.
        # dbcore.database_url() 은 빈 문자열을 SQLite 로 처리한다.
        monkeypatch.setenv("DATABASE_URL", "")
        monkeypatch.setattr(dbm, "DEFAULT_DB", str(tmp_path / "t.db"))
    import server
    monkeypatch.setattr(server, "AUTH", authm.AuthConfig())
    from fastapi.testclient import TestClient
    return TestClient(server.app)


def test_api_requires_login_and_records_audit(client):
    assert client.get("/api/overview").status_code == 401
    assert client.get("/healthz").json()["auth"] is True
    r = client.post("/api/login", json={"password": "wrong", "name": "홍길동"})
    assert r.status_code == 401
    r = client.post("/api/login", json={"password": "team-secret", "name": ""})
    assert r.status_code == 400                       # 작업자 이름 필수
    r = client.post("/api/login", json={"password": "team-secret", "name": "홍길동"})
    assert r.status_code == 200 and r.json()["operator"] == "홍길동"
    assert client.get("/api/auth/status").json() == {"enabled": True, "operator": "홍길동", "logged_in": True}
    assert client.get("/api/overview").status_code == 200
    # 변경 요청은 감사 로그에 작업자·경로·요약이 남는다(비밀번호는 제외)
    client.post("/api/training", json={"name": "투자유형_전표텍스트", "rows": [["동탄 GT 정비", "정기사업"]]})
    rows = client.get("/api/audit").json()["rows"]
    kinds = {(r["operator"], r["method"], r["path"], r["status"]) for r in rows}
    assert ("홍길동", "POST", "/api/training", 200) in kinds
    assert ("홍길동", "POST", "/api/login", 200) in kinds
    assert ("홍길동", "POST", "/api/login", 401) in kinds
    assert not any("team-secret" in (r["detail"] or "") for r in rows)
    client.post("/api/logout")
    assert client.get("/api/overview").status_code == 401


def test_registry_train_activate_download(client):
    client.post("/api/login", json={"password": "team-secret", "name": "김검토"})
    name = "투자유형_전표텍스트"
    # 학습데이터 부족 → 400
    r = client.post("/api/train", json={"name": name})
    assert r.status_code == 400
    rows = [[f"동탄 {i}호기 정기점검 부품", "정기사업"] for i in range(12)] + \
           [[f"보안 카메라 교체 {i}차", "보안강화"] for i in range(12)]
    r = client.post("/api/training", json={"name": name, "rows": rows, "confirmed": True})
    assert r.json()["inserted"] == 24
    st = client.get(f"/api/training?name={name}").json()["stats"]
    assert st["total"] == 24 and st["confirmed"] == 24 and st["trainable"]
    r = client.post("/api/train", json={"name": name, "note": "테스트"})
    assert r.status_code == 200, r.text
    v1 = r.json()
    assert v1["version"] == 1 and v1["active"] and v1["snapshot_id"]
    # 두 번째 학습 → v2 활성, v1 비활성; v1 재활성화 가능
    v2 = client.post("/api/train", json={"name": name}).json()
    models = client.get(f"/api/models?name={name}").json()["models"]
    assert [m["version"] for m in models] == [2, 1]
    assert [m["active"] for m in models] == [True, False]
    assert client.post(f"/api/models/{v1['id']}/activate").status_code == 200
    models = client.get(f"/api/models?name={name}").json()["models"]
    assert {m["version"]: m["active"] for m in models} == {1: True, 2: False}
    # 다운로드한 joblib이 v2 파일명으로 내려오고 실제 예측이 된다
    r = client.get(f"/api/models/{v1['id']}/download")
    assert r.status_code == 200 and "type_classifier.joblib" in r.headers["content-disposition"]
    import joblib
    model = joblib.load(io.BytesIO(r.content))
    labels, conf = ml_registry.predict(model, ["동탄 3호기 정기점검 부품 구매"])
    assert labels[0] == "정기사업" and 0 < conf[0] <= 1
    # CSV 내보내기/가져오기 왕복
    csv = client.get(f"/api/training/export.csv?name={name}").content
    df = pd.read_csv(io.BytesIO(csv))
    assert len(df) == 24 and set(df.columns) >= {"text", "label", "confirmed"}
    r = client.post(f"/api/training/import?name={name}", files={"file": ("t.csv", csv, "text/csv")})
    assert r.status_code == 200 and r.json()["inserted"] == 0      # 전부 이미 있음


def test_confirmed_label_not_overwritten_by_auto(tmp_path):
    conn = dbm.connect(str(tmp_path / "r.db"))
    name = "투자유형_사업명"
    ml_registry.add_examples(conn, name, [("화성 GT 정비 기계장치", "정기사업")], "사람확정", "A", confirmed=True)
    res = ml_registry.add_examples(conn, name, [("화성 GT 정비 기계장치", "노후설비개체")], "자동예측", "bot", confirmed=False)
    assert res == {"inserted": 0, "updated": 0, "skipped": 1}
    assert ml_registry.list_examples(conn, name)[0]["label"] == "정기사업"
    # 사람 확정은 덮어쓴다
    res = ml_registry.add_examples(conn, name, [("화성 GT 정비 기계장치", "노후설비개체")], "사람확정", "B", confirmed=True)
    assert res["updated"] == 1
    conn.close()


def test_v2_file_sync_roundtrip(tmp_path):
    conn = dbm.connect(str(tmp_path / "r.db"))
    v2 = tmp_path / "v2"
    v2.mkdir()
    pd.DataFrame({"text": [f"텍스트 {i}" for i in range(25)],
                  "label": ["LTSA" if i % 2 else "정기사업" for i in range(25)]}).to_csv(v2 / "training_data.csv", index=False)
    pd.DataFrame({"사업명": ["A공사", "B공사"], "예산과목": ["기계장치", "외주비-기타"],
                  "투자유형": ["설비개선", "정기사업"], "투자유형세부": ["AX/DX", ""]}).to_csv(
        v2 / "project_type_training.csv", index=False)
    rep = ml_registry.import_v2_files(conn, str(v2), actor="sync")
    assert rep["투자유형_전표텍스트/examples"]["inserted"] == 25
    assert rep["투자유형_사업명/examples"]["inserted"] == 2
    assert rep["투자유형세부_사업명/examples"]["inserted"] == 1        # 빈 세부는 제외
    ml_registry.train(conn, "투자유형_전표텍스트", actor="sync")
    written = ml_registry.export_to_v2_files(conn, str(v2))
    assert "type_classifier.joblib" in written and (v2 / "type_classifier.joblib").exists()
    # 같은 파일 재반입은 중복 등록되지 않는다
    rep2 = ml_registry.import_v2_files(conn, str(v2), actor="sync")
    assert "skipped" in rep2["투자유형_전표텍스트/model"]
    conn.close()
