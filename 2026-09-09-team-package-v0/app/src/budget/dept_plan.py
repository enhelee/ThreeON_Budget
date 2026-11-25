# -*- coding: utf-8 -*-
"""부서별 계획 올리기 — 처·지사가 따로 낸 계획 엑셀을 모아 한 계획으로 취합한다.

2026-11-25 팀장: 지금은 주관부서가 손으로 합친 «취합 계획»만 올릴 수 있다. 지사가 낸 파일만
올리면 앱이 합치고, 아직 안 낸 부서가 보이게 해 달라.

- 파일 양식은 취합 계획과 같다(양식1(월별) 시트, loaders.load_business_plan 이 읽는다).
- 부서는 파일 안 «예산귀속부서명(처.지사)» 열로 알아낸다 — 가장 많은 처지사가 그 파일의 부서.
  그 해 지사 구성(설정) 이름으로 맞춘다(별칭·접두 일치). 한 파일에 여러 부서 행이 있으면
  그 부서들 모두 «제출»로 센다.
- 같은 부서가 같은 이름의 파일을 다시 올리면 바꿔 끼운다(손익·자본은 이름이 달라 둘 다 남는다).
- 올리거나 지울 때마다 그 해 부서 파일 전부를 계획 데이터셋 하나로 다시 만든다 — 분석은 늘 가장
  최근 계획 데이터셋을 쓰므로 바로 반영된다. 직전 취합본이 아직 가장 최근이면 지워 기록이 쌓이지 않게 한다.
"""
import json
import os
import tempfile
from collections import Counter

from . import config_store, db as dbm, dbcore, loaders, normalize

AUTO_LABEL = "[부서별 취합]"


def _expected(conn, year):
    """그 해 지사 구성에서 «포함»인 부서 [(이름, 그룹)] — 설정 화면 순서 그대로."""
    return [(d["이름"], d["그룹"]) for d in config_store.load_dept_config(conn, year) if d.get("포함")]


def _canon(raw, names, alias):
    if raw is None or str(raw).strip() == "":
        return None
    return normalize.normalize_dept(str(raw).strip(), names, alias) or str(raw).strip()


def read_file(conn, year, path):
    """파일 하나를 읽어 (부서, 포함부서 목록, 행 수, 합계). 사업 행이 없으면 ValueError."""
    df = loaders.load_business_plan(path)
    if not len(df):
        raise ValueError("계획 사업 행이 없습니다 — «양식1(월별)» 시트의 계획 양식인지 확인하세요.")
    names = [n for n, _ in _expected(conn, year)]
    alias = config_store.load_dept_alias(conn)
    cnt = Counter(c for c in (_canon(v, names, alias) for v in df["처지사"]) if c)
    if not cnt:
        raise ValueError("«예산귀속부서명(처.지사)» 열이 비어 있어 어느 부서 파일인지 알 수 없습니다.")
    owner = cnt.most_common(1)[0][0]
    total = float(df["연예산"].fillna(0).sum())
    return owner, sorted(cnt), len(df), total


def add_files(conn, year, files):
    """files = [(파일 이름, bytes)]. 부서를 알아내 저장하고 [{부서, filename, rows}] 를 돌려준다."""
    out = []
    for name, data in files:
        fd, tmp = tempfile.mkstemp(suffix=".xlsx")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
            try:
                owner, depts, rows, total = read_file(conn, year, tmp)
            except Exception as e:
                raise ValueError(f"{name}: {e}") from e
        finally:
            try:
                os.remove(tmp)
            except OSError:
                pass
        conn.execute("DELETE FROM dept_plan_file WHERE year=? AND 부서=? AND filename=?",
                     (str(year), owner, name))
        conn.execute("INSERT INTO dept_plan_file(year,부서,포함부서,filename,uploaded_at,row_count,"
                     "total_amount,content) VALUES(?,?,?,?,?,?,?,?)",
                     (str(year), owner, json.dumps(depts, ensure_ascii=False), name, dbm._now(),
                      rows, total, data))
        out.append({"부서": owner, "포함부서": depts, "filename": name, "rows": rows})
    conn.commit()
    return out


def file_year(conn, file_id):
    row = conn.execute("SELECT year FROM dept_plan_file WHERE id=?", (file_id,)).fetchone()
    return row[0] if row else None


def remove_file(conn, file_id):
    conn.execute("DELETE FROM dept_plan_file WHERE id=?", (file_id,))
    conn.commit()


def _files(conn, year, content=False):
    cols = "id,부서,포함부서,filename,uploaded_at,row_count,total_amount" + (",content" if content else "")
    return conn.execute(f"SELECT {cols} FROM dept_plan_file WHERE year=? ORDER BY 부서,id",
                        (str(year),)).fetchall()


def status(conn, year):
    """화면용: 그 해 부서마다 제출 여부와 파일 목록, 구성 밖 부서, 지금 쓰는 계획이 취합본인지."""
    files = [{"id": r[0], "부서": r[1], "포함부서": json.loads(r[2] or "[]"), "filename": r[3],
              "uploaded_at": r[4], "row_count": r[5] or 0, "total_amount": r[6] or 0.0}
             for r in _files(conn, year)]
    covered = {d for f in files for d in f["포함부서"]} | {f["부서"] for f in files}
    depts = []
    expected = _expected(conn, year)
    for name, group in expected:
        own = [f for f in files if f["부서"] == name]
        depts.append({"부서": name, "그룹": group, "제출": name in covered, "files": own,
                      "다른파일": name in covered and not own})
    known = {n for n, _ in expected}
    extra = sorted({f["부서"] for f in files} - known)
    for name in extra:
        depts.append({"부서": name, "그룹": "구성 밖", "제출": True,
                      "files": [f for f in files if f["부서"] == name], "다른파일": False})
    latest = conn.execute("SELECT id,label FROM dataset WHERE kind='plan' AND year=? ORDER BY id DESC LIMIT 1",
                          (str(year),)).fetchone()
    n_exp = len(expected)
    n_done = sum(1 for d in depts[:n_exp] if d["제출"])
    return {"year": str(year), "depts": depts, "expected": n_exp, "submitted": n_done,
            "missing": [d["부서"] for d in depts[:n_exp] if not d["제출"]],
            "files": len(files),
            "current_is_merged": bool(latest and str(latest[1] or "").startswith(AUTO_LABEL)),
            "current_dataset": latest[0] if latest else None}


def rebuild(conn, year):
    """그 해 부서 파일 전부로 계획 데이터셋을 다시 만든다. 파일이 없으면 None.

    직전 취합본이 아직 그 해 가장 최근 계획이면 지운다(부서 하나 올릴 때마다 전체 사본이 쌓이지 않게).
    그 뒤에 누가 취합 계획을 직접 올렸다면 그건 건드리지 않는다.
    """
    prev = conn.execute("SELECT id,label FROM dataset WHERE kind='plan' AND year=? ORDER BY id DESC LIMIT 1",
                        (str(year),)).fetchone()
    rows = _files(conn, year, content=True)
    if prev and str(prev[1] or "").startswith(AUTO_LABEL):
        dbm.delete_dataset(conn, prev[0])
    if not rows:
        return None
    tmps, originals = [], []
    try:
        for r in rows:
            data = dbcore.as_bytes(r[7])
            fd, tmp = tempfile.mkstemp(suffix=".xlsx")
            tmps.append(tmp)
            with os.fdopen(fd, "wb") as f:
                f.write(data)
            originals.append((f"{r[1]}_{r[3]}", data))
        n_dept = len({r[1] for r in rows})
        label = f"{AUTO_LABEL} {n_dept}개 부서 · 파일 {len(rows)}개"
        info = dbm.ingest_plan(conn, tmps, year, label=label)
        dbm.save_dataset_files(conn, info["dataset_id"], originals)
        return info
    finally:
        for t in tmps:
            try:
                os.remove(t)
            except OSError:
                pass
