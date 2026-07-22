# 예산 실적 집계 프로그램 — 실행 방법

발전플랜트 지사별 유지보수 예산의 **계획 수립 · 실적 분석**을 자동화하는 로컬 웹앱(Streamlit).

## 1. 준비물
- **Python 3.10 이상** — 없으면 <https://www.python.org/downloads/> 에서 설치.
  (Windows 설치 시 **"Add Python to PATH"** 체크)
- 인터넷(최초 1회 패키지 설치용). 오프라인망은 아래 §4 참고.

## 2. 실행 (누구나)
| OS | 방법 |
|---|---|
| **Windows** | `run.bat` **더블클릭** |
| **macOS / Linux** | 터미널에서 `bash run.sh` (또는 `chmod +x run.sh` 후 `./run.sh`) |

실행하면 필요한 패키지를 자동 설치하고 웹앱이 뜹니다. 브라우저가 자동으로 열리며,
안 열리면 **http://localhost:8501** 로 접속하세요. 종료는 창에서 **Ctrl+C**.

## 3. 사용 흐름
- **① 계획본 생성 탭**: 구분(손익/자본)·연도 → 지사·예산과목 구성 → 사업별예산 xlsx 업로드 → 실행 → `{연도}년 {구분}예산_계획.xlsx` 다운로드
- **② 실적 분석 탭**: 지사·예산과목 구성 → 계획본 + `zrfm2` 업로드 → 실행 → `{연도}년 {구분}예산_실적.xlsx` · `zrfm2_V1` · `matched CSV` 다운로드

> **입력 데이터는 각자 준비**합니다(이 저장소에는 실데이터가 포함되지 않습니다).
> 계획 입력 양식은 앱의 "사업별예산_템플릿 다운로드" 버튼으로 받을 수 있습니다.

## 4. 오프라인(분리망) 설치
인터넷이 되는 PC에서 `pip download -r requirements.txt -d packages` 로 받은 뒤,
분리망 PC에서 `pip install --no-index --find-links packages -r requirements.txt` 로 설치하고
`run.bat`/`run.sh` 를 실행하세요.

## 5. 개발자용
- 수동 실행: `py -m streamlit run app.py` (Windows) / `python3 -m streamlit run app.py`
- 테스트: `py -m pytest -q`
- 모듈·설계 문서: `docs/`, 상위 프로젝트 문서(PRD·연계규격·연동규격) 참조.

## 6. 주의
- 이 프로그램은 **로컬 단일 사용자** 도구입니다. 실적/예산 데이터는 외부로 전송되지 않습니다.
- 저장소에는 **코드만** 포함되며 실데이터(zrfm2·예산·config·산출물)는 제외되어 있습니다.
