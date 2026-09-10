# -*- coding: utf-8 -*-
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

import pandas as pd
import streamlit as st

from budget import config_store, pipeline_plan, pipeline_actual
from budget import db as dbm
from budget import pipeline_db

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
            "실적반영": st.column_config.CheckboxColumn(
                help="해제하면 계획본에는 그대로 두고 실적 산출물에서만 제외합니다."),
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

    st.header("② 지사 구성 (분석 대상)")
    st.caption("'① 계획본 생성' 탭과 **동일한 config**를 공유합니다. 포함 해제된 지사의 전표는 "
               "종합표·양식1에서 제외되고 zrfm2_V1에 **'미반영'**으로 표기됩니다.")
    dept_config = config_store.load_dept_config(CONFIG_DIR, year)
    edited_dept = st.data_editor(
        pd.DataFrame(dept_config), num_rows="dynamic", key=f"a_dept_editor_{year}",
        column_config={
            "그룹": st.column_config.SelectboxColumn(options=config_store.DEPT_GROUPS),
            "포함": st.column_config.CheckboxColumn(),
        },
    )
    if st.button("✔ 지사 구성 적용 완료", key="a_apply_dept"):
        config_store.save_dept_config(CONFIG_DIR, year, edited_dept.to_dict("records"))
        st.success(f"{year}년 지사 구성이 저장되었습니다.")

    st.header("③ 예산과목 구성 (분석 대상)")
    st.caption("포함 해제된 과목의 전표는 종합표·양식1에서 제외되고 zrfm2_V1에 **'미반영'**으로 표기됩니다.")
    item_config = config_store.load_item_config(CONFIG_DIR, year, budget)
    edited_item = st.data_editor(
        pd.DataFrame(item_config), num_rows="dynamic", key=f"a_item_editor_{year}_{budget}",
        column_config={
            "심의대상": st.column_config.CheckboxColumn(),
            "포함": st.column_config.CheckboxColumn(),
            "실적반영": st.column_config.CheckboxColumn(
                help="해제하면 계획본에는 그대로 두고 실적 산출물에서만 제외합니다. "
                     "(예: ERP에 계정이 없는 건설공사 과목)"),
        },
    )
    if st.button("✔ 예산과목 구성 적용 완료", key="a_apply_item"):
        config_store.save_item_config(CONFIG_DIR, year, budget, edited_item.to_dict("records"))
        st.success(f"{year}년 {budget} 과목 구성이 저장되었습니다.")

    st.header("④ 계획본 자료 업로드")
    st.caption(f"1단계 산출물 `{year}년 {budget}예산_계획.xlsx` 의 양식1(월별)을 사용합니다. "
               f"손익·자본이 섞인 **사업별 예산 원본**을 올려도 됩니다 — 예산과목 기준으로 "
               f"**{budget}** 대상 행만 자동으로 골라냅니다(제외분은 검토리포트에 기록).")
    plan_file = st.file_uploader("계획본.xlsx", type=["xlsx"], key="a_plan_upload")

    st.header("⑤ ERP 실적자료(zrfm2) 업로드")
    st.caption("SAP에서 추출한 `zrfm2` 파일. 파일명은 반드시 **zrfm2** 로 추출해 주세요.")
    zr_file = st.file_uploader("zrfm2.XLSX", type=["xlsx"], key="a_zr_upload")

    st.header("⑥ 마스터(코드) 자료 — 선택")
    st.caption("`손익예산26_최종본` (예산코드·부서코드 시트). 계정코드→예산과목 정규화 정확도 향상용. 없으면 텍스트로 매칭.")
    master_file = st.file_uploader("손익예산26_최종본.xlsx", type=["xlsx"], key="a_master_upload")

    st.header("⑦ 분류 정책")
    policy_label = st.radio(
        "신규/계획집행 분류 정책",
        ["그룹 기반 (권장)", "엄격 사업명(80%)"],
        horizontal=True, key="a_policy",
        help=("그룹 기반: (예산과목×처지사)에 계획행이 없을 때만 신규. 계획행 있는 그룹의 "
              "전표는 사업명 최고유사 계획행에 귀속.\n"
              "엄격 사업명: 사업명 유사도 80% 이상만 계획집행(표기 차이로 신규가 과대해질 수 있음)."),
    )
    new_policy = "group" if policy_label.startswith("그룹") else "strict_name"

    st.header("⑧ 실행")
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
            with open(res["matched_csv_path"], "rb") as f:
                matched_bytes = f.read()
            st.session_state["actual_result"] = {
                "name": os.path.basename(res["output_path"]),
                "bytes": actual_bytes,
                "v1_name": os.path.basename(res["zrfm2_v1_path"]),
                "v1_bytes": v1_bytes,
                "matched_name": os.path.basename(res["matched_csv_path"]),
                "matched_bytes": matched_bytes,
                "요약": res["요약"],
                "미매핑처지사": res["미매핑처지사"],
                "미분류과목": res["미분류과목"],
                "미반영금액": res.get("미반영금액", 0),
                "제외전표": res.get("제외전표", []),
                "계획행제외": res.get("계획행제외", []),
                "경고": res.get("경고", []),
                "연도불일치": res["연도불일치"],
            }

    if "actual_result" in st.session_state:
        r = st.session_state["actual_result"]
        s = r["요약"]
        rate = s.get("집행률(%)")
        st.success(
            f"완료: 계획 {s.get('계획 연예산(천원)', 0):,}천원 대비 "
            f"총 실적 {s['총 실적(천원)']:,}천원"
            + (f" (집행률 {rate}%)" if rate is not None else "")
            + f" — 계획집행 {s['계획집행 실적(천원)']:,} / 신규 {s['신규 실적(천원)']:,}"
        )
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("계획집행 행수", f"{s['계획집행 행수']:,}")
        c2.metric("미시행 행수", f"{s['미시행 행수']:,}")
        c3.metric("신규 행수", f"{s['신규 행수']:,}")
        c4.metric("미반영(천원)", f"{r.get('미반영금액', 0):,}")
        for w in r.get("경고", []):
            st.warning("⚠ " + w)
        if r.get("계획행제외"):
            with st.expander("계획행 제외 내역 (이번 예산 실적 대상이 아닌 행)"):
                st.dataframe(pd.DataFrame(
                    r["계획행제외"], columns=["사유", "행수", "연예산(천원)", "예산과목"]),
                    hide_index=True)
        if r.get("제외전표"):
            with st.expander("집계 제외 전표 (합계행·타연도)"):
                st.dataframe(pd.DataFrame(
                    r["제외전표"], columns=["사유", "금액(천원)", "전표수"]),
                    hide_index=True)
        if r.get("미반영금액"):
            st.info(f"미반영 {r['미반영금액']:,}천원 = 선택 안 된 예산과목·지사(구성 미포함)·미분류·미매핑 전표. "
                    "→ zrfm2_V1의 '반영구분'='미반영' 및 실적파일 '검토리포트' 참고. "
                    "(종합표 총액 + 미반영 = ERP 전체)")
        if r["연도불일치"]:
            st.warning("⚠ " + r["연도불일치"])
        if r["미매핑처지사"]:
            amt = r.get("미매핑처지사금액", 0)
            st.warning(f"미매핑 처지사(종합표 집계 누락 {amt:,}천원): "
                       + ", ".join(r["미매핑처지사"])
                       + " → config/처지사_별칭.json 보강 필요")
        if r["미분류과목"]:
            iamt = r.get("미분류과목금액", 0)
            st.warning(f"미분류(결측) 예산과목 — 예산과목 구성에 없음 ({iamt:,}천원, 종합표 미반영): "
                       + ", ".join(r["미분류과목"]))
        st.download_button("실적 결과 파일 다운로드", r["bytes"], file_name=r["name"], key="a_dl_result")
        st.download_button("zrfm2_V1 다운로드", r["v1_bytes"], file_name=r["v1_name"], key="a_dl_v1")
        st.download_button("matched CSV 다운로드", r["matched_bytes"], file_name=r["matched_name"],
                           mime="text/csv", key="a_dl_matched")


def _db():
    return dbm.connect()


def render_db_tab():
    st.caption("🔒 **보안 모드** — 업로드한 원자료는 즉시 백엔드 DB(`data/budget.db`)로 흡수되고 "
               "파일은 남지 않습니다. 분석은 DB에서 실행되며, 이 화면에는 분석 **결과**만 "
               "표출됩니다(전표 재배정 등 수정 가능).")
    conn = _db()

    # ── ① 자료 등록 ────────────────────────────────────────────────
    st.header("① 자료 등록 (DB 흡수)")
    year = st.text_input("대상연도", value="2023", key="d_year")
    c1, c2 = st.columns(2)
    with c1:
        up_plan = st.file_uploader("계획 자료 (양식1(월별))", type=["xlsx"], key="d_plan")
        if up_plan and st.button("계획 자료 DB 등록", key="d_ing_plan"):
            tmp = _save_upload(up_plan)
            try:
                info = dbm.ingest_plan(conn, tmp, year, label=up_plan.name)
            finally:
                try:
                    os.remove(tmp)          # 원본 파일 미보관(보안)
                except OSError:
                    pass
            st.success(f"계획 {info['rows']:,}행 / {info['total']:,.0f}천원 흡수 완료 "
                       f"(dataset #{info['dataset_id']})")
    with c2:
        up_erp = st.file_uploader("ERP 실적 (zrfm2)", type=["xlsx"], key="d_erp")
        if up_erp and st.button("zrfm2 DB 등록", key="d_ing_erp"):
            tmp = _save_upload(up_erp)
            try:
                info = dbm.ingest_erp(conn, tmp, year, label=up_erp.name)
            finally:
                try:
                    os.remove(tmp)
                except OSError:
                    pass
            st.success(f"ERP {info['rows']:,}행 흡수 완료 (dataset #{info['dataset_id']})")

    ds = dbm.list_datasets(conn)
    if ds:
        with st.expander(f"등록된 데이터셋 {len(ds)}건 (같은 연도·종류는 최신본 사용)"):
            st.dataframe(pd.DataFrame(ds), hide_index=True)

    # ── ② 분석 실행 ────────────────────────────────────────────────
    st.header("② 분석 실행")
    c1, c2 = st.columns(2)
    with c1:
        budget = st.radio("구분", ["손익", "자본"], horizontal=True, key="d_budget")
    with c2:
        policy_label = st.radio("분류 정책", ["그룹 기반 (권장)", "엄격 사업명(80%)"],
                                horizontal=True, key="d_policy")
    if st.button("DB에서 실적 분석 실행", type="primary", key="d_run"):
        try:
            with st.spinner("분석 중..."):
                res = pipeline_db.run_actual_db(
                    conn, CONFIG_DIR, OUT_DIR, year, budget,
                    new_policy="group" if policy_label.startswith("그룹") else "strict_name",
                )
            st.session_state["db_run"] = {"year": year, "budget": budget,
                                          "run_id": res["run_id"], "요약": res["요약"],
                                          "paths": (res["output_path"], res["zrfm2_v1_path"],
                                                    res["matched_csv_path"])}
        except ValueError as e:
            st.error(str(e))

    run = dbm.latest_run(conn, year, budget)
    if run:
        s = run["summary"]
        st.info(f"최근 실행: {run['created_at']} · 총 실적 {s.get('총 실적(천원)', 0):,}천원 "
                f"(계획집행 {s.get('계획집행 실적(천원)', 0):,} / 신규 {s.get('신규 실적(천원)', 0):,} / "
                f"수동지정 전표 {s.get('수동지정 전표수', 0):,}건)")

        # ── ③ 결과 검토 — 사업 트리(사업 → 귀속 전표) + 전표 재배정 ──
        st.header("③ 결과 검토 · 수정 (사업 → 전표 트리)")
        detail = dbm.load_match_detail(conn, run["id"])
        detail = detail[detail["구분"].isin(["계획집행", "신규"])]
        if len(detail):
            items = sorted(detail["과목정규"].dropna().unique())
            c1, c2, c3 = st.columns(3)
            with c1:
                sel_item = st.selectbox("예산과목", items, key="d_sel_item")
            sub = detail[detail["과목정규"] == sel_item]
            depts = sorted(sub["처지사정규"].dropna().unique())
            with c2:
                sel_dept = st.selectbox("처지사", depts, key="d_sel_dept")
            sub = sub[sub["처지사정규"] == sel_dept]
            with c3:
                only_low = st.checkbox("확신도 낮은 사업만(<0.8)", key="d_low")

            biz_names = sorted(sub["매칭사업명"].dropna().unique())
            group_names = [b for b in biz_names]
            st.caption(f"{sel_item} / {sel_dept} — 사업 {len(biz_names)}개, "
                       f"전표 {len(sub):,}건, 순액 {sub['금액천원'].sum():,.0f}천원")
            for biz in biz_names:
                g = sub[sub["매칭사업명"] == biz]
                conf = g["매칭확신도"].dropna()
                avg_conf = float(conf.mean()) if len(conf) else None
                if only_low and (avg_conf is None or avg_conf >= 0.8):
                    continue
                label = (f"{'🟡 ' if str(biz).startswith('[신규]') else ''}{biz} — "
                         f"{g['금액천원'].sum():,.0f}천원 · 전표 {len(g)}건"
                         + (f" · 확신도 {avg_conf:.2f}" if avg_conf is not None else ""))
                with st.expander(label):
                    st.dataframe(
                        g[["erp_row_id", "전표번호", "전표텍스트", "금액천원", "전기일",
                           "매칭확신도"]].reset_index(drop=True),
                        hide_index=True)
                    # 전표 재배정
                    ids = st.multiselect(
                        "재배정할 전표(erp_row_id)", list(g["erp_row_id"]),
                        key=f"d_mv_{biz}")
                    targets = [b for b in group_names if b != biz] + ["(직접 입력: 신규 사업명)"]
                    tgt = st.selectbox("이동할 사업", targets, key=f"d_tg_{biz}")
                    manual_name = ""
                    if tgt == "(직접 입력: 신규 사업명)":
                        manual_name = st.text_input("신규 사업명", key=f"d_nm_{biz}")
                    if st.button("재배정 저장", key=f"d_sv_{biz}"):
                        target_name = manual_name.strip() if manual_name.strip() else tgt
                        if not ids:
                            st.warning("전표를 선택하세요.")
                        elif target_name.startswith("(직접"):
                            st.warning("신규 사업명을 입력하세요.")
                        else:
                            clean = target_name
                            if clean.startswith("[신규] "):
                                clean = clean[len("[신규] "):]
                            for rid in ids:
                                dbm.add_override(conn, year, budget, int(rid), clean)
                            st.success(f"{len(ids)}건 재배정 저장 — '② 분석 실행'을 다시 누르면 반영됩니다.")

        # 오버라이드 관리
        ovs = dbm.list_overrides(conn, year, budget)
        if ovs:
            with st.expander(f"수동 재배정 목록 {len(ovs)}건"):
                st.dataframe(pd.DataFrame(ovs), hide_index=True)
                del_id = st.number_input("삭제할 재배정 id", min_value=0, step=1, key="d_del")
                if st.button("재배정 삭제", key="d_del_btn") and del_id:
                    dbm.delete_override(conn, int(del_id))
                    st.success(f"재배정 #{del_id} 삭제 — 재실행 시 반영됩니다.")

        # ── ④ 다운로드 ────────────────────────────────────────────
        st.header("④ 결과 다운로드")
        for path in (os.path.join(OUT_DIR, f"{year}년 {budget}예산_실적.xlsx"),
                     os.path.join(OUT_DIR, f"zrfm2_{year}_V1({budget}).xlsx"),
                     os.path.join(OUT_DIR, f"matched_{year}_{budget}.csv")):
            if os.path.exists(path):
                with open(path, "rb") as f:
                    st.download_button(os.path.basename(path), f.read(),
                                       file_name=os.path.basename(path),
                                       key=f"d_dl_{os.path.basename(path)}")


def main():
    st.set_page_config(page_title="중장기 예산 분석", layout="wide")
    st.title("중장기 예산 — 계획·실적 자동 분석")
    tab_plan, tab_actual, tab_db = st.tabs(
        ["① 계획본 생성", "② 실적 분석", "③ DB 분석·검토 (보안)"])
    with tab_plan:
        render_plan_tab()
    with tab_actual:
        render_actual_tab()
    with tab_db:
        render_db_tab()


if __name__ == "__main__":
    main()
