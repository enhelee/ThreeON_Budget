# ONDO(온도) — 예산 계획 대비 집행실적 자동 대사 · 10개년 소요 전망

2026 공공 AI 대전환 챌린지 세션 1(자유주제) 출품작 · 한국지역난방공사 ThreeON 팀

> 이 저장소의 데이터는 전부 **난수로 만든 합성(가짜) 데이터**입니다. 실제 사업명·금액·전표는 들어 있지 않습니다.

## 접속 주소
- 심사용 시연 주소: (제출 시 기입) — 가짜 데이터가 미리 들어 있습니다.
- 직접 설치하면 `http://localhost:8080` (아래 «실행 방법»)

## 무엇을 하는 도구인가
공공기관이 매년 손으로 하는 «사업별 예산 계획(엑셀) ↔ 회계 집행 전표(SAP 등)» 대조를 자동화하고,
그 실적으로 표준예산과 10개년 소요 전망까지 이어서 계산하는 웹 도구입니다.
외부 생성형 AI를 호출하지 않아 **같은 입력이면 항상 같은 결과**가 나오고, 폐쇄망에서 그대로 동작합니다.

## 주요 기능
| 단계 | 기능 | 기술 |
|---|---|---|
| 1 예산 계획 | 계획 엑셀(양식1) 업로드 → DB 등록, 과목·지사 표기 정규화 | pandas · openpyxl |
| 2 실적 집계 | 전표를 계획 사업에 자동 연결(과목 → 지사 → 참조전표번호 묶음 → 사업명 유사도 4단계) | 규칙 + rapidfuzz 문자열 유사도 |
| 3 검토 | 확신도 낮은 전표만 금액 큰 순으로, 근거 문장 자동 작성, 승인·재배정 | 사실 4종 + 추정 규칙 9종 |
| 학습 | 담당자 판단을 학습표에 쌓아 다음 해 자동 적용, 엑셀 보정사전(배정·제외) | 조회표 · 규칙 |
| 분류 | 사업명 → 투자유형 | scikit-learn(TF-IDF + 로지스틱 회귀) |
| 4 통계 | 과목·지사·연도 비교, 팀 양식 엑셀 내려받기 | openpyxl |
| 5 표준화 | 마감 실적으로 지사 × 정비등급 표준금액, 설비용량 보정, 백테스트(학습 2·3·5·10년) | 통계 규칙 |
| 6 전망 | 2026~2035 10개년 소요(표준금액 × 물가 + 정비등급 일정 + 정기계약 + 투자계획) | 결정론적 계산 모델 |
| 보고서 | 기관 보고서 한글(.hwpx) 자동 작성 | hwpx 템플릿 채우기 |
| 운영 | 연도 마감(잠금)·감사 로그·원본 보존·캐릭터 챗봇 안내 | FastAPI · SQLite/PostgreSQL |

## 실행 방법
### A. Docker (권장)
```bash
cp .env.example .env              # 비밀번호를 비워 두면 로그인 없이 열립니다
DEMO_SEED=1 docker compose -f deploy/docker-compose.yml up -d --build
# 1~2분 뒤 http://localhost:8080 — 첫 기동 때 가짜 데이터(2016~2026)가 자동으로 들어갑니다
```

### B. 파이썬
```bash
cd app
python -m pip install -r requirements.txt
cd web && npm ci && npm run build && cd ..        # 화면 빌드(Node 18+)
python -m uvicorn server:app --port 8010
python scripts/load_demo.py http://localhost:8010  # 다른 터미널에서 — 가짜 데이터 넣기(약 10초)
```

### 가짜 데이터
- `app/demo_data/` — 2016~2026 계획, 2016~2025 전표(연 약 1,700건), 기준정보, 보정 규칙, 정비등급·물가지수
- 다시 만들기: `python app/scripts/make_demo_data.py` (시드 고정)
- 넣기: `python app/scripts/load_demo.py <주소>` — 자료가 이미 있는 서버에는 넣지 않습니다

## 써 보는 순서(핵심 흐름)
1. **실적 대사와 검토** — 2 실적 집계(2025) → 검토 대기 → 근거 확인 → 승인/재배정 → 설정 › AI 학습
2. **표준화와 전망** — 5 표준화(백테스트 오차) → 6 중장기 예측(정비등급을 바꾸면 전망이 다시 계산)
3. **보고서와 챗봇** — 보고서 › 한글 파일 받기 · 오른쪽 챗봇 «올해 어디까지 했어?»

## LLM
핵심 기능에는 LLM이 필요 없습니다(API 키 입력 없음). 챗봇은 규칙 엔진(`app/src/budget/chat/engine.py`)이며,
같은 인터페이스의 엔진을 추가해 공통기반 모델을 «질문 이해·문장 다듬기»에만 붙일 수 있게 설계했습니다(숫자는 항상 규칙 엔진).

## 폴더
```
app/            FastAPI 서버(server.py) · 계산부(src/budget) · 화면(web) · 테스트(tests) · 가짜 데이터(demo_data)
deploy/         Dockerfile · docker-compose · 사내 서버 반입 스크립트(onprem)
docs/           사내 이관 가이드 · 보안 설계
```

## 테스트
```bash
cd app && python -m pytest -q
```

## 오픈소스
FastAPI(MIT) · uvicorn(BSD) · pandas(BSD) · openpyxl(MIT) · rapidfuzz(MIT) · scikit-learn(BSD) · Vite(MIT) · Tailwind CSS(MIT)
