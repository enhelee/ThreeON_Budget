import { state, viewMeta } from "../state.js"
import { esc } from "../util.js"

// ─────────────────────────────────────────────────────────────
// ThreeON 캐릭터 — 한장이(전표 한 장)·매칭이(사업 찾기)·검토미(사람에게 묻기)·예측이(전망).
//
// 벡터 한 벌을 부팅 때 문서에 한 번 심고(<symbol>), 화면은 <use> 로 가져다 쓴다.
// 화면마다 SVG 를 손으로 붙여 두면 생김새가 조금씩 달라지는 날이 반드시 온다.
//
// 색은 캐릭터 고유색이라 한난 토큰을 쓰지 않는다 — 역할 구분용이다(청록=매칭, 산호=검토,
// 보라=전망). 배너 글자는 토큰(ink·sub)을 쓰므로 대비 기준은 토큰이 이미 맞춘다.
// 같은 그림이 홍보영상 콘티에도 쓰인다(팀 공유 artifact «ThreeON 전표 탐험대 콘티»).
// ─────────────────────────────────────────────────────────────

export const NAMES = {hj: "한장이", mt: "매칭이", gt: "검토미", yc: "예측이"}

const SPRITE = `
<svg id="charSprite" width="0" height="0" style="position:absolute;overflow:hidden" aria-hidden="true" focusable="false">
  <defs>
    <radialGradient id="chGT" cx="35%" cy="28%" r="80%"><stop offset="0" stop-color="#93EBDF"/><stop offset="1" stop-color="#17A090"/></radialGradient>
    <radialGradient id="chGC" cx="35%" cy="28%" r="80%"><stop offset="0" stop-color="#FFB0A3"/><stop offset="1" stop-color="#E85544"/></radialGradient>
    <radialGradient id="chGV" cx="35%" cy="28%" r="80%"><stop offset="0" stop-color="#D3C6FF"/><stop offset="1" stop-color="#8064DA"/></radialGradient>
  </defs>
  <symbol id="ch-hj" viewBox="0 0 160 200">
    <ellipse cx="80" cy="194" rx="46" ry="5" fill="#1B2125" opacity=".12"/>
    <path d="M62 168 L55 188 M98 168 L105 188" stroke="#2B3138" stroke-width="6" stroke-linecap="round"/>
    <ellipse cx="51" cy="190" rx="9" ry="5" fill="#2B3138"/><ellipse cx="109" cy="190" rx="9" ry="5" fill="#2B3138"/>
    <path d="M31 112 Q18 104 14 92 M129 112 Q144 118 150 132" stroke="#2B3138" stroke-width="6" stroke-linecap="round" fill="none"/>
    <path d="M30 20 H106 L130 44 V170 H30 Z" fill="#FFFFFF" stroke="#C9D2D8" stroke-width="3" stroke-linejoin="round"/>
    <path d="M106 20 V44 H130" fill="#EDF1F4" stroke="#C9D2D8" stroke-width="3" stroke-linejoin="round"/>
    <text x="68" y="56" text-anchor="middle" font-size="17" font-weight="700" fill="#2B3138">전표</text>
    <rect x="44" y="68" width="72" height="5" rx="2.5" fill="#DDE3E8"/><rect x="44" y="80" width="58" height="5" rx="2.5" fill="#DDE3E8"/>
    <circle cx="62" cy="114" r="5.5" fill="#2B3138"/><circle cx="98" cy="114" r="5.5" fill="#2B3138"/>
    <circle cx="50" cy="126" r="7" fill="#F59B8E" opacity=".45"/><circle cx="110" cy="126" r="7" fill="#F59B8E" opacity=".45"/>
    <path d="M70 126 Q80 136 90 126" stroke="#2B3138" stroke-width="4" stroke-linecap="round" fill="none"/>
  </symbol>
  <symbol id="ch-mt" viewBox="0 0 200 230">
    <ellipse cx="100" cy="224" rx="56" ry="5" fill="#1B2125" opacity=".12"/>
    <circle cx="72" cy="38" r="16" fill="url(#chGT)"/><circle cx="128" cy="38" r="16" fill="url(#chGT)"/>
    <rect x="12" y="84" width="24" height="44" rx="12" fill="url(#chGT)"/><rect x="164" y="84" width="24" height="44" rx="12" fill="url(#chGT)"/>
    <rect x="64" y="166" width="72" height="54" rx="26" fill="url(#chGT)"/>
    <rect x="26" y="40" width="148" height="126" rx="52" fill="url(#chGT)"/>
    <ellipse cx="70" cy="60" rx="26" ry="10" fill="#FFFFFF" opacity=".35" transform="rotate(-18 70 60)"/>
    <rect x="40" y="56" width="120" height="94" rx="42" fill="#FBF8F3"/>
    <rect x="48" y="63" width="104" height="80" rx="36" fill="#1C2230"/>
    <path d="M68 108 Q79 92 90 108 M110 108 Q121 92 132 108" stroke="#FFFFFF" stroke-width="7" stroke-linecap="round" fill="none"/>
    <rect x="72" y="150" width="56" height="66" rx="6" fill="#FFFFFF" stroke="#D3DAE0" stroke-width="2.5"/>
    <text x="100" y="172" text-anchor="middle" font-size="13" font-weight="700" fill="#2B3138">전표</text>
    <rect x="82" y="182" width="36" height="4" rx="2" fill="#DDE3E8"/><rect x="82" y="192" width="28" height="4" rx="2" fill="#DDE3E8"/><rect x="82" y="202" width="34" height="4" rx="2" fill="#DDE3E8"/>
    <ellipse cx="66" cy="186" rx="11" ry="14" fill="url(#chGT)"/><ellipse cx="134" cy="186" rx="11" ry="14" fill="url(#chGT)"/>
  </symbol>
  <symbol id="ch-gt" viewBox="0 0 200 230">
    <ellipse cx="100" cy="224" rx="56" ry="5" fill="#1B2125" opacity=".12"/>
    <circle cx="80" cy="30" r="13" fill="url(#chGC)"/><circle cx="120" cy="30" r="13" fill="url(#chGC)"/>
    <rect x="76" y="34" width="8" height="12" fill="url(#chGC)"/><rect x="116" y="34" width="8" height="12" fill="url(#chGC)"/>
    <rect x="12" y="84" width="24" height="44" rx="12" fill="url(#chGC)"/><rect x="164" y="84" width="24" height="44" rx="12" fill="url(#chGC)"/>
    <rect x="64" y="166" width="72" height="54" rx="26" fill="url(#chGC)"/>
    <circle cx="100" cy="192" r="9" fill="#C9402F" opacity=".5"/>
    <rect x="26" y="40" width="148" height="126" rx="52" fill="url(#chGC)"/>
    <ellipse cx="70" cy="60" rx="26" ry="10" fill="#FFFFFF" opacity=".35" transform="rotate(-18 70 60)"/>
    <rect x="40" y="56" width="120" height="94" rx="42" fill="#FBF8F3"/>
    <rect x="48" y="63" width="104" height="80" rx="36" fill="#1C2230"/>
    <ellipse cx="82" cy="102" rx="7" ry="10" fill="#FFFFFF"/>
    <path d="M128 94 L114 103 L128 112" stroke="#FFFFFF" stroke-width="7" stroke-linecap="round" stroke-linejoin="round" fill="none"/>
    <ellipse cx="134" cy="186" rx="11" ry="14" fill="url(#chGC)"/>
    <path d="M58 168 L82 196" stroke="#3A3F47" stroke-width="11" stroke-linecap="round"/>
    <circle cx="44" cy="150" r="26" fill="#FFFFFF" fill-opacity=".28" stroke="#9AA3AD" stroke-width="8"/>
    <ellipse cx="66" cy="186" rx="11" ry="14" fill="url(#chGC)"/>
  </symbol>
  <symbol id="ch-yc" viewBox="0 0 200 230">
    <ellipse cx="100" cy="224" rx="56" ry="5" fill="#1B2125" opacity=".12"/>
    <rect x="96" y="20" width="8" height="24" fill="url(#chGV)"/><circle cx="100" cy="20" r="15" fill="url(#chGV)"/>
    <rect x="12" y="84" width="24" height="44" rx="12" fill="url(#chGV)"/><rect x="164" y="84" width="24" height="44" rx="12" fill="url(#chGV)"/>
    <rect x="64" y="166" width="72" height="54" rx="26" fill="url(#chGV)"/>
    <circle cx="100" cy="192" r="9" fill="#5E45B8" opacity=".55"/>
    <rect x="26" y="40" width="148" height="126" rx="52" fill="url(#chGV)"/>
    <ellipse cx="70" cy="60" rx="26" ry="10" fill="#FFFFFF" opacity=".35" transform="rotate(-18 70 60)"/>
    <rect x="40" y="56" width="120" height="94" rx="42" fill="#FBF8F3"/>
    <rect x="48" y="63" width="104" height="80" rx="36" fill="#1C2230"/>
    <path d="M72 94 L86 103 L72 112" stroke="#FFFFFF" stroke-width="7" stroke-linecap="round" stroke-linejoin="round" fill="none"/>
    <ellipse cx="120" cy="102" rx="7" ry="10" fill="#FFFFFF"/>
    <ellipse cx="66" cy="186" rx="11" ry="14" fill="url(#chGV)"/>
    <rect x="122" y="146" width="66" height="58" rx="7" fill="#FFFFFF" stroke="#D3DAE0" stroke-width="2.5"/>
    <rect x="134" y="182" width="10" height="14" rx="2" fill="#B9A8F2"/><rect x="149" y="172" width="10" height="24" rx="2" fill="#9A84EA"/><rect x="164" y="160" width="10" height="36" rx="2" fill="#7A5FD6"/>
    <path d="M132 168 L156 156 L176 152" stroke="#7A5FD6" stroke-width="2.5" stroke-dasharray="4 4" fill="none"/>
    <ellipse cx="128" cy="188" rx="11" ry="14" fill="url(#chGV)"/>
  </symbol>
</svg>`

/** 부팅 때 한 번. 이미 있으면 아무것도 하지 않는다. */
export function injectCharacterSprite() {
  if (document.getElementById("charSprite")) return
  document.body.insertAdjacentHTML("afterbegin", SPRITE)
}

/** 캐릭터 그림. head=true 면 로봇의 머리만(사이드바 로고 옆처럼 작은 자리용). 장식이라 읽지 않는다. */
export function charSvg(who, cls = "", {head = false} = {}) {
  const paper = who === "hj"
  const [w, h] = paper ? [160, 200] : [200, 230]
  const vb = head && !paper ? "12 10 176 160" : `0 0 ${w} ${h}`
  return `<svg class="${cls}" viewBox="${vb}" aria-hidden="true" focusable="false"><use href="#ch-${who}" width="${w}" height="${h}"/></svg>`
}

/**
 * 캐릭터가 한마디 하는 안내 줄. title·body 는 HTML 이다 — 부르는 쪽이 esc() 로 감싼다.
 * tone 을 주면 배경을 그 의미색으로 바꾼다("warn" = 마감 등 주의).
 */
export function charSay({who, title, body = "", action = "", tone = ""}) {
  return `<section class="char-say char-say--${tone || who}">
    ${charSvg(who, "char-say__img")}
    <div class="min-w-0">
      <p class="char-say__title"><b class="char-say__name">${NAMES[who]}</b> ${title}</p>
      ${body ? `<p class="char-say__body">${body}</p>` : ""}
    </div>
    ${action}
  </section>`
}

// ── 도움말 — 오른쪽 아래 매칭이. 누르면 지금 화면에서 할 일 세 줄 ─────────────
// 내용은 docs/팀원_실행가이드.md 「한 해를 돌리는 순서」를 화면별로 나눈 것이다.
export const HELP = {
  home: ["오늘 기준 현황과 «다음 할 일»을 먼저 봐요.",
         "다음 할 일을 누르면 그 화면으로 바로 가요.",
         "대상연도는 오른쪽 위에서 바꿔요."],
  budget: ["사업별예산 xlsx(시트 «양식1(월별)»)를 올려요.",
           "올리면 그 해 계획이 DB에 등록돼요.",
           "계획본(양식1)은 여기서 내려받아요."],
  collect: ["zrfm2.XLSX 를 올려요. 파일 이름이 zrfm2 여야 해요.",
            "«분석 실행»을 누르면 손익·자본을 한 번에 매칭해요.",
            "확신도가 낮은 전표는 실적분석(상세)에서 확인해요."],
  branches: ["지사별 계획·실적·집행률을 한눈에 봐요.",
             "지사를 누르면 상세 화면으로 가요.",
             "검색창으로 지사를 찾을 수 있어요."],
  detail: ["사업을 누르면 전표가 펼쳐져요.",
           "전표를 체크해 다른 사업으로 옮겨요(재배정).",
           "다 고쳤으면 위의 «분석 반영»을 눌러요."],
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

export function helpFabHtml() {
  const steps = HELP[state.view] || []
  const title = `${(viewMeta[state.view] || ["이 화면"])[0]}에서는`
  const open = !!state.helpOpen && steps.length > 0
  return `<div class="help-fab">
    ${open ? `<div class="help-bubble" id="helpBubble" role="dialog" aria-label="${esc(title)} 도움말">
      <p class="help-bubble__title">${esc(title)}</p>
      <ol>${steps.map(s => `<li>${esc(s)}</li>`).join("")}</ol>
      <button class="help-bubble__close" data-action="close-help" aria-label="도움말 닫기">×</button>
    </div>` : ""}
    <button class="help-fab__btn" data-action="toggle-help" aria-expanded="${open}" aria-controls="helpBubble" title="이 화면 도움말">
      <span class="help-fab__pill">? 도움말</span>${charSvg("mt", "help-fab__img")}
    </button>
  </div>`
}
