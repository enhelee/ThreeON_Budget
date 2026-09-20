# 한난 디자인 시스템 적용 — UI 제작 메모 (Phase 8, 2026-09-21)

> 설계서: `docs/superpowers/specs/2026-09-21-한난-디자인시스템-design.md` · 계획서: `docs/superpowers/plans/2026-09-21-Phase8-한난-디자인시스템.md`
> 이 메모는 «무엇을 바꿨고, 왜 그 값인지, 무엇을 실측했고 무엇은 코드만 봤는지»를 남긴다. 다음 사람이 색 하나를 바꿀 때 어디를 봐야 하는지가 여기 있다.

## 1. 시안 대비 무엇을 바꿨나

한난 메인 시안(`hannan-template`)은 마케팅 홈페이지다. 이 앱은 팀 5~10명이 매일 쓰는 **업무 도구**라서 시안의 **색·글꼴·형태·톤**만 가져오고 **구조는 그대로** 두었다.

| 영역 | 유지 | 바꾼 것 |
|---|---|---|
| 레이아웃 | 사이드바 288px · 헤더 · 메뉴 7개 · 라우팅 · 상세표(`det-table`) 열폭 | — |
| 색 | — | Tailwind 기본 팔레트(`blue-600` 강조·`slate` 중성) → 한난 토큰. 화면 10개에서 495곳 치환, **잔존 0** (테스트로 고정) |
| 글꼴 | 본문·표·숫자 Pretendard 계열 | 제목(헤더 `#pageTitle` 22px · 뷰 h2 24→28px · 게이트 h1 28px · `.section-title` 18px)에만 **한난체** 서브셋 |
| 형태 | — | 카드 16px 곡률·1px 선·**그림자 없음** · 버튼 캡슐 44px · 입력 12px · 떠 있는 것(토스트·바쁨·전망 저장바)만 `shadow-float` |
| 셸 | — | 파란 집 아이콘 → **공식 시그니처 SVG**(184px, `alt="한국지역난방공사"`) · 헤더 72px 불투명 흰색 · 사이드바 활성 = 검정 굵게 + 왼쪽 2px 빨간 마커 · 작업자 배지 남색 → 중성 |
| 접근성 | — | 건너뛰기 링크 «본문 바로가기» · `:focus-visible` 빨간 2px 링 · 모바일 드로어 Escape/포커스 복귀/Tab 순환·`aria-expanded`·`role=dialog` · `prefers-reduced-motion` 억제 · 표 숫자 `tabular-nums` · 한글 `keep-all` |

**하지 않은 것:** 상단 메뉴 전환 · 다크 모드 · 시안의 마케팅 섹션 · 새 기능.

## 2. CI 사용 근거 — 어느 값을 왜 골랐나

| 값 | 채택 | 출처·이유 |
|---|---|---|
| 브랜드 빨강 **`#FE0009`** | ✅ | CI 매뉴얼 `한난 CI/color/전용색상1.pdf` BS 12 — 공식 RGB 254·0·9. `tailwind.config.js` 의 `brand` 와 `app.css :root --brand` 두 곳에 같은 값 |
| `#ED1C2B` | ❌ | 시안 `DESIGN-NOTES.md` 의 값 — 공식 로고 이미지에서 **추출**한 근사값. 기록만 하고 쓰지 않는다(테스트가 막는다) |
| 빨강 위 흰 글자 | ❌ | 대비 **4.02:1** — AA 4.5 미달. 그래서 주요 버튼은 시안 규칙대로 **검정 바탕 + 흰 글자 + 빨간 1px 테두리**. 빨강은 포커스 링·활성 마커·호버 글자색·스피너에만 |
| 시그니처 `kdhc-signature-ko.svg` | ✅ | `한난 CI/signi/…한글가로A타입.ai` 를 시안이 SVG 로 변환한 자산을 그대로 복사(`app/web/public/assets/`). viewBox 165.7×38.3 → 184px 폭에 42.5px |
| 한난체 `HananCha` | ✅ (제목만) | `한난 CI/font/HANAN.TTF`(866KB, 4,766 글리프) → `scripts/make_hanan_font.py` 로 완성형 2,350자+ASCII+기호 서브셋 **130KB woff2**(2,575 글리프). **라이선스 문구가 파일에 없다** — 사내 도구에서의 웹폰트 사용 범위 확인은 사용자 몫(§5) |
| 중성·상태색 | ✅ (2개 조정) | 시안 `globals.css` + `openai-light.md`. **`tri` `#8F8F8F`→`#767676`**, **`warn` `#9A6700`→`#8F6000`** 으로 조정 — §4 대비표 참조 |

### 폰트 서브셋에서 잡은 것 (재발 시 참고)

원본 HANAN.TTF 의 글리프 9개(래·챕·챗·쳅·햅·햇·헵·헷·혭)는 점이 0개인 **빈 윤곽**을 하나 더 갖고 있다(`endPtsOfContours` 에 같은 값이 연달아 — 래 = `[27, 27]`). 데스크톱 렌더러는 눈감아 주지만 Chrome/Edge 의 OTS 는 `glyf: Decreasing contour index` 로 **폰트 전체를 버린다** — 실측에서 제목이 전부 폴백 글꼴로 나왔다. `make_hanan_font.py` 의 `repair_empty_contours()` 가 빈 윤곽만 지운다. 재생성할 때 이 단계를 빼면 다시 깨진다.

`/assets/*` 는 서버가 `immutable` 캐시(1년)를 주므로 폰트를 바꾸면 **파일명을 `-v2` 로** 올려야 한다. 같은 이름으로 덮어쓰면 이미 받은 브라우저는 옛 파일을 계속 쓴다(이번 세션에서 실제로 겪었다 — 로컬 확인은 `127.0.0.1` 로 origin 을 바꿔서 했다).

## 3. 토큰 — 값을 바꿀 때 보는 곳

같은 값이 **두 곳**에 있다. 뷰의 유틸리티(`text-ink` `bg-subtle` …)는 `app/web/tailwind.config.js`, 손으로 쓴 `custom.css` 는 `app/web/src/styles/app.css` 의 `:root` 변수. 한쪽만 바꾸면 화면이 둘로 갈린다.

```
ink #0D0D0D  sub #5D5D5D  tri #767676  dis #A6A6A6
line #E5E5E5  line-strong #C9C9C9  line-subtle #F2F2F2  base #FFFFFF  subtle #F7F7F8  overlay rgba(13,13,13,.56)
brand #FE0009  brand-ink #000000
ok #16794A / #EAF5EF   warn #8F6000 / #FFF4D6   err #B42318 / #FDECEC   info #315EAC / #EAF2FF
rounded-card 16  rounded-visual 24  rounded-control 12  버튼 캡슐(999)   shadow-float 0 8px 24px rgba(0,0,0,.10)   duration 180ms
```

의미색과 브랜드색은 **값으로 분리**돼 있다: 오류 `err #B42318`(적갈) ≠ 브랜드 `#FE0009`(선홍). 배지·삭제 버튼·경고 박스는 `err`/`warn`/`ok`/`info` 만 쓴다. `restyle_sweep.py`(1회성 치환표)가 그 규칙을 기록한다.

## 4. 검증 결과

### 4-1. 실측한 것 (내장 브라우저 · 로컬 사본 DB `127.0.0.1:8099`, 2026-09-21)

| 항목 | 결과 |
|---|---|
| 가로 넘침 (`scrollWidth > innerWidth`) | **1440·768·390·360 × 홈·3 지사·3+ 상세(동탄지사)·5 전망(기준정보·표준화·전망)·설정 = 0건.** `det-table` 은 설계대로 `min-width:56rem` 안쪽 가로 스크롤(768px 에서 wrapper 896/703, `overflow-x:auto`) |
| 상세표 열폭 | 1440px 실측 `[64,173,83,357,99,99,86,70,38]` — `custom.css` 열폭 규칙 불변 |
| 헤더 | 높이 72px · 주요/보조 버튼 44px · 768px 에서 버튼 글자가 두 줄로 꺾이던 것을 `whitespace-nowrap` + 우측 묶음 `shrink-0` 로 고침(제목이 대신 말줄임) |
| 로고 | 사이드바·게이트 184×42.5px, SVG 선명 |
| 한난체 | `document.fonts` 상태 `loaded` · 헤더 제목·뷰 h2(28px)·게이트 h1 에 적용 확인 |
| 모바일 드로어 (390px) | 메뉴 버튼 → 열림·`aria-expanded=true`·`role=dialog` → 첫 항목(메인) 포커스 → Shift+Tab 은 마지막(설정)으로, Tab 은 다시 첫 항목으로 순환 → Escape → 닫힘·`aria-expanded=false`·`document.activeElement.id === "menuButton"` |
| 배지 의미색 | 3 지사 집행률: 95%↑ `info`(파랑) · 85~95 `ok`(초록) · 미만 `warn`(주황). 상세 상태: 계획집행 `info` · 신규 `warn` · 미시행 중립 · 미매핑 `err` |
| 5 전망 하위 탭 | 활성 = 검정 캡슐(`btn-primary`), `#/forecast/bench|table` 딥링크 정상 |
| 기존 버그 1건 수정 | 분석 버튼의 흰 점 — `.pending-count{display:inline-flex}` 가 `.hidden` 을 이겨서 미반영 0건에도 보였다(Phase 7 캡처에도 있음). `.pending-count.hidden{display:none}` |
| 캡처 | `docs/img/ui/{1440,768,390,360}-{home,branches,detail,forecast,forecast_bench,forecast_table,settings}.png` 28장 · `docs/img/share/*.png` 10장 갱신. 1440·768 은 Edge 헤드리스 `--window-size`, **390·360 은 DevTools Protocol `Emulation.setDeviceMetricsOverride`(mobile)** — Edge 헤드리스는 창 폭을 ~500px 아래로 못 내려서 `--window-size=390` 으로 찍으면 넓은 레이아웃이 잘려 나온다(처음 그렇게 찍혔다가 교체) |

### 4-2. 코드 검토만 한 것 (브라우저 에뮬레이션 없음)

| 항목 | 근거 |
|---|---|
| 모션 감소 | `app.css` `@media (prefers-reduced-motion: reduce)` — 애니메이션·전환 0.01ms, 부드러운 스크롤 해제. 내장 브라우저에 에뮬레이션이 없어 실측 못 함 |
| 대비 | 아래 표 — WCAG 상대 휘도 계산(파이썬). 실제 렌더 색을 측정한 것은 아니다 |

### 4-3. 대비표 (WCAG 2.x 상대 휘도, 계산값)

| 조합 | 값 | 비율 | 판정 |
|---|---|---|---|
| ink / base | `#0D0D0D` / `#FFFFFF` | 19.44 | AAA |
| sub / base | `#5D5D5D` / `#FFFFFF` | 6.58 | AA |
| sub / subtle | `#5D5D5D` / `#F7F7F8` | 6.15 | AA |
| **tri / base** | `#767676` / `#FFFFFF` | **4.54** | AA — 시안값 `#8F8F8F` 는 **3.23** 이라 올렸다. `text-tri` 가 «귀속 전표 없음»·«양식: …»·빈 표 문구처럼 **12px 캡션 본문**에 37곳 쓰이기 때문 |
| dis / base | `#A6A6A6` / `#FFFFFF` | 2.43 | 비활성 전용(면제) |
| white / ink (주요 버튼) | | 19.44 | AAA |
| white / #333 (주요 버튼 호버) | | 12.63 | AAA |
| ok / ok-bg | `#16794A` / `#EAF5EF` | 4.86 | AA |
| **warn / warn-bg** | `#8F6000` / `#FFF4D6` | **4.99** | AA — 시안값 `#9A6700` 은 **4.44** 로 미달이라 한 단계 어둡게 |
| err / err-bg | `#B42318` / `#FDECEC` | 5.76 | AA |
| info / info-bg | `#315EAC` / `#EAF2FF` | 5.60 | AA |
| white / err (삭제 버튼) | | 6.57 | AA |
| white / warn (미반영 버튼) | | 5.47 | AA |
| white / **brand** | `#FFFFFF` / `#FE0009` | **4.02** | **미달 → 쓰지 않는다** (버튼 바탕 금지의 근거) |
| brand / base (포커스 링·마커) | | 4.02 | 비텍스트 UI 요소 기준 3:1 충족 |

## 5. 남은 항목 (사용자 확인)

1. **한난체 웹폰트 사용 범위** — TTF 에 라이선스 문구가 없다. 사내 도구(비공개, 팀 내부)에서 자체 호스팅해도 되는지 CI 담당 부서 확인. 안 되면 `@font-face` 한 블록과 `font-hanan` 만 빼면 Pretendard 로 자동 폴백된다.
2. **팀 피드백** — 색·글꼴·형태만 바뀌었고 동선은 같지만, «낯설다»는 반응이 오면 `docs/팀공유_최종안내.html` 캡처(갱신됨)로 안내.
3. **배포 확인** (병합 후 Manual Deploy) — `/healthz` commit · 번들 해시 · `/assets/kdhc-signature-ko.svg` 200 · `/assets/fonts/HananCha-v1.woff2` 200 + `cache-control: immutable`.
4. 시안 대비 **조정한 토큰 2개**(`tri`·`warn`)는 대비 때문이다. 시안값으로 되돌리려면 §3 의 두 곳을 같이 바꾸고 §4-3 을 다시 계산한다.
