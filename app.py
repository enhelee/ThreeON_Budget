"""
1단계: 데이터 업로드 & 검증 화면
실행: streamlit run app.py
"""
import streamlit as st
import pandas as pd
from year_status import load_status, save_status, add_year, set_year_result, get_visible_cells, next_addable_year, prev_addable_year
from validate_upload import validate_upload
from classify import KEYWORD_RULES
from hybrid_classify import classify_dataframe
from ml_classifier import (
    append_training_examples, training_data_summary, can_train, train_model,
    MIN_SAMPLES_TO_TRAIN, MIN_CLASSES_TO_TRAIN,
    load_training_meta, reset_model, reset_all_training_data,
    export_training_data, import_training_data,
)

st.set_page_config(page_title="발전플랜트 예산 분석", layout="centered")
st.title("발전플랜트 유지보수 예산 분석")

page = st.sidebar.radio("단계 선택", ["1단계 · 데이터 업로드", "2단계 · 투자유형 분류 검토", "모델 관리"])
status = load_status()

if page == "모델 관리":
    st.caption("분류 모델 관리")

    # ---- 전체 학습 현황 ----
    st.subheader("전체 학습 현황")
    summary = training_data_summary()
    meta = load_training_meta()

    c1, c2 = st.columns(2)
    c1.metric("누적 학습데이터", f"{summary['count']}건")
    if meta:
        c2.metric("현재 모델 정확도(참고용)", f"{meta['cv_accuracy']*100:.0f}%" if meta.get("cv_accuracy") is not None else "-")
        st.caption(f"마지막 학습: {meta['trained_at']}  ·  학습 당시 샘플 {meta['n_samples']}건, 유형 {meta['n_classes']}개")
    else:
        c2.metric("현재 모델 정확도(참고용)", "학습 안됨")
        st.caption("아직 재학습한 적이 없습니다. 지금은 키워드 규칙으로 분류 중입니다.")

    if summary["per_class"]:
        st.write("유형별 누적 건수")
        st.bar_chart(pd.Series(summary["per_class"]))
    else:
        st.info("아직 축적된 학습데이터가 없습니다. 2단계에서 분류를 확정하면 여기 쌓입니다.")

    st.divider()

    # ---- 재학습 ----
    st.subheader("재학습")
    if can_train():
        if st.button("지금 재학습하기"):
            with st.spinner("학습 중..."):
                result = train_model()
            st.success(f"재학습 완료 — 샘플 {result['n_samples']}건, 유형 {result['n_classes']}개")
            if result["cv_accuracy"] is not None:
                st.write(f"교차검증 정확도(참고용): 약 {result['cv_accuracy']*100:.0f}%")
    else:
        need = MIN_SAMPLES_TO_TRAIN - summary["count"]
        st.caption(f"재학습하려면 최소 {MIN_SAMPLES_TO_TRAIN}건, {MIN_CLASSES_TO_TRAIN}개 이상 유형이 필요합니다. "
                   f"(현재 {summary['count']}건 — 약 {max(need,0)}건 더 필요)")

    st.divider()

    # ---- 내보내기 / 불러오기 ----
    st.subheader("학습 데이터 내보내기 · 불러오기")
    export_df = export_training_data()
    if export_df is not None:
        st.download_button(
            "학습 데이터 엑셀로 내보내기",
            data=export_df.to_csv(index=False).encode("utf-8-sig"),
            file_name="training_data.csv",
            mime="text/csv",
        )
        st.caption("엑셀(또는 텍스트 편집기)로 열어 라벨을 수정한 뒤, 아래에서 다시 업로드하면 반영됩니다.")
    else:
        st.caption("아직 내보낼 학습 데이터가 없습니다.")

    uploaded = st.file_uploader("수정한 학습 데이터 다시 업로드 (.csv, 'text'/'label' 컬럼 필요)", type=["csv"])
    if uploaded is not None:
        try:
            new_df = pd.read_csv(uploaded)
            mode = st.radio("반영 방식", ["병합(같은 텍스트는 새 라벨로 갱신)", "전체 교체"], horizontal=True)
            if st.button("업로드 내용 반영하기"):
                mode_key = "replace" if mode == "전체 교체" else "merge"
                n = import_training_data(new_df, mode=mode_key)
                st.success(f"반영 완료 — 현재 누적 {n}건. '재학습'을 다시 눌러 모델에 반영하세요.")
        except Exception as e:
            st.error(f"파일을 읽을 수 없습니다: {e}")

    st.divider()

    # ---- 초기화 ----
    st.subheader("학습 취소 / 초기화")
    ic1, ic2 = st.columns(2)
    with ic1:
        st.caption("모델만 초기화 → 학습데이터는 남기고, 분류 방식만 키워드 규칙으로 되돌립니다.")
        if st.button("모델만 초기화"):
            reset_model()
            st.success("모델을 초기화했습니다. 이제 키워드 규칙으로 분류합니다.")
    with ic2:
        st.caption("⚠️ 학습데이터까지 전부 삭제합니다. 되돌릴 수 없습니다.")
        confirm = st.checkbox("정말 전체 삭제할래요")
        if st.button("전체 초기화", disabled=not confirm):
            reset_all_training_data()
            st.success("학습데이터와 모델을 모두 초기화했습니다.")
    st.stop()

if page == "2단계 · 투자유형 분류 검토":
    st.caption("2단계 · 투자유형 분류 검토")
    uploaded_years = [int(y) for y, v in status.items() if v.get("uploaded")]
    if not uploaded_years:
        st.info("먼저 1단계에서 데이터를 업로드해주세요.")
        st.stop()

    # ---------------- 모델 학습 현황 (사내망 오프라인 재학습) ----------------
    with st.expander("🔧 분류 모델 학습 현황", expanded=False):
        summary = training_data_summary()
        st.write(f"현재까지 축적된 학습 데이터: **{summary['count']}건**")
        if summary["per_class"]:
            st.caption(" / ".join(f"{k}: {v}건" for k, v in summary["per_class"].items()))

        if can_train():
            if st.button("지금 재학습하기 (오프라인, 인터넷 불필요)"):
                with st.spinner("학습 중..."):
                    result = train_model()
                st.success(f"재학습 완료 — 샘플 {result['n_samples']}건, 유형 {result['n_classes']}개")
                if result["cv_accuracy"] is not None:
                    st.write(f"교차검증 정확도(참고용): 약 {result['cv_accuracy']*100:.0f}%")
        else:
            need = MIN_SAMPLES_TO_TRAIN - summary["count"]
            st.caption(f"재학습하려면 최소 {MIN_SAMPLES_TO_TRAIN}건, {MIN_CLASSES_TO_TRAIN}개 이상 유형의 확정 데이터가 필요합니다. "
                       f"(현재 {summary['count']}건 — 약 {max(need,0)}건 더 필요)")

    year = st.selectbox("연도 선택", sorted(uploaded_years, reverse=True))
    try:
        df = pd.read_csv(f"data_{year}.csv")
    except FileNotFoundError:
        st.warning("이 연도의 저장된 데이터가 없습니다. 1단계에서 다시 저장해주세요.")
        st.stop()

    classified, method = classify_dataframe(df)
    st.caption(f"현재 분류 방식: {'학습된 모델' if method == 'ml' else '키워드 규칙 (아직 학습모델 없음)'}")

    threshold = 0.7
    low_conf = classified[classified["확신도"] < threshold]
    high_conf = classified[classified["확신도"] >= threshold]

    c1, c2, c3 = st.columns(3)
    c1.metric("전체", len(classified))
    c2.metric("확신 높음", len(high_conf))
    c3.metric("검토 필요", len(low_conf))

    st.subheader(f"검토 필요 항목부터 ({len(low_conf)}건)")
    type_options = list(KEYWORD_RULES.keys()) + ["미분류"]

    edited_labels = {}
    for i, row in low_conf.iterrows():
        with st.container(border=True):
            st.caption(f"전표헤더텍스트  ·  확신도 {int(row['확신도']*100)}%")
            st.write(f"\"{row['전표헤더텍스트']}\"")
            default_idx = type_options.index(row["예측유형"]) if row["예측유형"] in type_options else len(type_options) - 1
            choice = st.selectbox("투자유형 확정", type_options, index=default_idx, key=f"sel_{year}_{i}")
            edited_labels[i] = choice

    st.divider()
    b1, b2 = st.columns(2)
    if b1.button(f"확신 높은 {len(high_conf)}건 일괄 승인 + 검토 반영 저장"):
        final = classified.copy()
        for i, choice in edited_labels.items():
            final.loc[i, "예측유형"] = choice
        final = final.rename(columns={"예측유형": "투자유형_확정"})
        final.to_csv(f"classified_{year}.csv", index=False)
        n = append_training_examples(list(zip(final["전표헤더텍스트"], final["투자유형_확정"])))
        st.success(f"{year}년 분류 결과 저장 완료 ({len(final)}건) · 누적 학습데이터 {n}건")
    if b2.button("변경사항만 저장 (일괄승인 없이)"):
        final = classified.copy()
        for i, choice in edited_labels.items():
            final.loc[i, "예측유형"] = choice
        final = final.rename(columns={"예측유형": "투자유형_확정"})
        final.to_csv(f"classified_{year}.csv", index=False)
        reviewed = final.loc[list(edited_labels.keys())]
        n = append_training_examples(list(zip(reviewed["전표헤더텍스트"], reviewed["투자유형_확정"])))
        st.success(f"저장 완료 · 누적 학습데이터 {n}건")
    st.stop()

st.caption("1단계 · 데이터 업로드")

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

        c1, c2, c3 = st.columns(3)
        c1.metric("총 건수", result["row_count"])
        c2.metric("유효 건수", result["valid_row_count"])
        c3.metric("오류 행", result["error_count"])

        if result["errors"]:
            st.error(f"검토가 필요한 행 ({len(result['errors'])}건)")
            st.dataframe(pd.DataFrame(result["errors"])[["row", "level", "type", "detail"]],
                         use_container_width=True, hide_index=True)

        if st.button("이 결과로 저장하기"):
            status = set_year_result(status, selected_year, result["row_count"], result["error_count"], result["errors"])
            save_status(status)
            result["data"].to_csv(f"data_{selected_year}.csv", index=False)
            st.success(f"{selected_year}년 데이터 저장 완료")
            st.rerun()
