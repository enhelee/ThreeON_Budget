"""실적집계 대시보드 화면"""
import glob
import os
import altair as alt
import streamlit as st
import pandas as pd
import budget_actual_summary as bas
import longterm_forecast as lf
import mapping_config
import build_state as bstate
from mapping_config import get_site_display_name, get_current_site_type, apply_mappings
from views.project_type_test_page import get_shared_actual_df


def _mtime(path: str) -> float:
    return os.path.getmtime(path) if os.path.exists(path) else -1.0


def _mapping_sig() -> tuple:
    """지사유형/손익자본 매핑에 쓰이는 파일들의 (절대경로, mtime) - 캐시 무효화 키.
    절대경로까지 포함하는 이유: pytest가 서로 다른 tmp_path(작업디렉터리)에서 같은 파일명을 써도
    캐시가 섞이지 않게 하기 위함."""
    paths = [mapping_config.SITE_TYPE_PATH, mapping_config.ACCOUNT_CAT_PATH, mapping_config.DEPT_MASTER_PATH]
    return tuple((os.path.abspath(p), _mtime(p)) for p in paths)


@st.cache_data(show_spinner="실적 데이터 불러오는 중...")
def _cached_classified_df(years: tuple, sig: tuple) -> pd.DataFrame:
    """classified_{연도}.csv를 읽어 지사유형·사업장명까지 매핑한 결과를 캐시한다.
    sig(해당 연도 파일들의 mtime + 매핑파일 mtime)가 바뀌지 않는 한(=새로 업로드되거나 매핑이
    바뀌지 않는 한) 다시 계산하지 않는다 - apply_mappings()의 행 단위 연산이 이 화면에서 가장 느린
    부분이라 rerun마다 반복하지 않도록 하는 게 핵심."""
    dfs = [pd.read_csv(f"classified_{y}.csv") for y in years]
    all_df = pd.concat(dfs, ignore_index=True)
    all_df["연도"] = pd.to_datetime(all_df["전기일"]).dt.year
    all_df = apply_mappings(all_df)  # 지사유형 컬럼 추가
    all_df["사업장명"] = all_df["사업장"].apply(lambda v: get_site_display_name(v) if pd.notna(v) else v)
    return all_df


@st.cache_data(show_spinner=False)
def _cached_budget_df(years: tuple, sig: tuple) -> pd.DataFrame:
    frames = [pd.read_csv(f"budget_{y}.csv") for y in years if os.path.exists(f"budget_{y}.csv")]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


@st.cache_data(show_spinner=False)
def _cached_test_actual_prep(shared: pd.DataFrame, sig: tuple) -> pd.DataFrame:
    """Test 모드 공유 실적에 사업장명·지사유형을 붙인다(shared 내용 자체는 st.cache_data가 해시)."""
    df = shared.copy()
    df["사업장명"] = df["사업장"].apply(lambda v: get_site_display_name(v) if pd.notna(v) and str(v).strip() else v)
    df["지사유형"] = df["사업장"].apply(lambda v: get_current_site_type(v) if pd.notna(v) and str(v).strip() else "미매핑")
    return df


@st.cache_data(show_spinner=False)
def _cached_test_budget_df(years: tuple, sig: tuple) -> pd.DataFrame:
    return lf.load_test_budget_plan_multi(list(years))


def _dashboard_test_fingerprint(shared: pd.DataFrame) -> str:
    """대시보드를 다시 만들어야 하는지 판단하는 데 쓰는 지문 - 공유 실적 내용 + 예산계획/매핑 파일들."""
    budget_paths = [lf.test_budget_plan_path(y) for y in lf.load_test_budget_plan_years()]
    mapping_paths = [mapping_config.SITE_TYPE_PATH, mapping_config.ACCOUNT_CAT_PATH, mapping_config.DEPT_MASTER_PATH]
    return bstate.fingerprint(df=shared, paths=tuple(budget_paths + mapping_paths))


def _labeled_bar_chart(series: pd.Series, unit: str = "억"):
    """금액이 큰 항목부터 정렬하고, 막대 위에 금액(억원) 라벨을 표시하는 차트.
    금액이 0인 항목은 시각적으로 제외한다(집계표에는 그대로 남아있음).
    st.bar_chart는 x축을 항상 가나다순으로 재정렬하고 막대 라벨을 지원하지 않아 Altair로 직접 그린다."""
    series = series[series != 0]
    if series.empty:
        st.caption("표시할 데이터가 없습니다.")
        return

    df = series.rename("금액").rename_axis("항목").reset_index()
    df = df.sort_values("금액", ascending=False).reset_index(drop=True)
    order = df["항목"].tolist()

    base = alt.Chart(df).encode(
        x=alt.X("항목:N", sort=order, title=None, axis=alt.Axis(labelAngle=-60)),
        y=alt.Y("금액:Q", title=f"금액({unit}원)"),
    )
    bars = base.mark_bar(color="#2d5980")
    labels = base.mark_text(dy=-8, fontSize=11).encode(
        text=alt.Text("금액:Q", format=",.1f"),
    )
    st.altair_chart(bars + labels, width="stretch")


def _render_budget_vs_actual(budget_df: pd.DataFrame, actual_df: pd.DataFrame):
    """'배정 대비 실적' 표(지사유형별 요약 + 계정과목별 상세)를 그린다.
    actual_df: 지사유형, 계정과목, 금액 컬럼 필요. 사업 매칭 단계 없이 지사유형×계정과목만으로
    집계하므로 Test 모드처럼 사업명 매칭을 거치지 않은 실적에도 그대로 쓸 수 있다."""
    st.subheader("배정 대비 실적")
    if budget_df.empty:
        st.caption("등록된 예산계획이 없어 배정 대비 실적을 계산할 수 없습니다.")
        return
    if actual_df.empty:
        st.caption("집계할 실적이 없습니다.")
        return

    budget_summary = bas.budget_by_site_type_account(budget_df)
    actual_summary = bas.actual_by_site_type_account(actual_df)
    merged = bas.merge_budget_actual(budget_summary, actual_summary)
    if merged.empty:
        st.caption("배정·실적 데이터가 없습니다.")
        return

    st.caption("금액 단위: 억원. 지사유형×계정과목 기준 집계이며, 사업명 매칭 결과(계획 대비 실적)와는 별개 화면입니다.")
    st.write("**지사유형별 요약**")
    st.dataframe(bas.site_type_summary_table(merged), width="stretch")

    st.write("**손익 계정과목별 상세**")
    st.dataframe(bas.account_detail_table(merged, "손익"), width="stretch")

    st.write("**자본 계정과목별 상세**")
    st.dataframe(bas.account_detail_table(merged, "자본"), width="stretch")


def render():
    st.caption("실적집계 대시보드")
    classified_files = sorted(glob.glob("classified_*.csv"))
    available_years = [int(f.split("_")[1].split(".")[0]) for f in classified_files]

    if not available_years:
        st.info("먼저 2단계에서 분류를 확정하고 저장해주세요.")
    else:
        sel_years = st.multiselect("연도 선택 (복수 선택 가능)", sorted(available_years), default=sorted(available_years))
        if not sel_years:
            st.warning("연도를 1개 이상 선택해주세요.")
        else:
            years_key = tuple(sorted(sel_years))
            sig = tuple(_mtime(f"classified_{y}.csv") for y in years_key) + _mapping_sig()
            all_df = _cached_classified_df(years_key, sig)

            sites = sorted(all_df["사업장명"].dropna().unique().tolist())
            sel_sites = st.multiselect("지사 선택 (복수 선택 가능)", sites, default=sites)
            filtered = all_df[all_df["사업장명"].isin(sel_sites)]

            c1, c2, c3 = st.columns(3)
            c1.metric("총 실적", f"{filtered['금액'].sum()/1e8:.1f}억")
            c2.metric("지사 수", filtered["사업장명"].nunique())
            c3.metric("투자유형 수", filtered["투자유형_확정"].nunique())

            st.subheader("지사별 실적")
            by_site = filtered.groupby("사업장명")["금액"].sum().sort_values(ascending=False) / 1e8
            _labeled_bar_chart(by_site)

            st.subheader("투자유형별 실적")
            by_type = filtered.groupby("투자유형_확정")["금액"].sum().sort_values(ascending=False) / 1e8
            _labeled_bar_chart(by_type)

            st.subheader("지사유형별 실적")
            by_sitetype = filtered.groupby("지사유형")["금액"].sum().sort_values(ascending=False) / 1e8
            _labeled_bar_chart(by_sitetype)

            st.subheader("예산과목별 실적")
            by_account = filtered.groupby("계정과목")["금액"].sum().sort_values(ascending=False) / 1e8
            _labeled_bar_chart(by_account)

            with st.expander("상세 집계 표 (지사 × 투자유형)"):
                pivot = filtered.pivot_table(index="사업장명", columns="투자유형_확정", values="금액", aggfunc="sum", fill_value=0) / 1e8
                st.dataframe(pivot.round(1), width="stretch")

            st.divider()
            budget_sig = tuple(_mtime(f"budget_{y}.csv") for y in years_key)
            budget_df = _cached_budget_df(years_key, budget_sig)
            if budget_df.empty:
                st.subheader("배정 대비 실적")
                st.caption("선택한 연도에 등록된 예산계획이 없어 배정 대비 실적을 계산할 수 없습니다. "
                           "'예산 계획 업로드'에서 먼저 등록해주세요.")
            else:
                _render_budget_vs_actual(budget_df, filtered[["지사유형", "계정과목", "금액"]])


def render_test():
    """Test 모드 · 실적집계 대시보드 - '계획 및 실적 업로드'(또는 '투자유형 예측 테스트')에서
    업로드·확정한 결과를 그대로 집계한다. 정식 집계(classified_*.csv 기반)와는 완전히 별개다."""
    st.caption("Test 모드 · 실적집계 대시보드")
    st.info("🧪 '계획 및 실적 업로드'(또는 '투자유형 예측 테스트') 화면에서 업로드하고 확인·수정한 결과를 "
            "기준으로 계산합니다. 정식 집계(예산 실적 분석 > 실적집계 대시보드)와는 별개입니다.")

    shared = get_shared_actual_df()
    has_actual = shared is not None and not shared.empty
    has_budget = bool(lf.load_test_budget_plan_years())

    mapping_config.load_site_type_map()  # 없으면 여기서 기본값으로 seed됨 - 지문 계산 전에 미리 해서
    # 파일이 "없다가 생기는" 것만으로 지문이 바뀌어 매번 "데이터가 변경되었습니다"로 오판하지 않게 한다.
    current_fp = _dashboard_test_fingerprint(shared) if has_actual else None
    saved_fp = bstate.load_build_fingerprint("dashboard_test")
    built = has_actual and saved_fp is not None
    data_changed = built and saved_fp != current_fp

    st.subheader("현재 상태")
    status_bits = [f"예산계획 업로드 {'완료' if has_budget else '미완료'}",
                   f"실적 업로드 {'완료' if has_actual else '미완료'}"]
    status_bits.append("⚠️ 데이터가 변경되었습니다 (다시 만들어주세요)" if data_changed
                        else f"대시보드 {'작성됨' if built else '미작성'}")
    st.info(" · ".join(status_bits))

    if not has_actual:
        st.info("먼저 '계획 및 실적 업로드'(또는 '투자유형 예측 테스트') 화면에서 실적 데이터를 업로드하고 결과를 확인해주세요.")
        return

    if (shared["사업장"].astype(str).str.strip() == "").all():
        st.warning("'사업장' 칸을 지정하지 않아 지사별 집계를 할 수 없습니다.")
        return

    button_label = "대시보드 다시 만들기 (데이터 변경 반영)" if data_changed else \
        ("대시보드 다시 만들기 (최신 업로드 반영)" if built else "이 데이터로 대시보드 만들기")
    rebuild_clicked = st.button(button_label, type="primary", key="dash_test_build_btn")
    if rebuild_clicked:
        built = True
        data_changed = False

    if not built or data_changed:
        st.caption("버튼을 누르면 현재 업로드된 예산계획·실적 데이터를 기준으로 대시보드를 계산합니다.")
        return

    # 지문이 일치하면(=버튼을 새로 누른 게 아니면) 저장해둔 결과를 그대로 불러와 다시 계산하지 않는다.
    # st.cache_data만으로는 부족하다 - 앱을 재시작하면 그 캐시는 비어서 첫 호출은 여전히 다시 계산되기
    # 때문에, 계산 결과 자체를 파일로 저장해뒀다가 재사용해야 진짜로 "다시 계산 안 함"이 된다.
    prepared = None if rebuild_clicked else bstate.load_artifact("dashboard_test_prepared")
    if prepared is None:
        with st.status("실적 데이터 준비 중 (사업장명·지사유형 매핑)...", expanded=True) as prep_status:
            st.write(f"실적 {len(shared)}건 매핑 중...")
            prepared = _cached_test_actual_prep(shared, _mapping_sig())
            prep_status.update(label="실적 데이터 준비 완료", state="complete", expanded=False)
        bstate.save_artifact("dashboard_test_prepared", prepared)
        bstate.save_build_fingerprint("dashboard_test", current_fp)
    else:
        st.caption("✅ 이전에 계산해둔 데이터를 그대로 불러왔습니다 (다시 계산하지 않음).")

    available_years = sorted(
        int(y) for y in pd.to_numeric(prepared.get("연도", pd.Series(dtype=float)), errors="coerce").dropna().unique()
    )
    if available_years:
        sel_years = st.multiselect("연도 선택 (복수 선택 가능)", available_years, default=available_years,
                                    key="dash_test_years")
        if not sel_years:
            st.warning("연도를 1개 이상 선택해주세요.")
            return
        all_df = prepared[pd.to_numeric(prepared["연도"], errors="coerce").isin(sel_years)]
        years_key = tuple(sorted(sel_years))
        budget_sig = tuple(_mtime(lf.test_budget_plan_path(y)) for y in years_key) + (_mtime(lf.TEST_BUDGET_PLAN_PATH),)
        test_budget_df = _cached_test_budget_df(years_key, budget_sig)
    else:
        # 연도 태그가 없는 구버전 세션 상태(예: 저장 전 방금 확정한 결과) - 전체를 그대로 쓰고,
        # 예산계획은 당해년도(BASE_YEAR) 백데이터로 대체한다(연도별 저장 이전과 동일한 동작 유지).
        all_df = prepared
        test_budget_df = lf.load_test_budget_plan(lf.BASE_YEAR)

    # 실제 집계(pandas 연산)는 st.status 블록 안에서 단계별로 진행 메시지를 남기며 계산하고,
    # 화면에 계속 보여야 하는 차트/표는 블록을 벗어난 뒤 그 계산 결과로 그린다 - st.status는
    # 완료 후 접히므로 안에서 직접 그리면 최종 화면에서 다시 사라져 버린다.
    with st.status("대시보드 계산 중...", expanded=True) as status:
        st.write("핵심 지표 계산 중...")
        total_actual = float(all_df["금액"].sum())
        n_sites = int(all_df["사업장명"].nunique())
        n_types = int(all_df["투자유형_확정"].nunique())

        st.write("지사별 실적 계산 중...")
        by_site = all_df.groupby("사업장명")["금액"].sum().sort_values(ascending=False) / 1e8

        st.write("투자유형별 실적 계산 중...")
        by_type = all_df.groupby("투자유형_확정")["금액"].sum().sort_values(ascending=False) / 1e8

        st.write("지사유형별 실적 계산 중...")
        by_sitetype = all_df.groupby("지사유형")["금액"].sum().sort_values(ascending=False) / 1e8

        st.write("예산과목별 실적 계산 중...")
        by_account = all_df.groupby("예산과목")["금액"].sum().sort_values(ascending=False) / 1e8

        st.write("상세 집계 표 계산 중...")
        pivot = all_df.pivot_table(index="사업장명", columns="투자유형_확정", values="금액", aggfunc="sum", fill_value=0) / 1e8

        status.update(label="대시보드 계산 완료", state="complete", expanded=False)

    c1, c2, c3 = st.columns(3)
    c1.metric("총 실적", f"{total_actual/1e8:.1f}억")
    c2.metric("지사 수", n_sites)
    c3.metric("투자유형 수", n_types)

    st.subheader("지사별 실적")
    _labeled_bar_chart(by_site)

    st.subheader("투자유형별 실적")
    _labeled_bar_chart(by_type)

    st.subheader("지사유형별 실적")
    _labeled_bar_chart(by_sitetype)

    st.subheader("예산과목별 실적")
    _labeled_bar_chart(by_account)

    with st.expander("상세 집계 표 (지사 × 투자유형)"):
        st.dataframe(pivot.round(1), width="stretch")

    st.divider()
    if test_budget_df.empty:
        st.subheader("배정 대비 실적")
        st.caption("테스트 예산계획이 없어 배정 대비 실적을 계산할 수 없습니다. "
                   "Test 모드 '계획 및 실적 업로드'에서 먼저 등록해주세요.")
    else:
        actual_for_summary = all_df.rename(columns={"예산과목": "계정과목"})[["지사유형", "계정과목", "금액"]]
        _render_budget_vs_actual(test_budget_df, actual_for_summary)
