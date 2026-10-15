# DB 지역 이전 절차 — Supabase 서울 → 싱가포르 (2026-10)

## 왜

- 앱은 Render **싱가포르**, DB 는 Supabase **서울(ap-northeast-2)** 이다. 질의 한 번이 ~75ms 왕복,
  연결 한 번이 ~0.5초였다(2026-10-15 운영 실측 · 재배정 193건 화면 30초의 증폭 요인).
- Render 에는 서울·도쿄 지역이 없다. 그래서 **DB 를 앱 쪽(싱가포르)으로** 옮긴다.
  사용자 → 앱(싱가포르) 구간은 지금과 같다. 바뀌는 것은 앱 → DB 구간뿐이다.
- 코드 변경은 없다. Render 의 `DATABASE_URL` 하나만 바꾼다. 원본(서울)은 **읽기 전용으로만** 읽으므로
  되돌리기는 `DATABASE_URL` 을 원래 값으로 돌리는 것이다.

## 규모 (2026-10-15)

PostgreSQL 17.6 · 85MB · 약 44만 행(`match_line` 34만 · `erp_row` 5만 · `biz_line` 2만 · `learned_match` 1만).

## 도구

`app/scripts/migrate_pg.py` — 연결 문자열은 화면에 찍지 않는다(호스트만).

| 명령 | 하는 일 | 쓰기 |
|---|---|---|
| `check` | 양쪽 접속·버전·표·행 수·왕복 | 없음 |
| `copy` | 대상에 앱 스키마(init_db) → 전 표 COPY(외래키 순서) → 시퀀스 맞춤 → verify | 대상만, 한 트랜잭션 |
| `copy --replace` | 대상 기존 행을 비우고 다시(리허설 반복) | 대상만 |
| `verify` | 표마다 행 수 + 내용 해시 · 시퀀스 ≥ max(id) | 없음 |

## 순서

### 1. 준비 — [사용자]

1. Supabase 대시보드 → **New project** · Region **Southeast Asia (Singapore)** · DB 비밀번호 새로 32자.
   (무료 플랜은 조직당 활성 프로젝트 2개 — 이미 2개면 하나를 일시정지해야 한다.)
2. 새 프로젝트 → **Connect** → **Session pooler (5432)** 문자열 복사, 끝에 `?sslmode=require`.
3. `app/.env.migrate` 파일에 한 줄: `TARGET_DATABASE_URL=<그 문자열>` (`.gitignore` 의 `.env.*` 로 커밋 안 됨).
   원본은 따로 안 적어도 `app/.env` 의 `DATABASE_URL`(지금 운영)을 쓴다.

### 2. 리허설 — [Claude] (운영 영향 없음, 몇 번이든)

```
cd app
py scripts/migrate_pg.py check
py scripts/migrate_pg.py copy          # 두 번째부터는 copy --replace
```

`결과: 모두 같음 ✅` 를 확인한다. 걸린 시간을 기록 — 전환 당일 작업 중지 시간을 정하는 근거.

### 3. 전환 — [사용자 + Claude] (작업 중지 공지 후, 10분 남짓)

1. 팀에 «지금부터 N분 동안 저장·업로드·분석 금지» 공지.
2. [Claude] `copy --replace` → `✅` 확인.
3. [사용자] Render → threeon-budget → **Environment** → `DATABASE_URL` 을 새 문자열로 → Save(재시작됨).
4. [Claude] `/healthz` 200 · `db: postgresql` 확인 → `verify` 다시(전환 사이 원본에 쓰기가 없었는지).
5. [Claude] Aside 로 운영 재측정(Server-Timing 의 db·conn 시간이 줄었는지) → 공지 해제.
6. [사용자] 로컬 `app/.env` 의 `DATABASE_URL` 도 새 값으로(로컬 스크립트가 옛 DB 를 보지 않게).

### 4. 되돌리기

- 전환 직후 문제 → Render `DATABASE_URL` 을 서울 값으로 되돌린다. 전환 뒤 새 DB 에만 쓰인 것이 있으면
  `SOURCE`/`TARGET` 을 바꿔(싱가포르 → 서울) `copy --replace` 로 되가져온다 — **서울을 덮어쓰므로**
  그 전에 서울의 `verify` 결과를 남겨 둔다.
- 서울 프로젝트는 최소 2주 그대로 둔다(그동안 백업 역할). 삭제·일시정지는 사용자 결정.

## 확인 지표

- 응답 헤더 `Server-Timing` 의 `conn;dur=` (연결)과 `db;dur=` (질의 합) — 전환 전후 비교.
- 2026-10-15 기준: 연결 ~500ms · 질의당 ~75ms.
