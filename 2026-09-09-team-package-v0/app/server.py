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

import glob
import json
import re
from urllib.parse import quote
import pandas as pd
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.gzip import GZipMiddleware

APP_DIR = os.path.dirname(os.path.abspath(__file__))

from budget import auth as authm                      # noqa: E402
authm.load_dotenv_if_present(APP_DIR)                 # .env → 환경변수 (DATABASE_URL·APP_PASSWORD 등)

from budget import api_forecast, config_store, db as dbm, dbcore, ml_registry, pipeline_db   # noqa: E402

OUT_DIR = os.environ.get("OUT_DIR") or os.path.join(APP_DIR, "output")
# 메인 대시보드 헤더에 찍히는 리비전 문자열(.env 또는 배포 플랫폼 환경변수).
# 값을 주지 않으면 "dev" — 화면만 보고 배포본인지 로컬 개발본인지 구분된다.
APP_REV = os.environ.get("APP_REV") or "dev"
# (FORECAST_URL 은 6-6 에서 iframe 과 함께 사라졌다 — 3·4단계는 /api/forecast/* 가 담당한다.)
# 지금 떠 있는 것이 «어느 커밋인가». Render 가 컨테이너에 자동으로 넣어 주는 값이다.
# 배포가 실제로 갈렸는지 확인할 때 이것 하나면 끝난다 — 2026-09-15 에 Caddyfile 만 바뀐
# 배포를 정적 파일 타임스탬프로 판별하려다 헛다리를 짚은 적이 있다(도커 레이어 캐시 때문에
# 타임스탬프가 그대로였다).
APP_COMMIT = (os.environ.get("RENDER_GIT_COMMIT") or os.environ.get("APP_COMMIT") or "")[:7]
# 프론트는 Vite 빌드 산출물(static/) 하나뿐이다. 빌드 전 원본은 web/ 에 있다.
#   로컬:   cd app/web && npm install && npm run build
#   도커:   Dockerfile 의 node 스테이지가 만들어 /srv/app/static/ 으로 넣는다
# 예전 webapp/index.html(단일 149KB)은 web/ 로 쪼개져 삭제되었다. 폴백을 두지 않는 이유는,
# 빌드가 실패했을 때 조용히 옛 화면을 서비스하는 것이 눈에 띄게 실패하는 것보다 나쁘기 때문이다.
STATIC_DIR = os.path.join(APP_DIR, "static")
WEB_DIR = STATIC_DIR
_PARENT = os.path.dirname(APP_DIR)
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


# ⚠ GZip 은 «가장 안쪽»이어야 한다 — 그래서 AuthAudit 보다 먼저 등록한다.
#   add_middleware 는 앞에 끼우므로 나중에 등록한 것이 바깥이다.
#   BaseHTTPMiddleware(AuthAudit·SecurityHeaders)를 거친 응답은 ASGI 수준에서 본문이
#   여러 조각(more_body=True)으로 흐른다. GZipResponder 는 조각이 이어질 때
#   «크기를 알 수 없다»고 보고 minimum_size 를 건너뛰고 무조건 압축한다 —
#   실측: /healthz 같은 100바이트 JSON 도 gzip 으로 나갔다. 안쪽에 두면 본문이 한 덩어리로
#   도착해 임계값이 제대로 걸린다.
app.add_middleware(GZipMiddleware, minimum_size=1024)
app.add_middleware(AuthAuditMiddleware)


# ── Caddy 가 내던 HTTP 속성 (Phase 6-8 에서 앱이 넘겨받았다) ──────────────
# 6-8 에서 Caddy 를 지웠다. 프록시 역할은 uvicorn 이 $PORT 를 직접 열면서 사라지지만,
# Caddyfile 의 `header {}` 와 `encode gzip` 이 하던 일은 **없어지면 조용하다** —
# 화면은 그대로 뜨고 보안 헤더만 사라진다. 그래서 여기로 옮기고 테스트로 고정했다
# (tests/test_http_hardening.py).
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "SAMEORIGIN",
    "Referrer-Policy": "strict-origin-when-cross-origin",
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        for k, v in SECURITY_HEADERS.items():
            response.headers.setdefault(k, v)   # 라우트가 직접 정한 값이 있으면 그것을 존중
        return response


# 바깥부터: SecurityHeaders → AuthAudit → GZip. 보안 헤더는 감사 미들웨어가 만든
# 응답에도 붙어야 하므로 가장 바깥이다.
app.add_middleware(SecurityHeadersMiddleware)


# ── 인증 (공용 비밀번호 + 작업자 이름) ─────────────────────────────────────

class LoginReq(BaseModel):
    password: str
    name: str


@app.get("/healthz")
def healthz():
    return {"ok": True, "auth": AUTH.enabled, "rev": APP_REV, "commit": APP_COMMIT,
            "db": "postgresql" if dbcore.is_postgres_url(dbcore.database_url()) else "sqlite"}


@app.get("/api/auth/status")
def auth_status(request: Request):
    op = AUTH.verify(request.cookies.get(AUTH.cookie_name)) if AUTH.enabled else "local"
    return {"enabled": AUTH.enabled, "operator": op, "logged_in": bool(op)}


@app.get("/api/auth/verify")
def auth_verify():
    """Caddy forward_auth 전용 - 로그인했으면 204, 아니면 401.

    /api/auth/status 를 쓸 수 없는 이유: 그 라우트는 비로그인 상태에서도 200 에
    {"logged_in": false} 를 실어 보낸다(SPA 가 게이트를 띄울지 판단하는 근거다).
    forward_auth 는 2xx 를 곧 통과로 보므로, 그것을 대상으로 삼으면 /forecast 가
    누구에게나 열린다.

    이 라우트는 PUBLIC_API 에 넣지 않는다 - 세션이 없으면 AuthAuditMiddleware 가
    먼저 401 을 돌려주고 여기까지 오지 않는다. 인증이 꺼진 사내망 모드에서는
    미들웨어가 통과시키므로 204 가 되어 /forecast 도 함께 열린다.
    """
    return Response(status_code=204)


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
    # ⚠ index.html 은 매번 서버에 물어봐야 한다.
    #   자산(/assets/*)은 파일명에 해시가 붙어 영구 캐시가 안전하지만, 그 파일명을 «가리키는»
    #   것이 index.html 이다. 이 파일이 캐시에 묶이면 브라우저가 옛 자바스크립트를 계속
    #   가리키게 되고, 서버에 새 코드를 올려도 사용자 화면은 바뀌지 않는다.
    #
    #   실측(2026-09-15 배포): 서버 번들에는 수정이 들어 있는데(assets/index-BRwYOFCn.js)
    #   화면은 옛 동작 그대로였다. 응답에 Cache-Control 이 아예 없어 브라우저가 자체
    #   판단으로 캐시한 결과였다.
    #
    #   no-cache = "저장은 하되 쓰기 전에 반드시 확인" — 안 바뀌었으면 304 라 비용도 거의 없다.
    return FileResponse(page, headers={"Cache-Control": "no-cache"})


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
async def upload_master(kind: str, year: str, file: UploadFile = File(...)):
    """기준정보 마스터 갱신: kind=item(예산과목) | dept(부서코드).

    ⚠ 연도가 필수다. 마스터는 «그 해의 기준표»이고, 연도 없이 넣으면
      아무도 읽지 않는 행이 쌓인다(조회는 전부 연도로 건다).
    """
    if kind not in ("item", "dept"):
        raise HTTPException(400, "kind는 item(예산과목) 또는 dept(부서코드)여야 합니다.")
    fd, tmp = tempfile.mkstemp(suffix=".xlsx")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(await file.read())
        conn = _conn()
        try:
            _guard_unlocked(conn, year, "마스터 갱신")
            n = (dbm.ingest_item_master(conn, tmp, year) if kind == "item"
                 else dbm.ingest_dept_master(conn, tmp, year))
            return {"rows": n, "master": dbm.master_stats(conn, year),
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
                conn, OUT_DIR, req.year, budget, new_policy=req.policy,
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
        item_alias = config_store.load_item_alias(conn)
        from budget import normalize as _norm
        items_cfg = {}
        for b in ("손익", "자본"):
            cfg = config_store.load_item_config(conn, year, b)
            items_cfg[b] = [_norm.normalize_item(x["과목"], item_alias) for x in cfg
                            if config_store.to_bool(x.get("포함"), True)
                            and config_store.to_bool(x.get("실적반영"), True)]
        return _clean_json({
            "year": year, "years": years,
            "datasets": ds[:10],
            "locked": dbm.is_locked(conn, year),
            "locks": dbm.locked_years(conn),
            # 열린 연도는 보고 있는 연도와 무관하게 알려야 한다 — 전 화면 배너의 근거
            "lock_state": dbm.open_years(conn),
            "master": dbm.master_stats(conn, year),
            "items": items_cfg,
            "runs": {b: {"created_at": r["created_at"], "summary": r["summary"]}
                     for b, r in runs.items()},
        })
    finally:
        conn.close()


# ── 연도별 기준정보(구성·별칭·마스터) ──────────────────────────────────
#   구성은 «그 해의 기준»이다. 조회는 연도를 받아 없으면 시드를 심어 돌려주고,
#   저장은 그 해 한 벌을 통째로 갈아 끼운다. 마감된 연도는 기준도 못 고친다 —
#   과거 분석 결과가 조용히 바뀌는 것을 막는 의도된 마찰이다.

class DeptCfgReq(BaseModel):
    year: str
    rows: list


class ItemCfgReq(BaseModel):
    year: str
    budget: str
    rows: list


class AliasReq(BaseModel):
    종류: str
    rows: dict


class CopyYearReq(BaseModel):
    from_year: str
    to_year: str
    overwrite: bool = False


@app.get("/api/config/depts")
def get_dept_config(year: str):
    conn = _conn()
    try:
        return _clean_json({"year": year,
                            "rows": config_store.load_dept_config(conn, year),
                            "groups": config_store.DEPT_GROUPS,
                            "locked": dbm.is_locked(conn, year)})
    finally:
        conn.close()


@app.put("/api/config/depts")
def put_dept_config(req: DeptCfgReq):
    conn = _conn()
    try:
        _guard_unlocked(conn, req.year, "기준정보 변경")
        rows = config_store.save_dept_config(conn, req.year, req.rows)
        return _clean_json({"year": req.year, "rows": rows})
    finally:
        conn.close()


@app.get("/api/config/items")
def get_item_config(year: str, budget: str):
    conn = _conn()
    try:
        return _clean_json({"year": year, "budget": budget,
                            "rows": config_store.load_item_config(conn, year, budget),
                            "locked": dbm.is_locked(conn, year)})
    finally:
        conn.close()


@app.put("/api/config/items")
def put_item_config(req: ItemCfgReq):
    if req.budget not in ("손익", "자본"):
        raise HTTPException(400, "budget은 손익 또는 자본이어야 합니다.")
    conn = _conn()
    try:
        _guard_unlocked(conn, req.year, "기준정보 변경")
        rows = config_store.save_item_config(conn, req.year, req.budget, req.rows)
        return _clean_json({"year": req.year, "budget": req.budget, "rows": rows})
    finally:
        conn.close()


@app.get("/api/config/alias")
def get_alias():
    """별칭은 연도 축이 없다 — 오래된 표기가 몇 년 뒤 자료에 다시 나타난다.

    seeded 는 코드 시드에서 온 열쇠들이다. 읽을 때마다 시드를 병합하므로 이들은
    지워도 되살아난다 — 화면은 이 목록을 보고 해당 행을 잠근다(사용자 결정
    2026-09-19). 지울 수 있는 것처럼 보여 놓고 되살아나는 쪽이 더 나쁘다.
    """
    conn = _conn()
    try:
        return _clean_json({"item": config_store.load_item_alias(conn),
                            "dept": config_store.load_dept_alias(conn),
                            "seeded": {"item": sorted(config_store.seed_item_alias()),
                                       "dept": sorted(config_store.seed_dept_alias())}})
    finally:
        conn.close()


@app.put("/api/config/alias")
def put_alias(req: AliasReq):
    if req.종류 not in ("item", "dept"):
        raise HTTPException(400, "종류는 item(예산과목) 또는 dept(처지사)여야 합니다.")
    conn = _conn()
    try:
        return _clean_json({"종류": req.종류,
                            "rows": config_store.save_alias(conn, req.종류, req.rows)})
    finally:
        conn.close()


@app.get("/api/master/items")
def get_item_master(year: str):
    conn = _conn()
    try:
        return _clean_json({"year": year, "rows": dbm.list_item_master(conn, year)})
    finally:
        conn.close()


@app.get("/api/master/depts")
def get_dept_master(year: str):
    conn = _conn()
    try:
        return _clean_json({"year": year, "rows": dbm.list_dept_master(conn, year)})
    finally:
        conn.close()


def _year_config_is_untouched(conn, year):
    """그 해 구성이 «읽을 때 자동으로 심긴 시드» 그대로인가.

    설정 화면을 여는 것만으로 그 해 구성이 심긴다. 사람이 손대지 않은 그 상태까지
    «이미 있음»으로 보고 복사를 막으면, 화면을 한 번 열었다는 이유만으로 연도 복사가
    영영 막힌다 — 실측으로 걸린 길이다. 마스터가 올라와 있으면 손댄 것으로 본다.
    """
    # master_stats 는 «그 해 분석이 실제로 쓰는» 마스터를 세므로 과거 연도로 물러선다.
    # 여기서 묻는 것은 «이 해에 사람이 올린 것이 있는가» 라 그 해 것만 봐야 한다.
    if dbm.list_item_master(conn, year) or dbm.list_dept_master(conn, year):
        return False
    if config_store.load_dept_config(conn, year) != config_store.seed_dept_config(year):
        return False
    return all(config_store.load_item_config(conn, year, b)
               == config_store.seed_item_config(year, b) for b in ("손익", "자본"))


@app.post("/api/config/copy-year")
def copy_year(req: CopyYearReq):
    """새 연도는 직전 연도를 복사해 시작한다 — 매년 조금씩만 바뀌기 때문이다."""
    if req.from_year == req.to_year:
        raise HTTPException(400, "같은 연도로는 복사할 수 없습니다.")
    conn = _conn()
    try:
        _guard_unlocked(conn, req.to_year, "기준정보 복사")
        # 손댄 연도를 말없이 덮어쓰지 않는다. 「＋연도」가 실수로 기존 연도를
        # 가리켰을 때 공들여 맞춘 구성이 사라지는 길을 막는 것이다.
        if not req.overwrite and not _year_config_is_untouched(conn, req.to_year):
            raise HTTPException(
                409, f"{req.to_year}년 기준정보를 이미 손댔습니다 — 덮어쓰려면 "
                     "overwrite=true 로 다시 요청하세요.")
        config_store.save_dept_config(
            conn, req.to_year, config_store.load_dept_config(conn, req.from_year))
        for b in ("손익", "자본"):
            config_store.save_item_config(
                conn, req.to_year, b,
                config_store.load_item_config(conn, req.from_year, b))
        dbm.copy_masters(conn, req.from_year, req.to_year)
        return {"copied": {"from": req.from_year, "to": req.to_year},
                "master": dbm.master_stats(conn, req.to_year)}
    finally:
        conn.close()


# ── 연도 마감(잠금) ────────────────────────────────────────────────────

class LockReq(BaseModel):
    year: str


class UnlockReq(BaseModel):
    reason: str


@app.post("/api/lock")
def lock(req: LockReq):
    conn = _conn()
    try:
        # 열려 있던 구간이면 그 사이 무엇이 바뀌었는지 먼저 센다 —
        # lock_year 가 해제 기록을 닫아 버리므로 순서가 중요하다.
        since = dbm.lock_state(conn, req.year).get("unlocked_at")
        changes = dbm.changes_since(conn, req.year, since) if since else {}
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
        summary = " · ".join(f"{k} {v}건" for k, v in changes.items())
        return {"locked": req.year, "snapshot": copied, "changes": changes,
                "notice": f"{req.year}년 마감 완료 — 업로드·분석·재배정·수정이 차단되고 "
                          f"산출물 {copied}종을 output/마감/{req.year}/에 보관했습니다. "
                          "(조회·통계·Excel 내보내기는 계속 가능)"
                          + (f" 열린 동안 바뀐 것: {summary}." if summary else "")}
    finally:
        conn.close()


@app.delete("/api/lock/{year}")
def unlock(year: str, req: UnlockReq, request: Request):
    """마감 해제 — 사유를 반드시 받는다.

    마감된 연도의 숫자는 대외 보고에 쓰인 값이다. 버튼 한 번으로 열리면 열린 줄
    모르고 며칠이 지나간다. 사유를 남겨야 나중에 «왜 2023년 숫자가 달라졌지»에
    답할 수 있다.
    """
    reason = (req.reason or "").strip()
    if not reason:
        raise HTTPException(400, "해제 사유를 입력하세요. 변경 이력에 기록됩니다.")
    conn = _conn()
    try:
        dbm.unlock_year(conn, year, reason, getattr(request.state, "operator", None))
        return {"unlocked": year, "reason": reason}
    finally:
        conn.close()


@app.get("/api/lock-state")
def get_lock_state(year: str = None):
    """year 를 주면 그 해 상태, 안 주면 «열려 있는 연도 전부».

    후자는 전 화면 배너용이다. 배너는 어느 화면에서나 떠야 하는데 /api/status 는
    일부 화면에서만 불린다 — 연도마다 한 번씩 묻지 않도록 한 번에 돌려준다.
    """
    conn = _conn()
    try:
        if year is None:
            return _clean_json({"open": dbm.open_years(conn)})
        return _clean_json(dbm.lock_state(conn, year))
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


@app.get("/api/export-status")
def export_status(year: str = None):
    """메인 대시보드 '이음새' 박스용 - 팀 연계 산출물을 마지막으로 넘긴 연도와 시각.

    /api/export-team 은 GET 이라 audit_log 에 남지 않는다(감사 기록은 변경 요청만 남긴다).
    그래서 '언제 넘겼는가'는 OUT_DIR 에 떨어진 파일의 수정시각으로 읽는다 -
    파일 자체가 산출물이므로 이것이 사실에 가장 가깝다.

    반환: {"last": {"year","at"} | None, "exports": [...], (year 지정 시) "files": {kind: at|None}}
    """
    tmpl = pipeline_db.TEAM_BUNDLE_FILES["json"]
    pre, post = tmpl.split("{y}")
    pat = re.compile(re.escape(pre) + r"(\d{4})" + re.escape(post) + "$")
    hits = []
    for path in glob.glob(os.path.join(OUT_DIR, tmpl.format(y="*"))):
        m = pat.match(os.path.basename(path))
        if m:
            hits.append({"year": m.group(1), "at": _mtime_str(path)})
    hits.sort(key=lambda h: h["at"])
    out = {"last": hits[-1] if hits else None, "exports": hits}
    if year:
        out["year"] = str(year)
        out["files"] = {k: (_mtime_str(f) if os.path.exists(f) else None)
                        for k, f in pipeline_db.team_bundle_paths(OUT_DIR, str(year)).items()}
    return out


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
        # 구성·별칭·마스터 변경도 «결과에 반영되지 않은 변경»이다. 알림을 두 갈래로
        # 나누면 어느 것을 눌러야 하는지 헷갈리므로 같은 배지에 합친다.
        n = sum(dbm.config_changes_since(conn, year, base).values())
        if n:
            out["counts"]["기준정보"] = n
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
            attr_map = dbm.load_item_attr_map(conn, year)
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
        dept_cfg = config_store.load_dept_config(conn, year)
        group_of = {d["이름"]: d["그룹"] for d in dept_cfg}
        out = {}
        for budget, r in runs.items():
            df = dbm.load_biz_lines(conn, r["id"])
            item_cfg = config_store.load_item_config(conn, year, budget)
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
            pipeline_db.run_actual_db(conn, OUT_DIR, year, budget,
                                      make_files=True, record_run=False)
    finally:
        conn.close()
    if not os.path.exists(path):
        raise HTTPException(500, "산출물 생성에 실패했습니다.")
    return FileResponse(path, filename=names[kind])


# ── 팀 연계 산출물 (docs/연계계약_CONTRACT.md §3.4) ─────────────────────────
#   json    : 결과 JSON(schemaVersion 1, 천원). 원래 동료 전망 앱(v2)에 올리던 파일 — v2 는
#             6-8 에서 이 앱에 흡수·삭제되어 지금 소비자는 없다. 외부 도구·감사용으로 유지.
#   matched / budget / data : CSV 계약(연도 단일 파일, 원 단위)
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
            pipeline_db.export_team_bundle(conn, OUT_DIR, year)
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


# ── 3·4단계(표준화·중장기 전망) API — src/budget/api_forecast.py ────────
# server.py 를 더 키우지 않으려고 라우터 파일로 분리했다. 연결·JSON 정리는 이 파일 것을 넘긴다.
app.include_router(api_forecast.make_router(_conn, _clean_json))

# ── Vite 빌드 자산 (해시 파일명 → 장기 캐시 가능) ──────────────────────
class ImmutableStaticFiles(StaticFiles):
    """Caddy 의 `handle /assets/*` 캐시 헤더 자리 (6-8).

    파일명에 내용 해시가 붙으므로 «영원히 캐시해도 안전»하다. 내용이 바뀌면 파일명이
    바뀌고, 그 파일명을 가리키는 index.html 은 no-cache 라 매번 재검증된다(index() 주석).
    """
    def file_response(self, *args, **kwargs):
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response


# check_dir=False — 빌드 전(static/ 없음)에도 import 가 죽지 않게. 없으면 그냥 404 다.
app.mount("/assets", ImmutableStaticFiles(directory=os.path.join(STATIC_DIR, "assets"),
                                          check_dir=False), name="assets")
