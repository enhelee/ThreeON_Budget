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

import pandas as pd
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from budget import config_store, db as dbm, pipeline_db

APP_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_DIR = os.path.join(APP_DIR, "config")
OUT_DIR = os.path.join(APP_DIR, "output")
WEB_DIR = os.path.join(APP_DIR, "webapp")

app = FastAPI(title="예산·실적 분석", docs_url=None, redoc_url=None)


def _conn():
    return dbm.connect()


def _guard_unlocked(conn, year, action="변경"):
    """마감(잠금)된 연도의 데이터 변경 차단."""
    if dbm.is_locked(conn, year):
        raise HTTPException(
            423, f"{year}년은 마감(잠금) 상태입니다 — {action}이(가) 차단됩니다. "
                 "설정 탭에서 잠금을 해제한 뒤 진행하세요.")


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
    return FileResponse(os.path.join(WEB_DIR, "index.html"))


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
    """손익·자본 모두 실행(25년 확정 분류체계 시드 사용)."""
    conn = _conn()
    try:
        _guard_unlocked(conn, req.year, "분석 실행")
        out = {}
        for budget in ("손익", "자본"):
            res = pipeline_db.run_actual_db(
                conn, CONFIG_DIR, OUT_DIR, req.year, budget, new_policy=req.policy)
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
    allowed = {"사업명", "속성", "주관부서명", "부서부", "처지사", "연예산"}
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
        # 사람이 확정한 재배정은 저장 즉시 학습 DB에도 자동 축적(수동확정)
        learned = dbm.learn_from_override(conn, req.year, req.budget,
                                          req.erp_row_ids, name)
        return {"saved": len(req.erp_row_ids), "learned": learned,
                "notice": "재배정 저장 + 학습 완료"}
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
    if not os.path.exists(path):
        raise HTTPException(404, "산출물이 없습니다. 먼저 분석을 실행하세요.")
    return FileResponse(path, filename=names[kind])
