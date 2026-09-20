import { state } from "../state.js"
import { esc } from "../util.js"

// 화면 하나에 API 가 예닐곱 개 붙는다. 그중 몇이 실패했는지 밝히지 않으면
// 그 구역은 «자료가 없음»과 구별되지 않는다 — 배포 직후 502 한 번에 설정 화면이
// 통째로 비어 보여 데이터가 날아간 줄 알았던 일이 있었다(2026-09-19).
// 비어 있는 것과 못 불러온 것은 다르다. 그 차이를 화면이 말해야 한다.
export function loadErrorBannerHtml() {
  const errs = state.loadErrors || []
  if (!errs.length) return ""
  return `
    <div class="border-t border-err bg-err-bg px-4 py-2 text-sm sm:px-6 lg:px-8">
      <div class="flex flex-wrap items-center gap-x-3 gap-y-1">
        <span class="font-bold text-err">⚠ ${errs.length}개 구역을 불러오지 못했습니다</span>
        <span class="text-xs text-err">아래 화면의 해당 구역은 <b>비어 있는 것이 아니라 조회에 실패한 것</b>입니다. 자료는 서버에 그대로 있습니다.</span>
        <button class="btn-secondary ml-auto" data-action="reload-view">다시 불러오기</button>
      </div>
      <ul class="mt-1 list-disc pl-5 text-xs text-err">
        ${errs.map(e => `<li>${esc(e)}</li>`).join("")}
      </ul>
    </div>`
}
