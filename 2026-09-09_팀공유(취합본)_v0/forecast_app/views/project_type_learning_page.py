"""투자유형 학습 (분류자료 업로드) 화면

사용자가 이미 분류해 둔 계획대비실적 양식 자료(사업명 + 투자유형 + 투자유형세부)를 올려
'사업명(+예산과목) -> 투자유형/세부' 모델을 학습시킨다. (예측 대상은 투자유형·투자유형세부 둘뿐이다 -
양식에 있는 '구분', '구분/투자유형' 컬럼은 SUMIFS용 보조컬럼이라 학습에 쓰지 않는다)

두 번째 탭은 아직 분류 체계가 없는 예산과목의 사업명을 유사도로 묶어 분류 후보를 제안한다
(정답 라벨이 없는 상태에서 쓰는 비지도 학습 - category_discovery.py).
"""
import io
import pandas as pd
import streamlit as st
import project_type_classifier as ptc
import category_discovery as cd


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


def _read_uploaded(file) -> pd.DataFrame | None:
    """업로드 파일(csv/xlsx)을 읽되, '사업명'이 들어있는 행을 헤더로 자동 인식한다."""
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

    header_row = None
    for i in range(min(15, len(df0))):
        rowvals = [str(v) for v in df0.iloc[i].tolist()]
        if any("사업명" in v for v in rowvals):
            header_row = i
            break
    if header_row is None:
        st.error(f"'{file.name}'에서 '사업명' 칸을 찾지 못했습니다. 헤더에 '사업명'이 있는지 확인해주세요.")
        return None

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


def _guess(cols, *keywords, avoid=()):
    """컬럼 목록에서 keyword를 포함하고 avoid는 피하는 첫 컬럼을 추천(없으면 None)."""
    # 정확 일치 우선
    for kw in keywords:
        for c in cols:
            if c == kw and not any(a in c for a in avoid):
                return c
    for kw in keywords:
        for c in cols:
            if kw in c and not any(a in c for a in avoid):
                return c
    return None


def _render_summary():
    summary = ptc.training_summary()
    meta = ptc.load_meta()
    cols = st.columns(1 + len(ptc.TARGETS))
    cols[0].metric("누적 학습데이터", f"{summary['count']}건")
    for i, t in enumerate(ptc.TARGETS, start=1):
        cols[i].metric(f"{t} 종류", f"{summary['per_target'][t]['classes']}종")
    if meta and meta.get("results"):
        trained = ", ".join(meta["results"].keys())
        st.caption(f"마지막 학습: {meta['trained_at']} · 학습된 모델: {trained}")
    elif ptc.has_any_model():
        st.caption("학습된 모델이 있습니다.")
    else:
        st.caption("아직 학습된 모델이 없습니다. 아래에서 분류자료를 올리고 '재학습'을 눌러주세요.")


def _render_upload_and_train():
    # ---------------- 분류자료 업로드 ----------------
    st.subheader("1) 분류 완료 자료 올리기 (5개년 등 여러 파일 가능)")
    st.caption("계획대비실적 양식에 '투자유형', '투자유형 세부'를 채워 둔 파일을 올리세요. (.xlsx 또는 .csv)")
    files = st.file_uploader("분류자료 업로드", type=["xlsx", "csv"], accept_multiple_files=True,
                             key="ptype_upload")

    if files:
        frames = [df for df in (_read_uploaded(f) for f in files) if df is not None]
        if frames:
            all_cols = list(dict.fromkeys(c for fr in frames for c in fr.columns))

            st.subheader("2) 칸 맞추기")
            st.caption("업로드한 자료의 어떤 칸이 무엇인지 골라주세요. (자동 추천을 확인만 하면 됩니다)")
            opt = ["(없음)"] + all_cols

            def _idx(guess):
                return opt.index(guess) if guess in opt else 0

            m1, m2 = st.columns(2)
            col_name = m1.selectbox("사업명 칸", opt, index=_idx(_guess(all_cols, "사업명")))
            col_acct = m2.selectbox("예산과목 칸", opt, index=_idx(_guess(all_cols, "예산과목", avoid=("구분",))))
            m3, m4 = st.columns(2)
            col_major = m3.selectbox("투자유형 칸", opt,
                                      index=_idx(_guess(all_cols, "투자유형", avoid=("세부", "구분"))))
            col_minor = m4.selectbox("투자유형 세부 칸", opt, index=_idx(_guess(all_cols, "투자유형세부", "세부")))

            col_map = {"사업명": col_name, "예산과목": col_acct,
                       "투자유형": col_major, "투자유형세부": col_minor}

            if col_name == "(없음)":
                st.warning("'사업명 칸'은 반드시 골라야 합니다.")
            elif all(col_map[t] == "(없음)" for t in ptc.TARGETS):
                st.warning("'투자유형' · '투자유형 세부' 중 최소 하나는 골라야 학습할 수 있습니다.")
            else:
                mapped_frames = []
                for fr in frames:
                    mapped = pd.DataFrame()
                    for canon, col in col_map.items():
                        mapped[canon] = fr[col] if col in fr.columns and col != "(없음)" else ""
                    mapped_frames.append(mapped)
                combined = pd.concat(mapped_frames, ignore_index=True)
                # 사업명 있고 (투자유형/세부 중) 라벨 하나라도 있는 행만 유효
                has_any_label = pd.Series(False, index=combined.index)
                for t in ptc.TARGETS:
                    has_any_label = has_any_label | (combined[t].astype(str).str.strip() != "")
                has_name = combined["사업명"].astype(str).str.strip() != ""
                in_scope = combined["예산과목"].apply(ptc.is_in_scope_account)
                valid = combined[has_name & has_any_label & in_scope]
                out_of_scope_count = int((has_name & has_any_label & ~in_scope).sum())

                st.caption(f"업로드 {len(files)}개 파일에서 학습 가능한 {len(valid)}건을 확인했습니다 "
                           f"(기계장치·외주비 범위 밖이라 제외된 {out_of_scope_count}건 포함).")
                with st.expander("미리보기 (앞 20건)"):
                    st.dataframe(valid.head(20), width="stretch", hide_index=True)

                if st.button(f"이 {len(valid)}건을 학습데이터에 추가", type="primary", disabled=valid.empty):
                    n = ptc.append_training_examples(valid)
                    st.success(f"추가 완료 · 현재 누적 {n}건. 아래 '재학습'을 눌러 모델에 반영하세요.")
                    st.rerun()

    st.divider()

    # ---------------- 재학습 (투자유형 · 투자유형세부 각각 따로) ----------------
    st.subheader("3) 재학습")
    st.caption(f"투자유형과 투자유형 세부를 각각 따로 재학습할 수 있습니다 "
               f"(라벨별 최소 {ptc.MIN_SAMPLES_TO_TRAIN}건·{ptc.MIN_CLASSES_TO_TRAIN}종 필요). "
               f"현재 정확도가 높은 것부터 위에 보여줍니다.")

    meta = ptc.load_meta()
    prev_results = (meta or {}).get("results", {})

    def _current_accuracy(t):
        r = prev_results.get(t)
        return r["cv_accuracy"] if r and r.get("cv_accuracy") is not None else -1

    ordered_targets = sorted(ptc.TARGETS, key=_current_accuracy, reverse=True)

    for t in ordered_targets:
        prev = prev_results.get(t)
        with st.container(border=True):
            if prev and prev.get("cv_accuracy") is not None:
                st.write(f"**{t}** — 현재 정확도(교차검증) 약 {prev['cv_accuracy']*100:.0f}% "
                         f"(샘플 {prev['n_samples']}건 · {prev['n_classes']}종)")
            elif prev:
                st.write(f"**{t}** — 학습됨 (샘플 {prev['n_samples']}건 · {prev['n_classes']}종, 정확도 계산 안 됨)")
            else:
                st.write(f"**{t}** — 아직 학습된 적 없음")

            if ptc.can_train(t):
                if st.button(f"'{t}' 재학습하기", key=f"retrain_{t}"):
                    try:
                        with st.spinner("학습 중..."):
                            r = ptc.train_and_save_meta(t)
                    except Exception as e:
                        st.error(f"학습 중 오류가 발생했습니다: {e}")
                    else:
                        acc = f" · 교차검증 정확도 약 {r['cv_accuracy']*100:.0f}%" if r["cv_accuracy"] is not None else ""
                        st.success(f"[{t}] 학습 완료 — 샘플 {r['n_samples']}건, {r['n_classes']}종{acc}")
                        st.rerun()
            else:
                labeled = ptc.training_summary()["per_target"][t]["labeled"]
                need = max(ptc.MIN_SAMPLES_TO_TRAIN - labeled, 0)
                st.caption(f"학습 불가 — 최소 {ptc.MIN_SAMPLES_TO_TRAIN}건·{ptc.MIN_CLASSES_TO_TRAIN}종 필요 "
                           f"(현재 {labeled}건 · 약 {need}건 더 필요)")

    # ---------------- 테스트 ----------------
    if ptc.has_any_model():
        st.divider()
        st.subheader("4) 테스트 — 사업명을 넣어보고 예측 확인")
        t1, t2 = st.columns(2)
        test_name = t1.text_input("사업명", key="ptype_test_name")
        test_acct = t2.text_input("예산과목 (선택)", key="ptype_test_acct")
        if test_name.strip():
            pred = ptc.predict(pd.DataFrame([{"사업명": test_name, "예산과목": test_acct}]))
            row = pred.iloc[0]
            result_cols = st.columns(len(ptc.TARGETS))
            for i, t in enumerate(ptc.TARGETS):
                if f"{t}_예측" not in pred.columns:
                    continue
                value = row[f"{t}_예측"]
                conf = row[f"{t}_확신도"]
                if str(value).strip() == "" or pd.isna(conf):
                    result_cols[i].metric(f"{t} 예측", "해당없음")
                else:
                    result_cols[i].metric(f"{t} 예측", str(value), f"확신도 {int(conf*100)}%")

    # ---------------- 초기화 ----------------
    st.divider()
    with st.expander("학습 초기화 (주의)"):
        ic1, ic2 = st.columns(2)
        with ic1:
            if st.button("모델만 초기화"):
                ptc.reset_models()
                st.success("모델을 초기화했습니다. (학습데이터는 보존)")
                st.rerun()
        with ic2:
            confirm = st.checkbox("학습데이터까지 전부 삭제", key="ptype_reset_all")
            if st.button("전체 초기화", disabled=not confirm):
                ptc.reset_all()
                st.success("학습데이터와 모델을 모두 초기화했습니다.")
                st.rerun()


def _render_discovery():
    st.caption("아직 '투자유형·투자유형 세부' 체계가 없는 예산과목의 사업명을 유사도로 묶어 후보를 제안합니다. "
               "묶인 그룹에 이름을 붙이면 그대로 학습데이터에 들어갑니다 (사람이 이름만 붙이면 됨).")

    categories = cd.list_budget_categories()
    if not categories:
        st.info("먼저 '예산 계획 업로드'에서 예산계획을 올려주세요 (사업명·예산과목 목록이 필요합니다).")
        return

    trained_categories = set(ptc.load_training_data()["예산과목"].astype(str).str.strip()) - {""}
    label_of = {c: f"{c}  ({'분류 데이터 있음' if c in trained_categories else '미분류'})" for c in categories}
    category = st.selectbox("예산과목 선택", categories, format_func=lambda c: label_of[c], key="disc_category")

    names = cd.project_names_for_category(category)
    if not names:
        st.warning(f"'{category}'에 속한 사업명을 예산계획에서 찾지 못했습니다.")
        return
    st.caption(f"'{category}'에 속한 사업명 {len(names)}건을 찾았습니다.")

    max_k = max(1, min(20, len(names)))
    default_k = max(1, min(max_k, len(names) // 4 or 1))
    n_clusters = st.slider("몇 개 그룹으로 나눠볼까요?", min_value=1, max_value=max_k, value=default_k,
                           key=f"disc_k_{category}")

    if st.button("그룹 나눠보기", key=f"disc_run_{category}"):
        st.session_state[f"disc_clusters_{category}"] = cd.suggest_clusters(names, n_clusters)

    clusters = st.session_state.get(f"disc_clusters_{category}")
    if not clusters:
        return

    st.divider()
    st.caption(f"{len(clusters)}개 그룹으로 나눴습니다. 각 그룹을 살펴보고 이름을 붙여주세요 (비워두면 학습에 반영되지 않습니다).")

    naming = {}
    for g in clusters:
        with st.container(border=True):
            st.write(f"**그룹 {g['cluster']}** — {g['count']}건")
            with st.expander(f"포함된 사업명 {g['count']}건 보기", expanded=g['count'] <= 8):
                st.dataframe(pd.DataFrame({"사업명": g["members"]}), width="stretch", hide_index=True)
            n1, n2 = st.columns(2)
            major_name = n1.text_input("투자유형", key=f"disc_major_{category}_{g['cluster']}").strip()
            if major_name == ptc.MINOR_TARGET_PARENT["투자유형세부"]:
                minor_name = n2.text_input("투자유형 세부", key=f"disc_minor_{category}_{g['cluster']}").strip()
            else:
                minor_name = ""
                n2.caption(f"(투자유형이 '{ptc.MINOR_TARGET_PARENT['투자유형세부']}'일 때만 입력)")
            naming[g["cluster"]] = (major_name, minor_name)

    named_count = sum(1 for v in naming.values() if any(v))
    if st.button(f"이름 붙인 {named_count}개 그룹을 학습데이터에 추가", type="primary",
                 disabled=named_count == 0, key=f"disc_add_{category}"):
        rows = []
        for g in clusters:
            major_name, minor_name = naming[g["cluster"]]
            if not (major_name or minor_name):
                continue
            for member in g["members"]:
                rows.append({"사업명": member, "예산과목": category,
                             "투자유형": major_name, "투자유형세부": minor_name})
        n = ptc.append_training_examples(pd.DataFrame(rows))
        st.success(f"{len(rows)}건을 학습데이터에 추가했습니다 · 현재 누적 {n}건. "
                   f"'분류자료 업로드해서 학습' 탭에서 재학습하면 반영됩니다.")
        del st.session_state[f"disc_clusters_{category}"]
        st.rerun()


def render():
    st.caption("투자유형 학습 · 이미 분류해 둔 자료를 올려 '사업명 → 투자유형/세부' 모델을 학습시킵니다")
    _render_summary()
    st.divider()

    tab_upload, tab_discover = st.tabs(["📥 분류자료 업로드해서 학습", "🔍 새 예산과목 분류 후보 제안"])
    with tab_upload:
        _render_upload_and_train()
    with tab_discover:
        _render_discovery()
