"""grace 최신 사업매칭 도구(별도 메뉴). 리더 기존 화면과 독립.

raw + 예산계획만으로 사업별 실적을 산출(실적/채점표 불필요). 담당자 확정 보정 내장.
임베드 HTML은 저장소 루트의 matching_tool_grace/ 폴더(별도)를 읽는다.
"""
from pathlib import Path
import streamlit as st
import streamlit.components.v1 as components

HTML = Path(__file__).resolve().parents[2] / 'matching_tool_grace' / '예산실적정리.html'


def render():
    st.subheader('사업 매칭 (grace 최신)')
    st.caption('raw + 예산계획만으로 사업별 실적 산출 · 실적/채점표 불필요 · 담당자 확정 보정 내장')
    st.info('별도 검토용 메뉴입니다. 리더 기존 「사업 실적 연결」 화면은 그대로 유지됩니다.')
    if not HTML.exists():
        st.error(f'매칭 도구 HTML을 찾지 못했습니다: {HTML}')
        return
    html = HTML.read_text(encoding='utf-8')
    st.download_button('매칭 HTML 다운로드', html, file_name='사업매칭_grace.html', mime='text/html')
    components.html(html, height=1000, scrolling=True)
