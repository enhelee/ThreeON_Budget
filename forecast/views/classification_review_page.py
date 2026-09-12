"""2단계 · 투자유형 분류 검토 화면"""
import streamlit as st
import pandas as pd
from classify import KEYWORD_RULES
from hybrid_classify import classify_dataframe, REVIEW_CONFIDENCE_THRESHOLD
from ml_classifier import (
    append_training_examples, training_data_summary, can_train, train_model,
    MIN_SAMPLES_TO_TRAIN, MIN_CLASSES_TO_TRAIN,
)


def render(status):
    st.caption("2단계 · 투자유형 분류 검토")
    uploaded_years = [int(y) for y, v in status.items() if v.get("uploaded")]
    if not uploaded_years:
        st.info("먼저 '실적 업데이트(zrfm2)'에서 데이터를 업로드해주세요.")
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
        st.warning("이 연도의 저장된 데이터가 없습니다. '실적 업데이트(zrfm2)'에서 다시 저장해주세요.")
        st.stop()

    classified, method = classify_dataframe(df)
    st.caption(f"현재 분류 방식: {'학습된 모델' if method == 'ml' else '키워드 규칙 (아직 학습모델 없음)'}")

    threshold = REVIEW_CONFIDENCE_THRESHOLD
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
