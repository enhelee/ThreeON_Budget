# -*- coding: utf-8 -*-
"""3·4단계 API — `/api/forecast/*`. `server.py` 가 `make_router(_conn, _clean_json)` 로 붙인다.

Phase 6-6. server.py 는 1,480줄이라 여기에 300줄을 더 얹지 않는다. 라우터 파일 하나로
분리하되 연결·JSON 정리·인증은 server 의 것을 그대로 쓴다(미들웨어가 /api/* 를 지키고
변경 요청을 감사 로그에 남긴다 — 이 파일은 그 아래에 있다).

기준연도(base_year)는 마감 대상이 아니다 — 마감은 분석 연도(2023·2025)의 개념이고
전망 상태는 «어느 해에 세운 가정인가»다. 그래서 마감 가드가 없다.
"""
from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel
import pandas as pd

from . import config_store, forecast_import, forecast_store as fs, pipeline_forecast as pf
from . import db as dbm

# 표 이름(URL) → forecast_store 저장 함수. 여기 없는 이름은 404.
SAVERS = {
    "grades": fs.save_grade_history,
    "methods": fs.save_method_map,
    "overrides": fs.save_overrides,
    "factors": fs.save_factors,
    "hot-parts": fs.save_hot_parts,
    "hq-ratio": fs.save_hq_ratio,
    "hq-temp": fs.save_hq_temp_projects,
    "surprise": fs.save_surprise_projects,
}
# 화면이 빈 표를 보낼 때 열 이름이 필요하다(iterrows 는 안 돌지만 KeyError 를 막기 위해).
EMPTY_COLS = {
    "grades": fs.GRADE_COLS, "methods": fs.METHOD_COLS, "overrides": fs.OVERRIDE_COLS,
    "factors": fs.FACTOR_COLS, "hot-parts": fs.HOT_PARTS_COLS, "hq-ratio": fs.HQ_RATIO_COLS,
    "hq-temp": fs.HQ_TEMP_COLS, "surprise": fs.SURPRISE_COLS,
}
IMPORTERS = {
    "grades": forecast_import.grades_from_workbook,
    "schedule": forecast_import.schedule_from_workbook,
    "hot-parts": forecast_import.hot_parts_from_workbook,
    "hq-master": forecast_import.hq_master_from_workbook,
}


class CopyReq(BaseModel):
    from_year: str
    to_year: str
    overwrite: bool = False


class RowsReq(BaseModel):
    base_year: str
    rows: list = []
    columns: list | None = None        # hq-master 만: 넓은 표의 열 순서
    ratio_rows: list | None = None     # hq-master 만: 같은 양식에서 온 배분비율


def _frame(rows, cols):
    return pd.DataFrame(rows, columns=cols) if not rows else pd.DataFrame(rows)


def make_router(conn_factory, clean_json) -> APIRouter:
    router = APIRouter(prefix="/api/forecast")

    def _state(conn, base_year):
        master = fs.load_hq_master(conn, base_year)
        accounts = {}
        for b in ("손익", "자본"):
            accounts[b] = [x["과목"] for x in config_store.load_item_config(conn, base_year, b)
                           if config_store.to_bool(x.get("포함"), True)]
        return {
            "base_year": str(base_year),
            "sites": pf.forecast_sites(conn, base_year),
            "site_groups": pf.site_groups(conn, base_year),
            "accounts": accounts,
            "grades": pf.records(fs.load_grade_history(conn, base_year)),
            "methods": pf.records(fs.load_method_map(conn, base_year)),
            "overrides": pf.records(fs.load_overrides(conn, base_year)),
            "factors": pf.records(fs.load_factors(conn, base_year)),
            "hot_parts": pf.records(fs.load_hot_parts(conn, base_year)),
            "hq_master": {"columns": [str(c) for c in master.columns], "rows": pf.records(master)},
            "hq_ratio": pf.records(fs.load_hq_ratio(conn, base_year)),
            "hq_temp": pf.records(fs.load_hq_temp_projects(conn, base_year)),
            "surprise": pf.records(fs.load_surprise_projects(conn, base_year)),
        }

    @router.get("/base-years")
    def base_years():
        conn = conn_factory()
        try:
            return {"base_years": fs.list_base_years(conn), "default": pf.default_base_year(conn),
                    "locked_years": sorted(dbm.locked_years(conn))}
        finally:
            conn.close()

    @router.post("/copy-base-year")
    def copy_base_year(req: CopyReq):
        """새 기준연도는 직전 기준연도의 사본으로 시작한다 — 가정은 해마다 조금씩만 바뀐다.
        손댄 대상은 말없이 덮지 않는다(config copy-year 와 같은 409 계약)."""
        if req.from_year == req.to_year:
            raise HTTPException(400, "같은 기준연도로는 복사할 수 없습니다.")
        conn = conn_factory()
        try:
            if not req.overwrite and not fs.base_year_is_untouched(conn, req.to_year):
                raise HTTPException(
                    409, f"{req.to_year}년 기준 전망 가정을 이미 손댔습니다 — 덮어쓰려면 "
                         "overwrite=true 로 다시 요청하세요.")
            fs.copy_base_year(conn, req.from_year, req.to_year)
            return {"to_year": req.to_year, "base_years": fs.list_base_years(conn)}
        finally:
            conn.close()

    @router.get("/state")
    def get_state(base_year: str):
        conn = conn_factory()
        try:
            return clean_json(_state(conn, base_year))
        finally:
            conn.close()

    @router.put("/state/{table}")
    def put_state(table: str, req: RowsReq):
        conn = conn_factory()
        try:
            if table == "hq-master":
                cols = req.columns or [str(c) for c in fs.load_hq_master(conn, req.base_year).columns]
                saved = fs.save_hq_master(conn, req.base_year, pd.DataFrame(req.rows, columns=cols))
                out = {"table": table, "columns": [str(c) for c in saved.columns], "rows": pf.records(saved)}
                if req.ratio_rows is not None:
                    ratio = fs.save_hq_ratio(conn, req.base_year, _frame(req.ratio_rows, fs.HQ_RATIO_COLS))
                    out["ratio_rows"] = pf.records(ratio)
                return clean_json(out)
            if table not in SAVERS:
                raise HTTPException(404, f"모르는 전망 상태 표: {table}")
            saved = SAVERS[table](conn, req.base_year, _frame(req.rows, EMPTY_COLS[table]))
            return clean_json({"table": table, "rows": pf.records(saved)})
        finally:
            conn.close()

    @router.post("/import")
    async def import_preview(kind: str, base_year: str, file: UploadFile = File(...)):
        """엑셀 → 파싱 결과만. 저장은 화면이 미리보기를 확인한 뒤 PUT 으로."""
        if kind not in IMPORTERS:
            raise HTTPException(400, "kind 는 grades·schedule·hot-parts·hq-master 중 하나여야 합니다.")
        data = await file.read()
        conn = conn_factory()
        try:
            sites = pf.forecast_sites(conn, base_year)
        finally:
            conn.close()
        try:
            if kind == "hq-master":
                master, ratio = forecast_import.hq_master_from_workbook(data, sites, int(base_year))
                return clean_json({"kind": kind, "columns": [str(c) for c in master.columns],
                                   "rows": pf.records(master), "ratio_rows": pf.records(ratio)})
            df = IMPORTERS[kind](data, sites)
            return clean_json({"kind": kind, "rows": pf.records(df)})
        except HTTPException:
            raise
        except Exception as e:                       # 깨진 xlsx·다른 양식 — 400 으로 알린다
            raise HTTPException(400, f"엑셀을 읽지 못했습니다: {e}")

    @router.get("/benchmark")
    def benchmark(base_year: str):
        conn = conn_factory()
        try:
            return clean_json(pf.run_benchmark(conn, base_year))
        finally:
            conn.close()

    @router.get("/table")
    def table(base_year: str):
        conn = conn_factory()
        try:
            return clean_json(pf.run_forecast(conn, base_year))
        finally:
            conn.close()

    return router
