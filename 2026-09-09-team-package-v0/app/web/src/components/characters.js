import { state } from "../state.js"
import { CHAR_IMG } from "./char_images.js"

// ─────────────────────────────────────────────────────────────
// ThreeON 캐릭터 — 한장이(전표 한 장)·매칭이(사업 찾기)·검토미(사람에게 묻기)·예측이(전망).
//
// 그림은 입체 v2 한 벌(components/char_images.js, webp)만 쓴다 — 챗봇·도움말·안내 줄·빈 화면·사이드바 머리 모두.
// (2026-10-27 옛 벡터 그림(sprite)을 걷어 냈다 — 화면마다 옛 그림과 새 그림이 섞여 보였다)
//
// 색은 캐릭터 고유색이라 한난 토큰을 쓰지 않는다 — 역할 구분용이다(청록=매칭, 산호=검토,
// 보라=전망). 배너 글자는 토큰(ink·sub)을 쓰므로 대비 기준은 토큰이 이미 맞춘다.
// 같은 그림이 홍보영상 콘티에도 쓰인다(팀 공유 artifact «ThreeON 전표 탐험대 콘티»).
// ─────────────────────────────────────────────────────────────

export const NAMES = {hj: "한장이", mt: "매칭이", gt: "검토미", yc: "예측이"}

/** 캐릭터 그림. head=true 면 머리만(사이드바 로고 옆처럼 작은 자리용), mood 로 표정을 고른다
 *  (full·think·wow·happy·empty — char_images.js). 장식이라 읽지 않는다(alt=""). */
export function charImg(who, cls = "", {head = false, mood = "full"} = {}) {
  const set = CHAR_IMG[who]
  const src = head ? set.head : (set[mood] || set.full)
  return `<img class="char-img ${cls}" src="${src}" alt="" aria-hidden="true" decoding="async">`
}

/**
 * 캐릭터가 한마디 하는 안내 줄. title·body 는 HTML 이다 — 부르는 쪽이 esc() 로 감싼다.
 * tone 을 주면 배경을 그 의미색으로 바꾼다("warn" = 마감 등 주의).
 */
export function charSay({who, title, body = "", action = "", tone = "", compact = false}) {
  return `<section class="char-say char-say--${tone || who}${compact ? " char-say--compact" : ""}">
    ${charImg(who, "char-say__img")}
    <div class="min-w-0">
      <p class="char-say__title"><b class="char-say__name">${NAMES[who]}</b> ${title}</p>
      ${body ? `<p class="char-say__body">${body}</p>` : ""}
    </div>
    ${action}
  </section>`
}

/** 마감 연도 안내 — 1·2·3+ 화면이 같은 모양·같은 말로 쓴다. blocked = 그 화면에서 막히는 일. */
export function lockedSay(blocked) {
  return charSay({who: "gt", tone: "warn", title: `${state.year}년은 마감(잠금) 상태예요.`,
    body: `${blocked} 고치려면 설정 탭에서 마감을 해제하세요.`});
}

// ── 도움말 — 오른쪽 아래 매칭이. 누르면 지금 화면에서 할 일 세 줄 ─────────────
// 내용은 docs/팀원_실행가이드.md 「한 해를 돌리는 순서」를 화면별로 나눈 것이다.
export const HELP = {
  home: ["오늘 기준 현황과 «다음 할 일»을 먼저 봐요.",
         "다음 할 일을 누르면 그 화면으로 바로 가요.",
         "대상연도는 오른쪽 위에서 바꿔요."],
  budget: ["사업별예산 xlsx(시트 «양식1(월별)»)를 올려요.",
           "올리면 그 해 계획이 DB에 등록돼요.",
           "주관부서예산 원본(손익·자본·건설공사)은 한 번에 같이 골라 올려요."],
  collect: ["zrfm2.XLSX 를 올려요. 파일 이름이 zrfm2 여야 해요.",
            "«분석 실행»을 누르면 손익·자본을 한 번에 매칭해요.",
            "확신도가 낮은 전표는 실적분석(상세)에서 확인해요."],
  branches: ["지사별 계획·실적·집행률을 한눈에 봐요.",
             "지사를 누르면 상세 화면으로 가요.",
             "검색창으로 지사를 찾을 수 있어요."],
  detail: ["사업을 누르면 전표가 펼쳐져요.",
           "전표를 체크해 다른 사업으로 옮겨요(재배정).",
           "다 고쳤으면 위의 «분석 반영»을 눌러요."],
  review: ["돈이 많이 걸린 줄부터 위에 있어요. 위에서부터 처리해요.",
           "«✓ 이상 없음»·사유 칩은 누르면 바로 저장돼요(마감 연도도 돼요).",
           "«전표·재배정»에서 추천대로 옮긴 뒤 위의 «분석 반영»을 눌러요."],
  stats: ["손익·자본 통계를 확인해요.",
          "실적본(재무팀 양식)·zrfm2 재검토본·전표 CSV 를 내려받아요.",
          "첫 다운로드는 20~30초 걸려요. 두 번째부터는 바로 받아져요."],
  forecast: ["위에서 전망 기준연도를 골라요.",
             "«기준정보(가정)»에서 양식을 내려받아 채워 올려요.",
             "«표준화»를 확인한 뒤 «중장기 전망» 표를 봐요."],
  settings: ["확정한 매칭은 «AI 학습»으로 배워요.",
             "검토가 끝난 연도는 «연도 마감»으로 잠가요.",
             "모든 변경은 «변경 이력»에 작업자 이름으로 남아요."],
}

// 2026-10-27: 버튼은 대화 패널(components/chat.js)을 연다 — 위 세 줄은 패널 첫 인사로 옮겨 갔다.
//   그림은 챗봇과 같은 파일(char_images.js)이라 캐릭터를 바꾸면 버튼도 같이 바뀐다.
export function helpFabHtml() {
  const open = !!state.chatOpen
  return `<div class="help-fab">
    <button class="help-fab__btn" data-action="toggle-help" aria-expanded="${open}" title="ONDO 탐험대에게 물어보기">
      <span class="help-fab__pill">물어보기</span><img class="help-fab__img help-fab__img--3d" src="${CHAR_IMG.mt.full}" alt="매칭이">
    </button>
  </div>`
}
