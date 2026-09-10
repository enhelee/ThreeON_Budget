"""Additive review entry point; never writes the team's existing data or programs."""
from pathlib import Path
import pandas as pd
import streamlit as st
from review_data import TABLES, load_result

st.set_page_config(page_title='사업매칭 중간 점검', layout='wide')
st.title('사업매칭 중간 점검')
st.write('HTML에서 생성한 결과를 팀 Python 환경에서 확인합니다. 금액 단위는 천원입니다.')
st.caption('이 화면은 검토용입니다. 기존 앱의 실적·예측 데이터로 자동 저장하지 않습니다.')
st.download_button('독립 HTML 작업본 다운로드',
                   Path(__file__).with_name('예산실적정리.html').read_bytes(),
                   file_name='사업매칭_중간점검.html', mime='text/html')
file = st.file_uploader('HTML의 「팀 점검용 결과 JSON」 파일', type=['json'])
if file is not None:
    try:
        result = load_result(file.getvalue())
    except (ValueError, TypeError, AttributeError) as exc:
        st.error(str(exc))
        st.stop()
    for tab, (key, label) in zip(st.tabs(list(TABLES.values())), TABLES.items()):
        with tab:
            rows = result[key]
            st.caption(f'{label}: {len(rows) - 1:,}행')
            st.dataframe(pd.DataFrame(rows[1:], columns=rows[0]), hide_index=True, width='stretch')
