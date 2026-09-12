# -*- coding: utf-8 -*-
"""예산·실적 분석 웹 서버 (FastAPI + SQLite).

보안 구조:
- 프론트(webapp/index.html)는 정적 파일 — 원자료를 갖지 않는다.
- 업로드 파일은 즉시 DB(data/budget.db)로 흡수되고 임시파일은 삭제된다.
- 모든 분석·수정(전표 재배정)은 백엔드 DB에서 수행되고,
  프론트에는 API 응답(분석 결과)만 내려간다.

실행:  py -m uvicorn server:app --port 8010   (budget_app 디렉토리에서)
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

import json
from urllib.parse import quote
import pandas as pd
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware

APP_DIR = os.path.dirname(os.path.abspath(__file__))

from budget import auth as authm                      # noqa: E402
authm.load_dotenv_if_present(APP_DIR)                 # .env → 환경변수 (DATABASE_URL·APP_PASSWORD 등)

from budget import config_store, db as dbm, dbcore, ml_registry, pipeline_db   # noqa: E402

CONFIG_DIR = os.environ.get("CONFIG_DIR") or os.path.join(APP_DIR, "config")
OUT_DIR = os.environ.get("OUT_DIR") or os.path.join(APP_DIR, "output")
# 프론트는 Vite 빌드 산출물(static/) 하나뿐이다. 빌드 전 원본은 web/ 에 있다.
#   로컬:   cd app/web && npm install && npm run build
#   도커:   Dockerfile 의 node 스테이지가 만들어 /srv/app/static/ 으로 넣는다
# 예전 webapp/index.html(단일 149KB)은 web/ 로 쪼개져 삭제되었다. 폴백을 두지 않는 이유는,
# 빌드가 실패했을 때 조용히 옛 화면을 서비스하는 것이 눈에 띄게 실패하는 것보다 나쁘기 때문이다.
STATIC_DIR = os.path.join(APP_DIR, "static")
WEB_DIR = STATIC_DIR
_PARENT = os.path.dirname(APP_DIR)
SITE_DIR = os.environ.get("SITE_DIR") or next(              # 소개 사이트: 패키지는 docs/, 개발 폴더는 site/
    (d for d in (os.path.join(_PARENT, "docs"), os.path.join(_PARENT, "site"))
     if os.path.exists(os.path.join(d, "index.html"))), os.path.join(_PARENT, "docs"))
AUTH = authm.AuthConfig()

app = FastAPI(title="예산·실적 분석", docs_url=None, redoc_url=None)


def _conn():
    return dbm.connect()


def _operator(request: Request):
    """현재 요청의 작업자 이름(감사 로그·이력 표기). 인증 비활성 시 'local'."""
    return getattr(request.state, "operator", None) or "local"


class AuthAuditMiddleware(BaseHTTPMiddleware):
    """① /api/* 는 세션 쿠키 필수(로그인·상태·헬스체크 제외) ② 변경 요청은 audit_log에 기록.

    공용 비밀번호 1개 체계(사용자 결정)에서 수정 이력은 이 미들웨어가 남기는 audit_log가 근거다:
    작업자(로그인 때 입력) · 시각 · 메서드 · 경로 · 응답코드 · 요청 요약(JSON 키/식별자, 파일 본문 제외).
    """

    async def dispatch(self, request, call_next):
        path = request.url.path
        operator = None
        if AUTH.enabled:
            operator = AUTH.verify(request.cookies.get(AUTH.cookie_name))
            if path.startswith("/api/") and path not in authm.PUBLIC_API and not operator:
                return JSONResponse({"detail": "login_required"}, status_code=401)
        request.state.operator = operator or ("local" if not AUTH.enabled else None)

        body_json = None
        if (request.method in ("POST", "PUT", "PATCH", "DELETE") and path.startswith("/api/")
                and "application/json" in (request.headers.get("content-type") or "")):
            raw = await request.body()           # Starlette가 캐시 → 라우트에서 다시 읽을 수 있다
            if len(raw) <= 65536:
                try:
                    body_json = json.loads(raw.decode("utf-8"))
                except (ValueError, UnicodeDecodeError):
                    body_json = None
        response = await call_next(request)
        if (request.method in ("POST", "PUT", "PATCH", "DELETE") and path.startswith("/api/")
                and path not in ("/api/login", "/api/logout")):
            if body_json and "password" in body_json:
                body_json = {k: v for k, v in body_json.items() if k != "password"}
            try:
                conn = _conn()
                try:
                    dbm.add_audit(conn, request.state.operator, request.method, path,
                                  response.status_code,
                                  authm.audit_detail(path, request.url.query, body_json))
                finally:
                    conn.close()
            except Exception:              # 감사 기록 실패가 본 요청을 깨뜨리지 않게
                pass
        return response


app.add_middleware(AuthAuditMiddleware)


# ── 인증 (공용 비밀번호 + 작업자 이름) ─────────────────────────────────────

class LoginReq(BaseModel):
    password: str
    name: str


@app.get("/healthz")
def healthz():
    return {"ok": True, "auth": AUTH.enabled, "db": "postgresql" if dbcore.is_postgres_url(dbcore.database_url()) else "sqlite"}


@app.get("/api/auth/status")
def auth_status(request: Request):
    op = AUTH.verify(request.cookies.get(AUTH.cookie_name)) if AUTH.enabled else "local"
    return {"enabled": AUTH.enabled, "operator": op, "logged_in": bool(op)}


@app.post("/api/login")
def login(req: LoginReq, request: Request):
    if not AUTH.enabled:
        return {"ok": True, "operator": "local", "enabled": False}
    name = authm.clean_operator(req.name)
    if not name:
        raise HTTPException(400, "작업자 이름을 입력하세요(수정 이력에 기록됩니다).")
    if not AUTH.check_password(req.password):
        conn = _conn()
        try:
            dbm.add_audit(conn, name, "POST", "/api/login", 401, "비밀번호 불일치")
        finally:
            conn.close()
        raise HTTPException(401, "비밀번호가 맞지 않습니다.")
    secure = AUTH.cookie_secure or request.url.scheme == "https" \
        or request.headers.get("x-forwarded-proto") == "https"
    resp = JSONResponse({"ok": True, "operator": name, "enabled": True})
    resp.set_cookie(AUTH.cookie_name, AUTH.issue(name), httponly=True, samesite="lax",
                    secure=secure, max_age=int(AUTH.session_hours * 3600), path="/")
    conn = _conn()
    try:
        dbm.add_audit(conn, name, "POST", "/api/login", 200, "로그인")
    finally:
        conn.close()
    return resp


@app.post("/api/logout")
def logout(request: Request):
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(AUTH.cookie_name, path="/")
    return resp


@app.get("/api/audit")
def audit(request: Request, limit: int = 100, operator: str = None):
    conn = _conn()
    try:
        return {"rows": dbm.list_audit(conn, limit=min(int(limit), 1000), operator=operator)}
    finally:
        conn.close()


def _guard_unlocked(conn, year, action="변경"):
    """마감(잠금)된 연도의 데이터 변경 차단."""
    if dbm.is_locked(conn, year):
        raise HTTPException(
            423, f"{year}년은 마감(잠금) 상태입니다 — {action}이(가) 차단됩니다. "
                 "설정 탭에서 잠금을 해제한 뒤 진행하세요.")


def _mtime_str(path):
    """파일 수정시각을 DB의 created_at과 같은 'YYYY-MM-DD HH:MM:SS' 문자열로."""
    import datetime
    return datetime.datetime.fromtimestamp(os.path.getmtime(path)).strftime(
        "%Y-%m-%d %H:%M:%S")


def _clean_json(obj):
    """NaN → None 재귀 정리(JSON 직렬화 안전)."""
    if isinstance(obj, dict):
        return {k: _clean_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_clean_json(v) for v in obj]
    if isinstance(obj, float) and obj != obj:
        return None
    return obj


# ── 정적 프론트 ──────────────────────────────────────────────────────────

@app.get("/")
def index():
    page = os.path.join(WEB_DIR, "index.html")
    if not os.path.isfile(page):
        raise HTTPException(500, "프론트가 빌드되지 않았습니다 — `cd app/web && npm install && npm run build` 를 실행하세요.")
    return FileResponse(page)


@app.get("/app")
@app.get("/app/{path:path}")
def app_redirect(path: str = ""):
    """예전 주소(/app/)를 새 루트로 영구 이동 — 팀원이 저장해 둔 북마크를 지킨다."""
    return RedirectResponse("/", status_code=301)


# ── 자료 업로드 (DB 흡수, 원본 미보관) ──────────────────────────────────

async def _ingest(file: UploadFile, year: str, kind: str):
    fd, tmp = tempfile.mkstemp(suffix=".xlsx")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(await file.read())
        conn = _conn()
        try:
            _guard_unlocked(conn, year, "자료 업로드")
            if kind == "plan":
                info = dbm.ingest_plan(conn, tmp, year, label=file.filename)
            else:
                info = dbm.ingest_erp(conn, tmp, year, label=file.filename)
        finally:
            conn.close()
        return info
    finally:
        try:
            os.remove(tmp)          # 보안: 원본 파일 미보관
        except OSError:
            pass


@app.post("/api/upload/plan")
async def upload_plan(year: str, file: UploadFile = File(...)):
    try:
        return _clean_json(await _ingest(file, year, "plan"))
    except Exception as e:
        raise HTTPException(400, f"계획 파일 흡수 실패: {e}")


@app.post("/api/upload/erp")
async def upload_erp(year: str, file: UploadFile = File(...)):
    try:
        return _clean_json(await _ingest(file, year, "erp"))
    except Exception as e:
        raise HTTPException(400, f"zrfm2 파일 흡수 실패: {e}")


@app.post("/api/upload/master")
async def upload_master(kind: str, file: UploadFile = File(...)):
    """기준정보 마스터 갱신: kind=item(예산과목) | dept(부서코드)."""
    if kind not in ("item", "dept"):
        raise HTTPException(400, "kind는 item(예산과목) 또는 dept(부서코드)여야 합니다.")
    fd, tmp = tempfile.mkstemp(suffix=".xlsx")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(await file.read())
        conn = _conn()
        try:
            n = (dbm.ingest_item_master(conn, tmp) if kind == "item"
                 else dbm.ingest_dept_master(conn, tmp))
            return {"rows": n, "master": dbm.master_stats(conn),
                    "notice": f"{'예산과목' if kind == 'item' else '부서코드'} 마스터 "
                              f"{n}건 갱신 — 다음 분석부터 적용됩니다."}
        finally:
            conn.close()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, f"마스터 흡수 실패: {e}")
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


@app.get("/api/datasets")
def datasets():
    conn = _conn()
    try:
        return _clean_json(dbm.list_datasets(conn))
    finally:
        conn.close()


# ── 분석 실행 ───────────────────────────────────────────────────────────

class AnalyzeReq(BaseModel):
    year: str
    policy: str = "group"


@app.post("/api/analyze")
def analyze(req: AnalyzeReq):
    """손익·자본 모두 실행(25년 확정 분류체계 시드 사용).

    Excel/CSV 산출물은 만들지 않는다 — 그게 시간의 63%였다(zrfm2_V1 8.2초).
    파일은 `/api/export`에서 필요할 때 생성한다.
    """
    conn = _conn()
    try:
        _guard_unlocked(conn, req.year, "분석 실행")
        out = {}
        for budget in ("손익", "자본"):
            res = pipeline_db.run_actual_db(
                conn, CONFIG_DIR, OUT_DIR, req.year, budget, new_policy=req.policy,
                make_files=False)
            out[budget] = {"run_id": res["run_id"], "요약": res["요약"],
                           "경고": res.get("경고", [])}
        return _clean_json(out)
    except ValueError as e:
        raise HTTPException(400, str(e))
    finally:
        conn.close()


def _latest_runs(conn, year):
    runs = {}
    for budget in ("손익", "자본"):
        r = dbm.latest_run(conn, year, budget)
        if r:
            runs[budget] = r
    return runs


@app.get("/api/status")
def status(year: str):
    """홈·집계 화면용: 최근 실행 요약 + 데이터셋 현황 + 잠금·마스터 상태."""
    conn = _conn()
    try:
        runs = _latest_runs(conn, year)
        ds = dbm.list_datasets(conn)
        years = sorted({d["year"] for d in ds}, reverse=True)
        item_alias = config_store.load_item_alias(CONFIG_DIR)
        from budget import normalize as _norm
        items_cfg = {}
        for b in ("손익", "자본"):
            cfg = config_store.load_item_config(CONFIG_DIR, year, b)
            items_cfg[b] = [_norm.normalize_item(x["과목"], item_alias) for x in cfg
                            if config_store.to_bool(x.get("포함"), True)
                            and config_store.to_bool(x.get("실적반영"), True)]
        return _clean_json({
            "year": year, "years": years,
            "datasets": ds[:10],
            "locked": dbm.is_locked(conn, year),
            "locks": dbm.locked_years(conn),
            "master": dbm.master_stats(conn),
            "items": items_cfg,
            "runs": {b: {"created_at": r["created_at"], "summary": r["summary"]}
                     for b, r in runs.items()},
        })
    finally:
        conn.close()


# ── 연도 마감(잠금) ────────────────────────────────────────────────────

class LockReq(BaseModel):
    year: str


@app.post("/api/lock")
def lock(req: LockReq):
    conn = _conn()
    try:
        dbm.lock_year(conn, req.year)
        # 마감 스냅샷: 그 시점의 산출물 6종을 output/마감/{연도}/에 증빙 보관
        import shutil
        snap_dir = os.path.join(OUT_DIR, "마감", str(req.year))
        os.makedirs(snap_dir, exist_ok=True)
        copied = 0
        for budget in ("손익", "자본"):
            for name in (f"{req.year}년 {budget}예산_실적.xlsx",
                         f"zrfm2_{req.year}_V1({budget}).xlsx",
                         f"matched_{req.year}_{budget}.csv"):
                src = os.path.join(OUT_DIR, name)
                if os.path.exists(src):
                    shutil.copy2(src, os.path.join(snap_dir, name))
                    copied += 1
        return {"locked": req.year, "snapshot": copied,
                "notice": f"{req.year}년 마감 완료 — 업로드·분석·재배정·수정이 차단되고 "
                          f"산출물 {copied}종을 output/마감/{req.year}/에 보관했습니다. "
                          "(조회·통계·Excel 내보내기는 계속 가능)"}
    finally:
        conn.close()


@app.delete("/api/lock/{year}")
def unlock(year: str):
    conn = _conn()
    try:
        dbm.unlock_year(conn, year)
        return {"unlocked": year}
    finally:
        conn.close()


@app.get("/api/overview")
def overview():
    """홈 화면용: DB에 있는 모든 연도의 최신 실행 요약(다년도 계획·실적)."""
    conn = _conn()
    try:
        ds = dbm.list_datasets(conn)
        years = sorted({d["year"] for d in ds})
        rows = []
        for y in years:
            entry = {"year": y}
            for budget in ("손익", "자본"):
                r = dbm.latest_run(conn, y, budget)
                if r:
                    s = r["summary"]
                    entry[budget] = {
                        "계획": s.get("계획 연예산(천원)", 0),
                        "실적": s.get("총 실적(천원)", 0),
                        "집행률": s.get("집행률(%)"),
                        "실행일시": r["created_at"],
                    }
            rows.append(entry)
        return _clean_json({"years": rows})
    finally:
        conn.close()


# ── 학습 (완료 자료 → 텍스트-사업 매핑 축적) ────────────────────────────

class LearnReq(BaseModel):
    year: str


@app.post("/api/learn")
def learn(req: LearnReq):
    conn = _conn()
    try:
        counts = dbm.learn_from_year(conn, req.year)
        stats_ = dbm.learned_stats(conn)
        return _clean_json({"learned": counts, "total": stats_,
                            "notice": f"{req.year}년 확정 결과 학습 완료 — 다음 분석부터 자동 적용됩니다."})
    finally:
        conn.close()


@app.get("/api/pending")
def pending(year: str):
    """분석에 아직 반영되지 않은 변경 건수 + 학습 대기 건수.

    최신 run 시각보다 나중에 저장된 지시(재배정·수정·삭제·사업추가)를 센다.
    """
    conn = _conn()
    try:
        runs = _latest_runs(conn, year)
        # 손익·자본 중 더 오래된 실행 시각 기준(둘 다 최신이어야 반영 완료)
        stamps = [str(r["created_at"]) for r in runs.values()]
        base = min(stamps) if len(stamps) == 2 else (stamps[0] if stamps else None)
        out = {"analyzed_at": base, "counts": {}, "total": 0}
        tables = (("override", "전표 재배정"), ("biz_edit", "사업 수정"),
                  ("biz_delete", "사업 삭제"), ("manual_biz", "사업 추가"))
        for tbl, label in tables:
            if base is None:
                n = conn.execute(
                    f"SELECT COUNT(*) FROM {tbl} WHERE year=?", (str(year),)).fetchone()[0]
            else:
                n = conn.execute(
                    f"SELECT COUNT(*) FROM {tbl} WHERE year=? AND created_at > ?",
                    (str(year), base)).fetchone()[0]
            if n:
                out["counts"][label] = n
                out["total"] += n
        out["learn_pending"] = dbm.count_learn_pending(conn, year)
        return _clean_json(out)
    finally:
        conn.close()


@app.get("/api/learned")
def learned_status():
    conn = _conn()
    try:
        return _clean_json(dbm.learned_stats(conn))
    finally:
        conn.close()


@app.delete("/api/learned")
def learned_clear():
    conn = _conn()
    try:
        dbm.clear_learned(conn)
        return {"cleared": True}
    finally:
        conn.close()


# ── 사업 내용 수정 (관리자) ─────────────────────────────────────────────

class BizEditReq(BaseModel):
    year: str
    budget: str
    예산과목: str
    처지사: str
    사업명: str
    fields: dict


@app.post("/api/biz-edit")
def biz_edit(req: BizEditReq):
    # 처지사 = 예산귀속 지사. 종합표·지사별 집계 기준이라 이 값이 바뀌면 사업이 통째로
    #   이동한다(계획행=여기, 귀속 전표=override.target_dept — 둘 다 매칭 전에 적용).
    # 연예산(천원)도 고칠 수 있다 — 원본 plan_row는 보존하고 분석에만 덧씌운다.
    # 예산과목도 고칠 수 있다(계획본 분류 오류 정정). 단 전표의 과목은 ERP 계정코드가
    #   정하므로 귀속 전표는 옛 과목에 신규로 남는다 — UI가 미리 경고한다.
    allowed = {"사업명", "속성", "주관부서명", "부서부", "처지사", "연예산", "예산과목"}
    fields = {}
    for k, v in req.fields.items():
        if k not in allowed:
            continue
        if k == "연예산":
            s = str(v).replace(",", "").strip()
            if s == "":
                fields[k] = ""            # 빈칸 = 연예산 결측으로 되돌림
                continue
            try:
                fields[k] = float(s)
            except ValueError:
                raise HTTPException(400, f"연예산은 숫자(천원)로 입력하세요: '{v}'")
        else:
            fields[k] = str(v)
    if not fields:
        raise HTTPException(
            400, "수정할 필드가 없습니다. (사업명/속성/주관부서명/부서부/처지사/연예산)")
    if "처지사" in fields and not str(fields["처지사"]).strip():
        raise HTTPException(400, "예산귀속 지사는 비울 수 없습니다.")
    if "예산과목" in fields and not str(fields["예산과목"]).strip():
        raise HTTPException(400, "예산과목은 비울 수 없습니다.")
    conn = _conn()
    try:
        _guard_unlocked(conn, req.year, "사업 내용 수정")
        dbm.add_biz_edit(conn, req.year, req.budget, req.예산과목, req.처지사,
                         req.사업명, fields)
        # 이름을 바꾸면 그 이름을 가리키던 재배정·학습도 함께 옮긴다 — 안 하면
        #   재분석 때 옛 이름의 동명 신규 사업이 따로 생겨 중복 행이 된다.
        moved = {}
        new_name = fields.get("사업명")
        if new_name and new_name != req.사업명:
            moved = dbm.rename_biz_references(conn, req.year, req.budget, req.예산과목,
                                              req.처지사, req.사업명, new_name)
        patched = dbm.patch_latest_run_biz(conn, req.year, req.budget, req.예산과목,
                                           req.처지사, req.사업명, fields)
        notice = "저장됨 — 화면에 즉시 반영되며, 이후 분석에도 유지됩니다."
        if moved.get("override") or moved.get("learned"):
            notice += (f" (이름 변경 연동: 재배정 {moved.get('override', 0)}건 ·"
                       f" 학습 {moved.get('learned', 0)}건)")
        return {"patched": patched, "moved": moved, "notice": notice}
    finally:
        conn.close()


class BizDeleteReq(BaseModel):
    year: str
    budget: str
    예산과목: str
    처지사: str
    사업명: str
    memo: str | None = None


@app.post("/api/biz-delete")
def biz_delete(req: BizDeleteReq):
    """사업 삭제 = 분석 대상에서 제외(원본 plan_row는 보존 → 이력 삭제로 복구).

    귀속 전표를 먼저 다른 사업으로 옮기는 것은 호출자(UI)의 책임이다. 남아 있어도
    금액이 사라지지는 않고 매칭이 신규로 되살리므로 총액은 항상 보존된다.
    """
    conn = _conn()
    try:
        _guard_unlocked(conn, req.year, "사업 삭제")
        dbm.add_biz_delete(conn, req.year, req.budget, req.예산과목, req.처지사,
                           req.사업명, req.memo)
        return {"deleted": req.사업명,
                "notice": "삭제됨 — 설정 탭 '사업 삭제 이력'에서 되돌릴 수 있습니다."}
    finally:
        conn.close()


@app.get("/api/biz-deletes")
def biz_deletes(year: str):
    conn = _conn()
    try:
        return _clean_json(dbm.list_biz_deletes(conn, year))
    finally:
        conn.close()


@app.delete("/api/biz-delete/{del_id}")
def restore_biz_delete(del_id: int):
    conn = _conn()
    try:
        dbm.delete_biz_delete(conn, del_id)
        return {"restored": del_id}
    finally:
        conn.close()


@app.get("/api/biz-edits")
def biz_edits(year: str):
    conn = _conn()
    try:
        return _clean_json(dbm.list_biz_edits(conn, year))
    finally:
        conn.close()


@app.delete("/api/biz-edit/{edit_id}")
def delete_biz_edit(edit_id: int):
    conn = _conn()
    try:
        dbm.delete_biz_edit(conn, edit_id)
        return {"deleted": edit_id}
    finally:
        conn.close()


# ── 수동 사업 추가 (계획본에 없는 사업 등록) ────────────────────────────

class ManualBizReq(BaseModel):
    year: str
    budget: str
    예산과목: str
    처지사: str
    사업명: str
    속성: str | None = None
    주관부서명: str | None = None
    부서부: str | None = None
    연예산: float | None = None      # 천원


@app.post("/api/manual-biz")
def add_manual_biz(req: ManualBizReq):
    if not req.사업명.strip() or not req.예산과목.strip() or not req.처지사.strip():
        raise HTTPException(400, "예산과목·지사·사업명은 필수입니다.")
    conn = _conn()
    try:
        _guard_unlocked(conn, req.year, "사업 추가")
        bid = dbm.add_manual_biz(conn, req.year, req.budget, req.예산과목.strip(),
                                 req.처지사.strip(), req.사업명.strip(),
                                 attr=(req.속성 or None), owner=(req.주관부서명 or None),
                                 part=(req.부서부 or None), plan_amt=req.연예산)
        return {"id": bid,
                "notice": "사업 추가됨 — 분석 재실행 시 계획 사업으로 편입되어 "
                          "전표 재배정 대상으로 사용할 수 있습니다."}
    finally:
        conn.close()


@app.get("/api/manual-biz")
def manual_biz_list(year: str):
    conn = _conn()
    try:
        return _clean_json(dbm.list_manual_biz(conn, year))
    finally:
        conn.close()


@app.delete("/api/manual-biz/{biz_id}")
def delete_manual_biz(biz_id: int):
    conn = _conn()
    try:
        dbm.delete_manual_biz(conn, biz_id)
        return {"deleted": biz_id}
    finally:
        conn.close()


# ── 지사별 현황·상세 ────────────────────────────────────────────────────

UNMAPPED_SUFFIX = " (미매핑)"


def _unmapped_detail(conn, runs):
    """미반영(미매핑 처지사) 전표를 원문 지사별로 수집: {raw: [voucher...]}."""
    out = {}
    for budget, r in runs.items():
        detail = dbm.load_match_detail(conn, r["id"])
        um = detail[(detail["구분"] == "미반영") & (detail["처지사정규"].isna())]
        for _, v in um.iterrows():
            raw = str(v["지사원문"] or "(지사명 없음)").strip()
            out.setdefault(raw, []).append({
                "budget": budget,
                "과목": v["과목정규"],
                "erp_row_id": int(v["erp_row_id"]),
                "전표번호": v["전표번호"], "전기일": v["전기일"],
                "텍스트": v["전표텍스트"], "부서부": v["부서부원문"],
                "금액원": round(v["금액원"] or 0),
                "금액천원": round(v["금액천원"] or 0),
            })
    return out


@app.get("/api/branches")
def branches(year: str):
    """전지사 요약: 지사 × (손익/자본) 계획·실적 + 미매핑 가상 지사."""
    conn = _conn()
    try:
        runs = _latest_runs(conn, year)
        if not runs:
            return {"rows": []}
        agg = {}
        for budget, r in runs.items():
            df = dbm.load_biz_lines(conn, r["id"])
            for _, row in df.iterrows():
                dept = row["처지사"] or "(미매핑)"
                g = agg.setdefault(dept, {"branch": dept,
                                          "profitPlan": 0, "profitActual": 0,
                                          "capitalPlan": 0, "capitalActual": 0,
                                          "lowConf": 0, "unmapped": 0})
                p = row["연예산"] or 0
                a = row["실적금액"] or 0
                if budget == "손익":
                    g["profitPlan"] += p
                    g["profitActual"] += a
                else:
                    g["capitalPlan"] += p
                    g["capitalActual"] += a
                conf = row["매칭확신도"]
                if row["구분"] == "계획집행" and conf is not None and conf < 0.8:
                    g["lowConf"] += 1
        rows = sorted(agg.values(), key=lambda x: x["branch"])
        # 미매핑 전표는 원문 지사별 가상 행으로 맨 아래에 노출(종합표 미포함 금액)
        for raw, vs in sorted(_unmapped_detail(conn, runs).items()):
            rows.append({"branch": raw + UNMAPPED_SUFFIX,
                         "profitPlan": 0, "profitActual": 0,
                         "capitalPlan": 0, "capitalActual": 0,
                         "lowConf": 0, "unmapped": len(vs),
                         "unmappedAmt": sum(v["금액천원"] for v in vs)})
        return _clean_json({"rows": rows})
    finally:
        conn.close()


@app.get("/api/branch-detail")
def branch_detail(year: str, branch: str):
    """지사 상세: 손익·자본 통합 사업 목록 + 사업별 귀속 ERP 전표(트리).

    '{원문} (미매핑)' 가상 지사는 미매핑 전표를 과목별 [미매핑] 행으로 보여준다
    — 재배정(지사 지정)으로 실제 지사에 귀속시킬 수 있다.
    """
    conn = _conn()
    try:
        runs = _latest_runs(conn, year)
        if not runs:
            raise HTTPException(404, "분석 실행 이력이 없습니다. 먼저 분석을 실행하세요.")

        if branch.endswith(UNMAPPED_SUFFIX):
            raw = branch[:-len(UNMAPPED_SUFFIX)]
            vs = _unmapped_detail(conn, runs).get(raw, [])
            groups = {}
            for v in vs:
                groups.setdefault((v["budget"], v["과목"]), []).append(v)
            attr_map = dbm.load_item_attr_map(conn)
            biz_out = []
            for (budget, item), vv in sorted(groups.items()):
                vouchers = [{k: v[k] for k in
                             ("erp_row_id", "전표번호", "전기일", "텍스트", "금액원", "금액천원")}
                            | {"확신도": None, "과목": v["과목"]} for v in vv]
                vouchers.sort(key=lambda v: -abs(v["금액원"]))
                biz_out.append({
                    "budget": budget, "예산과목": item,
                    "속성": attr_map.get(item), "주관부서명": None,
                    "부서부": vv[0].get("부서부"),
                    "사업명": f"[미매핑] {raw} {item} 전표",
                    "연예산": 0, "연예산원": 0,
                    "실적": round(sum(v["금액천원"] for v in vv)),
                    "실적원": sum(v["금액원"] for v in vv),
                    "구분": "미매핑", "확신도": None,
                    "전표": vouchers,
                })
            items = sorted({b["예산과목"] for b in biz_out})
            present = {str(b["속성"]) for b in biz_out if b["속성"]}
            attrs = [a for a in ("일반", "제조", "건가", "자산") if a in present]
            return _clean_json({"branch": branch, "items": items, "attrs": attrs,
                                "biz": biz_out, "unmapped": True})

        biz_out = []
        for budget, r in runs.items():
            biz = dbm.load_biz_lines(conn, r["id"])
            biz = biz[biz["처지사"] == branch]
            detail = dbm.load_match_detail(conn, r["id"])
            detail = detail[detail["처지사정규"] == branch]
            # 사업별 전표 묶기: 계획행 = 매칭행(행번호) 우선 — 동명 사업 충돌 방지.
            #   신규(계획행 없음)는 '[신규] 사업명' 라벨로 연결.
            by_row, by_label = {}, {}
            for _, v in detail.iterrows():
                rec = {
                    "erp_row_id": int(v["erp_row_id"]),
                    "과목": v["과목정규"],
                    "전표번호": v["전표번호"], "전기일": v["전기일"],
                    "텍스트": v["전표텍스트"],
                    "금액천원": round(v["금액천원"] or 0),
                    "금액원": round(v["금액원"] or 0),
                    "확신도": v["매칭확신도"],
                }
                mrow = v["매칭행"]
                if mrow is not None and not pd.isna(mrow):
                    by_row.setdefault(int(mrow), []).append(rec)
                else:
                    by_label.setdefault((v["과목정규"], v["매칭사업명"]), []).append(rec)
            for i, (_, b) in enumerate(biz.iterrows()):
                label = b["사업명"]
                src = b.get("src_row")
                if src is not None and not pd.isna(src):
                    vouchers = by_row.get(int(src), [])
                else:
                    vouchers = by_label.get((b["예산과목"], label)) \
                        or by_label.get((b["예산과목"], f"[신규] {label}")) or []
                attr = b["속성"]
                if attr is None or (isinstance(attr, float) and attr != attr):
                    attr = None
                vouchers = sorted(vouchers, key=lambda v: -abs(v["금액원"]))
                # 실적 원단위: 귀속 전표의 원단위 정밀 합(전표 있으면), 없으면 천원×1000
                actual_won = sum(v["금액원"] for v in vouchers) if vouchers \
                    else round((b["실적금액"] or 0) * 1000)
                biz_out.append({
                    "budget": budget,
                    "예산과목": b["예산과목"], "속성": attr,
                    "주관부서명": b["주관부서명"], "부서부": b["부서부"],
                    "사업명": label,
                    "연예산": round(b["연예산"] or 0),
                    "연예산원": round((b["연예산"] or 0) * 1000),
                    "실적": round(b["실적금액"] or 0),
                    "실적원": actual_won,
                    "구분": b["구분"], "확신도": b["매칭확신도"],
                    "전표": vouchers,
                })
        # 과목 → 계획 사업 먼저(신규는 뒤) → 실적 큰 순
        biz_out.sort(key=lambda x: (str(x["예산과목"]),
                                    str(x["구분"]).startswith("신규"),
                                    -abs(x["실적"])))
        items = sorted({b["예산과목"] for b in biz_out if b["예산과목"]})
        # 속성은 4종 고정 순서(일반/제조/건가/자산) — 마스터로 정규화됨
        present = {str(b["속성"]) for b in biz_out if b["속성"]}
        attrs = [a for a in ("일반", "제조", "건가", "자산") if a in present]
        attrs += sorted(present - set(attrs))     # 혹시 남은 비표준 값 노출(진단용)
        return _clean_json({"branch": branch, "items": items, "attrs": attrs,
                            "biz": biz_out})
    finally:
        conn.close()


# ── 재배정(오버라이드) ─────────────────────────────────────────────────

class OverrideReq(BaseModel):
    year: str
    budget: str
    erp_row_ids: list[int]
    target_name: str
    target_dept: str | None = None      # 지정 시 그 지사로 이동(타지사·미매핑 지정)
    memo: str | None = None


@app.post("/api/override")
def add_override(req: OverrideReq):
    name = req.target_name.strip()
    if name.startswith("[신규] "):
        name = name[len("[신규] "):]
    if name.startswith("[미매핑] "):
        name = name[len("[미매핑] "):]
    if not name or not req.erp_row_ids:
        raise HTTPException(400, "전표와 대상 사업명을 지정하세요.")
    dept = req.target_dept.strip() if req.target_dept else None
    conn = _conn()
    try:
        _guard_unlocked(conn, req.year, "전표 재배정")
        for rid in req.erp_row_ids:
            dbm.add_override(conn, req.year, req.budget, rid, name, req.memo,
                             target_dept=dept)
        # 학습은 여기서 하지 않는다(사용자 확정) — 설정 탭 [AI 학습] 버튼으로 분리.
        #   수정 중에 학습이 쌓이면 되돌려도 학습에 흔적이 남고, 저장도 느려진다.
        return {"saved": len(req.erp_row_ids),
                "notice": f"저장됨 — 전표 {len(req.erp_row_ids)}건. "
                          "'분석 반영'을 누르면 결과에 적용됩니다."}
    finally:
        conn.close()


@app.get("/api/overrides")
def overrides(year: str):
    conn = _conn()
    try:
        return _clean_json({b: dbm.list_overrides(conn, year, b)
                            for b in ("손익", "자본")})
    finally:
        conn.close()


@app.delete("/api/override/{override_id}")
def delete_override(override_id: int):
    conn = _conn()
    try:
        dbm.delete_override(conn, override_id)
        return {"deleted": override_id}
    finally:
        conn.close()


# ── 통계 (25년 확정 분류체계 기준) ──────────────────────────────────────

@app.get("/api/stats")
def stats(year: str):
    """과목별·지사그룹별 계획 대비 실적 통계(손익/자본)."""
    conn = _conn()
    try:
        runs = _latest_runs(conn, year)
        if not runs:
            return {"budgets": {}}
        dept_cfg = config_store.load_dept_config(CONFIG_DIR, year)
        group_of = {d["이름"]: d["그룹"] for d in dept_cfg}
        out = {}
        for budget, r in runs.items():
            df = dbm.load_biz_lines(conn, r["id"])
            item_cfg = config_store.load_item_config(CONFIG_DIR, year, budget)
            cat_of = {x["과목"]: x["대분류"] for x in item_cfg}
            by_item = {}
            by_group = {}
            for _, row in df.iterrows():
                it = row["예산과목"]
                g = by_item.setdefault(it, {"예산과목": it,
                                            "대분류": cat_of.get(it, "기타"),
                                            "계획": 0, "실적": 0, "집행": 0, "신규": 0,
                                            "사업수": 0, "미시행": 0})
                g["계획"] += row["연예산"] or 0
                g["실적"] += row["실적금액"] or 0
                g["사업수"] += 1
                if row["구분"] == "미시행":
                    g["미시행"] += 1
                elif row["구분"] == "계획집행":
                    g["집행"] += row["실적금액"] or 0
                else:
                    g["신규"] += row["실적금액"] or 0
                grp = group_of.get(row["처지사"], "기타")
                gg = by_group.setdefault(grp, {"그룹": grp, "계획": 0, "실적": 0})
                gg["계획"] += row["연예산"] or 0
                gg["실적"] += row["실적금액"] or 0
            order = ["본사", "중대형CHP", "소형CHP", "DH", "기타"]
            out[budget] = {
                "items": sorted(by_item.values(), key=lambda x: str(x["예산과목"])),
                "groups": sorted(by_group.values(),
                                 key=lambda x: order.index(x["그룹"])
                                 if x["그룹"] in order else 99),
                "summary": runs[budget]["summary"],
            }
        return _clean_json({"budgets": out})
    finally:
        conn.close()


@app.get("/api/stats-compare")
def stats_compare(year: str):
    """전년 대비 증감: 과목별 실적(현재 연도 vs 직전 분석 연도)."""
    conn = _conn()
    try:
        ds_years = sorted({d["year"] for d in dbm.list_datasets(conn)})
        prevs = [y for y in ds_years if y < str(year)]
        prev = None
        for cand in reversed(prevs):
            if _latest_runs(conn, cand):
                prev = cand
                break
        if not prev:
            return {"prev": None, "budgets": {}}

        def _by_item(y):
            out = {}
            for budget, r in _latest_runs(conn, y).items():
                df = dbm.load_biz_lines(conn, r["id"])
                for _, row in df.iterrows():
                    k = (budget, row["예산과목"])
                    g = out.setdefault(k, {"계획": 0, "실적": 0})
                    g["계획"] += row["연예산"] or 0
                    g["실적"] += row["실적금액"] or 0
            return out

        cur, old = _by_item(year), _by_item(prev)
        budgets = {}
        for (budget, item) in sorted(set(cur) | set(old)):
            c = cur.get((budget, item), {"계획": 0, "실적": 0})
            o = old.get((budget, item), {"계획": 0, "실적": 0})
            diff = c["실적"] - o["실적"]
            rate = (diff / o["실적"] * 100) if o["실적"] else None
            budgets.setdefault(budget, []).append({
                "예산과목": item,
                "전년실적": round(o["실적"]), "당년실적": round(c["실적"]),
                "당년계획": round(c["계획"]),
                "증감": round(diff),
                "증감률": None if rate is None else round(rate, 1),
            })
        return _clean_json({"prev": prev, "budgets": budgets})
    finally:
        conn.close()


# ── Excel 내보내기 (분석 실행 시 생성된 산출물 서빙) ─────────────────────

@app.get("/api/export")
def export(year: str, budget: str, kind: str = "actual"):
    names = {
        "actual": f"{year}년 {budget}예산_실적.xlsx",
        "v1": f"zrfm2_{year}_V1({budget}).xlsx",
        "matched": f"matched_{year}_{budget}.csv",
    }
    if kind not in names:
        raise HTTPException(400, "kind는 actual|v1|matched 중 하나여야 합니다.")
    path = os.path.join(OUT_DIR, names[kind])
    conn = _conn()
    try:
        run = dbm.latest_run(conn, year, budget)
        if not run:
            raise HTTPException(404, "분석 이력이 없습니다. 먼저 분석을 실행하세요.")
        # 분석은 속도를 위해 파일을 만들지 않는다 → 없거나 최신 분석보다 오래됐으면 지금 생성.
        stale = (not os.path.exists(path)
                 or _mtime_str(path) < str(run["created_at"]))
        if stale:
            # 파일만 다시 만든다 — 새 실행 이력을 남기면 매 다운로드마다 재생성된다.
            pipeline_db.run_actual_db(conn, CONFIG_DIR, OUT_DIR, year, budget,
                                      make_files=True, record_run=False)
    finally:
        conn.close()
    if not os.path.exists(path):
        raise HTTPException(500, "산출물 생성에 실패했습니다.")
    return FileResponse(path, filename=names[kind])


# ── 팀 v2 앱(예산예측프로그램_팀공유_v2) 연계 산출물 ──────────────────────────
#   json    : 「예산 실적 집계 → 사업 실적 연결」에 올리는 결과 JSON(schemaVersion 1, 천원)
#   matched / budget / data : 연동규격_INTERFACE CSV 계약(연도 단일 파일, 원 단위)
#   손익·자본 최신 분석을 한 번에 담으므로 어느 한쪽 분석이라도 최신 파일보다 새로우면 재생성한다.

@app.get("/api/export-team")
def export_team(year: str, kind: str = "json"):
    if kind not in pipeline_db.TEAM_BUNDLE_FILES:
        raise HTTPException(400, "kind는 json|matched|budget|data 중 하나여야 합니다.")
    path = pipeline_db.team_bundle_paths(OUT_DIR, year)[kind]
    conn = _conn()
    try:
        runs = [dbm.latest_run(conn, year, b) for b in ("손익", "자본")]
        runs = [r for r in runs if r]
        if not runs:
            raise HTTPException(404, "분석 이력이 없습니다. 먼저 손익·자본 분석을 실행하세요.")
        newest = max(str(r["created_at"]) for r in runs)
        stale = (not os.path.exists(path) or _mtime_str(path) < newest)
        if stale:
            pipeline_db.export_team_bundle(conn, CONFIG_DIR, OUT_DIR, year)
    finally:
        conn.close()
    if not os.path.exists(path):
        raise HTTPException(500, "연계 산출물 생성에 실패했습니다.")
    return FileResponse(path, filename=os.path.basename(path))


# ── 모델 레지스트리 · 학습데이터 (ml_registry.py) ─────────────────────────────

@app.get("/api/models")
def models(name: str = None):
    conn = _conn()
    try:
        out = {"models": ml_registry.list_models(conn, name), "names": list(ml_registry.MODEL_NAMES),
               "stats": {n: ml_registry.example_stats(conn, n) for n in ml_registry.MODEL_NAMES}}
        return _clean_json(out)
    finally:
        conn.close()


@app.post("/api/models/{model_id}/activate")
def model_activate(model_id: int, request: Request):
    conn = _conn()
    try:
        if not ml_registry.activate_model(conn, model_id):
            raise HTTPException(404, "모델이 없습니다.")
        return {"ok": True, "operator": _operator(request)}
    finally:
        conn.close()


@app.get("/api/models/{model_id}/download")
def model_download(model_id: int):
    conn = _conn()
    try:
        meta, blob = ml_registry.get_model_blob(conn, model_id=model_id)
    finally:
        conn.close()
    if blob is None:
        raise HTTPException(404, "모델이 없습니다.")
    fname = ml_registry.V2_MODEL_FILES.get(meta["name"], f"{meta['name']}_v{meta['version']}.joblib")
    return Response(blob, media_type="application/octet-stream",
                    headers={"Content-Disposition": f"attachment; filename*=utf-8''{quote(fname)}"})


class TrainReq(BaseModel):
    name: str
    note: str = None


@app.post("/api/train")
def train(req: TrainReq, request: Request):
    if req.name not in ml_registry.MODEL_NAMES:
        raise HTTPException(400, f"모델 이름은 {list(ml_registry.MODEL_NAMES)} 중 하나여야 합니다.")
    conn = _conn()
    try:
        try:
            return _clean_json(ml_registry.train(conn, req.name, actor=_operator(request), note=req.note))
        except ValueError as exc:
            raise HTTPException(400, str(exc))
    finally:
        conn.close()


@app.get("/api/training")
def training(name: str, limit: int = 200, unconfirmed: int = 0):
    conn = _conn()
    try:
        return {"rows": ml_registry.list_examples(conn, name, limit=min(int(limit), 2000),
                                                  only_unconfirmed=bool(unconfirmed)),
                "stats": ml_registry.example_stats(conn, name)}
    finally:
        conn.close()


class ExampleReq(BaseModel):
    name: str
    rows: list                 # [[text, label], …]
    confirmed: bool = True
    source: str = "사람확정"


@app.post("/api/training")
def training_add(req: ExampleReq, request: Request):
    if req.name not in ml_registry.MODEL_NAMES:
        raise HTTPException(400, "모델 이름이 올바르지 않습니다.")
    conn = _conn()
    try:
        return ml_registry.add_examples(conn, req.name, [tuple(r[:2]) for r in req.rows if len(r) >= 2],
                                        source=req.source, actor=_operator(request), confirmed=req.confirmed)
    finally:
        conn.close()


@app.post("/api/training/import")
async def training_import(request: Request, name: str, file: UploadFile = File(...)):
    if name not in ml_registry.MODEL_NAMES:
        raise HTTPException(400, "모델 이름이 올바르지 않습니다.")
    content = await file.read()
    conn = _conn()
    try:
        try:
            return ml_registry.import_csv(conn, name, content, actor=_operator(request))
        except ValueError as exc:
            raise HTTPException(400, str(exc))
    finally:
        conn.close()


class ExampleIdsReq(BaseModel):
    ids: list
    label: str = None


@app.post("/api/training/confirm")
def training_confirm(req: ExampleIdsReq, request: Request):
    conn = _conn()
    try:
        return {"updated": ml_registry.confirm_examples(conn, req.ids, actor=_operator(request), label=req.label)}
    finally:
        conn.close()


@app.post("/api/training/deactivate")
def training_deactivate(req: ExampleIdsReq, request: Request):
    conn = _conn()
    try:
        return {"updated": ml_registry.deactivate_examples(conn, req.ids, actor=_operator(request))}
    finally:
        conn.close()


@app.get("/api/training/export.csv")
def training_export(name: str):
    conn = _conn()
    try:
        csv = ml_registry.export_csv(conn, name)
    finally:
        conn.close()
    return Response(csv.encode("utf-8-sig"), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f"attachment; filename*=utf-8''{quote('training_' + name + '.csv')}"})


# ── 소개·문서 사이트(정적, docs/index.html) — Caddy 없이 단독 실행할 때 /site 로 제공 ──

@app.get("/site")
@app.get("/site/{path:path}")
def site(path: str = "index.html"):
    target = os.path.normpath(os.path.join(SITE_DIR, path or "index.html"))
    if not target.startswith(os.path.normpath(SITE_DIR)) or not os.path.isfile(target):
        raise HTTPException(404, "파일이 없습니다.")
    return FileResponse(target)


# ── Vite 빌드 자산 (해시 파일명 → 장기 캐시 가능) ──────────────────────
if os.path.isdir(os.path.join(STATIC_DIR, "assets")):
    app.mount("/assets", StaticFiles(directory=os.path.join(STATIC_DIR, "assets")), name="assets")
