import { charImg } from "./characters.js"
import { esc, fmt } from "../util.js"

// ─────────────────────────────────────────────────────────────
// 단계 화면(1 예산 계획 · 2 실적 집계) 공통 조각 — 2026-11-03 grace «처음 보는 사람도 뭘 할지 바로 알게».
//   stepGuide  위 세 단계 안내(끝난 단계 ✓, 지금 할 단계가 은은하게 반짝)
//   slimDrop   얇은 업로드 칸(누르거나 끌어다 놓기). 파일이 없으면 캐릭터가 가리킨다
//   fileList   올라간 파일 목록 + 원본 내려받기
//   nextStep   맨 아래 따로 떨어진 큰 «다음 단계» 버튼
// ─────────────────────────────────────────────────────────────

export function stepGuide(labels, now, aria) {
  return `<ol class="step-guide" aria-label="${esc(aria)}">${labels.map((label, i) => {
    const n = i + 1, done = n < now
    return `<li class="step-guide__item ${done ? "is-done" : ""} ${n === now ? "is-now" : ""}"><span class="step-guide__no">${done ? "✓" : n}</span><span>${esc(label)}</span></li>`
  }).join("")}</ol>`
}

export function slimDrop({action, drop, title, sub, locked, empty, hint}) {
  return `<button class="drop-zone drop-zone--slim mt-4 ${locked ? "cursor-not-allowed opacity-50" : ""}" data-action="${action}" data-drop="${drop}" ${locked ? 'disabled aria-disabled="true" title="마감된 연도 — 설정에서 해제 후 업로드"' : ""}>
      <span class="drop-zone__icon"><svg viewBox="0 0 24 24" class="h-5 w-5" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 16V4m0 0 4 4m-4-4L8 8M5 14v5h14v-5"/></svg></span>
      <span class="min-w-0 text-left"><span class="block font-bold text-ink">${title}</span><span class="block text-xs text-sub">${sub}</span></span></button>
    ${empty && !locked ? `<p class="plan-hint" aria-hidden="true">${charImg("mt", "plan-hint__char", {head: true})}<span class="plan-hint__bubble">${hint}</span><span class="plan-hint__arrow">↑</span></p>` : ""}`
}

export function fileList(ds, {emptyText, showAmount}) {
  if (!ds.length) return `<p class="rounded-control bg-subtle p-4 text-sm text-sub">${emptyText}</p>`
  return `<ul class="space-y-2 text-sm">${ds.map((d, i) => `<li class="flex items-center justify-between gap-3 rounded-control ${i === 0 ? "border border-line-strong bg-base" : "bg-subtle"} p-3">
      <div class="min-w-0"><p class="truncate font-semibold text-ink">${esc(d.label)}</p><p class="text-xs text-sub">${d.row_count.toLocaleString()}행${showAmount ? ` · ${fmt(d.total_amount)} 천원` : ""} · ${esc(d.uploaded_at)}</p></div>
      <div class="flex shrink-0 items-center gap-2">${i === 0 ? '<span class="badge bg-ok-bg text-ok">지금 쓰는 파일</span>' : '<span class="badge bg-subtle text-sub">예전 파일</span>'}
        <a class="file-dl" href="/api/datasets/${d.id}/download" download title="올린 원본 그대로 받기">내려받기</a></div></li>`).join("")}</ul>
    <ul class="mt-3 space-y-0.5 text-xs text-sub">
      <li>* 가장 최근에 올린 파일이 쓰여요.</li>
      <li>* «내려받기»는 올린 원본 그대로 받아요(여러 개면 zip). 원본 저장 전에 올린 파일은 앱이 읽어 둔 내용을 표로 받아요.</li>
    </ul>`
}

export function nextStep({view, label, desc, ready}) {
  return `<section class="next-cta ${ready ? "is-ready" : ""}">
      <div class="min-w-0"><p class="next-cta__k">다음 단계</p><p class="next-cta__desc">${desc}</p></div>
      <button type="button" class="next-cta__btn" data-view="${view}">${label} <span aria-hidden="true">→</span></button>
    </section>`
}
