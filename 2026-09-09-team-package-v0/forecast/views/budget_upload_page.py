"""예산 계획 업로드 (신규) 화면"""
import os
import glob
import streamlit as st
import pandas as pd
from budget_upload import parse_budget_workbook, validate_budget_form
from builtin_categories import get_category_for_account


def render():
    st.caption("예산 계획 업로드 · 양식1(월별) + 예산코드 + 부서코드 마스터를 한 번에 처리")
    st.write("실제 사용하시는 예산계획 엑셀 파일(양식1(월별), 예산코드, 부서코드 시트 포함)을 그대로 업로드해주세요. 여러 파일을 한 번에 올릴 수 있습니다.")

    # ---------------- 연도별 예산계획 현황 ----------------
    st.subheader("연도별 예산계획 현황")
    overview_years = sorted(int(f.split("_")[1].split(".")[0]) for f in glob.glob("budget_*.csv"))
    if not overview_years:
        st.info("아직 등록된 예산계획이 없습니다. 아래에서 첫 연도를 업로드하세요.")
    else:
        cols = st.columns(min(len(overview_years), 5))
        for i, y in enumerate(overview_years):
            with cols[i % len(cols)]:
                n_rows = len(pd.read_csv(f"budget_{y}.csv"))
                st.markdown(f"**{y}년**")
                st.markdown("✅")
                st.caption(f"{n_rows}건")

    st.divider()

    # ---------------- 신규 업로드 ----------------
    st.subheader("신규 업로드")
    budget_year = st.number_input("예산 연도", min_value=2000, max_value=2100, value=2026, step=1)
    budget_files = st.file_uploader("예산계획 엑셀 업로드 (.xlsx, 여러 개 선택 가능)", type=["xlsx"],
                                     accept_multiple_files=True, key="budget_uploader")

    if budget_files:
        parsed_results = []  # (파일명, parsed, result) 목록 - 일괄저장에 사용

        for idx, bf in enumerate(budget_files):
            temp_path = f"temp_budget_upload_{idx}.xlsx"
            with open(temp_path, "wb") as f:
                f.write(bf.getbuffer())

            with st.container(border=True):
                st.markdown(f"**파일: {bf.name}**")
                try:
                    parsed = parse_budget_workbook(temp_path)
                except ValueError as e:
                    st.error(str(e))
                    continue
                finally:
                    # 삭제 실패(예: OS/백신이 잠깐 파일을 잡고 있는 경우)는 무시한다 -
                    # 임시파일 하나 못 지운 것 때문에 업로드 자체가 실패하면 안 된다.
                    try:
                        if os.path.exists(temp_path):
                            os.remove(temp_path)
                    except OSError:
                        pass

                st.caption(f"예산코드 마스터 {len(parsed['account_master'])}건 / 부서코드 마스터 {len(parsed['dept_master'])}건 인식됨")
                result = validate_budget_form(parsed["form"], parsed["account_master"], parsed["dept_master"])

                c1, c2 = st.columns(2)
                c1.metric("총 라인 수", result["row_count"])
                c2.metric("오류/경고", result["error_count"])

                if result["errors"]:
                    st.error(f"검토가 필요한 행 ({len(result['errors'])}건)")
                    st.dataframe(pd.DataFrame(result["errors"])[["row", "level", "type", "detail"]],
                                 width="stretch", hide_index=True)

                if not result["data"].empty:
                    preview_data = result["data"].copy()
                    if "예산과목" in preview_data.columns:
                        preview_data["손익자본구분"] = preview_data["예산과목"].apply(get_category_for_account)
                        n_unmapped = (preview_data["손익자본구분"] == "미매핑").sum()
                        if n_unmapped:
                            st.warning(f"손익/자본 미매핑 예산과목 {n_unmapped}건이 있습니다 (내장 목록에 없는 예산과목명).")
                    with st.expander("미리보기"):
                        st.dataframe(preview_data.head(10), width="stretch")
                    parsed_results.append((bf.name, parsed, result))

        if parsed_results:
            st.divider()
            st.subheader("전체 파일 일괄 처리")
            total_lines = sum(len(r["data"]) for _, _, r in parsed_results)
            st.caption(f"업로드된 {len(parsed_results)}개 파일에서 총 {total_lines}건의 예산 라인을 확인했습니다. "
                       f"아래 버튼을 누르면 모든 파일의 사업명·예산 데이터가 한 번에 합쳐져 저장됩니다.")

            if st.button(f"✅ {len(parsed_results)}개 파일 전체 확정해서 한 번에 저장", type="primary"):
                combined_data = pd.concat([r["data"] for _, _, r in parsed_results], ignore_index=True)
                existing_path = f"budget_{int(budget_year)}.csv"
                if os.path.exists(existing_path):
                    existing = pd.read_csv(existing_path)
                    combined_data = pd.concat([existing, combined_data], ignore_index=True)
                combined_data.to_csv(existing_path, index=False)

                all_account = pd.concat([p["account_master"] for _, p, _ in parsed_results], ignore_index=True)
                all_dept = pd.concat([p["dept_master"] for _, p, _ in parsed_results], ignore_index=True)
                if os.path.exists("account_code_master.csv"):
                    all_account = pd.concat([pd.read_csv("account_code_master.csv"), all_account], ignore_index=True)
                if os.path.exists("dept_code_master.csv"):
                    all_dept = pd.concat([pd.read_csv("dept_code_master.csv"), all_dept], ignore_index=True)
                all_account.drop_duplicates().to_csv("account_code_master.csv", index=False)
                all_dept.drop_duplicates().to_csv("dept_code_master.csv", index=False)

                n_projects = combined_data["사업명"].nunique() if "사업명" in combined_data.columns else 0
                st.success(f"{len(parsed_results)}개 파일 전체 저장 완료 · 총 {len(combined_data)}건 "
                           f"(사업명 {n_projects}건) · {int(budget_year)}년 예산계획에 누적됨")

            with st.expander("개별 파일만 따로 저장/제외하고 싶다면 (선택)", expanded=False):
                for name, parsed, result in parsed_results:
                    bcol1, bcol2 = st.columns(2)
                    if bcol1.button(f"'{name}'만 저장", key=f"save_budget_{name}"):
                        existing_path = f"budget_{int(budget_year)}.csv"
                        if os.path.exists(existing_path):
                            existing = pd.read_csv(existing_path)
                            combined = pd.concat([existing, result["data"]], ignore_index=True)
                        else:
                            combined = result["data"]
                        combined.to_csv(existing_path, index=False)
                        st.success(f"'{name}' 저장 완료 ({len(result['data'])}건 추가, 누적 {len(combined)}건)")
                    if bcol2.button(f"'{name}' 제외", key=f"skip_budget_{name}"):
                        st.info(f"'{name}'은 저장하지 않았습니다.")

    st.divider()
    st.subheader("저장된 예산계획 관리")
    saved_years = sorted(int(f.split("_")[1].split(".")[0]) for f in glob.glob("budget_*.csv"))
    if not saved_years:
        st.caption("아직 저장된 예산계획이 없습니다.")
    else:
        manage_year = st.selectbox("연도 선택", saved_years, key="budget_manage_year")
        current = pd.read_csv(f"budget_{manage_year}.csv")
        n_proj = current["사업명"].nunique() if "사업명" in current.columns else 0
        st.caption(f"{manage_year}년 예산계획 — 총 {len(current)}건 저장되어 있음 (사업명 {n_proj}건)")

        if "예산과목" in current.columns:
            current["손익자본구분"] = current["예산과목"].apply(get_category_for_account)
            cat_summary = current.groupby("손익자본구분")["연예산 합계"].sum() / 1e8 if "연예산 합계" in current.columns else None
            if cat_summary is not None:
                cc1, cc2, cc3 = st.columns(3)
                cc1.metric("손익예산", f"{cat_summary.get('손익', 0):.1f}억")
                cc2.metric("자본예산", f"{cat_summary.get('자본', 0):.1f}억")
                cc3.metric("미매핑", f"{cat_summary.get('미매핑', 0):.1f}억")
            with st.expander("손익/자본 구분 포함 상세 보기"):
                st.dataframe(current, width="stretch", hide_index=True)

        confirm_del = st.checkbox(f"{manage_year}년 예산계획을 삭제할래요", key="confirm_del_budget")
        if st.button(f"{manage_year}년 예산계획 삭제", disabled=not confirm_del):
            os.remove(f"budget_{manage_year}.csv")
            st.success(f"{manage_year}년 예산계획을 삭제했습니다.")
            st.rerun()
