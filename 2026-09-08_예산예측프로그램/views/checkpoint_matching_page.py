"""기존 앱 내부의 매칭 실행·확인·표준화 연결 화면."""
from pathlib import Path
import json
import streamlit as st
import streamlit.components.v1 as components
import checkpoint_actuals

HTML = Path(__file__).resolve().parents[2] / 'checkpoints/2026-09-08-codex/예산실적정리.html'

def render():
    st.subheader('사업 실적 연결')
    st.write('① 매칭 실행 → ② 결과 JSON 확인 → ③ 표준화·중장기 예산으로 연결')
    st.caption('집계표 기준으로 배정한 연간 실적을 사용합니다. 원본 전표와 기존 분류 CSV는 덮어쓰지 않습니다.')
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
        if st.button(f'3. {year}년 배정분을 표준화·중장기 예산에 연결', key='save_matching_actuals'):
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
