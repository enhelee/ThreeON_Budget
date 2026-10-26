import { state } from "../state.js"
import { esc } from "../util.js"

// 마감된 연도의 숫자는 대외 보고에 쓰인 값이다. 열려 있다는 사실을 잊지 않게 하되,
// 다른 연도를 보는 동안까지 화면마다 큰 띠를 띄우면 소음이다(2026-10-26 사용자 결정):
//   보고 있는 연도가 열려 있으면 → 헤더 제목 옆 작은 배지(+ 다시 마감)
//   다른 연도를 보고 있으면     → 메인 «다음 할 일»에 한 줄(openLockItems)
export function lockBadgeHtml() {
  const s = (state.lockStates || {})[String(state.year)]
  if (!s) return ""
  const meta = [s.reason, s.by, s.unlocked_at].filter(Boolean).join(" · ")
  return `<span class="lock-chip" title="${esc(meta)}">🔓 ${esc(state.year)} 마감 해제
    <button class="lock-chip__btn" data-action="relock-year" data-year="${esc(state.year)}">다시 마감</button></span>`
}

/** 메인 «다음 할 일»에 넣을 줄 — 지금 보고 있지 않은 연도까지 포함해 열린 연도 전부. */
export function openLockItems() {
  return Object.keys(state.lockStates || {}).map(year => ({tone: "warn", view: "settings",
    text: `${year}년 마감 해제됨 — 검토가 끝나면 다시 마감하세요.`}))
}
