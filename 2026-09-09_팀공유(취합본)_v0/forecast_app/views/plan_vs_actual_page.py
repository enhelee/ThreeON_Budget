"""계획 대비 실적 (신규) 화면"""
import glob
import streamlit as st
from plan_vs_actual import build_plan_vs_actual
from template_fill import (
    list_templates, save_template, delete_template, fill_template,
    diagnose_unmatched_locations,
)


def render():
    st.caption("사업명 기준 · 연예산(A) vs 최종실적금액(B)")
    years_with_budget = sorted(int(f.split("_")[1].split(".")[0]) for f in glob.glob("budget_*.csv"))
    if not years_with_budget:
        st.info("먼저 '예산 계획 업로드'에서 예산계획을 업로드해주세요.")
        st.stop()

    py = st.selectbox("연도 선택", years_with_budget, index=len(years_with_budget) - 1, key="pva_year")
    category_choice = st.radio("구분", ["전체", "손익", "자본"], horizontal=True, key="pva_category")
    category_filter = None if category_choice == "전체" else category_choice

    table = build_plan_vs_actual(py, category_filter=category_filter)
    if table.empty:
        st.warning("표시할 데이터가 없습니다.")
        st.stop()

    with st.expander("🔍 사업명 매칭 진단 (예산/실적 어긋남 확인)", expanded=False):
        budget_only = table[(table["연예산(A)"] > 0) & (table["최종실적금액(B)"] == 0)]
        actual_only = table[(table["연예산(A)"] == 0) & (table["최종실적금액(B)"] > 0)]
        both = table[(table["연예산(A)"] > 0) & (table["최종실적금액(B)"] > 0)]
        d1, d2, d3 = st.columns(3)
        d1.metric("예산만 있음 (실적 0)", f"{len(budget_only)}건")
        d2.metric("실적만 있음 (예산 0)", f"{len(actual_only)}건")
        d3.metric("둘 다 있음", f"{len(both)}건")
        st.caption("'예산만 있음'과 '실적만 있음'이 많다면, 사업명이 예산계획과 실적데이터에서 서로 다르게 "
                   "저장돼 있어(오탈자, 띄어쓰기 등) 매칭이 안 되고 있을 가능성이 높습니다. 아래에서 실제 이름을 비교해보세요.")
        if not budget_only.empty:
            st.write("**예산만 있고 실적이 0인 사업명 (실적 쪽에서 이름이 다를 수 있음)**")
            st.dataframe(budget_only[["사업명", "연예산(A)"]].head(20), width="stretch", hide_index=True)
        if not actual_only.empty:
            st.write("**실적만 있고 예산이 0인 사업명 (예산 쪽에서 이름이 다를 수 있음, 또는 신규사업)**")
            st.dataframe(actual_only[["사업명", "최종실적금액(B)"]].head(20), width="stretch", hide_index=True)

    if (table["손익자본구분"] == "미매핑").any():
        unmapped = table[table["손익자본구분"] == "미매핑"]
        st.warning(f"일부 사업({len(unmapped)}건)의 예산과목이 손익/자본 내장 목록에 없어 구분이 안 됐습니다. "
                   f"예산과목명이 정확한지 확인해주세요. (미매핑 사업: {', '.join(unmapped['사업명'].astype(str).tolist()[:5])}{' 등' if len(unmapped) > 5 else ''})")

    total_a = table["연예산(A)"].sum()
    total_b = table["최종실적금액(B)"].sum()
    c1, c2, c3 = st.columns(3)
    c1.metric("연예산 합계", f"{total_a/1e8:.1f}억")
    c2.metric("실적 합계", f"{total_b/1e8:.1f}억")
    c3.metric("전체 집행률", f"{(total_b/total_a*100):.1f}%" if total_a else "-")

    display = table.copy()
    display["연예산(A)"] = (display["연예산(A)"] / 1e8).round(2)
    display["최종실적금액(B)"] = (display["최종실적금액(B)"] / 1e8).round(2)
    display["차이(B-A)"] = (display["차이(B-A)"] / 1e8).round(2)
    st.dataframe(display, width="stretch", hide_index=True)
    st.caption("금액 단위: 억원")

    st.download_button("엑셀로 내보내기 (간단 CSV)", data=table.to_csv(index=False).encode("utf-8-sig"),
                        file_name=f"{py}년_{category_choice}_계획대비실적.csv", mime="text/csv")

    st.divider()
    st.subheader("실제 결과 양식에 채워서 다운로드")
    st.caption("손익예산·자본예산 양식은 이미 내장되어 있어 별도 업로드 없이 바로 사용할 수 있습니다. "
               "필요하면 추가 양식을 더 등록할 수도 있습니다.")

    templates = list_templates()
    st.caption(f"✅ 사용 가능한 양식 {len(templates)}개: {', '.join(templates.keys())}")

    with st.expander("추가 양식 등록/관리 (선택)", expanded=False):
        new_name = st.text_input("양식 이름", key="template_new_name")
        new_file = st.file_uploader("양식 파일 업로드 (.xlsx)", type=["xlsx"], key="template_new_upload")
        if new_file is not None and new_name.strip():
            if st.button("이 이름으로 양식 등록"):
                save_template(new_name.strip(), new_file.getbuffer())
                st.success(f"'{new_name.strip()}' 양식을 등록했습니다.")
                st.rerun()
        elif new_file is not None and not new_name.strip():
            st.warning("양식 이름을 먼저 입력해주세요.")

        custom_templates = {k: v for k, v in templates.items() if k not in ("손익", "자본")}
        if custom_templates:
            st.divider()
            del_name = st.selectbox("삭제할 양식 선택", list(custom_templates.keys()), key="template_del_select")
            if st.button(f"'{del_name}' 양식 삭제"):
                delete_template(del_name)
                st.success(f"'{del_name}' 양식을 삭제했습니다.")
                st.rerun()

    if templates:
        template_options = list(templates.keys())
        default_idx = template_options.index(category_choice) if category_choice in template_options else 0
        fill_template_name = st.selectbox("채울 양식 선택", template_options, index=default_idx, key="fill_template_select")

        diag = diagnose_unmatched_locations(py, fill_template_name, category_filter=category_filter)
        if diag["unmatched_count"] > 0:
            st.warning(f"⚠️ 종합표에서 집계되지 않을 항목이 {diag['unmatched_count']}건, "
                       f"{diag['unmatched_amount']/1e8:.1f}억원 있습니다. "
                       f"'예산귀속 부서명(처.지사)'이 이 양식이 인식하는 24개 지사/부서명과 다르기 때문입니다.")
            with st.expander("어떤 항목이 빠지는지 보기"):
                st.dataframe(diag["items"], width="stretch", hide_index=True)
                st.caption(f"양식이 인식하는 지사/부서명 24개: {', '.join(sorted(diag['known_locations']))}")

        if st.button(f"{py}년 [{category_choice}] 결과를 '{fill_template_name}' 양식에 채워서 만들기"):
            try:
                safe_cat = category_choice
                out_path = f"filled_{py}_{safe_cat}_결과.xlsx"
                fill_template(py, fill_template_name, out_path, category_filter=category_filter)
                with open(out_path, "rb") as f:
                    file_bytes = f.read()
                # 세션에 저장해두어야 아래 다운로드 버튼이 이후 재실행에서도 계속 남아있는다.
                # (st.button 블록 안에서만 st.download_button을 그리면, 한 번이라도 다시 그려질 때
                #  버튼이 사라져버리는 Streamlit의 흔한 함정을 피하기 위함)
                st.session_state["filled_template_bytes"] = file_bytes
                st.session_state["filled_template_filename"] = f"{py}년_{safe_cat}_{fill_template_name}.xlsx"
            except Exception as e:
                st.error(f"양식을 채우는 중 오류가 발생했습니다: {e}")

        if st.session_state.get("filled_template_bytes"):
            st.download_button(
                "채워진 엑셀 다운로드",
                data=st.session_state["filled_template_bytes"],
                file_name=st.session_state["filled_template_filename"],
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
