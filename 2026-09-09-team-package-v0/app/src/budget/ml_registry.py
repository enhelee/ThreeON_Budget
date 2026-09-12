# -*- coding: utf-8 -*-
"""학습 모델 레지스트리 + 학습데이터 관리 (DB 저장, 사용자 결정 2026-09-08).

왜 DB인가: 팀 v2 앱의 분류기(scikit-learn joblib)와 학습 CSV는 각자 PC 폴더에만 있어
누가 언제 어떤 데이터로 학습했는지, 어느 버전이 쓰이는지 남지 않았다. 여기서는
  model_registry     모델 버전(메타 + joblib 바이너리 BLOB, SHA256, 활성 플래그, 학습 스냅샷 링크)
  training_example   학습 예제(입력 텍스트·라벨·출처·확정 여부·작업자·활성)
  training_snapshot  재학습 시점의 학습데이터 스냅샷(CSV BLOB) — 모델↔데이터 재현성
세 표로 관리하고, 재학습은 관리자가 [재학습] 버튼으로만 실행한다(자동 재학습 없음).

모델 이름(팀 v2 대응):
  투자유형_전표텍스트   v2 ml_classifier: 전표헤더텍스트 → 투자유형          (type_classifier.joblib)
  투자유형_사업명       v2 project_type_classifier: '사업명 예산과목' → 투자유형     (project_type_model_major.joblib)
  투자유형세부_사업명   v2 project_type_classifier: '사업명 예산과목' → 투자유형세부 (project_type_model_minor.joblib)
학습 파이프라인은 v2와 동일(TF-IDF char_wb 2~4그램 + 로지스틱회귀)이라 v2 코드가 그대로 읽는다.
v2 앱은 파일에서 모델을 읽으므로 `export_to_v2_files`로 활성 버전을 파일로 내려주고,
`import_v2_files`로 팀원 PC의 기존 파일·CSV를 레지스트리에 흡수한다(scripts/v2_model_sync.py).
"""
import hashlib
import io
import json
from datetime import datetime

import pandas as pd

from . import dbcore

MODEL_NAMES = ("투자유형_전표텍스트", "투자유형_사업명", "투자유형세부_사업명")
V2_MODEL_FILES = {
    "투자유형_전표텍스트": "type_classifier.joblib",
    "투자유형_사업명": "project_type_model_major.joblib",
    "투자유형세부_사업명": "project_type_model_minor.joblib",
}
MIN_SAMPLES_TO_TRAIN = 20
MIN_CLASSES_TO_TRAIN = 2


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def init_tables(conn):
    cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS model_registry(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,               -- MODEL_NAMES
        version INTEGER NOT NULL,
        trained_at TEXT NOT NULL,
        n_samples INTEGER, n_classes INTEGER,
        metrics_json TEXT,                -- {"cv_accuracy":…, "per_class":{…}}
        sha256 TEXT NOT NULL,
        blob BLOB NOT NULL,               -- joblib.dump 바이너리
        active INTEGER NOT NULL DEFAULT 0,
        snapshot_id INTEGER,              -- training_snapshot.id
        note TEXT, created_by TEXT)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS training_example(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        model_name TEXT NOT NULL,
        text TEXT NOT NULL,               -- 입력(전표텍스트 또는 '사업명 예산과목')
        label TEXT NOT NULL,              -- 정답 라벨
        source TEXT,                      -- 'v2파일반입' | '사람확정' | '자동예측' | 'CSV가져오기'
        confirmed INTEGER NOT NULL DEFAULT 0,   -- 1=사람이 확정
        actor TEXT, created_at TEXT NOT NULL, updated_at TEXT,
        active INTEGER NOT NULL DEFAULT 1)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS training_snapshot(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        model_name TEXT NOT NULL,
        created_at TEXT NOT NULL,
        n_examples INTEGER NOT NULL,
        sha256 TEXT NOT NULL,
        csv BLOB NOT NULL,
        actor TEXT)""")
    cur.execute("CREATE INDEX IF NOT EXISTS ix_te_model ON training_example(model_name, active)")
    cur.execute("CREATE INDEX IF NOT EXISTS ix_mr_name ON model_registry(name, active)")
    conn.commit()


# ── 학습데이터 ─────────────────────────────────────────────────────────────

def add_examples(conn, model_name, rows, source, actor=None, confirmed=False):
    """rows: [(text, label), …]. 같은 (model_name, text)는 최신 라벨로 갱신(사람확정은 자동예측이 덮지 못함).
    반환 {"inserted": n, "updated": m, "skipped": k}"""
    cur = conn.cursor()
    ins = upd = skip = 0
    now = _now()
    for text, label in rows:
        text = str(text or "").strip()
        label = str(label or "").strip()
        if not text or not label:
            skip += 1
            continue
        row = cur.execute("SELECT id, confirmed, label FROM training_example WHERE model_name=? AND text=?",
                          (model_name, text)).fetchone()
        if row is None:
            cur.execute("INSERT INTO training_example(model_name,text,label,source,confirmed,actor,created_at,active)"
                        " VALUES(?,?,?,?,?,?,?,1)",
                        (model_name, text, label, source, 1 if confirmed else 0, actor, now))
            ins += 1
        else:
            ex_id, ex_conf, ex_label = row
            if ex_conf and not confirmed:
                skip += 1                       # 사람이 확정한 라벨은 자동값이 덮지 못한다
                continue
            if ex_label == label and bool(ex_conf) == bool(confirmed):
                skip += 1
                continue
            cur.execute("UPDATE training_example SET label=?, source=?, confirmed=?, actor=?, updated_at=?, active=1"
                        " WHERE id=?", (label, source, 1 if confirmed else 0, actor, now, ex_id))
            upd += 1
    conn.commit()
    return {"inserted": ins, "updated": upd, "skipped": skip}


def list_examples(conn, model_name, limit=200, only_unconfirmed=False, active_only=True):
    q = "SELECT id,text,label,source,confirmed,actor,created_at,updated_at,active FROM training_example WHERE model_name=?"
    p = [model_name]
    if active_only:
        q += " AND active=1"
    if only_unconfirmed:
        q += " AND confirmed=0"
    q += " ORDER BY id DESC LIMIT ?"
    p.append(int(limit))
    cols = ["id", "text", "label", "source", "confirmed", "actor", "created_at", "updated_at", "active"]
    return [dict(zip(cols, r)) for r in conn.execute(q, tuple(p)).fetchall()]


def example_stats(conn, model_name):
    tot = conn.execute("SELECT COUNT(*) FROM training_example WHERE model_name=? AND active=1", (model_name,)).fetchone()[0]
    conf = conn.execute("SELECT COUNT(*) FROM training_example WHERE model_name=? AND active=1 AND confirmed=1",
                        (model_name,)).fetchone()[0]
    per = dict(conn.execute("SELECT label, COUNT(*) FROM training_example WHERE model_name=? AND active=1 GROUP BY label",
                            (model_name,)).fetchall())
    return {"total": tot, "confirmed": conf, "unconfirmed": tot - conf, "per_class": per,
            "trainable": tot >= MIN_SAMPLES_TO_TRAIN and len(per) >= MIN_CLASSES_TO_TRAIN}


def confirm_examples(conn, ids, actor=None, label=None):
    n = 0
    for i in ids:
        if label is not None:
            cur = conn.execute("UPDATE training_example SET confirmed=1, label=?, actor=?, updated_at=? WHERE id=?",
                               (label, actor, _now(), int(i)))
        else:
            cur = conn.execute("UPDATE training_example SET confirmed=1, actor=?, updated_at=? WHERE id=?",
                               (actor, _now(), int(i)))
        n += cur.rowcount
    conn.commit()
    return n


def deactivate_examples(conn, ids, actor=None):
    n = 0
    for i in ids:
        cur = conn.execute("UPDATE training_example SET active=0, actor=?, updated_at=? WHERE id=?",
                           (actor, _now(), int(i)))
        n += cur.rowcount
    conn.commit()
    return n


def examples_frame(conn, model_name):
    rows = conn.execute("SELECT text,label,source,confirmed,actor,created_at FROM training_example"
                        " WHERE model_name=? AND active=1 ORDER BY id", (model_name,)).fetchall()
    return pd.DataFrame(rows, columns=["text", "label", "source", "confirmed", "actor", "created_at"])


def export_csv(conn, model_name):
    return examples_frame(conn, model_name).to_csv(index=False, encoding="utf-8-sig")


def import_csv(conn, model_name, content, actor=None, source="CSV가져오기", confirmed=True):
    """text,label 컬럼(또는 v2 형식 사업명/예산과목/투자유형/투자유형세부)을 가진 CSV 반입."""
    df = pd.read_csv(io.BytesIO(content) if isinstance(content, (bytes, bytearray)) else io.StringIO(content), dtype=str)
    df = df.fillna("")
    if {"text", "label"} <= set(df.columns):
        rows = list(zip(df["text"], df["label"]))
    elif {"사업명", "예산과목"} <= set(df.columns):
        target = "투자유형세부" if model_name.startswith("투자유형세부") else "투자유형"
        if target not in df.columns:
            raise ValueError(f"CSV에 '{target}' 열이 없습니다.")
        rows = [(f"{a} {b}".strip(), c) for a, b, c in zip(df["사업명"], df["예산과목"], df[target]) if c]
    else:
        raise ValueError("CSV는 text,label 열 또는 사업명,예산과목,투자유형(세부) 열이 필요합니다.")
    return add_examples(conn, model_name, rows, source=source, actor=actor, confirmed=confirmed)


def make_snapshot(conn, model_name, actor=None):
    csv = export_csv(conn, model_name).encode("utf-8")
    sha = hashlib.sha256(csv).hexdigest()
    n = conn.execute("SELECT COUNT(*) FROM training_example WHERE model_name=? AND active=1", (model_name,)).fetchone()[0]
    cur = conn.cursor()
    cur.execute("INSERT INTO training_snapshot(model_name,created_at,n_examples,sha256,csv,actor) VALUES(?,?,?,?,?,?)",
                (model_name, _now(), int(n), sha, csv, actor))
    conn.commit()
    return cur.lastrowid


# ── 모델 ────────────────────────────────────────────────────────────────────

def _pipeline():
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline
    return Pipeline([
        ("tfidf", TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4))),
        ("clf", LogisticRegression(max_iter=1000)),
    ])


def register_model(conn, name, blob, n_samples=None, n_classes=None, metrics=None,
                   snapshot_id=None, note=None, actor=None, activate=True):
    blob = bytes(blob)
    sha = hashlib.sha256(blob).hexdigest()
    cur = conn.cursor()
    ver = cur.execute("SELECT COALESCE(MAX(version),0) FROM model_registry WHERE name=?", (name,)).fetchone()[0]
    ver = int(ver or 0) + 1
    if activate:
        cur.execute("UPDATE model_registry SET active=0 WHERE name=?", (name,))
    cur.execute("INSERT INTO model_registry(name,version,trained_at,n_samples,n_classes,metrics_json,sha256,blob,"
                "active,snapshot_id,note,created_by) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (name, ver, _now(), n_samples, n_classes, json.dumps(metrics or {}, ensure_ascii=False),
                 sha, blob, 1 if activate else 0, snapshot_id, note, actor))
    conn.commit()
    return {"id": cur.lastrowid, "name": name, "version": ver, "sha256": sha, "active": bool(activate)}


def list_models(conn, name=None):
    q = ("SELECT id,name,version,trained_at,n_samples,n_classes,metrics_json,sha256,active,snapshot_id,note,created_by,"
         "LENGTH(blob) FROM model_registry" + (" WHERE name=?" if name else "") + " ORDER BY name, version DESC")
    cols = ["id", "name", "version", "trained_at", "n_samples", "n_classes", "metrics", "sha256", "active",
            "snapshot_id", "note", "created_by", "size"]
    out = []
    for r in conn.execute(q, (name,) if name else ()).fetchall():
        d = dict(zip(cols, r))
        d["metrics"] = json.loads(d["metrics"]) if d["metrics"] else {}
        d["active"] = bool(d["active"])
        out.append(d)
    return out


def activate_model(conn, model_id):
    row = conn.execute("SELECT name FROM model_registry WHERE id=?", (int(model_id),)).fetchone()
    if not row:
        return False
    conn.execute("UPDATE model_registry SET active=0 WHERE name=?", (row[0],))
    conn.execute("UPDATE model_registry SET active=1 WHERE id=?", (int(model_id),))
    conn.commit()
    return True


def get_model_blob(conn, model_id=None, name=None):
    """model_id 또는 name(활성 버전)의 (meta, bytes). 없으면 (None, None)."""
    if model_id is not None:
        row = conn.execute("SELECT id,name,version,blob FROM model_registry WHERE id=?", (int(model_id),)).fetchone()
    else:
        row = conn.execute("SELECT id,name,version,blob FROM model_registry WHERE name=? AND active=1", (name,)).fetchone()
    if not row:
        return None, None
    return {"id": row[0], "name": row[1], "version": row[2]}, dbcore.as_bytes(row[3])


def load_active_model(conn, name):
    import joblib
    meta, blob = get_model_blob(conn, name=name)
    if blob is None:
        return None, None
    return meta, joblib.load(io.BytesIO(blob))


def train(conn, model_name, actor=None, note=None, activate=True):
    """활성 학습예제로 재학습 → 스냅샷 + 새 버전 등록. 반환 메타(dict)."""
    import joblib
    from sklearn.model_selection import cross_val_score
    df = examples_frame(conn, model_name)
    if len(df) < MIN_SAMPLES_TO_TRAIN or df["label"].nunique() < MIN_CLASSES_TO_TRAIN:
        raise ValueError(f"학습 데이터가 부족합니다: {len(df)}건 / 유형 {df['label'].nunique()}개 "
                         f"(최소 {MIN_SAMPLES_TO_TRAIN}건·{MIN_CLASSES_TO_TRAIN}개 유형)")
    pipe = _pipeline()
    n_classes = int(df["label"].nunique())
    folds = int(min(5, df["label"].value_counts().min(), len(df) // n_classes))
    cv_acc = None
    if folds >= 2:
        cv_acc = round(float(cross_val_score(pipe, df["text"], df["label"], cv=folds).mean()), 3)
    pipe.fit(df["text"], df["label"])
    buf = io.BytesIO()
    joblib.dump(pipe, buf)
    snap_id = make_snapshot(conn, model_name, actor=actor)
    metrics = {"cv_accuracy": cv_acc, "cv_folds": folds,
               "per_class": {str(k): int(v) for k, v in df["label"].value_counts().items()},
               "confirmed_share": round(float(df["confirmed"].astype(int).mean()), 3) if len(df) else None}
    info = register_model(conn, model_name, buf.getvalue(), n_samples=len(df), n_classes=n_classes,
                          metrics=metrics, snapshot_id=snap_id, note=note or "재학습(관리자)", actor=actor,
                          activate=activate)
    info.update({"metrics": metrics, "n_samples": len(df), "n_classes": n_classes, "snapshot_id": snap_id})
    return info


def predict(model, texts):
    labels = model.predict(list(texts))
    proba = model.predict_proba(list(texts))
    return list(labels), [round(float(p), 3) for p in proba.max(axis=1)]


# ── 팀 v2 앱 파일 ↔ 레지스트리 동기화 ─────────────────────────────────────

def import_v2_files(conn, v2_dir, actor=None):
    """팀원 PC의 v2 폴더(training_data.csv, project_type_training.csv, *.joblib)를 레지스트리로 흡수."""
    import os
    report = {}
    p = os.path.join(v2_dir, "training_data.csv")
    if os.path.exists(p):
        df = pd.read_csv(p, dtype=str).fillna("")
        if {"text", "label"} <= set(df.columns):
            report["투자유형_전표텍스트/examples"] = add_examples(
                conn, "투자유형_전표텍스트", list(zip(df["text"], df["label"])), "v2파일반입", actor, confirmed=True)
    p = os.path.join(v2_dir, "project_type_training.csv")
    if os.path.exists(p):
        df = pd.read_csv(p, dtype=str).fillna("")
        if {"사업명", "예산과목"} <= set(df.columns):
            txt = (df["사업명"] + " " + df["예산과목"]).str.strip()
            if "투자유형" in df.columns:
                rows = [(t, l) for t, l in zip(txt, df["투자유형"]) if l]
                report["투자유형_사업명/examples"] = add_examples(conn, "투자유형_사업명", rows, "v2파일반입", actor, True)
            if "투자유형세부" in df.columns:
                rows = [(t, l) for t, l in zip(txt, df["투자유형세부"]) if l]
                report["투자유형세부_사업명/examples"] = add_examples(conn, "투자유형세부_사업명", rows, "v2파일반입", actor, True)
    for name, fname in V2_MODEL_FILES.items():
        p = os.path.join(v2_dir, fname)
        if os.path.exists(p):
            blob = open(p, "rb").read()
            sha = hashlib.sha256(blob).hexdigest()
            dup = conn.execute("SELECT id FROM model_registry WHERE name=? AND sha256=?", (name, sha)).fetchone()
            if dup:
                report[f"{name}/model"] = {"skipped": "동일 파일 이미 등록", "id": dup[0]}
                continue
            has_active = conn.execute("SELECT 1 FROM model_registry WHERE name=? AND active=1", (name,)).fetchone()
            report[f"{name}/model"] = register_model(conn, name, blob, note=f"v2 파일 반입: {fname}", actor=actor,
                                                     activate=not has_active)
    return report


def export_to_v2_files(conn, v2_dir):
    """활성 모델을 v2가 읽는 파일명으로, 학습예제를 v2 CSV 형식으로 내려준다(팀원 PC 동기화)."""
    import os
    written = []
    for name, fname in V2_MODEL_FILES.items():
        meta, blob = get_model_blob(conn, name=name)
        if blob:
            with open(os.path.join(v2_dir, fname), "wb") as f:
                f.write(blob)
            written.append(fname)
    df = examples_frame(conn, "투자유형_전표텍스트")
    if len(df):
        df[["text", "label"]].to_csv(os.path.join(v2_dir, "training_data.csv"), index=False)
        written.append("training_data.csv")
    return written
