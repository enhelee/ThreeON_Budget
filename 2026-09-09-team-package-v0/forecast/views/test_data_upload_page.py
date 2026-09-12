"""Test 모드 · 계획 및 실적 업로드

Test 모드의 '실적집계 대시보드'에서 '배정 대비 실적'을 계산하려면 예산계획(배정)과 실적이 모두
있어야 한다. 이 화면이 Test 모드에서 그 둘을 올리는 단일 창구다.

예산계획은 연도별로 저장되며(longterm_forecast.save_test_budget_plan/load_test_budget_plan),
BASE_YEAR(당해년도)분은 '중장기 예산 (26-35년)' Test 모드와 같은 저장소를 공유한다.

실적은 '실적 업데이트(zrfm2)' 정식 화면과 같은 원본 엑셀을 그대로 올릴 수 있다(validate_upload로
정리). 예측 -> 확인/수정 -> 저장 로직은 '투자유형 예측 테스트'와 완전히 같은 함수
(project_type_test_page.render_predict_review_and_save)를 그대로 재사용한다 - 입력 방식만 다를 뿐
분류·저장 방식은 하나로 유지한다. 이미 정리된 파일을 올려 칸을 직접 지정하고 싶으면 '투자유형
예측 테스트' 화면을 대신 이용하면 된다.
"""
import os
import pandas as pd
import streamlit as st
import longterm_forecast as lf
import project_type_classifier as ptc
from budget_upload import parse_budget_workbook, validate_budget_form
from validate_upload import validate_upload
from views.project_type_test_page import get_shared_actual_df, render_predict_review_and_save


def _render_zrfm2_upload():
    """'실적 업데이트(zrfm2)' 화면과 같은 원본 엑셀을 그대로 올려 validate_upload()로 정리한다
    (합계행/KSV5/역분개/인지세/상쇄전표를 자동으로 걸러낸다). zrfm2 원본에는 '사업명'이 없어
    '전표헤더텍스트'를 사업명 대신 쓴다. 반환: (정리된 DataFrame, 사업명칸, 예산과목칸, 사업장칸,
    금액칸, 금액단위, 연도) - 아직 업로드가 없으면 전부 None."""
    ref_year = st.number_input("실적 연도 (저장 시 이 연도로 기록됩니다 - 전기일 연도가 다르면 경고만 표시)",
                                min_value=2000, max_value=2100, value=2025, step=1, key="tdata_zrfm2_year")
    files = st.file_uploader("zrfm2 원본 엑셀 업로드 (.xlsx, 여러 개 가능)", type=["xlsx"],
                              accept_multiple_files=True, key="tdata_zrfm2_upload")
    if not files:
        return None, None, None, None, None, None, None

    frames = []
    for f in files:
        temp_path = f"temp_upload_tdata_zrfm2_{f.name}.xlsx"
        with open(temp_path, "wb") as out:
            out.write(f.getbuffer())
        try:
            result = validate_upload(temp_path, year=int(ref_year))
        finally:
            try:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            except OSError:
                pass

        with st.container(border=True):
            st.markdown(f"**파일: {f.name}**")
            if result.get("summary_row_excluded"):
                st.caption("마지막 행을 합계행으로 판단해 제외했습니다.")
            if result.get("excluded_by_code_count"):
                st.caption(f"트랜잭션 코드 'KSV5' {result['excluded_by_code_count']}건을 제외했습니다.")
            if result.get("excluded_by_reversal_count"):
                st.caption(f"역분개(취소전표) 상쇄 {result['excluded_by_reversal_count']}건을 제외했습니다.")
            if result.get("merged_stamp_tax_count"):
                st.caption(f"인지세 {result['merged_stamp_tax_count']}건을 관련 전표에 합산했습니다.")
            if result.get("excluded_by_text_offset_count"):
                st.caption(f"상쇄되는 전표 {result['excluded_by_text_offset_count']}건을 제외했습니다.")
            c1, c2, c3 = st.columns(3)
            c1.metric("총 건수", result["row_count"])
            c2.metric("유효 건수", result["valid_row_count"])
            c3.metric("오류 행", result["error_count"])
            if result["errors"]:
                st.dataframe(pd.DataFrame(result["errors"])[["row", "level", "type", "detail"]],
                             width="stretch", hide_index=True)
        if not result["data"].empty:
            frames.append(result["data"])

    if not frames:
        return None, None, None, None, None, None, None

    combined = pd.concat(frames, ignore_index=True)
    st.caption(f"zrfm2 원본에서 {len(combined)}건을 인식했습니다. 사업명 정보가 없어 '전표헤더텍스트'를 "
               "사업명 대신 씁니다(사업명만큼 정확하진 않을 수 있습니다). 사업장·계정과목·금액 칸은 "
               "자동으로 맞춰졌습니다.")
    return combined, "전표헤더텍스트", "계정과목", "사업장", "금액", "원", int(ref_year)


def render():
    st.caption("Test 모드 · 계획 및 실적 업로드")
    st.info("🧪 여기서 올린 예산계획과 실적을 합쳐, Test 모드 '실적집계 대시보드'의 '배정 대비 실적'을 "
            "계산합니다. 실제 데이터 파이프라인과는 무관합니다.")

    st.subheader("1) 예산계획 업로드")
    st.caption("'예산 계획 업로드' 화면과 같은 양식(양식1(월별)/예산코드/부서코드 시트)입니다. "
               "손익예산/자본예산/건설예산처럼 여러 파일로 나뉘어 있으면 한 번에 모두 선택해 올리면 "
               "합쳐서 반영됩니다. 새로 올리면 그 연도의 기존 백데이터만 교체합니다(다른 연도는 유지). "
               "'중장기 예산 (26-35년)' Test 모드와 같은 예산계획을 공유합니다(단, 그 화면은 "
               f"{lf.BASE_YEAR}년 당해년도 예산만 사용합니다).")
    budget_year = st.number_input("예산 연도", min_value=2000, max_value=2100, value=lf.BASE_YEAR, step=1,
                                   key="tdata_budget_year")
    budget_upload_files = st.file_uploader("예산계획 엑셀(.xlsx, 여러 개 선택 가능)", type=["xlsx"],
                                            accept_multiple_files=True, key="tdata_budget_upload")
    if budget_upload_files:
        parsed_results = []  # (파일명, result) 목록 - 합쳐서 저장하는 데 사용
        for idx, bf in enumerate(budget_upload_files):
            temp_path = f"temp_budget_upload_tdata_{idx}.xlsx"
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
            if st.button("이 예산계획을 백데이터로 저장", key="tdata_budget_apply"):
                lf.save_test_budget_plan(combined_data, year=int(budget_year))
                st.success(f"{int(budget_year)}년 예산계획으로 저장했습니다.")
                st.rerun()

    test_budget_years = lf.load_test_budget_plan_years()
    if not test_budget_years:
        st.caption("현재 저장된 예산계획 백데이터가 없습니다.")
    else:
        st.caption("현재 저장된 예산계획 백데이터 (연도별):")
        cols = st.columns(min(len(test_budget_years), 5))
        for i, y in enumerate(test_budget_years):
            with cols[i % len(cols)]:
                st.markdown(f"**{y}년**")
                st.caption(f"{len(lf.load_test_budget_plan(y))}건")

    st.divider()
    st.subheader("2) 실적 업로드 (zrfm2 원본)")
    st.caption("'실적 업데이트(zrfm2)' 화면과 같은 원본 엑셀을 그대로 올리면 자동으로 정리하고, "
               "학습된 모델로 투자유형을 예측합니다. 이미 정리된 파일에서 칸을 직접 지정하고 싶다면 "
               "'투자유형 예측 테스트' 화면을 이용해주세요.")
    if not ptc.has_any_model():
        st.info("아직 학습된 모델이 없습니다. '투자유형 학습 (분류자료)' 화면에서 먼저 학습을 완료해주세요.")
    else:
        combined, col_name, col_acct, col_site, col_amt, amt_unit, year = _render_zrfm2_upload()
        if combined is not None:
            render_predict_review_and_save(combined, col_name, col_acct, col_site, col_amt, amt_unit, year)

    st.divider()
    st.subheader("3) 실적 연동 상태")
    shared = get_shared_actual_df()
    if shared is None or shared.empty:
        st.warning("아직 실적이 없습니다. 위에서 zrfm2 원본을 올리고 결과를 저장하거나, "
                   "'투자유형 예측 테스트' 화면에서 실적을 확정하고 저장해주세요.")
    else:
        has_site = not (shared["사업장"].astype(str).str.strip() == "").all()
        has_amount = shared["금액"].sum() != 0
        if has_site and has_amount:
            st.success(f"✅ 확정한 실적 {len(shared)}건이 연동되어 있습니다.")
        else:
            st.warning("실적을 확정했지만, '사업장' 또는 '금액' 칸을 지정하지 않아 "
                       "지사유형·계정과목 기준 집계가 제한됩니다.")
        with st.expander("연동된 실적 미리보기"):
            st.dataframe(shared.head(20), width="stretch", hide_index=True)

    st.divider()
    ready = bool(test_budget_years) and shared is not None and not shared.empty
    if ready:
        st.success("✅ 예산계획과 실적이 모두 준비되었습니다. Test 모드 '실적집계 대시보드'에서 "
                   "'배정 대비 실적'을 확인해보세요.")
    else:
        st.caption("예산계획과 실적이 모두 있어야 '배정 대비 실적'을 계산할 수 있습니다.")
