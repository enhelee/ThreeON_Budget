"""사업 매칭 (신규) 화면"""
import streamlit as st
import pandas as pd
from mapping_config import get_site_display_name
from project_matching import (
    load_project_master, save_project_master, build_master_from_budget,
    load_extra_projects, add_extra_project, match_dataframe_by_category,
    suggest_low_value_buckets, SMALL_AMOUNT_THRESHOLD, apply_single_project_override,
    suggest_uncategorized_buckets, MATCH_CONFIDENCE_THRESHOLD,
)


def render(status):
    st.caption("전표를 예산계획의 '사업명'과 매칭 · 투자유형과는 별개의 분류축입니다")

    uploaded_years = [int(y) for y, v in status.items() if v.get("uploaded")]
    if not uploaded_years:
        st.info("먼저 '실적 업데이트(zrfm2)'에서 데이터를 업로드해주세요.")
        st.stop()

    year = st.selectbox("연도 선택", sorted(uploaded_years, reverse=True), key="proj_year")

    budget_master = build_master_from_budget(year)
    if budget_master.empty:
        st.warning(f"{year}년 예산계획이 아직 없어 자동으로 사업명을 가져올 수 없습니다. "
                   f"'예산 계획 업로드'에서 먼저 올려주세요.")
        with st.expander("대신 사업 마스터 목록을 직접 업로드하기 (예산계획이 없을 때만 사용)", expanded=False):
            upload_master = st.file_uploader("사업 마스터 목록 업로드 (.csv 또는 .xlsx, '사업코드'/'사업명' 컬럼 필요)", type=["csv", "xlsx"])
            if upload_master is not None:
                if upload_master.name.endswith(".xlsx"):
                    new_master = pd.read_excel(upload_master)
                else:
                    new_master = pd.read_csv(upload_master)
                if {"사업코드", "사업명"}.issubset(new_master.columns):
                    st.dataframe(new_master.head(), width="stretch", hide_index=True)
                    if st.button("이 목록으로 저장(덮어쓰기)"):
                        save_project_master(new_master[["사업코드", "사업명"]])
                        st.success(f"{len(new_master)}건 저장 완료")
                        st.rerun()
                else:
                    st.error("'사업코드', '사업명' 컬럼이 필요합니다.")
        budget_master = load_project_master()
        if budget_master.empty:
            st.stop()
    else:
        st.caption(f"{year}년 예산계획에서 사업명 {len(budget_master)}건을 자동으로 가져왔습니다.")
        with st.expander("가져온 사업명 목록 보기"):
            st.dataframe(budget_master, width="stretch", hide_index=True)

    extra_projects = load_extra_projects()
    master = pd.concat([budget_master, extra_projects], ignore_index=True).drop_duplicates(subset="사업명").reset_index(drop=True)
    if not extra_projects.empty:
        st.caption(f"+ 신규 등록한 사업 {len(extra_projects)}건 포함")

    try:
        df = pd.read_csv(f"data_{year}.csv")
    except FileNotFoundError:
        st.warning("이 연도의 저장된 데이터가 없습니다.")
        st.stop()

    progress_bar = st.progress(0, text="사업 매칭 계산 중... 0%")

    def _update_progress(frac):
        progress_bar.progress(frac, text=f"사업 매칭 계산 중... {int(frac * 100)}%")

    matched = match_dataframe_by_category(df, master, progress_callback=_update_progress)
    progress_bar.empty()
    matched = apply_single_project_override(matched, master)
    threshold = MATCH_CONFIDENCE_THRESHOLD
    low_conf = matched[matched["매칭확신도"] < threshold]
    high_conf = matched[matched["매칭확신도"] >= threshold]
    total = len(matched)
    high_pct = len(high_conf) / total * 100 if total else 0
    low_pct = len(low_conf) / total * 100 if total else 0

    st.subheader("매칭 진행 현황")
    c1, c2, c3 = st.columns(3)
    c1.metric("전체", total)
    c2.metric("확신 높음", f"{len(high_conf)}건 ({high_pct:.0f}%)")
    c3.metric("검토 필요", f"{len(low_conf)}건 ({low_pct:.0f}%)")
    progress_df = pd.DataFrame({"건수": [len(high_conf), len(low_conf)]}, index=["확신 높음", "검토 필요"])
    st.bar_chart(progress_df, horizontal=True)

    st.divider()
    st.subheader(f"소액 건 자동 분류 ({SMALL_AMOUNT_THRESHOLD/10000:.0f}만원 이하)")
    st.caption(f"검토 대상 중 소액 건은 지사별로 자동 묶여 **'{{지사}} 설비개선, 보완 및 소액구매'**로 바로 확정됩니다. "
               "이상한 게 있으면 체크 해제해서 아래 개별 검토로 빼서 따로 확인할 수 있습니다.")

    bucket_confirmed_indices = set()
    bucket_assignments = {}
    buckets = suggest_low_value_buckets(low_conf) if not low_conf.empty else pd.DataFrame()

    if buckets.empty:
        st.caption("소액 건이 없습니다.")
    else:
        total_small = buckets["건수"].sum()
        st.caption(f"총 {len(buckets)}개 지사, {total_small}건이 자동 확정 대상입니다.")

        PAGE_SIZE = 20
        show_all = st.session_state.get(f"bucket_show_all_{year}", False)
        visible_buckets = buckets if show_all else buckets.iloc[:PAGE_SIZE]

        for bi, brow in visible_buckets.iterrows():
            confirm_key = f"bucket_confirm_{year}_{bi}"
            # 기본값 True: 소액 건은 기본적으로 자동 확정. 이상하면 체크 해제해서 개별 검토로 뺀다.
            with st.container(border=True):
                bc1, bc2 = st.columns([3, 1])
                bc1.write(f"**{brow['추천사업명']}** — {brow['건수']}건, 합계 {brow['합계금액']/1e8:.2f}억")
                confirm = bc2.checkbox("자동확정 유지", key=confirm_key, value=True)
                with st.expander(f"포함된 {brow['건수']}건 보기"):
                    detail = low_conf.loc[brow["행인덱스"], ["전표헤더텍스트", "금액"]].copy()
                    detail["금액"] = detail["금액"].apply(lambda v: f"{v:,.0f}원")
                    st.dataframe(detail, width="stretch", hide_index=True)

            if confirm:
                for idx in brow["행인덱스"]:
                    bucket_assignments[idx] = brow["추천사업명"]
                    bucket_confirmed_indices.add(idx)

        if not show_all and len(buckets) > PAGE_SIZE:
            if st.button(f"더보기 (전체 {len(buckets)}개 중 {PAGE_SIZE}개 표시 중)"):
                st.session_state[f"bucket_show_all_{year}"] = True
                st.rerun()

    low_conf_remaining = low_conf.drop(index=list(bucket_confirmed_indices), errors="ignore")

    st.divider()
    st.subheader("나머지 항목 - 예산과목별 미분류 묶음")
    st.caption("소액 자동확정 등으로 처리되지 않은 나머지 항목을 예산과목별로 묶었습니다. "
               "확인 후 '확정'을 누르면 '{예산과목}_미분류'로 합쳐서 저장됩니다. 확정하지 않은 건 아래 개별 검토에 남습니다.")

    uncategorized_confirmed_indices = set()
    uncategorized_assignments = {}
    uncategorized_buckets = suggest_uncategorized_buckets(low_conf_remaining) if not low_conf_remaining.empty else pd.DataFrame()

    if uncategorized_buckets.empty:
        st.caption("묶을 항목이 없습니다.")
    else:
        for ui, urow in uncategorized_buckets.iterrows():
            with st.container(border=True):
                uc1, uc2 = st.columns([3, 1])
                uc1.write(f"**{urow['추천사업명']}** — {urow['건수']}건, 합계 {urow['합계금액']/1e8:.2f}억")
                confirm_uncat = uc2.checkbox("확정", key=f"uncat_confirm_{year}_{ui}")
                with st.expander(f"포함된 {urow['건수']}건 보기"):
                    detail = low_conf_remaining.loc[urow["행인덱스"], ["전표헤더텍스트", "금액"]].copy()
                    detail["금액"] = detail["금액"].apply(lambda v: f"{v:,.0f}원" if pd.notna(v) else "-")
                    st.dataframe(detail, width="stretch", hide_index=True)

            if confirm_uncat:
                for idx in urow["행인덱스"]:
                    uncategorized_assignments[idx] = urow["추천사업명"]
                    uncategorized_confirmed_indices.add(idx)

    low_conf_remaining = low_conf_remaining.drop(index=list(uncategorized_confirmed_indices), errors="ignore")

    NEW_PROJECT_OPTION = "🆕 신규 사업으로 등록"

    st.divider()
    st.subheader("일괄 매칭 - 여러 건을 한 번에 같은 사업으로 확정")
    st.caption("같은 사업으로 묶을 항목들을 아래 표에서 체크하고, 확정할 사업을 선택하세요. "
               "맨 아래 '저장' 버튼을 눌러야 최종 반영됩니다 (개별 검토 없이 한 번에 처리됩니다).")

    bulk_confirmed_indices = set()
    bulk_assignments = {}

    if low_conf_remaining.empty:
        st.caption("일괄 매칭할 항목이 없습니다.")
    else:
        bulk_target_options = master["사업명"].tolist() + [NEW_PROJECT_OPTION]
        bulk_target = st.selectbox("일괄 확정할 사업", bulk_target_options, key=f"bulk_target_{year}")
        bulk_new_name = ""
        if bulk_target == NEW_PROJECT_OPTION:
            bulk_new_name = st.text_input("신규 사업명 입력", key=f"bulk_new_name_{year}")

        bulk_display = low_conf_remaining[["전표헤더텍스트", "금액"]].copy()
        if "계정과목" in low_conf_remaining.columns:
            bulk_display.insert(0, "예산과목", low_conf_remaining["계정과목"])
        bulk_display["금액"] = bulk_display["금액"].apply(lambda v: f"{v:,.0f}원" if pd.notna(v) else "-")
        bulk_display.insert(0, "선택", False)

        edited_bulk = st.data_editor(
            bulk_display, width="stretch", key=f"bulk_match_editor_{year}",
            disabled=[c for c in bulk_display.columns if c != "선택"],
            column_config={"선택": st.column_config.CheckboxColumn("선택")},
        )
        selected_idx = edited_bulk.index[edited_bulk["선택"]].tolist()

        if selected_idx:
            target_name = bulk_new_name.strip() if bulk_target == NEW_PROJECT_OPTION else bulk_target
            if target_name:
                st.caption(f"✅ {len(selected_idx)}건이 저장 시 '{target_name}'(으)로 확정됩니다.")
                for idx in selected_idx:
                    bulk_assignments[idx] = target_name
                    bulk_confirmed_indices.add(idx)
            else:
                st.warning("신규 사업명을 입력해야 일괄 확정에 반영됩니다.")

    low_conf_remaining = low_conf_remaining.drop(index=list(bulk_confirmed_indices), errors="ignore")

    st.divider()
    st.subheader(f"검토 필요 항목부터 ({len(low_conf_remaining)}건)")
    st.caption("같은 예산과목(계정과목) 안의 사업명만 후보로 보여드립니다. "
               "예산계획에 없는 신규 사업이거나, 반대로 올해 시행하지 않은 사업일 수 있습니다. "
               "마스터에 맞는 게 없으면 '🆕 신규 사업으로 등록'을 선택해 직접 이름을 입력해주세요.")
    has_category = "예산과목" in master.columns and "계정과목" in low_conf_remaining.columns

    auto_use_own_text = False
    if not low_conf_remaining.empty:
        auto_use_own_text = st.checkbox(
            f"나머지 {len(low_conf_remaining)}건은 개별 검토 없이, 전표헤더텍스트를 그대로 사업명으로 신규 등록",
            key=f"auto_own_text_{year}",
        )

    edited = {}
    new_names = {}
    own_text_indices = []

    if auto_use_own_text:
        with st.expander(f"전표명으로 등록될 {len(low_conf_remaining)}건 미리보기"):
            preview = low_conf_remaining[["전표헤더텍스트", "금액"]].copy()
            preview["금액"] = preview["금액"].apply(lambda v: f"{v:,.0f}원" if pd.notna(v) else "-")
            st.dataframe(preview, width="stretch", hide_index=True)
        own_text_indices = low_conf_remaining.index.tolist()
    else:
        for i, row in low_conf_remaining.iterrows():
            with st.container(border=True):
                row_category = row.get("계정과목") if has_category else None
                amt = row.get("금액")
                amt_text = f"{amt:,.0f}원" if pd.notna(amt) else "-"
                site_name = get_site_display_name(row.get("사업장")) if pd.notna(row.get("사업장")) else "-"
                st.caption(f"{site_name}  ·  매칭확신도 {int(row['매칭확신도']*100)}%  ·  금액: {amt_text}"
                           + (f"  ·  예산과목: {row_category}" if row_category else ""))
                st.write(f"\"{row['전표헤더텍스트']}\"")

                if has_category and row_category is not None:
                    same_category_names = master[master["예산과목"] == row_category]["사업명"].tolist()
                else:
                    same_category_names = master["사업명"].tolist()
                project_options = same_category_names + [NEW_PROJECT_OPTION, "해당없음/미분류"]

                default_idx = project_options.index(row["사업명"]) if row["사업명"] in project_options else len(project_options) - 1
                choice = st.selectbox("사업 확정", project_options, index=default_idx, key=f"proj_sel_{year}_{i}")
                edited[i] = choice
                if choice == NEW_PROJECT_OPTION:
                    new_name = st.text_input("신규 사업명 입력", key=f"new_proj_name_{year}_{i}")
                    new_names[i] = (new_name, row_category)

    st.divider()
    if st.button(f"확신 높은 {len(high_conf)}건 + 소액그룹 {len(bucket_confirmed_indices)}건 + "
                 f"미분류묶음 {len(uncategorized_confirmed_indices)}건 + 일괄매칭 {len(bulk_confirmed_indices)}건 + "
                 f"전표명 신규등록 {len(own_text_indices)}건 저장"):
        final = matched.copy()

        for idx in own_text_indices:
            own_name = str(final.loc[idx, "전표헤더텍스트"]).strip()
            own_category = final.loc[idx, "계정과목"] if "계정과목" in final.columns else None
            add_extra_project(own_name, category=own_category)
            final.loc[idx, "사업명"] = own_name
            final.loc[idx, "사업코드"] = None

        for i, choice in edited.items():
            if choice == NEW_PROJECT_OPTION:
                actual_name, row_category = new_names.get(i, ("", None))
                actual_name = actual_name.strip()
                if not actual_name:
                    st.error("신규 사업명을 입력하지 않은 항목이 있습니다. 입력 후 다시 저장해주세요.")
                    st.stop()
                add_extra_project(actual_name, category=row_category)
                final.loc[i, "사업명"] = actual_name
                final.loc[i, "사업코드"] = None
            else:
                final.loc[i, "사업명"] = choice
                match_row = master[master["사업명"] == choice]
                final.loc[i, "사업코드"] = match_row["사업코드"].iloc[0] if not match_row.empty else None

        for idx, bucket_name in bucket_assignments.items():
            row_category = final.loc[idx, "계정과목"] if "계정과목" in final.columns else None
            add_extra_project(bucket_name, category=row_category)
            final.loc[idx, "사업명"] = bucket_name
            final.loc[idx, "사업코드"] = None

        for idx, uncat_name in uncategorized_assignments.items():
            row_category = final.loc[idx, "계정과목"] if "계정과목" in final.columns else None
            add_extra_project(uncat_name, category=row_category)
            final.loc[idx, "사업명"] = uncat_name
            final.loc[idx, "사업코드"] = None

        for idx, bulk_name in bulk_assignments.items():
            match_row = master[master["사업명"] == bulk_name]
            if match_row.empty:
                row_category = final.loc[idx, "계정과목"] if "계정과목" in final.columns else None
                add_extra_project(bulk_name, category=row_category)
                final.loc[idx, "사업코드"] = None
            else:
                final.loc[idx, "사업코드"] = match_row["사업코드"].iloc[0]
            final.loc[idx, "사업명"] = bulk_name

        final.to_csv(f"matched_{year}.csv", index=False)
        st.success(f"{year}년 사업 매칭 결과 저장 완료 ({len(final)}건, 소액그룹 {len(bucket_assignments)}건 · "
                   f"미분류묶음 {len(uncategorized_assignments)}건 · 일괄매칭 {len(bulk_assignments)}건 · "
                   f"전표명 신규등록 {len(own_text_indices)}건 포함)")
