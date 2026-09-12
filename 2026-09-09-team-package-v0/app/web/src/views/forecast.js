import { emptyState } from "../components/widgets.js"

export function renderForecast() {
  return `<div class="space-y-6"><section><p class="text-sm font-semibold text-blue-700">STAGE 5</p><h2 class="mt-1 text-2xl font-bold tracking-tight text-slate-950">중장기 예산 예측</h2><p class="mt-2 text-sm text-slate-500">예산 표준화(3단계)·중장기 예산 26~35년(4단계)은 팀 공유 앱 <b>예산예측프로그램(팀공유 v2)</b>이 담당합니다. 이 앱의 「통계·내보내기 → 팀 연계 → 결과 JSON」을 v2 앱의 「예산 실적 집계 → 사업 실적 연결」에 올리면, 검토가 끝난 매칭 실적이 표준화·예측 입력으로 연결됩니다.</p></section>${emptyState("이 화면은 안내용입니다 — 3·4단계 계산과 재무팀 양식 내보내기는 예산예측프로그램(팀공유 v2)에서 실행하세요.")}</div>`;
}
