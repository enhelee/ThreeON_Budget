# -*- coding: utf-8 -*-
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

import pandas as pd
import streamlit as st

from budget import config_store, pipeline_plan, pipeline_actual

APP = os.path.dirname(os.path.abspath(__file__))
CONFIG_DIR = os.path.join(APP, "config")
OUT_DIR = os.path.join(APP, "output")
TEMPLATE_PATH = os.path.join(APP, "templates", "사업별예산_템플릿.xlsx")


def _save_upload(uploaded, suffix=".xlsx"):
    fd, tmp = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, "wb") as f:
        f.write(uploaded.getbuffer())
    return tmp


def render_plan_tab():
    st.header("① 구분 · 대상연도 선택")
    col1, col2 = st.columns(2)
    with col1:
        budget = st.radio("구분", ["손익", "자본"], horizontal=True, key="p_budget")
    with col2:
        year = st.text_input("대상연도", value="2026", key="p_year")

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
            tmp_path = _save_upload(plan_file)
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
            st.session_state["plan_result"] = {
                "name": os.path.basename(res["output_path"]),
                "bytes": data,
                "총액": s["총액"], "행수": s["행수"],
                "미분류과목": s["미분류과목"], "결측치건수": s["결측치건수"],
            }

    if "plan_result" in st.session_state:
        r = st.session_state["plan_result"]
        st.success(f"완료: {r['행수']}행, 총액 {r['총액']:,.0f}천원")
        if r["미분류과목"]:
            st.warning("미분류 예산과목: " + ", ".join(r["미분류과목"]))
        if r["결측치건수"]:
            st.warning(f"결측치 {r['결측치건수']}건 — 결과 파일의 '결측치검토' 시트를 확인하세요.")
        st.download_button("결과 파일 다운로드", r["bytes"], file_name=r["name"], key="dl_result")


def render_actual_tab():
    st.header("① 구분 · 대상연도 선택")
    col1, col2 = st.columns(2)
    with col1:
        budget = st.radio("구분", ["손익", "자본"], horizontal=True, key="a_budget")
    with col2:
        year = st.text_input("대상연도", value="2025", key="a_year")
    st.caption("지사·예산과목·정규화(별칭) 구성은 '① 계획본 생성' 탭 및 config 폴더에서 관리됩니다.")

    st.header("② 계획본 자료 업로드")
    st.caption(f"1단계 산출물 `{year}년 {budget}예산_계획.xlsx` 의 양식1(월별)을 사용합니다.")
    plan_file = st.file_uploader("계획본.xlsx", type=["xlsx"], key="a_plan_upload")

    st.header("③ ERP 실적자료(zrfm2) 업로드")
    st.caption("SAP에서 추출한 `zrfm2` 파일. 파일명은 반드시 **zrfm2** 로 추출해 주세요.")
    zr_file = st.file_uploader("zrfm2.XLSX", type=["xlsx"], key="a_zr_upload")

    st.header("④ 마스터(코드) 자료 — 선택")
    st.caption("`손익예산26_최종본` (예산코드·부서코드 시트). 계정코드→예산과목 정규화 정확도 향상용. 없으면 텍스트로 매칭.")
    master_file = st.file_uploader("손익예산26_최종본.xlsx", type=["xlsx"], key="a_master_upload")

    st.header("⑤ 분류 정책")
    policy_label = st.radio(
        "신규/계획집행 분류 정책",
        ["그룹 기반 (권장)", "엄격 사업명(80%)"],
        horizontal=True, key="a_policy",
        help=("그룹 기반: (예산과목×처지사)에 계획행이 없을 때만 신규. 계획행 있는 그룹의 "
              "전표는 사업명 최고유사 계획행에 귀속.\n"
              "엄격 사업명: 사업명 유사도 80% 이상만 계획집행(표기 차이로 신규가 과대해질 수 있음)."),
    )
    new_policy = "group" if policy_label.startswith("그룹") else "strict_name"

    st.header("⑥ 실행")
    if st.button("실적 분석 실행", type="primary", key="a_run"):
        if not plan_file or not zr_file:
            st.error("계획본과 zrfm2 파일을 모두 업로드하세요.")
        else:
            plan_tmp = _save_upload(plan_file)
            zr_tmp = _save_upload(zr_file)
            master_tmp = _save_upload(master_file) if master_file else None
            try:
                res = pipeline_actual.run_actual(
                    plan_tmp, zr_tmp, master_tmp, CONFIG_DIR, OUT_DIR, year, budget,
                    new_policy=new_policy,
                )
            finally:
                for p in (plan_tmp, zr_tmp, master_tmp):
                    if p:
                        try:
                            os.remove(p)
                        except OSError:
                            pass
            with open(res["output_path"], "rb") as f:
                actual_bytes = f.read()
            with open(res["zrfm2_v1_path"], "rb") as f:
                v1_bytes = f.read()
            st.session_state["actual_result"] = {
                "name": os.path.basename(res["output_path"]),
                "bytes": actual_bytes,
                "v1_name": os.path.basename(res["zrfm2_v1_path"]),
                "v1_bytes": v1_bytes,
                "요약": res["요약"],
                "미매핑처지사": res["미매핑처지사"],
                "미분류과목": res["미분류과목"],
                "연도불일치": res["연도불일치"],
            }

    if "actual_result" in st.session_state:
        r = st.session_state["actual_result"]
        s = r["요약"]
        st.success(
            f"완료: 총 실적 {s['총 실적(천원)']:,}천원 "
            f"(계획집행 {s['계획집행 실적(천원)']:,} / 신규 {s['신규 실적(천원)']:,})"
        )
        c1, c2, c3 = st.columns(3)
        c1.metric("계획집행 행수", f"{s['계획집행 행수']:,}")
        c2.metric("미시행 행수", f"{s['미시행 행수']:,}")
        c3.metric("신규 행수", f"{s['신규 행수']:,}")
        if r["연도불일치"]:
            st.warning("⚠ " + r["연도불일치"])
        if r["미매핑처지사"]:
            amt = r.get("미매핑처지사금액", 0)
            st.warning(f"미매핑 처지사(종합표 집계 누락 {amt:,}천원): "
                       + ", ".join(r["미매핑처지사"])
                       + " → config/처지사_별칭.json 보강 필요")
        if r["미분류과목"]:
            st.warning("미분류 예산과목: " + ", ".join(r["미분류과목"]))
        st.download_button("실적 결과 파일 다운로드", r["bytes"], file_name=r["name"], key="a_dl_result")
        st.download_button("zrfm2_V1 다운로드", r["v1_bytes"], file_name=r["v1_name"], key="a_dl_v1")


def main():
    st.set_page_config(page_title="중장기 예산 분석", layout="wide")
    st.title("중장기 예산 — 계획·실적 자동 분석")
    tab_plan, tab_actual = st.tabs(["① 계획본 생성", "② 실적 분석"])
    with tab_plan:
        render_plan_tab()
    with tab_actual:
        render_actual_tab()


if __name__ == "__main__":
    main()
