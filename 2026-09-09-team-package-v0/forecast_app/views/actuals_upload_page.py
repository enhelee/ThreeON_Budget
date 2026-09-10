"""실적 업데이트(zrfm2) & 검증 화면 (기본/홈 페이지)"""
import os
import streamlit as st
import pandas as pd
from validate_upload import validate_upload
from year_status import (
    save_status, add_year, set_year_result, get_visible_cells,
    next_addable_year, prev_addable_year, clear_year_data, remove_year,
)


def render(status):
    st.caption("실적 업데이트(zrfm2)")

    # ---------------- 연도별 현황판 (5칸 고정) ----------------
    st.subheader("연도별 데이터 현황")
    cells = get_visible_cells(status)

    if not cells:
        st.info("아직 등록된 연도가 없습니다. 아래에서 첫 연도를 추가하세요.")
    else:
        cols = st.columns(5)
        for i, cell in enumerate(cells):
            with cols[i]:
                if cell["type"] == "group":
                    st.markdown(f"**{cell['label']}**")
                    if st.button("펼쳐보기", key=f"grp_{cell['label']}"):
                        st.session_state["expand_group"] = cell["years"]
                else:
                    icon = {"done": "✅", "warning": "⚠️", "empty": "➖"}[cell["state"]]
                    st.markdown(f"**{cell['year']}**")
                    st.markdown(icon)

        if st.session_state.get("expand_group"):
            group_years = st.session_state["expand_group"]
            group_label = f"{group_years[0]}~{group_years[-1]}"
            with st.expander(f"{group_label} 개별 현황", expanded=True):
                for y in group_years:
                    info = status.get(str(y), {})
                    st.write(f"{y}년 — 건수 {info.get('row_count', 0)} / 오류 {info.get('error_count', 0)}")

    st.divider()

    # ---------------- 새 연도 추가 (다음 연도 / 이전 연도) ----------------
    add_col1, add_col2 = st.columns(2)
    next_year = next_addable_year(status)
    prev_year = prev_addable_year(status)
    with add_col1:
        if st.button(f"＋ {next_year}년 칸 추가하기 (최신)"):
            status = add_year(status, next_year)
            save_status(status)
            st.rerun()
    with add_col2:
        if st.button(f"＋ {prev_year}년 칸 추가하기 (과거)"):
            status = add_year(status, prev_year)
            save_status(status)
            st.rerun()

    # ---------------- 업로드 ----------------
    st.subheader("신규 업로드")
    available_years = sorted(int(y) for y in status.keys()) if status else []
    if not available_years:
        st.warning("먼저 위에서 연도 칸을 추가해주세요.")
    else:
        selected_year = st.selectbox("연도 선택", available_years, index=len(available_years) - 1)
        already = status.get(str(selected_year), {}).get("uploaded", False)
        if already:
            st.caption(f"⚠️ {selected_year}년은 이미 데이터가 있습니다. 다시 업로드하면 덮어씁니다.")
        else:
            st.caption(f"{selected_year}년은 아직 데이터가 없습니다.")

        uploaded_file = st.file_uploader("엑셀 파일 (.xlsx)", type=["xlsx"])

        if uploaded_file is not None:
            with open("temp_upload.xlsx", "wb") as f:
                f.write(uploaded_file.getbuffer())

            result = validate_upload("temp_upload.xlsx", year=selected_year)

            if result.get("summary_row_excluded"):
                st.info("마지막 행을 합계행으로 판단해 집계에서 제외했습니다.")

            if result.get("filled_text_count"):
                st.info(f"특정 예산과목 3종의 텍스트 {result['filled_text_count']}건을 '날짜+구매' 형식으로 통일했습니다.")

            if result.get("excluded_by_code_count"):
                st.info(f"트랜잭션 코드가 'KSV5'인 행 {result['excluded_by_code_count']}건을 분류 대상에서 제외했습니다.")

            if result.get("excluded_by_reversal_count"):
                st.info(f"역분개(취소전표)와 원본전표가 상쇄되는 {result['excluded_by_reversal_count']}건을 분류 대상에서 제외했습니다.")

            if result.get("merged_stamp_tax_count"):
                st.info(f"인지세 {result['merged_stamp_tax_count']}건을 같은 참조전표번호의 항목에 합산했습니다.")

            if result.get("excluded_by_text_offset_count"):
                st.info(f"같은 텍스트의 +전표/-전표가 상쇄되는 {result['excluded_by_text_offset_count']}건을 분류 대상에서 제외했습니다.")

            c1, c2, c3 = st.columns(3)
            c1.metric("총 건수", result["row_count"])
            c2.metric("유효 건수", result["valid_row_count"])
            c3.metric("오류 행", result["error_count"])

            if result["errors"]:
                st.error(f"검토가 필요한 행 ({len(result['errors'])}건)")
                st.dataframe(pd.DataFrame(result["errors"])[["row", "level", "type", "detail"]],
                             width="stretch", hide_index=True)

            if st.button("이 결과로 저장하기"):
                status = set_year_result(status, selected_year, result["row_count"], result["error_count"], result["errors"])
                save_status(status)
                result["data"].to_csv(f"data_{selected_year}.csv", index=False)
                st.success(f"{selected_year}년 데이터 저장 완료")
                st.rerun()

    st.divider()

    # ---------------- 삭제 / 재업로드 관리 ----------------
    st.subheader("데이터 삭제 / 재업로드")
    existing_years = sorted(int(y) for y in status.keys()) if status else []
    if not existing_years:
        st.caption("삭제할 데이터가 없습니다.")
    else:
        del_year = st.selectbox("연도 선택", existing_years, key="del_year_select")
        del_info = status.get(str(del_year), {})
        st.caption(f"{del_year}년 — 건수 {del_info.get('row_count', 0)} / 오류 {del_info.get('error_count', 0)} "
                   f"/ 상태: {'업로드됨' if del_info.get('uploaded') else '미업로드'}")

        dc1, dc2 = st.columns(2)
        with dc1:
            st.caption("데이터만 지우고 이 연도 칸은 남겨서 다시 업로드")
            if st.button(f"{del_year}년 데이터 삭제 (재업로드용)"):
                status = clear_year_data(status, del_year)
                save_status(status)
                for f in [f"data_{del_year}.csv", f"classified_{del_year}.csv", f"matched_{del_year}.csv"]:
                    if os.path.exists(f):
                        os.remove(f)
                st.success(f"{del_year}년 데이터를 삭제했습니다. 위 '신규 업로드'에서 다시 올려주세요.")
                st.rerun()
        with dc2:
            st.caption("⚠️ 연도 칸 자체를 삭제 (잘못 추가한 연도를 없앨 때)")
            confirm_remove = st.checkbox(f"{del_year}년 칸을 완전히 삭제할래요", key="confirm_remove_year")
            if st.button(f"{del_year}년 칸 완전 삭제", disabled=not confirm_remove):
                status = remove_year(status, del_year)
                save_status(status)
                for f in [f"data_{del_year}.csv", f"classified_{del_year}.csv", f"matched_{del_year}.csv"]:
                    if os.path.exists(f):
                        os.remove(f)
                st.success(f"{del_year}년 칸을 삭제했습니다.")
                st.rerun()

        st.caption("참고: 이미 '모델 관리'의 학습 데이터로 반영된 내용은 여기서 자동으로 빠지지 않습니다. "
                   "필요하면 '모델 관리'에서 학습 데이터를 직접 수정/재업로드해주세요.")
