# -*- coding: utf-8 -*-
"""3·4단계 API — `/api/forecast/*`. `server.py` 가 `make_router(_conn, _clean_json)` 로 붙인다.

Phase 6-6. server.py 는 1,480줄이라 여기에 300줄을 더 얹지 않는다. 라우터 파일 하나로
분리하되 연결·JSON 정리·인증은 server 의 것을 그대로 쓴다(미들웨어가 /api/* 를 지키고
변경 요청을 감사 로그에 남긴다 — 이 파일은 그 아래에 있다).

기준연도(base_year)는 마감 대상이 아니다 — 마감은 분석 연도(2023·2025)의 개념이고
전망 상태는 «어느 해에 세운 가정인가»다. 그래서 마감 가드가 없다.
"""
import time
from urllib.parse import quote

from fastapi import APIRouter, File, HTTPException, Response, UploadFile
from pydantic import BaseModel
import pandas as pd

from . import config_store, forecast_backtest, forecast_calc, forecast_export, forecast_import, forecast_reference
from . import forecast_store as fs, pipeline_forecast as pf
from . import benchmark as bm, db as dbm, uploads, viewcache

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

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
# 표준화 방향 반영 표(2026-10-26) — URL 이름 → forecast_store.SPECS 이름. 참고 엑셀 표 둘은
# 가져오기로만 채운다(손으로 고치는 값이 아니라 대조 기준이라서).
SPEC_TABLES = {"site-history": "site_history", "site-event": "site_event", "site-grade-eq": "site_grade_eq",
               "benchmark-rule": "benchmark_rule", "actual-tag": "actual_tag",
               "regular-contract": "regular_contract", "cri-rule": "cri_rule", "investment-plan": "investment_plan",
               "site-capacity": "site_capacity", "capacity-rule": "capacity_rule",
               "hot-parts-contract": "hot_parts_contract"}
IMPORTERS = {
    "grades": forecast_import.grades_from_workbook,
    "schedule": forecast_import.schedule_from_workbook,
    "hot-parts": forecast_import.hot_parts_from_workbook,
    "hq-master": forecast_import.hq_master_from_workbook,
}


class GradePlanReq(BaseModel):
    base_year: str
    cells: list = []


class CopyReq(BaseModel):
    from_year: str
    to_year: str
    overwrite: bool = False


class SettingsReq(BaseModel):
    base_year: str
    values: dict = {}


class RowsReq(BaseModel):
    base_year: str
    rows: list = []
    columns: list | None = None        # hq-master 만: 넓은 표의 열 순서
    ratio_rows: list | None = None     # hq-master 만: 같은 양식에서 온 배분비율


def _frame(rows, cols):
    return pd.DataFrame(rows, columns=cols) if not rows else pd.DataFrame(rows)


# ── 표준화·전망 결과 캐시 ────────────────────────────────────────────────
# 전망 표는 계산이 무겁다(운영 첫 계산 수십 초 — Render 무료 CPU). 입력(마감 실적·전망 가정·구성)이
# 바뀌지 않았으면 같은 답이므로 저장해 두고 다시 쓴다. 규칙(버전·유효 시간·동시 계산 막기)은 viewcache.py.
# 키는 계산 «전»에 읽는다 — 계산 중 들어온 쓰기는 다음 요청이 반영한다.
VIEW_CACHE_TTL = viewcache.TTL


def _data_version(conn):
    return viewcache.data_version(conn)


def _cached_view(kind, conn, base_year, compute):
    return viewcache.get_or_compute(("forecast", kind, str(base_year)), _data_version(conn), compute,
                                    ttl=VIEW_CACHE_TTL)


def standard_rows(conn, base_year=None) -> dict:
    """표준화 결과(화면과 같은 캐시) — 챗봇 근거 답·엑셀이 쓴다."""
    by = base_year or pf.default_base_year(conn)
    out = _cached_view("benchmark", conn, by, lambda: clean_json(pf.run_benchmark(conn, by)))
    return {"base_year": str(by), "rows": out.get("rows") or []}


STANDARD_XLSX_COLS = ["사업장", "구분", "예산과목", "등급", "표준금액", "산출방식", "방식출처", "추천사유", "비고", "근거",
                      "재무팀금액", "재무팀대비"]


def standard_xlsx(rows) -> bytes:
    import io
    from openpyxl import Workbook
    from openpyxl.styles import Font
    wb = Workbook()
    ws = wb.active
    ws.title = "표준금액 근거"
    ws.append([c if c != "표준금액" else "표준금액(천원)" for c in STANDARD_XLSX_COLS])
    for c in ws[1]:
        c.font = Font(bold=True)
    for r in rows:
        ws.append([r.get(c) for c in STANDARD_XLSX_COLS])
    for col, w in zip("ABCDEFGHIJKL", (12, 6, 28, 8, 14, 14, 10, 40, 30, 40, 14, 10)):
        ws.column_dimensions[col].width = w
    for row in ws.iter_rows(min_row=2, min_col=5, max_col=5):
        row[0].number_format = "#,##0"
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


_HOT_NOTES = None


def _hot_notes():
    """내장 고온부품 양식의 «(작성 기준)» — 계약단가·물가·관세·운전시간 가정(한 번 읽어 둔다)."""
    global _HOT_NOTES
    if _HOT_NOTES is None:
        _HOT_NOTES = forecast_import.hot_parts_notes(open(forecast_import.HOT_TEMPLATE, "rb").read())
    return _HOT_NOTES


def build_state(conn, base_year):
    """5번 «기준정보(가정)» 한 벌 — 상태 표 20여 개·구성·지사 목록. 표마다 모양이 달라 한 질의로 못 합친다(질의 ~25번,
    운영 DB 1.75초 · 2026-10-27). 그래서 화면은 캐시(get_state)로 받고, 참고 엑셀 건수 둘만 한 질의로 묶었다."""
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
        **{name: pf.records(fs.load_table(conn, base_year, name)) for name in SPEC_TABLES.values()},
        "reference": dict(zip(("reference_actual", "reference_standard"), (int(v or 0) for v in conn.execute(
            "SELECT (SELECT COUNT(*) FROM reference_actual WHERE base_year=?),"
            " (SELECT COUNT(*) FROM reference_standard WHERE base_year=?)",
            (str(base_year), str(base_year))).fetchone()))),
        "settings": fs.load_settings(conn, base_year),
        "options": {"rule_methods": bm.RULE_METHODS, "event_types": fs.EVENT_TYPES,
                    "tag_types": fs.TAG_TYPES, "contract_items": fs.CONTRACT_ITEMS,
                    "factor_scopes": fs.FACTOR_SCOPES, "groups": ["중대형CHP", "소형CHP", "DH", "본사"],
                    "hot_parts_notes": _hot_notes()},
    }


def warm(conn, clean_json):
    """기본 기준연도의 전망 표·표준화·정기비용 분리를 미리 계산해 캐시에 채운다(이미 있으면 바로 끝).
    server 의 예열 스레드가 배포 직후와 자료가 바뀐 뒤 부른다 — 사용자가 첫 계산(운영 수십 초)을 맞지 않게."""
    by = str(pf.default_base_year(conn))
    for kind, fn in (("state", build_state), ("table", pf.run_forecast), ("benchmark", pf.run_benchmark),
                     ("regular", pf.regular_breakdown)):
        _cached_view(kind, conn, by, lambda fn=fn: clean_json(fn(conn, by)))
    return by


def make_router(conn_factory, clean_json) -> APIRouter:
    router = APIRouter(prefix="/api/forecast")

    _state = build_state

    @router.get("/base-years")
    def base_years():
        conn = conn_factory()
        try:
            years = fs.list_base_years(conn)
            return {"base_years": years, "default": pf.default_base_year(conn, years),
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

    # 조회 셋(state·benchmark·table)은 base_year 를 비우면 서버가 기본 기준연도(/base-years 의
    # default 와 같은 함수)를 쓴다. 화면이 첫 진입에 «기준연도 → 가정 → 표»를 차례로 기다리지 않고
    # 셋을 동시에 부를 수 있게 하려는 것이다(운영 실측 2026-10-15: 2.0 + 1.5 + 6.2초 순차 = 탭 10초).
    # 응답마다 base_year 가 실려 화면이 어느 해로 계산됐는지 안다.
    def _base(conn, base_year):
        return base_year or pf.default_base_year(conn)

    @router.get("/state")
    def get_state(base_year: str = None):
        conn = conn_factory()
        try:
            by = _base(conn, base_year)
            # 가정 한 벌은 질의 ~25번이라 캐시한다 — 가정·구성·업로드 저장(감사 로그)이 있으면 다시 읽는다.
            #   (읽기가 팩터 시드를 심는 첫 회는 캐시 전 계산에서 한 번만 일어난다.)
            return _cached_view("state", conn, by, lambda: clean_json(_state(conn, by)))
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
            if table in SPEC_TABLES:
                name = SPEC_TABLES[table]
                saved = fs.save_table(conn, req.base_year, name, _frame(req.rows, fs.SPECS[name]["cols"]))
                return clean_json({"table": table, "rows": pf.records(saved)})
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
        data = await uploads.read_upload(file)
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
            if kind == "schedule":
                # 정비등급 양식(한 해 한 열)이면 설비별 등급도 같이 — 화면이 site_grade_eq 의 미래 줄로 넣는다
                df, units = forecast_import.grade_plan_from_workbook(data, sites)
                if df.empty:
                    df = IMPORTERS[kind](data, sites)
                return clean_json({"kind": kind, "rows": pf.records(df), "eq_rows": pf.records(units)})
            df = IMPORTERS[kind](data, sites)
            if kind == "hot-parts":
                # 계약방식·계약기간도 같이 — 화면이 고온부품 표 지사 칸에 그대로 보인다
                return clean_json({"kind": kind, "rows": pf.records(df),
                                   "contract_rows": pf.records(forecast_import.hot_parts_contracts_from_workbook(data, sites))})
            return clean_json({"kind": kind, "rows": pf.records(df)})
        except HTTPException:
            raise
        except Exception as e:                       # 깨진 xlsx·다른 양식 — 400 으로 알린다
            raise HTTPException(400, f"엑셀을 읽지 못했습니다: {e}")

    @router.post("/reference")
    async def reference_import(base_year: str, apply: bool = False, file: UploadFile = File(...)):
        """참고 엑셀(예산표준화 V3 양식) — apply=false 면 미리보기(건수·표본), true 면 저장.

        저장하는 것: 참고 실적·표준금액(대조 기준), 설비별·대표 정비등급, 산정 규칙(엑셀 수식 해석),
        지사 연혁(그룹 시트 수식), CRI 규칙 초안, LTSA 정기계약 초안(최근 실적 유지 가정).
        그 기준연도의 해당 표는 통째로 바뀐다 — 다른 기준연도는 그대로다."""
        data = await uploads.read_upload(file)
        conn = conn_factory()
        try:
            sites = pf.forecast_sites(conn, base_year)
            try:
                parsed = forecast_reference.parse_reference(data, sites)
            except Exception as e:
                raise HTTPException(400, f"엑셀을 읽지 못했습니다: {e}")
            counts = forecast_reference.preview_counts(parsed)
            if not apply:
                sample = {k: v[:30] for k, v in parsed.items() if isinstance(v, list) and k != "warnings"}
                return clean_json({"counts": counts, "warnings": parsed["warnings"], "sample": sample})
            if not parsed["reference_standard"] and not parsed["reference_actual"]:
                raise HTTPException(400, "이 파일에서 지사 시트를 찾지 못했습니다 — 시트명이 지사 이름(예: 화성)인지 확인하세요.")
            frames = forecast_reference.to_frames(parsed)
            for name in ("reference_actual", "reference_standard", "site_grade_eq", "benchmark_rule",
                         "site_history", "cri_rule"):
                fs.save_table(conn, base_year, name, frames[name] if not frames[name].empty
                              else pd.DataFrame(columns=fs.SPECS[name]["cols"]))
            fs.save_grade_history(conn, base_year, frames["site_grade"] if not frames["site_grade"].empty
                                  else pd.DataFrame(columns=fs.GRADE_COLS))
            plan = forecast_reference.contract_plan(parsed["regular_contract"], int(base_year))
            fs.save_table(conn, base_year, "regular_contract",
                          pd.DataFrame(plan, columns=fs.SPECS["regular_contract"]["cols"]))
            counts["regular_contract"] = len(plan)
            return clean_json({"applied": True, "counts": counts, "warnings": parsed["warnings"]})
        finally:
            conn.close()

    @router.put("/settings")
    def put_settings(req: SettingsReq):
        conn = conn_factory()
        try:
            return clean_json({"settings": fs.save_settings(conn, req.base_year, req.values)})
        finally:
            conn.close()

    @router.get("/backtest")
    def backtest(base_year: str = None):
        """학습 기간별 백테스트(제안 ⑤) — 과목 합계·지사 3년 누적·칸별 오차와 A급정비 일정 적중."""
        conn = conn_factory()
        try:
            by = _base(conn, base_year)

            def compute():
                fs.bind_site_resolvers(conn, by)
                actuals, locked, ref_years = pf.actuals_with_reference(conn, by)
                runs = forecast_backtest.compare_windows(
                    actuals, forecast_calc.canon_grades(fs.load_grade_history(conn, by)), (2, 3, 5, 10),
                    fs.load_table(conn, by, "site_grade_eq"), pf.site_groups(conn, by))
                return clean_json({"base_year": str(by), "window": fs.learning_window(conn, by),
                                   "sources": {"마감": locked, "참고": ref_years}, "runs": runs})
            return _cached_view("backtest", conn, by, compute)
        finally:
            conn.close()

    @router.get("/compare")
    def compare(base_year: str = None):
        conn = conn_factory()
        try:
            by = _base(conn, base_year)
            return _cached_view("compare", conn, by, lambda: clean_json(pf.compare_reference(conn, by)))
        finally:
            conn.close()

    @router.get("/standard.xlsx")
    def standard_download(base_year: str = None, site: str = None, account: str = None, grade: str = None):
        """표준금액 근거 엑셀 — 챗봇 «엑셀로 받기». 지사·과목·등급으로 거른다(빈 칸 = 전부)."""
        conn = conn_factory()
        try:
            data = standard_rows(conn, base_year)
        finally:
            conn.close()
        g = (grade or "").lower()
        rows = [r for r in data["rows"] if (not site or r["사업장"] == site) and (not account or r["예산과목"] == account)
                and (not g or str(r["등급"]).lower() == g)]
        name = f"표준금액_근거_{data['base_year']}년{'_' + site if site else ''}.xlsx"
        return Response(standard_xlsx(rows), media_type=XLSX,
                        headers={"Content-Disposition": f"attachment; filename*=utf-8''{quote(name)}"})

    @router.get("/grade-plan")
    def grade_plan(base_year: str = None):
        """정비등급 화면 — 엑셀 양식(발전설비·DH, 지사·설비 줄) 그대로의 기준연도~ 10년 표."""
        conn = conn_factory()
        try:
            by = _base(conn, base_year)
            return clean_json(forecast_export.grade_plan_grid(
                fs.load_grade_history(conn, by), pf.forecast_sites(conn, by), int(by),
                units=fs.load_table(conn, by, "site_grade_eq")))
        finally:
            conn.close()

    @router.put("/grade-plan")
    def put_grade_plan(req: GradePlanReq):
        """화면 칸 → 엑셀 가져오기와 같은 규칙으로 대표·설비별 등급. 기준연도 앞 이력·양식에 없는 설비 줄은 그대로."""
        conn = conn_factory()
        try:
            by = int(req.base_year)
            sites = pf.forecast_sites(conn, req.base_year)
            grades, units, multi = forecast_export.grade_plan_from_cells(req.cells, sites, by)
            old = fs.load_grade_history(conn, req.base_year)
            fs.save_grade_history(conn, req.base_year, pd.concat([old[old["연도"].astype(int) < by], grades], ignore_index=True))
            eq = fs.load_table(conn, req.base_year, "site_grade_eq")
            # 양식에 줄이 둘 이상인 지사의 기준연도~ 설비 줄은 화면 값으로 통째로(지운 칸이 남지 않게)
            keep = eq[~(eq["사업장"].isin(multi) & (eq["연도"].astype(int) >= by))] if not eq.empty else eq
            fs.save_table(conn, req.base_year, "site_grade_eq", pd.concat([keep, units], ignore_index=True))
            return clean_json(forecast_export.grade_plan_grid(
                fs.load_grade_history(conn, req.base_year), sites, by, units=fs.load_table(conn, req.base_year, "site_grade_eq")))
        finally:
            conn.close()

    @router.get("/capacity")
    def capacity_model(base_year: str = None):
        """설비용량·신규표준 — 용량 규칙(고정분·등급별 MW당 단가·LOO 오차)과 대상 지사 등급별 표준 합계."""
        conn = conn_factory()
        try:
            by = _base(conn, base_year)
            return _cached_view("capacity", conn, by, lambda: clean_json(pf.capacity_view(conn, by)))
        finally:
            conn.close()

    @router.get("/regular")
    def regular(base_year: str = None):
        conn = conn_factory()
        try:
            by = _base(conn, base_year)
            return _cached_view("regular", conn, by, lambda: clean_json(pf.regular_breakdown(conn, by)))
        finally:
            conn.close()

    @router.get("/benchmark")
    def benchmark(base_year: str = None):
        conn = conn_factory()
        try:
            by = _base(conn, base_year)
            return _cached_view("benchmark", conn, by, lambda: clean_json(pf.run_benchmark(conn, by)))
        finally:
            conn.close()

    @router.get("/table")
    def table(base_year: str = None):
        conn = conn_factory()
        try:
            by = _base(conn, base_year)
            return _cached_view("table", conn, by, lambda: clean_json(pf.run_forecast(conn, by)))
        finally:
            conn.close()

    @router.get("/export")
    def export(kind: str, base_year: str):
        """재무팀 양식 내보내기(6-7). 결과 파일을 저장하지 않고 그때그때 만든다 — 화면과 같은 계산.

        kind: standardization(표준화 양식 25시트) · longterm(중장기예산 양식) ·
              schedule / hot-parts / hq-master(현재 저장된 가정이 채워진 원본 양식 — 고쳐서 다시 올리는 용도)
        """
        by = int(base_year)
        conn = conn_factory()
        try:
            if kind == "standardization":
                b = pf.benchmark_frames(conn, base_year)
                data = forecast_export.fill_standardization_workbook(b["actuals"], b["grade"], b["std"], b["sites"])
                name = f"예산표준화_{by}년기준_결과.xlsx"
            elif kind == "longterm":
                f = pf.forecast_frames(conn, base_year)
                data = forecast_export.fill_longterm_workbook(f["tables"], f["grade"], f["hq_master"], f["sites"], by)
                name = f"중장기예산_{by}-{by + 9}년_결과.xlsx"
            elif kind == "schedule":
                data = forecast_export.build_grade_plan_download(
                    fs.load_grade_history(conn, base_year), pf.forecast_sites(conn, base_year), by,
                    units=fs.load_table(conn, base_year, "site_grade_eq"))
                name = f"전지사_정비등급_{by}-{by + 9}년_현재값.xlsx"
            elif kind == "hot-parts":
                data = forecast_export.build_hot_parts_download(
                    fs.load_hot_parts(conn, base_year), pf.forecast_sites(conn, base_year), by,
                    contracts=fs.load_table(conn, base_year, "hot_parts_contract"))
                name = f"전지사_고온부품_{by}-{by + 9}년_현재값.xlsx"
            elif kind == "hq-master":
                data = forecast_export.build_hq_master_download(
                    fs.load_hq_master(conn, base_year), pf.forecast_sites(conn, base_year), by)
                name = f"본사_원가분배_{by}년기준_현재값.xlsx"
            else:
                raise HTTPException(400, "kind 는 standardization·longterm·schedule·hot-parts·hq-master 중 하나여야 합니다.")
        finally:
            conn.close()
        return Response(data, media_type=XLSX,
                        headers={"Content-Disposition": f"attachment; filename*=utf-8''{quote(name)}"})

    return router
