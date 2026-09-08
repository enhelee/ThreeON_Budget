"""중장기 예산 (26-35년) 화면

당해년도(BASE_YEAR) 예산은 예산계획(예산 계획 업로드 화면에서 등록한 budget_{연도}.csv) 확정 금액을 쓰고,
다음년도부터는 표준화 금액에 팩터(물가상승률 등)를 복리로 곱해 2027~2035년 예산을 추정한다. 여기에
정기점검보수공사 일정·고온부품 계획·투자비·본사 원가분배·돌발사업을 더해 재무팀 참고 양식(25개+ 시트)으로
내보낸다.
"""
import glob
import os
import streamlit as st
import pandas as pd
import standardization as std
import longterm_forecast as lf
import longterm_forecast_template as lft
import mapping_config
import build_state as bstate
from mapping_config import get_site_display_name
from budget_upload import parse_budget_workbook, validate_budget_form


def _longterm_test_fingerprint() -> str:
    """중장기 예산 Test 모드 '계산 결과' 입력이 되는 모든 백데이터 파일의 지문 - 사용자 세션과
    무관하게 전부 파일 기반이라 df는 필요 없다."""
    paths = [
        lf.TEST_ACTUALS_PATH, std.GRADE_HISTORY_PATH, lf.HOT_PARTS_PATH, lf.HQ_MASTER_PATH,
        lf.HQ_RATIO_PATH, lf.FACTORS_PATH, lf.HQ_TEMP_PROJECTS_PATH, lf.SURPRISE_PATH,
        std.METHOD_MAP_PATH, std.OVERRIDE_PATH,
        mapping_config.SITE_TYPE_PATH, mapping_config.ACCOUNT_CAT_PATH, mapping_config.DEPT_MASTER_PATH,
    ]
    paths += [lf.test_budget_plan_path(y) for y in lf.load_test_budget_plan_years()]
    return bstate.fingerprint(paths=tuple(paths))


def render():
    st.caption("중장기 예산 (26-35년) · 표준화 금액 + 팩터 + 정기점검 일정 + 고온부품 + 투자비 + 본사 원가분배")

    grade_hist = _render_schedule_manager()
    hot_parts = _render_hot_parts_manager()
    hq_master, hq_ratio = _render_hq_master_manager()
    factors = _render_factor_manager()
    hq_temp = _render_hq_temp_projects()
    surprise = _render_surprise_projects()

    st.divider()
    st.subheader("계산 결과 미리보기 및 내보내기")

    files = sorted(glob.glob("classified_*.csv"))
    if not files:
        st.info("먼저 '예산 실적 분석'에서 분류를 확정해주세요 - 표준화 금액 계산의 기반 데이터입니다.")
        return

    all_df = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
    all_df["연도"] = pd.to_datetime(all_df["전기일"]).dt.year
    all_df["사업장명"] = all_df["사업장"].apply(lambda v: get_site_display_name(v) if pd.notna(v) else v)
    actuals = pd.DataFrame({
        "사업장": all_df["사업장명"], "연도": all_df["연도"],
        "예산과목": all_df["계정과목"], "금액": all_df["금액"],
    })

    budget_path = f"budget_{lf.BASE_YEAR}.csv"
    budget_df = pd.read_csv(budget_path) if os.path.exists(budget_path) else pd.DataFrame()
    investment_df = lf.investment_by_site(budget_df)
    if budget_df.empty:
        st.caption(f"ℹ️ {lf.BASE_YEAR}년 예산계획이 없어 투자비를 0으로 두고, 표준화 대상 계정과목은 "
                   f"{lf.BASE_YEAR}년에도 표준화 금액으로 대체합니다. '예산 계획 업로드'에서 먼저 등록해주세요.")

    _render_compute_and_export(actuals, grade_hist, hot_parts, hq_master, hq_ratio, factors,
                                hq_temp, surprise, investment_df, budget_df, section_key="prod")


def render_test():
    """Test 모드 · 중장기 예산 (26-35년) - 표준화 참고 양식(정비등급 이력이 있는 엑셀)을 이 화면에서
    직접 업로드해 지사×연도×예산과목 실적을 백데이터로 쓴다. 정기점검보수공사 일정(미래 등급)·고온부품·
    본사원가분배·팩터·돌발사업은 정식 화면에서 관리한 값을 그대로 읽어서 쓴다."""
    st.caption("Test 모드 · 중장기 예산 (26-35년)")
    st.info("🧪 아래에서 표준화 참고 양식(★ 예산표준화 실적/정비등급 엑셀)을 업로드하면 지사×연도×예산과목 실적을 "
            "백데이터로 씁니다. 정기점검보수공사 일정(미래 등급)·고온부품 계획·본사 원가분배·팩터·돌발사업은 "
            "정식 '중장기 예산 (26-35년)' 화면에서 관리한 값을 그대로 사용합니다.")

    with st.expander("표준화 실적 엑셀 업로드 (백데이터)", expanded=True):
        st.caption("'예산 표준화' 화면에서 쓰는 것과 같은 참고 양식입니다 - 지사 시트의 연도별 실적 금액과 "
                   "정비등급 이력을 함께 가져옵니다. 새로 올리면 기존 백데이터를 통째로 교체합니다.")
        upload = st.file_uploader("표준화 실적 엑셀(.xlsx)", type=["xlsx"], key="ltf_test_actuals_upload")
        if upload is not None:
            imported_actuals = std.import_actuals_from_workbook(upload.getvalue())
            imported_grades = std.import_grade_history_from_workbook(upload.getvalue())
            if imported_actuals.empty:
                st.warning("이 파일에서 지사별 실적 금액을 찾지 못했습니다.")
            else:
                st.success(f"{imported_actuals['사업장'].nunique()}개 지사, {len(imported_actuals)}건의 실적을 찾았습니다"
                           f"(정비등급 {len(imported_grades)}건 포함).")
                st.dataframe(imported_actuals.head(20), width="stretch", hide_index=True)
                if st.button("이 실적을 백데이터로 저장", key="ltf_test_actuals_apply"):
                    lf.save_test_actuals(imported_actuals)
                    if not imported_grades.empty:
                        grade_hist = std.load_grade_history()
                        combined = pd.concat([grade_hist, imported_grades], ignore_index=True)
                        merged = combined.drop_duplicates(subset=["사업장", "연도"], keep="last")
                        std.save_grade_history(merged)
                    st.success("저장했습니다.")
                    st.rerun()

        test_actuals = lf.load_test_actuals()
        if not test_actuals.empty:
            st.caption(f"현재 저장된 백데이터: {test_actuals['사업장'].nunique()}개 지사, {len(test_actuals)}건")

    with st.expander(f"예산계획 엑셀 업로드 ({lf.BASE_YEAR}년 당해년도 백데이터)", expanded=True):
        st.caption("'예산 계획 업로드' 화면과 같은 양식(양식1(월별)/예산코드/부서코드 시트)입니다. 표준화 대상 "
                   f"계정과목의 {lf.BASE_YEAR}년(당해년도) 금액은 표준화 계산값 대신 여기 업로드한 예산계획 확정 "
                   "금액을 씁니다(다음년도부터는 여전히 표준화 금액에 팩터를 곱해 예측합니다). "
                   "손익예산/자본예산/건설예산처럼 여러 파일로 나뉘어 있으면 한 번에 모두 선택해 올리면 합쳐서 "
                   "반영됩니다. 새로 올리면 기존 백데이터를 통째로 교체합니다.")
        budget_upload_files = st.file_uploader("예산계획 엑셀(.xlsx, 여러 개 선택 가능)", type=["xlsx"],
                                                accept_multiple_files=True, key="ltf_test_budget_upload")
        if budget_upload_files:
            parsed_results = []  # (파일명, result) 목록 - 합쳐서 저장하는 데 사용
            for idx, bf in enumerate(budget_upload_files):
                temp_path = f"temp_budget_upload_ltf_test_{idx}.xlsx"
                with open(temp_path, "wb") as f:
                    f.write(bf.getbuffer())
                parsed = None
                try:
                    parsed = parse_budget_workbook(temp_path)
                except ValueError as e:
                    st.error(f"'{bf.name}': {e}")
                finally:
                    try:
                        if os.path.exists(temp_path):
                            os.remove(temp_path)
                    except OSError:
                        pass

                if parsed is not None:
                    result = validate_budget_form(parsed["form"], parsed["account_master"], parsed["dept_master"])
                    with st.container(border=True):
                        st.markdown(f"**파일: {bf.name}**")
                        st.caption(f"{result['row_count']}건 인식됨 · 오류/경고 {result['error_count']}건")
                        if result["errors"]:
                            st.dataframe(pd.DataFrame(result["errors"])[["row", "level", "type", "detail"]],
                                         width="stretch", hide_index=True)
                        if not result["data"].empty:
                            st.dataframe(result["data"].head(20), width="stretch")
                            parsed_results.append((bf.name, result))

            if parsed_results:
                combined_data = pd.concat([r["data"] for _, r in parsed_results], ignore_index=True)
                st.divider()
                st.caption(f"{len(parsed_results)}개 파일 합계 {len(combined_data)}건을 백데이터로 저장합니다.")
                if st.button("이 예산계획을 백데이터로 저장", key="ltf_test_budget_apply"):
                    lf.save_test_budget_plan(combined_data)
                    st.success("저장했습니다.")
                    st.rerun()

        test_budget = lf.load_test_budget_plan()
        if not test_budget.empty:
            st.caption(f"현재 저장된 예산계획 백데이터: {len(test_budget)}건")

    actuals = lf.load_test_actuals()
    if actuals.empty:
        st.info("먼저 위에서 표준화 실적 엑셀을 업로드하고 저장해주세요.")
        return

    grade_hist = std.load_grade_history()
    hot_parts = lf.load_hot_parts()
    hq_master = lf.load_hq_master()
    hq_ratio = lf.load_hq_ratio()
    factors = lf.load_factors()
    hq_temp = lf.load_hq_temp_projects()
    surprise = lf.load_surprise_projects()

    budget_df = lf.load_test_budget_plan()
    investment_df = lf.investment_by_site(budget_df)
    if budget_df.empty:
        st.caption(f"ℹ️ 예산계획 백데이터가 없어 투자비를 0으로 두고, 표준화 대상 계정과목은 {lf.BASE_YEAR}년에도 "
                   "표준화 금액으로 대체합니다.")

    mapping_config.load_site_type_map()  # 없으면 여기서 기본값으로 seed됨 - 지문 계산 전에 미리 해서
    # 파일이 "없다가 생기는" 것만으로 지문이 바뀌어 매번 "데이터가 변경되었습니다"로 오판하지 않게 한다.
    current_fp = _longterm_test_fingerprint()
    saved_fp = bstate.load_build_fingerprint("longterm_test")
    built = saved_fp is not None
    data_changed = built and saved_fp != current_fp

    st.subheader("현재 상태")
    status_bits = [f"표준화 실적 백데이터 {'있음' if not actuals.empty else '없음'}",
                   f"예산계획 백데이터 {'있음' if not budget_df.empty else '없음'}"]
    status_bits.append("⚠️ 데이터가 변경되었습니다 (다시 만들어주세요)" if data_changed
                        else f"계산 결과 {'작성됨' if built else '미작성'}")
    st.info(" · ".join(status_bits))

    button_label = "계산 결과 다시 만들기 (데이터 변경 반영)" if data_changed else \
        ("계산 결과 다시 만들기 (최신 업로드 반영)" if built else "이 데이터로 계산 결과 만들기")
    rebuild_clicked = st.button(button_label, type="primary", key="ltf_test_build_btn")
    if rebuild_clicked:
        built = True
        data_changed = False

    if not built or data_changed:
        st.caption("버튼을 누르면 현재 업로드된 표준화 실적·예산계획 데이터를 기준으로 26~35년 계산 결과를 만듭니다 "
                   "(지사가 많으면 시간이 걸릴 수 있습니다).")
        return

    # 지문이 일치하면(=버튼을 새로 누른 게 아니면) 저장해둔 지사별 계산 결과를 그대로 불러와
    # compute_all_sites()를 다시 돌리지 않는다(가장 오래 걸리는 부분).
    cached_site_tables = None if rebuild_clicked else bstate.load_artifact("longterm_test_site_tables")
    if cached_site_tables is not None:
        st.caption("✅ 이전에 계산해둔 데이터를 그대로 불러왔습니다 (다시 계산하지 않음).")

    site_tables = _render_compute_and_export(actuals, grade_hist, hot_parts, hq_master, hq_ratio, factors,
                                              hq_temp, surprise, investment_df, budget_df, section_key="test",
                                              cached_site_tables=cached_site_tables)
    if cached_site_tables is None and site_tables:
        bstate.save_artifact("longterm_test_site_tables", site_tables)
        bstate.save_build_fingerprint("longterm_test", current_fp)


def _render_compute_and_export(actuals: pd.DataFrame, grade_hist: pd.DataFrame, hot_parts: pd.DataFrame,
                                hq_master: pd.DataFrame, hq_ratio: pd.DataFrame, factors: pd.DataFrame,
                                hq_temp: pd.DataFrame, surprise: pd.DataFrame, investment_df: pd.DataFrame,
                                budget_df: pd.DataFrame, section_key: str, cached_site_tables: dict = None):
    """정식/Test 모드가 공유하는 계산 결과 미리보기 + 엑셀 내보내기. actuals/grade_hist만 다르고 나머지 로직은 동일하다.
    cached_site_tables가 있으면(Test 모드가 저장해둔 결과 재사용) compute_all_sites()를 다시 부르지 않는다.
    반환: 이번에 실제로 계산한 site_tables(호출부가 저장에 쓸 수 있게) - cached를 그대로 썼으면 None."""
    st.subheader("계산 결과 미리보기 및 내보내기")

    method_map = std.load_method_map()
    overrides = std.load_overrides()
    standard_df = std.compute_standard_amounts(actuals, grade_hist, method_map, overrides)
    if not std.has_ltsa_detail(actuals):
        st.caption("ℹ️ '기계장치' 항목에서 LTSA/CRI를 분리할 '투자유형세부' 정보가 없어 총액을 그대로 씁니다.")

    sites = sorted(grade_hist["사업장"].dropna().unique().tolist())
    if not sites:
        st.warning("정비등급 이력이 없어 지사별 계산을 할 수 없습니다.")
        return None

    newly_computed = None
    if cached_site_tables is not None:
        site_tables = cached_site_tables
    else:
        with st.status(f"{len(sites)}개 지사 26~35년 계산 중...", expanded=True) as status:
            st.write("지사별 표준화 금액·팩터·본사 원가분배·고온부품·투자비 반영 중...")
            site_tables = lf.compute_all_sites(sites, grade_hist, standard_df, hot_parts, hq_master,
                                                hq_temp, hq_ratio, factors, surprise, investment_df, budget_df)
            status.update(label="지사별 계산 완료", state="complete", expanded=False)
        newly_computed = site_tables

    sel_site = st.selectbox("미리보기 지사 선택", sites, key=f"{section_key}_preview_site")
    preview = site_tables[sel_site].copy()
    for y in lf.FORECAST_YEARS:
        preview[y] = (preview[y] / 1e8).round(3)
    preview.columns = [str(c) for c in preview.columns]
    st.dataframe(preview, width="stretch", hide_index=True)
    st.caption("표시 단위: 억원")

    st.divider()
    st.write("**엑셀로 내보내기**")
    st.caption("재무팀 참고 양식(19개 지사 탭 + 26년 총원가배분/본사원가분배 + 총괄표)에 결과를 채워 내려받습니다. "
               "27~35년 개별 시트, 자본 건물/구축물 세부, 정기점검·고온부품 원본 시트는 이번 버전에서 건드리지 않습니다.")
    export_key = f"{section_key}_export_bytes"
    if st.button("중장기 예산 양식으로 내보내기", type="primary", key=f"{section_key}_export_btn"):
        out_path = f"filled_중장기예산_{section_key}.xlsx"
        lft.fill_longterm_workbook(site_tables, grade_hist, hq_master, out_path)
        with open(out_path, "rb") as f:
            st.session_state[export_key] = f.read()

    if st.session_state.get(export_key):
        st.download_button(
            "채워진 엑셀 다운로드", data=st.session_state[export_key],
            file_name=f"중장기예산_26-35년_{section_key}_결과.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=f"{section_key}_download_btn",
        )

    return newly_computed


def _render_schedule_manager() -> pd.DataFrame:
    with st.expander("정비등급 이력 · 정기점검보수공사 일정(미래) 업로드", expanded=False):
        st.caption("과거 실적 등급 이력(표준화 화면에서 관리)에 이어, 미래(2026~) 정비등급을 정기점검보수공사 "
                   "일정 엑셀에서 가져와 같은 이력에 더할 수 있습니다. GT계열 등급이 있는 지사는 GT를, "
                   "ST계열만 있는 지사는 ST를 대표등급으로 씁니다.")
        grade_hist = std.load_grade_history()
        st.download_button(
            "현재 저장된 정비등급이 반영된 양식 다운로드",
            data=lft.build_schedule_download(grade_hist),
            file_name="정기점검보수공사_일정_현재값.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="ltf_schedule_download",
        )
        upload = st.file_uploader("정기점검보수공사 일정 엑셀(.xlsx)", type=["xlsx"], key="ltf_schedule_upload")
        if upload is not None:
            imported = lf.import_schedule_from_workbook(upload.getvalue())
            if imported.empty:
                st.warning("이 파일에서 미래 정비등급 일정을 찾지 못했습니다.")
            else:
                st.success(f"{imported['사업장'].nunique()}개 지사, {len(imported)}건의 미래 정비등급을 찾았습니다.")
                st.dataframe(imported, width="stretch", hide_index=True)
                if st.button("정비등급 이력에 병합", key="ltf_schedule_apply"):
                    combined = pd.concat([grade_hist, imported], ignore_index=True)
                    merged = combined.drop_duplicates(subset=["사업장", "연도"], keep="last")
                    std.save_grade_history(merged)
                    st.success("저장했습니다.")
                    st.rerun()
    return std.load_grade_history()


def _render_hot_parts_manager() -> pd.DataFrame:
    with st.expander("고온부품 계획 업로드", expanded=False):
        st.caption("고온부품(26) 양식을 업로드하면 지사×연도×항목(고온부품재생/신품구매) 금액을 그대로 반영합니다"
                   "(물가상승률 등 팩터는 적용하지 않습니다).")
        hot_parts = lf.load_hot_parts()
        st.download_button(
            "현재 저장된 고온부품 계획이 반영된 양식 다운로드",
            data=lft.build_hot_parts_download(hot_parts),
            file_name="고온부품_계획_현재값.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="ltf_hotparts_download",
        )
        upload = st.file_uploader("고온부품 계획 엑셀(.xlsx)", type=["xlsx"], key="ltf_hotparts_upload")
        if upload is not None:
            imported = lf.import_hot_parts_from_workbook(upload.getvalue())
            if imported.empty:
                st.warning("이 파일에서 고온부품 계획을 찾지 못했습니다.")
            else:
                st.success(f"{imported['사업장'].nunique()}개 지사, {len(imported)}건의 고온부품 계획을 찾았습니다.")
                st.dataframe(imported, width="stretch", hide_index=True)
                if st.button("고온부품 계획 저장", key="ltf_hotparts_apply"):
                    lf.save_hot_parts(imported)
                    st.success("저장했습니다.")
                    st.rerun()
        if not hot_parts.empty:
            st.caption(f"현재 저장된 고온부품 계획: {len(hot_parts)}건")
    return lf.load_hot_parts()


def _render_hq_master_manager() -> tuple:
    with st.expander("본사 원가분배 마스터 표 업로드", expanded=False):
        st.caption("'26년 본사 원가분배' 양식을 업로드하면 배분 구조·비율을 그대로 가져옵니다. "
                   "배분은 이 표에 있는 비율을 그대로 따르며 앱이 임의로 재계산하지 않습니다 - "
                   "비율을 바꾸려면 같은 형식의 수정본을 다시 올려주세요.")
        hq_master = lf.load_hq_master()
        hq_ratio = lf.load_hq_ratio()
        st.download_button(
            "현재 저장된 본사 원가분배가 반영된 양식 다운로드",
            data=lft.build_hq_master_download(hq_master),
            file_name="본사_원가분배_현재값.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="ltf_hqmaster_download",
        )
        upload = st.file_uploader("본사 원가분배 엑셀(.xlsx)", type=["xlsx"], key="ltf_hqmaster_upload")
        if upload is not None:
            imported_master, imported_ratio = lf.import_hq_master_from_workbook(upload.getvalue())
            if imported_master.empty:
                st.warning("이 파일에서 본사 원가분배 표를 찾지 못했습니다.")
            else:
                st.success(f"{len(imported_master)}개 라인, 배분비율 {len(imported_ratio)}개 지사를 찾았습니다.")
                st.dataframe(imported_master, width="stretch", hide_index=True)
                if st.button("본사 원가분배 표 저장(전체 교체)", key="ltf_hqmaster_apply"):
                    lf.save_hq_master(imported_master)
                    lf.save_hq_ratio(imported_ratio)
                    st.success("저장했습니다.")
                    st.rerun()
        if not hq_master.empty:
            st.caption(f"현재 저장된 본사 원가분배: {len(hq_master)}개 라인 / 배분비율 {len(hq_ratio)}개 지사")
    return lf.load_hq_master(), lf.load_hq_ratio()


def _render_factor_manager() -> pd.DataFrame:
    with st.expander("팩터 관리 (물가상승률 등)", expanded=False):
        st.caption("미래 연도 금액 추정에 곱하는 팩터입니다. 등록된 모든 활성 팩터의 (1+연간비율)을 복리로 "
                   "곱합니다. 물가상승률 외에 노후화 팩터 등을 추가로 등록할 수 있습니다.")
        factors = lf.load_factors()
        edited = st.data_editor(
            factors, width="stretch", hide_index=True, num_rows="dynamic", key="ltf_factors_editor",
            column_config={
                "연간비율": st.column_config.NumberColumn(format="%.4f"),
                "활성": st.column_config.CheckboxColumn(),
            },
        )
        if st.button("팩터 저장", key="ltf_factors_save"):
            lf.save_factors(edited)
            st.success("저장했습니다.")
            st.rerun()
    return lf.load_factors()


def _render_hq_temp_projects() -> pd.DataFrame:
    with st.expander("본사 일시적 사업 추가", expanded=False):
        st.caption("계획에 없던 본사 일시적 사업을 추가합니다 - 계약체결금액 비율로 19개 지사에 자동 배분됩니다.")
        temp_df = lf.load_hq_temp_projects()
        if not temp_df.empty:
            st.dataframe(temp_df, width="stretch", hide_index=True)
        with st.form("ltf_hq_temp_form", clear_on_submit=True):
            c1, c2, c3, c4 = st.columns(4)
            name = c1.text_input("사업명")
            account = c2.selectbox("예산과목", list(std.ALL_ACCOUNTS))
            year = c3.number_input("연도", min_value=2026, max_value=2035, value=2026, step=1)
            amount = c4.number_input("금액(원)", min_value=0.0, step=1_000_000.0)
            if st.form_submit_button("추가"):
                if name.strip():
                    lf.append_hq_temp_project(name.strip(), account, int(year), amount)
                    st.success(f"'{name}' 추가했습니다.")
                    st.rerun()
                else:
                    st.warning("사업명을 입력해주세요.")
    return lf.load_hq_temp_projects()


def _render_surprise_projects() -> pd.DataFrame:
    with st.expander("지사별 돌발 사업 추가", expanded=False):
        st.caption("표준화 금액에 없던 지사별 돌발 사업을 추가합니다.")
        surprise_df = lf.load_surprise_projects()
        if not surprise_df.empty:
            st.dataframe(surprise_df, width="stretch", hide_index=True)
        grade_hist = std.load_grade_history()
        sites = sorted(grade_hist["사업장"].dropna().unique().tolist())
        with st.form("ltf_surprise_form", clear_on_submit=True):
            c1, c2, c3, c4 = st.columns(4)
            site = c1.selectbox("지사", sites) if sites else c1.text_input("지사")
            year = c2.number_input("연도", min_value=2026, max_value=2035, value=2026, step=1, key="ltf_surprise_year")
            account = c3.selectbox("예산과목", list(std.ALL_ACCOUNTS), key="ltf_surprise_account")
            amount = c4.number_input("금액(원)", min_value=0.0, step=1_000_000.0, key="ltf_surprise_amount")
            reason = st.text_input("사유")
            if st.form_submit_button("추가"):
                if site:
                    lf.append_surprise_project(site, int(year), account, amount, reason)
                    st.success(f"'{site}' 돌발사업을 추가했습니다.")
                    st.rerun()
                else:
                    st.warning("지사를 선택해주세요.")
    return lf.load_surprise_projects()
