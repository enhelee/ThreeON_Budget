# -*- coding: utf-8 -*-
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

import pandas as pd
import streamlit as st

from budget import config_store, pipeline_plan

APP = os.path.dirname(os.path.abspath(__file__))
CONFIG_DIR = os.path.join(APP, "config")
OUT_DIR = os.path.join(APP, "output")
TEMPLATE_PATH = os.path.join(APP, "templates", "사업별예산_템플릿.xlsx")


def main():
    st.set_page_config(page_title="예산 계획본 생성", layout="wide")
    st.title("중장기 예산 계획본 — 자동 생성")

    st.header("① 구분 · 대상연도 선택")
    col1, col2 = st.columns(2)
    with col1:
        budget = st.radio("구분", ["손익", "자본"], horizontal=True, key="budget")
    with col2:
        year = st.text_input("대상연도", value="2026", key="year")

    st.header("② 지사 구성")
    dept_config = config_store.load_dept_config(CONFIG_DIR, year)
    dept_df = pd.DataFrame(dept_config)
    edited_dept = st.data_editor(
        dept_df, num_rows="dynamic", key=f"dept_editor_{year}",
        column_config={
            "그룹": st.column_config.SelectboxColumn(options=config_store.DEPT_GROUPS),
            "포함": st.column_config.CheckboxColumn(),
        },
    )
    if st.button("✔ 지사 구성 적용 완료", key="apply_dept"):
        config_store.save_dept_config(CONFIG_DIR, year, edited_dept.to_dict("records"))
        st.success(f"{year}년 지사 구성이 저장되었습니다.")

    st.header("③ 예산과목 구성")
    item_config = config_store.load_item_config(CONFIG_DIR, year, budget)
    item_df = pd.DataFrame(item_config)
    edited_item = st.data_editor(
        item_df, num_rows="dynamic", key=f"item_editor_{year}_{budget}",
        column_config={
            "심의대상": st.column_config.CheckboxColumn(),
            "포함": st.column_config.CheckboxColumn(),
        },
    )
    if st.button("✔ 예산과목 구성 적용 완료", key="apply_item"):
        config_store.save_item_config(CONFIG_DIR, year, budget, edited_item.to_dict("records"))
        st.success(f"{year}년 {budget} 과목 구성이 저장되었습니다.")

    st.header("④ 파일 업로드")
    if os.path.exists(TEMPLATE_PATH):
        with open(TEMPLATE_PATH, "rb") as f:
            st.download_button(
                "사업별예산_템플릿 다운로드", f.read(),
                file_name="사업별예산_템플릿.xlsx", key="dl_template",
            )
    plan_file = st.file_uploader("사업별 예산.xlsx", type=["xlsx"], key="plan_upload")

    st.header("⑤ 실행")
    if st.button("분석 실행", type="primary", key="run"):
        if not plan_file:
            st.error("사업별 예산 파일을 업로드하세요.")
        else:
            fd, tmp_path = tempfile.mkstemp(suffix=".xlsx")
            with os.fdopen(fd, "wb") as f:
                f.write(plan_file.getbuffer())
            try:
                res = pipeline_plan.run_plan(tmp_path, CONFIG_DIR, OUT_DIR, year, budget)
            finally:
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
            s = res["요약"]
            with open(res["output_path"], "rb") as f:
                data = f.read()
            st.session_state["result"] = {
                "name": os.path.basename(res["output_path"]),
                "bytes": data,
                "총액": s["총액"], "행수": s["행수"],
                "미분류과목": s["미분류과목"], "결측치건수": s["결측치건수"],
            }

    if "result" in st.session_state:
        r = st.session_state["result"]
        st.success(f"완료: {r['행수']}행, 총액 {r['총액']:,.0f}천원")
        if r["미분류과목"]:
            st.warning("미분류 예산과목: " + ", ".join(r["미분류과목"]))
        if r["결측치건수"]:
            st.warning(f"결측치 {r['결측치건수']}건 — 결과 파일의 '결측치검토' 시트를 확인하세요.")
        st.download_button("결과 파일 다운로드", r["bytes"], file_name=r["name"], key="dl_result")


if __name__ == "__main__":
    main()
