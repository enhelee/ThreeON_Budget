"""4단계 · 맞춤 리포트 화면"""
import glob
import streamlit as st
import pandas as pd
import mapping_config
import build_state as bstate
from mapping_config import apply_mappings, get_site_display_name
from report_builder import build_pivot, yoy_growth
from views.project_type_test_page import get_shared_actual_df


def _report_test_fingerprint(shared: pd.DataFrame) -> str:
    mapping_paths = (mapping_config.SITE_TYPE_PATH, mapping_config.ACCOUNT_CAT_PATH, mapping_config.DEPT_MASTER_PATH)
    return bstate.fingerprint(df=shared, paths=mapping_paths)


def render():
    st.caption("4단계 · 맞춤 리포트")
    files = sorted(glob.glob("classified_*.csv"))

    if not files:
        st.info("먼저 2단계에서 분류를 확정하고 저장해주세요.")
    else:
        dfs = [pd.read_csv(f) for f in files]
        all_df = pd.concat(dfs, ignore_index=True)
        all_df["연도"] = pd.to_datetime(all_df["전기일"]).dt.year
        mapped = apply_mappings(all_df)
        mapped["사업장명"] = mapped["사업장"].apply(lambda v: get_site_display_name(v) if pd.notna(v) else v)

        if (mapped["지사유형"] == "미매핑").all() or (mapped["손익자본구분"] == "미매핑").all():
            st.warning("지사유형 또는 손익/자본 매핑이 아직 설정되지 않았습니다. '설정 (매핑 관리)' 메뉴에서 먼저 입력해주세요.")

        DIM_OPTIONS = ["연도", "사업장명", "지사유형", "계정과목", "거래처명", "투자유형_확정", "손익자본구분"]

        st.subheader("바로 보기")
        preset = st.columns(3)
        if preset[0].button("① 연도별 손익/자본/합계"):
            st.session_state["report_rows"] = ["연도"]
            st.session_state["report_col"] = "손익자본구분"
        if preset[1].button("② 지사유형별 실적"):
            st.session_state["report_rows"] = ["지사유형"]
            st.session_state["report_col"] = "연도"
        if preset[2].button("③ 예산과목별 실적+증감율"):
            st.session_state["report_rows"] = ["계정과목", "연도"]
            st.session_state["report_col"] = None

        st.divider()
        st.subheader("직접 조합하기")
        row_dims = st.multiselect("행 기준 (복수 선택 가능)", DIM_OPTIONS,
                                   default=st.session_state.get("report_rows", ["연도"]))
        col_dim = st.selectbox("열 기준 (선택 안 해도 됨)", [None] + DIM_OPTIONS,
                                index=([None] + DIM_OPTIONS).index(st.session_state.get("report_col", None))
                                if st.session_state.get("report_col", None) in ([None] + DIM_OPTIONS) else 0)
        show_yoy = st.checkbox("전년대비 증감율 표시 ('연도'가 행 기준에 포함되어야 함)")

        if not row_dims:
            st.warning("행 기준을 1개 이상 선택해주세요.")
        elif show_yoy:
            if "연도" not in row_dims:
                st.warning("증감율을 보려면 행 기준에 '연도'를 포함해주세요.")
            else:
                result = yoy_growth(mapped, row_dims)
                result["금액"] = (result["금액"] / 1e8).round(1)
                st.dataframe(result, width="stretch", hide_index=True)
                st.download_button("엑셀로 내보내기", data=result.to_csv(index=False).encode("utf-8-sig"),
                                    file_name="맞춤리포트.csv", mime="text/csv")
        else:
            pivot = build_pivot(mapped, row_dims, col_dim) / 1e8
            if col_dim:
                pivot["합계"] = pivot.sum(axis=1)
            pivot = pivot.round(1)
            st.dataframe(pivot, width="stretch")
            st.download_button("엑셀로 내보내기", data=pivot.to_csv().encode("utf-8-sig"),
                                file_name="맞춤리포트.csv", mime="text/csv")


def render_test():
    """Test 모드 · 맞춤 리포트 - '투자유형 예측 테스트' 화면에서 업로드·확정하고 저장한 결과를 그대로
    리포트에 반영한다. 정식 리포트(classified_*.csv 기반)와는 완전히 별개이며, 실제 데이터에는 영향을 주지 않는다."""
    st.caption("Test 모드 · 맞춤 리포트")
    st.info("🧪 '투자유형 예측 테스트' 화면에서 업로드·확인·저장한 결과를 기준으로 계산합니다. "
            "정식 리포트(예산 실적 분석 > 맞춤 리포트)와는 별개입니다.")

    shared = get_shared_actual_df()
    has_actual = shared is not None and not shared.empty

    mapping_config.load_site_type_map()  # 없으면 여기서 기본값으로 seed됨 - 지문 계산 전에 미리 해서
    # 파일이 "없다가 생기는" 것만으로 지문이 바뀌어 매번 "데이터가 변경되었습니다"로 오판하지 않게 한다.
    current_fp = _report_test_fingerprint(shared) if has_actual else None
    saved_fp = bstate.load_build_fingerprint("report_test")
    built = has_actual and saved_fp is not None
    data_changed = built and saved_fp != current_fp

    st.subheader("현재 상태")
    status_bits = [f"실적 업로드 {'완료' if has_actual else '미완료'}"]
    status_bits.append("⚠️ 데이터가 변경되었습니다 (다시 만들어주세요)" if data_changed
                        else f"리포트 {'작성됨' if built else '미작성'}")
    st.info(" · ".join(status_bits))

    if not has_actual:
        st.info("먼저 '계획 및 실적 업로드'(또는 '투자유형 예측 테스트') 화면에서 실적 데이터를 업로드하고 결과를 확인해주세요.")
        return

    if (shared["사업장"].astype(str).str.strip() == "").all():
        st.warning("'사업장' 칸을 지정하지 않아 지사별 집계를 할 수 없습니다.")
        return

    button_label = "리포트 다시 만들기 (데이터 변경 반영)" if data_changed else \
        ("리포트 다시 만들기 (최신 업로드 반영)" if built else "이 데이터로 리포트 만들기")
    rebuild_clicked = st.button(button_label, type="primary", key="report_test_build_btn")
    if rebuild_clicked:
        built = True
        data_changed = False

    if not built or data_changed:
        st.caption("버튼을 누르면 현재 업로드된 실적 데이터를 기준으로 리포트를 계산합니다.")
        return

    # 지문이 일치하면(=버튼을 새로 누른 게 아니면) 저장해둔 결과를 그대로 불러와 다시 계산하지 않는다.
    all_df = None if rebuild_clicked else bstate.load_artifact("report_test_prepared")
    if all_df is None:
        with st.status("실적 데이터 준비 중...", expanded=True) as prep_status:
            st.write(f"실적 {len(shared)}건 사업장명 매핑 중...")
            all_df = shared.copy()
            all_df["사업장명"] = all_df["사업장"].apply(lambda v: get_site_display_name(v) if pd.notna(v) and str(v).strip() else v)
            prep_status.update(label="실적 데이터 준비 완료", state="complete", expanded=False)
        bstate.save_artifact("report_test_prepared", all_df)
        bstate.save_build_fingerprint("report_test", current_fp)
    else:
        st.caption("✅ 이전에 계산해둔 데이터를 그대로 불러왔습니다 (다시 계산하지 않음).")

    DIM_OPTIONS = ["연도", "사업장명", "예산과목", "투자유형_확정", "투자유형세부_확정"]

    available_years = sorted(
        int(y) for y in pd.to_numeric(all_df.get("연도", pd.Series(dtype=float)), errors="coerce").dropna().unique()
    )
    if available_years:
        sel_years = st.multiselect("연도 선택 (복수 선택 가능)", available_years, default=available_years,
                                    key="report_test_years")
        if not sel_years:
            st.warning("연도를 1개 이상 선택해주세요.")
            return
        all_df = all_df[pd.to_numeric(all_df["연도"], errors="coerce").isin(sel_years)]

    st.subheader("직접 조합하기")
    row_dims = st.multiselect("행 기준 (복수 선택 가능)", DIM_OPTIONS, default=["사업장명"], key="report_test_rows")
    col_dim = st.selectbox("열 기준 (선택 안 해도 됨)", [None] + DIM_OPTIONS, key="report_test_col")

    if not row_dims:
        st.warning("행 기준을 1개 이상 선택해주세요.")
        return

    with st.status("리포트 계산 중...", expanded=True) as calc_status:
        st.write("피벗 테이블 계산 중...")
        pivot = build_pivot(all_df, row_dims, col_dim) / 1e8
        if col_dim:
            pivot["합계"] = pivot.sum(axis=1)
        pivot = pivot.round(1)
        calc_status.update(label="리포트 계산 완료", state="complete", expanded=False)

    st.dataframe(pivot, width="stretch")
    st.download_button("엑셀로 내보내기", data=pivot.to_csv().encode("utf-8-sig"),
                        file_name="맞춤리포트.csv", mime="text/csv", key="report_test_download")
