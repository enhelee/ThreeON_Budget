"""예산 표준화 화면

과년도 실적을 지사×예산과목×정비등급 단위로 통계 내어 표준 금액(벤치마크)을 만든다.
정식 섹션은 classified_*.csv(2단계에서 분류 확정한 실적) 기반이고, 아래 테스트 섹션은
'투자유형 예측 테스트'에서 업로드·확정하고 저장한 결과를 백데이터로 쓴다.
"""
import glob
import streamlit as st
import pandas as pd
import standardization as std
import standardization_template as std_tmpl
import mapping_config
import build_state as bstate
from views.project_type_test_page import get_shared_actual_df
from mapping_config import get_site_display_name, get_current_site_type, apply_mappings


def _standardization_test_fingerprint(shared: pd.DataFrame) -> str:
    paths = (
        std.GRADE_HISTORY_PATH, std.METHOD_MAP_PATH, std.OVERRIDE_PATH,
        mapping_config.SITE_TYPE_PATH, mapping_config.ACCOUNT_CAT_PATH, mapping_config.DEPT_MASTER_PATH,
    )
    return bstate.fingerprint(df=shared, paths=paths)

def _pivot_grade_history(long_df: pd.DataFrame) -> pd.DataFrame:
    """(사업장,연도,등급) 긴 표를 행=사업장, 열=연도(최신순)인 넓은 표로 바꾼다 - 한눈에 보기 위함."""
    if long_df.empty:
        return pd.DataFrame(columns=["사업장"])
    wide = long_df.pivot_table(index="사업장", columns="연도", values="등급", aggfunc="first")
    wide = wide.reindex(sorted(wide.columns, reverse=True), axis=1)
    return wide.reset_index()


def _unpivot_grade_history(wide_df: pd.DataFrame) -> pd.DataFrame:
    """행=사업장, 열=연도인 넓은 표를 다시 (사업장,연도,등급) 긴 표로 바꿔서 저장용으로 만든다."""
    year_cols = [c for c in wide_df.columns if c != "사업장"]
    if not year_cols:
        return pd.DataFrame(columns=["사업장", "연도", "등급"])
    long_df = wide_df.melt(id_vars="사업장", value_vars=year_cols, var_name="연도", value_name="등급")
    long_df = long_df.dropna(subset=["사업장", "등급"])
    long_df["사업장"] = long_df["사업장"].astype(str).str.strip()
    long_df["등급"] = long_df["등급"].astype(str).str.strip()
    long_df = long_df[(long_df["사업장"] != "") & (long_df["등급"] != "")]
    long_df["연도"] = long_df["연도"].astype(int)
    return long_df[["사업장", "연도", "등급"]].sort_values(["사업장", "연도"], ascending=[True, False]).reset_index(drop=True)


def render():
    st.caption("예산 표준화 · 과년도 실적 기반 지사×예산과목×정비등급 표준 금액")

    grade_hist = _render_grade_history_manager()

    st.divider()
    st.subheader("정식 · 지사별 실적 표준화")
    files = sorted(glob.glob("classified_*.csv"))
    if not files:
        st.info("먼저 2단계에서 분류를 확정하고 저장해주세요.")
    else:
        dfs = [pd.read_csv(f) for f in files]
        all_df = pd.concat(dfs, ignore_index=True)
        all_df["연도"] = pd.to_datetime(all_df["전기일"]).dt.year
        all_df = apply_mappings(all_df)  # 지사유형 컬럼 추가
        all_df["사업장명"] = all_df["사업장"].apply(lambda v: get_site_display_name(v) if pd.notna(v) else v)

        actuals = pd.DataFrame({
            "사업장": all_df["사업장명"],
            "연도": all_df["연도"],
            "예산과목": all_df["계정과목"],
            "금액": all_df["금액"],
            "지사유형": all_df["지사유형"],
        })
        _render_standardization(actuals, grade_hist, section_key="prod")


def _render_grade_history_manager() -> pd.DataFrame:
    st.subheader("정비등급 이력 관리")
    st.caption(
        "지사×연도별 정비등급 이력입니다. 중대형CHP는 MI/TI(HGPI)/CI/간이, 소형CHP는 A급/C급 "
        "(그 외 등급도 실제 이력에 있으면 그대로 씁니다), DH는 등급 구분이 없어 항상 'A' 하나로 취급됩니다. "
        "재무팀 표준화 참고 엑셀(연도별 정비등급 이력이 있는 파일)에서 한 번에 가져올 수 있습니다."
    )
    grade_hist = std.load_grade_history()

    with st.expander("엑셀에서 정비등급 이력 가져오기", expanded=grade_hist.empty):
        upload = st.file_uploader("표준화 참고 엑셀(.xlsx)", type=["xlsx"], key="grade_import_upload")
        if upload is not None:
            imported = std.import_grade_history_from_workbook(upload.getvalue())
            if imported.empty:
                st.warning("이 파일에서 지사별 정비등급 이력을 찾지 못했습니다.")
            else:
                st.success(f"{imported['사업장'].nunique()}개 지사, {len(imported)}건의 정비등급 이력을 찾았습니다.")
                st.dataframe(imported, width="stretch", hide_index=True)
                merge_new_only = st.checkbox("기존 이력에 없는 (지사,연도)만 추가 (해제하면 전체 교체)",
                                              value=True, key="grade_import_merge")
                if st.button("가져오기 적용", key="grade_import_apply"):
                    if merge_new_only and not grade_hist.empty:
                        combined = pd.concat([grade_hist, imported], ignore_index=True)
                        merged = combined.drop_duplicates(subset=["사업장", "연도"], keep="first")
                    else:
                        merged = imported
                    std.save_grade_history(merged)
                    st.success("저장했습니다.")
                    st.rerun()

    with st.expander("정비등급 이력 직접 보기·수정", expanded=False):
        st.caption("행은 지사, 열은 연도입니다. 빈 칸은 그 해 등급 이력이 없다는 뜻입니다.")
        wide = _pivot_grade_history(grade_hist)
        edited_wide = st.data_editor(wide, width="stretch", hide_index=True, num_rows="dynamic",
                                      key="grade_history_editor")
        if st.button("정비등급 이력 저장", key="grade_history_save"):
            std.save_grade_history(_unpivot_grade_history(edited_wide))
            st.success("저장했습니다.")
            st.rerun()

    return std.load_grade_history()


def _render_standardization(actuals: pd.DataFrame, grade_hist: pd.DataFrame, section_key: str):
    if actuals.empty:
        st.info("실적 데이터가 없습니다.")
        return

    site_types = sorted(actuals["지사유형"].dropna().unique().tolist()) if "지사유형" in actuals.columns else []
    if site_types:
        sel_types = st.multiselect("지사유형 선택", site_types, default=site_types, key=f"{section_key}_site_types")
        actuals = actuals[actuals["지사유형"].isin(sel_types)]

    if not std.has_ltsa_detail(actuals):
        st.caption("ℹ️ 정식 파이프라인에는 아직 '투자유형세부' 정보가 없어, '기계장치' 항목에서 LTSA/CRI를 "
                   "분리하지 못하고 총액을 그대로 씁니다.")

    method_map = std.load_method_map()
    overrides = std.load_overrides()
    standard_df = std.compute_standard_amounts(actuals, grade_hist, method_map, overrides)

    if standard_df.empty:
        st.info("표준화 대상(손익/자본 예산과목) 실적이 없습니다.")
        return

    display = standard_df.copy()
    display["표준금액(억원)"] = (display["표준금액"] / 1e8).round(3)
    display = display.sort_values(["사업장", "구분", "예산과목", "등급"]).reset_index(drop=True)

    st.write(f"**표준 금액 계산 결과** ({len(display)}건)")
    st.caption(
        "'방식출처'가 '자동추천'인 항목은 실적 패턴(연도별 변동성, 등급별 편차)을 분석해 "
        "자동으로 산출방식을 골랐습니다 - '추천사유'에 근거가 나옵니다. "
        "'산출방식'을 바꾸거나 '표준금액(억원)'을 직접 고치면 그 항목은 '사용자지정'으로 고정됩니다."
    )
    edited = st.data_editor(
        display[["사업장", "구분", "예산과목", "등급", "산출방식", "방식출처", "추천사유", "표준금액(억원)", "비고"]],
        width="stretch", hide_index=True, key=f"{section_key}_std_editor",
        column_config={
            "산출방식": st.column_config.SelectboxColumn(options=std.METHOD_OPTIONS),
        },
        disabled=["사업장", "구분", "예산과목", "등급", "방식출처", "추천사유", "비고"],
    )

    if st.button("변경사항 저장 (산출방식 / 표준금액 수정)", key=f"{section_key}_save_changes"):
        merged = edited.merge(
            display[["사업장", "구분", "예산과목", "등급", "산출방식", "표준금액(억원)"]],
            on=["사업장", "구분", "예산과목", "등급"], suffixes=("", "_원래"),
        )

        method_changed = merged[merged["산출방식"] != merged["산출방식_원래"]]
        if not method_changed.empty:
            new_methods = method_changed[["사업장", "예산과목", "산출방식"]].rename(columns={"산출방식": "방식"})
            existing_methods = method_map[~method_map.set_index(["사업장", "예산과목"]).index.isin(
                new_methods.set_index(["사업장", "예산과목"]).index)] if not method_map.empty else method_map
            std.save_method_map(pd.concat([existing_methods, new_methods], ignore_index=True))

        amount_changed = merged[(merged["표준금액(억원)"] - merged["표준금액(억원)_원래"]).abs() > 1e-9]
        if not amount_changed.empty:
            new_overrides = amount_changed[["사업장", "예산과목", "등급", "표준금액(억원)"]].copy()
            new_overrides["표준금액"] = new_overrides["표준금액(억원)"] * 1e8
            new_overrides = new_overrides[["사업장", "예산과목", "등급", "표준금액"]]
            existing_overrides = overrides[~overrides.set_index(["사업장", "예산과목", "등급"]).index.isin(
                new_overrides.set_index(["사업장", "예산과목", "등급"]).index)] if not overrides.empty else overrides
            std.save_overrides(pd.concat([existing_overrides, new_overrides], ignore_index=True))

        st.success("저장했습니다.")
        st.rerun()

    st.divider()
    st.write("**엑셀로 내보내기**")
    st.caption("재무팀 표준화 양식(25개 시트)에 실적·정비등급 이력·표준 금액을 채워서 내려받습니다.")
    export_key = f"{section_key}_export_bytes"
    if st.button("표준화 양식으로 내보내기", key=f"{section_key}_export_btn"):
        out_path = f"filled_표준화_{section_key}.xlsx"
        std_tmpl.fill_standardization_workbook(actuals, grade_hist, standard_df, out_path)
        with open(out_path, "rb") as f:
            st.session_state[export_key] = f.read()

    if st.session_state.get(export_key):
        st.download_button(
            "채워진 엑셀 다운로드", data=st.session_state[export_key],
            file_name=f"예산표준화_{section_key}_결과.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=f"{section_key}_download_btn",
        )


def render_test():
    """Test 모드 · 예산 표준화 - '투자유형 예측 테스트'에서 업로드·확정한 결과를 백데이터로 표준화를 계산해본다.
    이 자료는 연도 정보가 없는 단일 배치라, 지사별 '현재' 정비등급을 임시로 붙여서 계산한다."""
    st.caption("Test 모드 · 예산 표준화")
    grade_hist = std.load_grade_history()
    st.info("🧪 '투자유형 예측 테스트' 화면에서 업로드·확정한 결과를 백데이터로 씁니다. "
            "그 자료엔 연도가 없어, 지사별 '현재' 정비등급 하나로 표준화를 계산합니다(과년도 등급별 평균이 아님). "
            "정비등급 이력 자체는 '예산 표준화' 화면에서 관리합니다. "
            "엑셀로 내보내면 이 실적은 정비등급 이력의 가장 최근 연도 칸에 표시됩니다.")

    shared = get_shared_actual_df()
    has_actual = shared is not None and not shared.empty

    mapping_config.load_site_type_map()  # 없으면 여기서 기본값으로 seed됨 - 지문 계산 전에 미리 해서
    # 파일이 "없다가 생기는" 것만으로 지문이 바뀌어 매번 "데이터가 변경되었습니다"로 오판하지 않게 한다.
    current_fp = _standardization_test_fingerprint(shared) if has_actual else None
    saved_fp = bstate.load_build_fingerprint("standardization_test")
    built = has_actual and saved_fp is not None
    data_changed = built and saved_fp != current_fp

    st.subheader("현재 상태")
    status_bits = [f"실적 업로드 {'완료' if has_actual else '미완료'}"]
    status_bits.append("⚠️ 데이터가 변경되었습니다 (다시 만들어주세요)" if data_changed
                        else f"표준화 {'작성됨' if built else '미작성'}")
    st.info(" · ".join(status_bits))

    if not has_actual:
        st.info("먼저 '계획 및 실적 업로드'(또는 '투자유형 예측 테스트') 화면에서 실적 데이터를 업로드하고 결과를 확인해주세요.")
        return

    if (shared["사업장"].astype(str).str.strip() == "").all():
        st.warning("'사업장' 칸을 지정하지 않아 표준화를 계산할 수 없습니다.")
        return

    button_label = "표준화 다시 계산하기 (데이터 변경 반영)" if data_changed else \
        ("표준화 다시 계산하기 (최신 업로드 반영)" if built else "이 데이터로 표준화 계산하기")
    rebuild_clicked = st.button(button_label, type="primary", key="std_test_build_btn")
    if rebuild_clicked:
        built = True
        data_changed = False

    if not built or data_changed:
        st.caption("버튼을 누르면 현재 업로드된 실적 데이터를 기준으로 표준화를 계산합니다.")
        return

    # 지문이 일치하면(=버튼을 새로 누른 게 아니면) 저장해둔 결과를 그대로 불러와 다시 계산하지 않는다.
    prepared = None if rebuild_clicked else bstate.load_artifact("standardization_test_prepared")
    if prepared is None:
        with st.status("표준화 계산 중...", expanded=True) as status:
            st.write("사업장명·지사유형 매핑 중...")
            ref_year = std.reference_year_for_undated(grade_hist)
            df = shared.copy()
            df["사업장"] = df["사업장"].apply(lambda v: get_site_display_name(v) if pd.notna(v) and str(v).strip() else v)
            df["연도"] = ref_year
            df["지사유형"] = df["사업장"].apply(lambda v: get_current_site_type(v) if pd.notna(v) and str(v).strip() else "미매핑")

            st.write("정비등급 이력 보강 중...")
            extra_grades = []
            for site in df["사업장"].dropna().unique():
                grade = std.get_current_grade(site, grade_hist)
                if grade:
                    extra_grades.append({"사업장": site, "연도": ref_year, "등급": grade})
            augmented_grade_hist = pd.concat([grade_hist, pd.DataFrame(extra_grades)], ignore_index=True)
            status.update(label="표준화 데이터 준비 완료", state="complete", expanded=False)
        prepared = {"df": df, "augmented_grade_hist": augmented_grade_hist}
        bstate.save_artifact("standardization_test_prepared", prepared)
        bstate.save_build_fingerprint("standardization_test", current_fp)
    else:
        st.caption("✅ 이전에 계산해둔 데이터를 그대로 불러왔습니다 (다시 계산하지 않음).")

    _render_standardization(prepared["df"], prepared["augmented_grade_hist"], section_key="test")
