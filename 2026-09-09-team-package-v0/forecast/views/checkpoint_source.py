"""두 계산 화면이 동일한 연결 실적을 사용하게 하는 선택기."""
import streamlit as st
import checkpoint_actuals
from mapping_config import get_current_site_type

def select_actuals(key):
    try:
        actuals, summary = checkpoint_actuals.load_saved()
    except (ValueError, KeyError, OSError) as exc:
        st.error(f'연결 실적을 읽지 못했습니다: {exc}')
        st.stop()
    if actuals.empty:
        return None
    choice = st.radio('계산에 사용할 실적', ['연결한 사업 실적', '기존 투자유형 분류 실적'], key=key)
    if choice == '기존 투자유형 분류 실적':
        return None
    actuals = actuals.copy()
    actuals['지사유형'] = actuals['사업장'].apply(get_current_site_type)
    st.caption('연결 연도: '+', '.join(map(str, sorted(actuals['연도'].unique())))+' · 기존 분류 실적과 중복 합산하지 않습니다.')
    st.warning('현재는 연결된 사업 배정분만 계산에 사용합니다. 미배정·제외 금액은 예측 입력에 포함되지 않으므로 중간 점검용으로 확인하세요.')
    with st.expander('계산에 포함된 금액과 미배정·제외 내역'):
        st.dataframe(summary, hide_index=True, width='stretch')
    return actuals
