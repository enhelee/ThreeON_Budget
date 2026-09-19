import { state } from "../state.js"
import { esc } from "../util.js"

// 마감된 연도의 숫자는 대외 보고에 쓰인 값이다. 열려 있다는 사실이 설정 화면
// 안쪽에만 있으면 잊힌다 — 다른 연도·다른 화면을 보고 있어도 보이도록 헤더에
// 붙여 둔다. 헤더는 sticky 라 스크롤해도 따라온다.
export function lockBannerHtml() {
  const open = Object.entries(state.lockStates || {})
  if (!open.length) return ""
  return open.map(([year, s]) => `
    <div class="flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-amber-300 bg-amber-50 px-4 py-2 text-sm sm:px-6 lg:px-8">
      <span class="font-bold text-amber-900">🔓 ${esc(year)}년이 마감 해제 상태입니다</span>
      <span class="text-xs text-amber-800">${esc(s.reason || "")}${s.by ? ` · ${esc(s.by)}` : ""}${s.unlocked_at ? ` · ${esc(s.unlocked_at)}` : ""}</span>
      <button class="btn-secondary ml-auto" data-action="relock-year" data-year="${esc(year)}">${esc(year)}년 다시 마감</button>
    </div>`).join("")
}
