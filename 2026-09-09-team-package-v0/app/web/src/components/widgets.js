import { state } from "../state.js"
import { esc } from "../util.js"
import { charSvg } from "./characters.js"

export function pendingBarHtml() {
  const p = state.pending;
  if (!p || !p.total || state.yearLocked === true) return "";   // 마감 연도엔 반영할 수 없다(423)
  const detail = Object.entries(p.counts || {}).map(([k, v]) => `${k} ${v}건`).join(" · ");
  return `<section class="pending-bar mb-4">
    <b>분석 미반영 변경 ${p.total}건</b>
    <span class="text-xs text-warn">${esc(detail)}</span>
    <button class="btn-primary push-right" data-action="analyze">분석 반영 (${p.total})</button>
  </section>`;
}

export function emptyState(msg) {
  // 빈 화면에는 한장이가 선다 — «전표가 아직 자리를 못 찾았다»는 뜻이 그림으로도 읽힌다.
  return `<div class="rounded-card border border-dashed border-line-strong bg-subtle px-6 py-8 text-center">${charSvg("hj", "empty-state__img")}<p class="mt-2 font-semibold text-ink">${esc(msg)}</p></div>`;
}

export function yearPicker(prefix) {
  return `<div class="flex flex-wrap items-end gap-3">
    <label class="block"><span class="mb-1.5 block text-xs font-semibold text-sub">대상연도</span>
    <select class="control" data-yearpick="1">${state.years.map(y => `<option value="${y}" ${String(y) === String(state.year) ? "selected" : ""}>${y}년</option>`).join("")}</select></label>
    <label class="block"><span class="mb-1.5 block text-xs font-semibold text-sub">새 연도 직접 입력</span>
    <div class="flex gap-2"><input id="${prefix}NewYear" class="control" style="width:7rem" placeholder="예: 2021" maxlength="4">
    <button class="btn-secondary" data-action="add-year" data-input="${prefix}NewYear">추가</button></div></label>
  </div>`;
}

// ───────────────────────── 1 예산 계획 ─────────────────────────
