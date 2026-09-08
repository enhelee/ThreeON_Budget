"""
실적 업데이트(zrfm2) & 검증 화면
실행: streamlit run app.py

각 메뉴의 실제 화면 로직은 views/ 아래 모듈로 분리되어 있다.
이 파일은 사이드바 메뉴 구성과 페이지 라우팅만 담당한다.

메뉴 구성은 PRD의 파이프라인을 따른다:
예산 계획 수립 -> 예산 실적 집계 -> 예산 실적 분석 -> 예산 표준화 -> 중장기 예산 예측
('예산 실적 집계'는 원자료를 만드는 단계 - 업로드/매칭/계획대비실적,
 '예산 실적 분석'은 그 결과를 들여다보는 단계 - 분류검토/대시보드/리포트)
"""
import streamlit as st
from year_status import load_status
from views import (
    checkpoint_matching_page,
    actuals_upload_page,
    budget_upload_page,
    project_matching_page,
    classification_review_page,
    plan_vs_actual_page,
    dashboard_page,
    custom_report_page,
    standardization_page,
    longterm_forecast_page,
    settings_page,
    project_type_learning_page,
    project_type_test_page,
    test_data_upload_page,
)

from pathlib import Path

st.set_page_config(page_title="ThreeON · 예산·실적 관리", layout="wide")
style = (Path(__file__).parent / "styles/workspace.css").read_text(encoding="utf-8")
st.markdown("<style>" + style + "</style>", unsafe_allow_html=True)
st.sidebar.markdown('<div class="threeon-brand"><b>Three<span>ON</span></b><small>발전설비 예산 워크스페이스</small></div>', unsafe_allow_html=True)
st.caption("THREEON / BUDGET WORKSPACE")
st.title("예산·실적 관리")
st.caption("사업별 실적을 검토하고, 다음 계획의 근거로 연결합니다.")

CATEGORY_PAGES = {
    "예산 계획 수립": ["예산 계획 업로드"],
    "예산 실적 집계": ["실적 업데이트(zrfm2)", "사업 매칭", "사업 실적 연결", "계획 대비 실적"],
    "예산 실적 분석": [
        "투자유형 분류 검토", "투자유형 학습 (분류자료)",
        "실적집계 대시보드", "맞춤 리포트",
    ],
    "예산 표준화": ["예산 표준화"],
    "중장기 예산 예측": ["중장기 예산 (26-35년)"],
    "설정": ["매핑 관리"],
    # 개발자용 - 실제 데이터 파이프라인과 무관하게 '투자유형 예측 테스트' 업로드분을 기준으로
    # 각 정식 메뉴와 동일한 계산을 미리 확인해보는 화면들을 모아둔다.
    "Test 모드": [
        "계획 및 실적 업로드", "실적집계 대시보드", "투자유형 예측 테스트", "맞춤 리포트",
        "예산 표준화", "중장기 예산 (26-35년)",
    ],
}
category = st.sidebar.radio("메뉴", list(CATEGORY_PAGES.keys()))
st.sidebar.divider()
page = st.sidebar.radio("세부 메뉴", CATEGORY_PAGES[category])
status = load_status()

# 연도(status)가 필요 없는 페이지는 인자 없이, 필요한 페이지는 status를 넘겨 호출한다.
# 같은 페이지명이 '정식'과 'Test 모드'에 동시에 존재할 수 있어 (카테고리, 페이지) 조합으로 키를 잡는다.
PAGE_RENDERERS = {
    ("예산 실적 집계", "사업 실적 연결"): lambda: checkpoint_matching_page.render(),
    ("예산 계획 수립", "예산 계획 업로드"): lambda: budget_upload_page.render(),
    ("예산 실적 집계", "실적 업데이트(zrfm2)"): lambda: actuals_upload_page.render(status),
    ("예산 실적 집계", "사업 매칭"): lambda: project_matching_page.render(status),
    ("예산 실적 집계", "계획 대비 실적"): lambda: plan_vs_actual_page.render(),
    ("예산 실적 분석", "투자유형 분류 검토"): lambda: classification_review_page.render(status),
    ("예산 실적 분석", "투자유형 학습 (분류자료)"): lambda: project_type_learning_page.render(),
    ("예산 실적 분석", "실적집계 대시보드"): lambda: dashboard_page.render(),
    ("예산 실적 분석", "맞춤 리포트"): lambda: custom_report_page.render(),
    ("예산 표준화", "예산 표준화"): lambda: standardization_page.render(),
    ("중장기 예산 예측", "중장기 예산 (26-35년)"): lambda: longterm_forecast_page.render(),
    ("설정", "매핑 관리"): lambda: settings_page.render(),
    ("Test 모드", "투자유형 예측 테스트"): lambda: project_type_test_page.render(),
    ("Test 모드", "계획 및 실적 업로드"): lambda: test_data_upload_page.render(),
    ("Test 모드", "실적집계 대시보드"): lambda: dashboard_page.render_test(),
    ("Test 모드", "맞춤 리포트"): lambda: custom_report_page.render_test(),
    ("Test 모드", "예산 표준화"): lambda: standardization_page.render_test(),
    ("Test 모드", "중장기 예산 (26-35년)"): lambda: longterm_forecast_page.render_test(),
}

PAGE_RENDERERS[(category, page)]()
