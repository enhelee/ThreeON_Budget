# 예산·실적 분석 프로그램 — 실행 방법

발전플랜트 지사별 유지보수 예산의 **계획 수립 → 실적 자동매칭 → 검토·수정·학습 → 통계/Excel**을
제공하는 로컬 웹 시스템 (FastAPI + SQLite + 웹 SPA).

> 통합·개발 인수인계는 상위 폴더의 **`통합_인수인계_MASTER.md`** 를 보세요.

## 1. 준비물
- **Python 3.10 이상** (Windows 설치 시 "Add Python to PATH" 체크)
- 최초 1회 패키지 설치: `py -m pip install -r requirements.txt`

## 2. 실행
| 방법 | 내용 |
|---|---|
| **더블클릭** | `분석프로그램_실행.bat` — 서버 기동 + 브라우저 자동 오픈 |
| 터미널 | `py -m uvicorn server:app --port 8010` |

접속: **http://localhost:8010** · 종료: 창에서 Ctrl+C

## 3. 사용 흐름
1. **1 예산 계획**: 연도 선택 → 계획본(양식1(월별)) 업로드 (DB로 흡수, 원본 미보관)
2. **2 실적 집계**: zrfm2(SAP) 업로드 → **분석 실행** (손익·자본 일괄, 약 1분)
3. **3+ 실적분석(상세)**: 지사별 사업 목록 → 전표 트리 검토 → 재배정(자동 재분석+자동 학습) · ✎ 수정 · ＋사업 추가
4. **4 통계·내보내기**: 과목별/지사그룹/전년비교 + `{연도}년 {구분}예산_실적.xlsx` 등 다운로드
5. **설정**: 확정 결과 일괄 학습 → **연도 마감(잠금)** — 완료 연도 숫자 고정 + 스냅샷 보관

## 4. 데이터 위치
- 모든 데이터: `data/budget.db` (SQLite 1파일 — 백업은 이 파일만)
- 산출물: `output/` · 마감 스냅샷: `output/마감/{연도}/`
- DB 내용 문서화: `py scripts/make_db_snapshot.py` → `docs/DB_스냅샷.md`
- 용량 정리(과거 분석 이력 삭제): `py scripts/db_정리.py`

## 5. 테스트
```bash
py -m pytest -q     # 61 passed
```

## 6. 참고
- `app.py`(Streamlit)·`run.bat`·`run.sh`는 **구버전 UI**입니다 — 기본 실행은 위 웹 시스템.
- 오프라인 분리망: 인터넷 연결된 PC에서 `py -m pip download -r requirements.txt -d pkgs`
  후 폴더 복사 → `py -m pip install --no-index --find-links pkgs -r requirements.txt`
