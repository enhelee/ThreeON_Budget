"""투자유형 예측 테스트 (실적 데이터 적용) 화면

⚠️ 테스트 전용 화면이다. project_type_classifier로 학습한 모델을 실제 실적 데이터에
적용해보고 결과를 눈으로 확인하는 용도일 뿐, data_/matched_/classified_{year}.csv 같은
실제 파이프라인에는 전혀 연결하지 않는다. (추후 실데이터와 어떻게 연동할지는 별도로 결정)

다만 예측 결과를 사람이 확인·수정한 뒤 '학습데이터에 추가'는 할 수 있다 - 그렇게 모인
데이터는 '투자유형 학습' 화면에서 재학습해야 실제로 모델에 반영된다.

지금은 '기계장치'·'외주비' 계열 예산과목만 다루기로 했으므로, 그 외 예산과목 행은
결과에서 제외한다(project_type_classifier.is_in_scope_account).

예측 -> 확인/수정 -> 저장 단계(render_predict_review_and_save)는 이 화면에서 직접 지정한
파일을 올릴 때뿐 아니라, 'Test 모드 계획 및 실적 업로드'의 zrfm2 원본 업로드에서도 그대로
재사용한다 - 입력 방식과 무관하게 예측·저장 로직은 하나로 유지한다.
"""
import io
import os
import pandas as pd
import streamlit as st
import project_type_classifier as ptc
import longterm_forecast as lf

TEST_ACTUAL_RESULT_PATH = os.path.join(lf.TEST_DATA_DIR, "project_type_test_actual.csv")
_SHARED_COLUMNS = ["사업명", "예산과목", "사업장", "금액", "투자유형_확정", "투자유형세부_확정", "연도"]
_NO_COL_SENTINEL = "(없음)"
_LEGACY_DEFAULT_YEAR = 2025  # 연도 태그가 없던 예전 백데이터를 마이그레이션할 때 부여하는 연도


def save_shared_actual_df(df: pd.DataFrame):
    """확정 결과를 test_data/ 폴더에 저장한다 - 다음에 다시 업로드하지 않아도 재사용할 수 있게 한다.
    같은 연도의 기존 데이터만 이번 확정 결과로 교체하고, 다른 연도 데이터는 그대로 유지한다 -
    그래야 여러 연도를 한 번에 올리지 않아도 '실적집계 대시보드'에서 연도별로 누적·비교할 수 있다."""
    os.makedirs(lf.TEST_DATA_DIR, exist_ok=True)
    existing = load_shared_actual_df()
    if not df.empty and "연도" in df.columns and not existing.empty:
        years_in_new = set(df["연도"].unique())
        existing = existing[~existing["연도"].isin(years_in_new)]
    combined = pd.concat([existing, df], ignore_index=True) if not existing.empty else df
    combined.to_csv(TEST_ACTUAL_RESULT_PATH, index=False)


def load_shared_actual_df() -> pd.DataFrame:
    if not os.path.exists(TEST_ACTUAL_RESULT_PATH):
        return pd.DataFrame(columns=_SHARED_COLUMNS)
    df = pd.read_csv(TEST_ACTUAL_RESULT_PATH, dtype={"사업장": str})
    if "연도" not in df.columns:
        # 연도 태그 없이 저장된 예전 백데이터 - 1회성으로 기본 연도를 채워 넣고 그대로 다시 저장한다.
        df["연도"] = _LEGACY_DEFAULT_YEAR
        df.to_csv(TEST_ACTUAL_RESULT_PATH, index=False)
    return df


def get_shared_actual_df() -> pd.DataFrame:
    """이번 세션에서 방금 확정한 결과가 있으면 그걸, 없으면 이전에 저장해둔 테스트 백데이터를
    대신 쓴다 - Test 모드 다른 화면(실적집계 대시보드 등)에서 매번 다시 업로드하지 않아도 되게 한다."""
    shared = st.session_state.get("ptest_shared_df")
    if shared is not None and not shared.empty:
        return shared
    return load_shared_actual_df()


def _dedupe_columns(cols):
    """헤더에 같은 이름이 여러 번 나오면 뒤쪽에 번호를 붙인다.
    (안 그러면 여러 파일을 합칠 때 pandas가 컬럼을 정렬 못해 InvalidIndexError가 난다)"""
    seen = {}
    out = []
    for c in cols:
        c = str(c).strip()
        if c in seen:
            seen[c] += 1
            out.append(f"{c}_{seen[c]}")
        else:
            seen[c] = 0
            out.append(c)
    return out


def _guess(cols, *keywords, avoid=()):
    """컬럼 목록에서 keyword를 포함하고 avoid는 피하는 첫 컬럼을 추천(없으면 None)."""
    for kw in keywords:
        for c in cols:
            if c == kw and not any(a in c for a in avoid):
                return c
    for kw in keywords:
        for c in cols:
            if kw in c and not any(a in c for a in avoid):
                return c
    return None


def _read_uploaded(file) -> pd.DataFrame | None:
    """업로드 파일(csv/xlsx)을 읽되, '사업명'·'전표헤더텍스트'·'계정과목' 등이 보이는
    행을 헤더로 자동 인식한다(못 찾으면 첫 행을 헤더로 가정)."""
    name = file.name.lower()
    raw = file.getvalue()
    try:
        if name.endswith(".csv"):
            df0 = pd.read_csv(io.BytesIO(raw), header=None, dtype=str)
        else:
            df0 = pd.read_excel(io.BytesIO(raw), header=None, dtype=str)
    except Exception as e:
        st.error(f"'{file.name}' 파일을 읽을 수 없습니다: {e}")
        return None

    header_row = 0
    for i in range(min(15, len(df0))):
        rowvals = [str(v) for v in df0.iloc[i].tolist()]
        if any(kw in v for v in rowvals for kw in ("사업명", "전표헤더텍스트", "계정과목", "예산과목")):
            header_row = i
            break

    header_vals = df0.iloc[header_row].tolist()
    df = df0.iloc[header_row + 1:].copy()
    df.columns = _dedupe_columns(header_vals)
    # 원래 헤더 칸 자체가 비어있던 컬럼(엑셀의 이름 없는 여분 칸)은 의미가 없으므로 통째로 뺀다.
    # (안 그러면 'nan', 'nan_1'... 같은 빈 컬럼이 그대로 표/다운로드에 남는다)
    blank_header = [pd.isna(v) or str(v).strip() == "" for v in header_vals]
    df = df.loc[:, [not b for b in blank_header]]
    df = df.dropna(axis=1, how="all")  # 헤더는 있었지만 값이 전부 빈 컬럼도 함께 제거
    df = df.dropna(how="all").reset_index(drop=True)
    return df


def _render_flexible_upload():
    """이미 어느 정도 정리된 파일(사업명/계정과목 등)을 올려 사람이 직접 칸을 지정한다.
    반환: (합친 DataFrame, 사업명칸, 예산과목칸, 사업장칸, 금액칸, 금액단위, 연도) - 아직 업로드가 없으면 전부 None."""
    files = st.file_uploader("실적 파일 업로드 (.xlsx 또는 .csv, 여러 개 가능)", type=["xlsx", "csv"],
                             accept_multiple_files=True, key="ptest_upload")
    if not files:
        return None, None, None, None, None, None, None

    frames = [df for df in (_read_uploaded(f) for f in files) if df is not None]
    if not frames:
        return None, None, None, None, None, None, None
    all_cols = list(dict.fromkeys(c for fr in frames for c in fr.columns))

    st.subheader("2) 칸 맞추기")
    st.caption("모델 입력으로 쓸 칸을 골라주세요. '사업명'이 없으면 '전표헤더텍스트'를 대신 써도 됩니다 "
               "(사업명만큼 정확하진 않을 수 있습니다).")
    opt = [_NO_COL_SENTINEL] + all_cols

    def _idx(guess):
        return opt.index(guess) if guess in opt else 0

    c1, c2 = st.columns(2)
    col_name = c1.selectbox("사업명(또는 전표헤더텍스트) 칸", opt,
                             index=_idx(_guess(all_cols, "사업명", "전표헤더텍스트", "텍스트")))
    col_acct = c2.selectbox("예산과목(계정과목) 칸 (선택)", opt,
                             index=_idx(_guess(all_cols, "예산과목", "계정과목", avoid=("구분",))))

    st.caption("아래 두 칸을 지정하면 '실적집계 대시보드'·'맞춤 리포트'의 테스트 섹션에서 이 결과를 지사별·금액 기준으로 집계할 수 있습니다.")
    c3, c4 = st.columns(2)
    col_site = c3.selectbox("사업장(지사) 칸 (선택)", opt,
                             index=_idx(_guess(all_cols, "사업장", "사업영역", "지사")))
    col_amt = c4.selectbox("금액 칸 (선택)", opt,
                            index=_idx(_guess(all_cols, "금액", "최종실적금액", "실적금액")))
    amt_unit = st.radio(
        "금액 칸의 단위", ["천원", "원"], index=0, horizontal=True,
        help="'계획 대비 실적'에서 다운받은 양식은 '[단위: 천원]'로 표시되어 있습니다. "
             "원본 실적 데이터(예: matched_*.csv)를 그대로 올린 경우엔 '원'을 선택하세요.",
    )
    year = st.number_input(
        "연도", min_value=2000, max_value=2100, value=2025, step=1, key="ptest_year",
        help="이 업로드 전체를 하나의 연도로 태그합니다. '실적집계 대시보드'에서 연도별로 필터링할 때 쓰입니다.",
    )

    combined = pd.concat(frames, ignore_index=True)
    return combined, col_name, col_acct, col_site, col_amt, amt_unit, int(year)


def render_predict_review_and_save(combined: pd.DataFrame, col_name: str, col_acct: str,
                                    col_site: str, col_amt: str, amt_unit: str, year: int):
    """업로드 방식(zrfm2 원본/직접 지정 파일)과 무관하게 공통으로 쓰는 예측 -> 확인/수정 -> 저장 단계.
    col_*는 combined의 실제 컬럼명이거나 _NO_COL_SENTINEL이다. year는 이 배치 전체에 붙일 연도 태그."""
    if not ptc.has_any_model():
        st.info("아직 학습된 모델이 없습니다. '투자유형 학습 (분류자료)' 화면에서 먼저 학습을 완료해주세요.")
        return
    if col_name == _NO_COL_SENTINEL:
        st.warning("최소한 '사업명(또는 전표헤더텍스트) 칸'은 있어야 예측할 수 있습니다.")
        return

    trained_targets = [t for t in ptc.TARGETS if ptc.load_model(t) is not None]

    # 투자유형 분류기는 기계장치·외주비(자본) 계열만 다루도록 학습되어 있다. 손익예산 등 범위 밖
    # 계정과목은 "예측 대상이 아닐" 뿐 실적 자체가 아닌 게 아니므로, 여기서 행을 통째로 지우면
    # (예전 방식) 손익 실적이 '배정 대비 실적' 등 다른 화면에서 통째로 안 잡히는 문제가 생긴다.
    # 그래서 범위 밖 행도 그대로 남겨두고 투자유형 예측만 빈 값으로 둔다.
    if col_acct != _NO_COL_SENTINEL:
        in_scope = combined[col_acct].apply(ptc.is_in_scope_account)
        st.caption(f"투자유형 예측은 기계장치·외주비 범위({int(in_scope.sum())}건)에만 적용됩니다. "
                   f"그 외 {int((~in_scope).sum())}건(손익예산 등)은 예측 없이도 실적 금액에는 그대로 포함됩니다.")
    else:
        in_scope = pd.Series(True, index=combined.index)
        st.caption("예산과목 칸을 지정하지 않아 범위(기계장치·외주비) 구분 없이 전체 건을 그대로 예측합니다.")

    model_input = pd.DataFrame({
        "사업명": combined[col_name],
        "예산과목": combined[col_acct] if col_acct != _NO_COL_SENTINEL else "",
    })

    st.divider()
    st.subheader("예측 결과")
    with st.status("투자유형 예측 실행 중...", expanded=True) as predict_status:
        st.write(f"예측 대상 {int(in_scope.sum())}건 예측 중...")
        pred_scope = ptc.predict(model_input[in_scope]) if in_scope.any() else pd.DataFrame(index=model_input.index[:0])
        predict_status.update(label="예측 완료", state="complete", expanded=False)

    # 원본 컬럼은 그대로 두고, 예측 결과만 옆에 붙여서 비교하기 쉽게 보여준다. 범위 밖 행은
    # reindex로 생기는 빈 값을 그대로 두되, 예측 라벨 칸만 빈 문자열로 채워 "예측 안 함"을 나타낸다.
    display = combined.copy()
    for t in ptc.TARGETS:
        col_pred, col_conf = f"{t}_예측", f"{t}_확신도"
        if col_pred in pred_scope.columns:
            display[col_pred] = pred_scope[col_pred].reindex(display.index).fillna("")
            display[col_conf] = pred_scope[col_conf].reindex(display.index)

    metric_cols = st.columns(1 + len(trained_targets))
    metric_cols[0].metric("전체 건수", len(display))
    for i, t in enumerate(trained_targets, start=1):
        conf_col = f"{t}_확신도"
        if conf_col in display.columns:
            metric_cols[i].metric(f"{t} 평균 확신도", f"{display[conf_col].mean()*100:.0f}%")

    st.divider()
    st.subheader("결과 확인 · 수정")
    st.caption("예측이 틀린 행은 '확정' 칸을 직접 고쳐주세요. 맞는 행은 그대로 두면 예측값이 확정값으로 쓰입니다.")

    display["투자유형_확정"] = display.get("투자유형_예측", "")
    display["투자유형세부_확정"] = display.get("투자유형세부_예측", "")

    fixed_cols = [c for c in display.columns if c not in ("투자유형_확정", "투자유형세부_확정")]
    edited = st.data_editor(
        display, width="stretch", hide_index=True, key="ptest_result_editor",
        disabled=fixed_cols,
    )

    st.download_button(
        "결과 다운로드 (CSV, 확정값 포함)",
        data=edited.to_csv(index=False).encode("utf-8-sig"),
        file_name="투자유형_예측결과_테스트.csv",
        mime="text/csv",
    )

    if col_amt != _NO_COL_SENTINEL:
        amt_won = pd.to_numeric(combined[col_amt].astype(str).str.replace(",", "").str.strip(), errors="coerce").fillna(0)
        amt_won = amt_won * (1000 if amt_unit == "천원" else 1)
    else:
        amt_won = 0

    st.session_state["ptest_shared_df"] = pd.DataFrame({
        "사업명": model_input["사업명"],
        "예산과목": model_input["예산과목"],
        "사업장": combined[col_site] if col_site != _NO_COL_SENTINEL else "",
        "금액": amt_won,
        "투자유형_확정": edited["투자유형_확정"],
        "투자유형세부_확정": edited["투자유형세부_확정"],
        "연도": year,
    })
    if col_site == _NO_COL_SENTINEL or col_amt == _NO_COL_SENTINEL:
        st.caption("⚠️ '사업장'·'금액' 칸을 지정하지 않아 '실적집계 대시보드'·'맞춤 리포트'의 테스트 섹션에서 "
                   "지사별·금액 기준 집계가 제한됩니다.")
    else:
        st.caption("✅ 이 결과는 '실적집계 대시보드'·'맞춤 리포트'의 테스트 섹션에도 그대로 반영됩니다.")

    if st.button("이 실적을 테스트 백데이터로 저장 (다음에 다시 안 올려도 됨)", key="ptest_save_backdata"):
        save_shared_actual_df(st.session_state["ptest_shared_df"])
        st.success("저장했습니다. 세션이 끊기거나 나중에 다시 접속해도 이 데이터를 계속 쓸 수 있습니다.")

    st.divider()
    st.subheader("확정 결과를 학습데이터에 반영")
    st.caption("위에서 확정한 '투자유형_확정' · '투자유형세부_확정'을 학습데이터에 추가합니다. "
               "실제 모델에 반영하려면 '투자유형 학습' 화면에서 재학습을 눌러야 합니다.")
    to_add = pd.DataFrame({
        "사업명": model_input["사업명"],
        "예산과목": model_input["예산과목"],
        "투자유형": edited["투자유형_확정"],
        "투자유형세부": edited["투자유형세부_확정"],
    })
    ready = to_add[(to_add["사업명"].astype(str).str.strip() != "") &
                    ((to_add["투자유형"].astype(str).str.strip() != "") |
                     (to_add["투자유형세부"].astype(str).str.strip() != ""))]
    if st.button(f"이 {len(ready)}건을 학습데이터에 추가", type="primary", disabled=ready.empty):
        n = ptc.append_training_examples(ready)
        st.success(f"학습데이터에 반영했습니다 (현재 누적 {n}건). "
                   f"'투자유형 학습' 화면에서 재학습해야 모델에 실제로 반영됩니다.")


def render():
    st.caption("투자유형 예측 테스트 · 학습된 모델을 실제 실적 데이터에 적용해봅니다")

    st.warning(
        "⚠️ **테스트 전용 화면입니다.** 여기서 나온 예측 결과는 정식 메뉴(집계·대시보드·계획 대비 실적 등)와는 "
        "전혀 연결되지 않습니다. 지금은 학습된 모델이 실제 데이터에 얼마나 잘 맞는지 눈으로 확인해보는 "
        "용도이며, 실데이터와 실제로 연동하는 방식은 추후 별도로 정해서 반영할 예정입니다. "
        "다만 아래에서 저장하면 Test 모드의 다른 화면(실적집계 대시보드 등)에서는 다시 업로드하지 않고도 "
        "계속 재사용할 수 있습니다. zrfm2 원본 엑셀을 그대로 올리려면 'Test 모드 > 계획 및 실적 업로드'를 "
        "이용해주세요 - 이 화면은 이미 정리된 파일에서 칸을 직접 지정하는 용도입니다."
    )

    if not ptc.has_any_model():
        st.info("아직 학습된 모델이 없습니다. '투자유형 학습 (분류자료)' 화면에서 먼저 학습을 완료해주세요.")
        return

    trained_targets = [t for t in ptc.TARGETS if ptc.load_model(t) is not None]
    st.caption(f"현재 학습된 예측 대상: {', '.join(trained_targets)}")

    saved_df = load_shared_actual_df()
    if not saved_df.empty and st.session_state.get("ptest_shared_df") is None:
        with st.container(border=True):
            st.caption(f"💾 이전에 저장해둔 테스트 실적이 있습니다 ({len(saved_df)}건).")
            c1, c2 = st.columns([3, 1])
            c1.caption("새로 업로드하지 않고 이 데이터를 그대로 쓰려면 눌러주세요.")
            if c2.button("이 데이터 계속 쓰기", key="ptest_use_saved"):
                st.session_state["ptest_shared_df"] = saved_df
                st.success("불러왔습니다. Test 모드의 '실적집계 대시보드' 등에서 바로 확인할 수 있습니다.")

    st.divider()
    st.subheader("1) 실적 데이터 올리기")
    combined, col_name, col_acct, col_site, col_amt, amt_unit, year = _render_flexible_upload()
    if combined is None:
        return

    predicted = st.session_state.get("ptest_predicted", False)
    st.subheader("현재 상태")
    st.info(f"업로드 파일 인식 완료 ({len(combined)}건) · 예측 {'완료' if predicted else '미실행'}")

    button_label = "예측 다시 실행 (최신 업로드 반영)" if predicted else "이 데이터로 예측 실행"
    if st.button(button_label, type="primary", key="ptest_predict_btn"):
        st.session_state["ptest_predicted"] = True
        predicted = True

    if not predicted:
        st.caption("버튼을 누르면 업로드한 데이터에 투자유형 예측을 실행합니다.")
        return

    render_predict_review_and_save(combined, col_name, col_acct, col_site, col_amt, amt_unit, year)
