"""기존 앱 내부의 매칭 실행·확인·표준화 연결 화면."""
from pathlib import Path
import json
import streamlit as st
import streamlit.components.v1 as components
import checkpoint_actuals

HTML = Path(__file__).resolve().parents[1] / 'matching/예산실적정리.html'

def render():
    st.subheader('사업 실적 연결')
    st.caption('전표를 사업에 연결하고, 확인한 배정분을 예산 계획에 활용하세요.')
    try:
        current, current_summary = checkpoint_actuals.load_saved()
    except (ValueError, KeyError, OSError) as exc:
        st.error(f'저장한 연결을 읽지 못했습니다: {exc}')
        return
    if not current.empty:
        columns = st.columns(3)
        columns[0].metric('연결된 실적 연도', ' · '.join(map(str, sorted(current['연도'].unique()))))
        columns[1].metric('연결된 사업행', f'{len(current):,}개')
        columns[2].metric('배정된 실적', f'{current["금액"].sum()/100000000:,.2f}억원')
        st.caption('연결된 배정분 기준입니다. 미배정·제외 금액은 아래 상세 내역에서 확인하세요.')
    st.markdown('<div class="flow-strip"><div class="flow-step"><span>01 / MATCH</span><strong>원천자료 매칭</strong></div><div class="flow-step"><span>02 / REVIEW</span><strong>배정 결과 확인</strong></div><div class="flow-step"><span>03 / PLAN</span><strong>예산 계획에 연결</strong></div></div>', unsafe_allow_html=True)
    with st.expander('1. 매칭 도구 실행 / 다운로드', expanded=False):
        html = HTML.read_text(encoding='utf-8')
        st.download_button('매칭 HTML 다운로드', html, file_name='사업매칭.html', mime='text/html')
        components.html(html, height=1000, scrolling=True)
    upload = st.file_uploader('2. 매칭 도구에서 내려받은 팀 점검용 결과 JSON', type=['json'], key='matching_json')
    if upload is not None:
        content = upload.getvalue()
        try:
            meta = json.loads(content)
            years = meta.get('sourceYears', [])
            if len(years) != 1 or not isinstance(years[0], int):
                raise ValueError('최신 매칭 도구에서 단일 연도 결과를 다시 생성하세요.')
            year = years[0]
            _, frame, summary = checkpoint_actuals.prepare_result(content, year)
        except (ValueError, TypeError, AttributeError, KeyError) as exc:
            st.error(str(exc))
            st.stop()
        st.write(f'{year}년 · {len(frame):,}개 사업행 · 연결금액 {int(frame["금액"].sum()):,}원')
        st.dataframe(summary, hide_index=True, width='stretch')
        with st.expander('사업별 연결금액 확인'):
            st.dataframe(frame, hide_index=True, width='stretch')
        st.warning('미배정 금액은 연결되지 않습니다. 아래 버튼은 표시된 배정분을 중간 점검용 예측 입력으로 저장합니다. 같은 연도의 이전 버전은 보관됩니다.')
        if st.button(f'3. {year}년 배정분을 표준화·중장기 예산에 연결', key='save_matching_actuals', type='primary'):
            checkpoint_actuals.save_result(content, year)
            st.success('연결했습니다. 「예산 표준화」 또는 「중장기 예산 예측」에서 「연결한 사업 실적」을 선택하세요.')
    try:
        saved, summary = checkpoint_actuals.load_saved()
    except (ValueError, KeyError, OSError) as exc:
        st.error(f'저장한 연결을 읽지 못했습니다: {exc}')
        return
    if not saved.empty:
        st.subheader('현재 연결된 실적')
        st.dataframe(summary, hide_index=True, width='stretch')
