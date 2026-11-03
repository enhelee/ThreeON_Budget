// ─────────────────────────────────────────────────────────────
// 화면 사용법 둘러보기(2026-11-03 grace: 처음 보는 사람도 뭘 할지 바로 알게).
// 화면마다 말풍선 몇 개가 차례로 그 자리를 가리킨다. 처음 들어왔을 때 한 번만 저절로 뜨고
// (사람마다 localStorage «ondo.tour.<화면>»), 화면 제목 옆 «사용법» 버튼으로 언제든 다시 본다.
// 움직임 줄이기 설정이어도 말풍선은 뜨되 반짝임만 멈춘다(CSS).
// ─────────────────────────────────────────────────────────────

export const TOURS = {
  budget: [
    {sel: ".step-guide", text: "예산 계획은 이 세 단계예요. 지금 할 단계가 반짝여요."},
    {sel: '[data-action="pick-plan"]', text: "여기를 눌러 계획 엑셀을 올려요. 손익·자본·건설공사 파일을 한 번에 골라도 되고, 끌어다 놓아도 돼요."},
    {sel: ".plan-files", text: "올라간 파일이 여기 보여요. 맨 위 «지금 쓰는 파일»이 분석에 쓰여요."},
    {sel: ".next-cta", text: "다 올렸으면 이 버튼으로 다음 단계 «실적 집계»로 넘어가요."},
  ],
  branches: [
    {sel: ".br-filters", text: "지사 이름으로 찾거나, 손익·자본을 고르고, 정렬을 바꿀 수 있어요."},
    {sel: ".br-metrics", text: "조회한 지사의 계획·실적·집행률 합계예요."},
    {sel: ".br-scatter", text: "점 하나가 지사 하나예요. 가로는 계획, 세로는 실적. 초록 띠 안(집행률 80~120%)이면 적정, ▲는 계획보다 더 씀, ▼는 덜 씀이에요."},
    {sel: ".br-scatter svg", text: "궁금한 점을 누르면 그 지사의 상세 화면(사업·전표)으로 바로 가요."},
    {sel: ".br-table", text: "지사별 숫자를 표로도 볼 수 있어요. 지사 이름을 눌러도 상세 화면으로 가요."},
  ],
  stats: [
    {sel: ".stats-tabs", text: "손익·자본 통계, 전년과 비교, 한글 보고서를 여기서 골라 봐요."},
    {sel: '[data-export="actual"]', text: "«실적 집계표»는 팀 양식2·3에 숫자를 채운 엑셀이에요. 보고·제출용으로 이걸 받으면 돼요."},
    {sel: '[data-export="v1"]', text: "«전표+매칭 원장»은 zrfm2 원본에 «어느 사업에 붙었는지» 열을 더한 엑셀이에요. 전표 하나하나 확인할 때 써요."},
    {sel: '[data-export="matched"]', text: "«전표별 매칭 CSV»는 다른 프로그램에 넣을 때 쓰는 파일이에요(엑셀로도 열려요)."},
    {sel: ".stats-table", text: "과목 줄을 누르면 지사별 실적이 펼쳐지고, 지사를 누르면 전표까지 내려가 볼 수 있어요."},
    {sel: ".stats-groups", text: "지사 그룹별로 계획(옅은 막대)과 실적(진한 막대)을 비교해요."},
  ],
  collect: [
    {sel: ".step-guide", text: "실적 집계는 이 세 단계예요. 지금 할 단계가 반짝여요."},
    {sel: '[data-action="pick-erp"]', text: "SAP 에서 받은 zrfm2 엑셀을 여기에 올려요. 끌어다 놓아도 돼요."},
    {sel: ".analyze-box", text: "올린 다음 «분석 실행»을 누르면 전표마다 맞는 사업을 찾아 붙여요(약 1분)."},
    {sel: ".match-results", text: "분석이 끝나면 손익·자본 매칭 결과가 여기에 억원 단위로 보여요."},
    {sel: ".next-cta", text: "결과를 확인했으면 다음 단계로 넘어가 지사별로 검토해요."},
  ],
}

let cur = null

const seenKey = view => `ondo.tour.${view}`
function seen(view) { try { return localStorage.getItem(seenKey(view)) === "1" } catch { return true } }
function markSeen(view) { try { localStorage.setItem(seenKey(view), "1") } catch {} }

// 사용법 보기 버튼(2026-11-03 grace 시안 3): 지금 모양 그대로, 그 화면에서 한 번도 안 눌렀으면 오른쪽 위에 빨간 점.
const clickedKey = view => `ondo.tourBtn.${view}`
function clicked(view) { try { return localStorage.getItem(clickedKey(view)) === "1" } catch { return true } }
export function tourButton(view, extra = "") {
  return `<button type="button" class="btn-secondary tour-btn${clicked(view) ? "" : " is-new"}${extra ? ` ${extra}` : ""}" data-action="tour" data-tour="${view}"><span class="tour-btn__icon" aria-hidden="true">?</span>사용법 보기</button>`
}
export function markTourClicked(btn) {
  try { localStorage.setItem(clickedKey(btn.dataset.tour), "1") } catch {}
  btn.classList.remove("is-new")
}

/** 둘러보기를 건너뛴 사람에게 — [사용법 보기] 아래에 «나중에 여기서 다시 볼 수 있어요» 말풍선을 4초 띄운다(2026-11-03 grace). */
function laterHint(view) {
  const btn = document.querySelector(`[data-action="tour"][data-tour="${view}"]`)
  if (!btn) return
  document.querySelector(".tour-later")?.remove()
  btn.scrollIntoView({block: "nearest", behavior: "instant"})
  const r = btn.getBoundingClientRect()
  const tip = document.createElement("div")
  tip.className = "tour-later"
  tip.setAttribute("role", "status")
  tip.textContent = "나중에 여기서 다시 볼 수 있어요"
  document.body.appendChild(tip)
  tip.style.top = `${r.bottom + 10}px`
  tip.style.left = `${Math.max(12, Math.min(r.right - tip.offsetWidth, innerWidth - tip.offsetWidth - 12))}px`
  setTimeout(() => tip.classList.add("is-out"), 3600)
  setTimeout(() => tip.remove(), 4000)
}

export function endTour() {
  if (!cur) return
  cur.el.remove(); window.removeEventListener("resize", cur.place); document.removeEventListener("keydown", cur.key)
  markSeen(cur.view); cur = null
}

/** 화면을 그린 뒤 부른다 — 처음 온 화면이면 둘러보기를 연다. */
export function maybeStartTour(view) {
  if (!TOURS[view] || seen(view) || cur) return
  setTimeout(() => startTour(view), 400)        // 화면이 자리 잡은 뒤
}

export function startTour(view) {
  endTour()
  const steps = (TOURS[view] || []).filter(s => document.querySelector(s.sel))
  if (!steps.length) return
  const el = document.createElement("div")
  el.className = "tour"
  el.innerHTML = `<div class="tour__ring"></div><div class="tour__bubble" role="dialog" aria-live="polite">
    <p class="tour__text"></p><div class="tour__foot"><span class="tour__count"></span>
    <button type="button" class="tour__skip">건너뛰기</button><button type="button" class="tour__next btn-primary"></button></div></div>`
  document.body.appendChild(el)
  let i = 0
  const ring = el.querySelector(".tour__ring"), bub = el.querySelector(".tour__bubble")
  function place() {
    const t = document.querySelector(steps[i].sel)
    if (!t) return endTour()
    t.scrollIntoView({block: "center", behavior: "instant"})
    const r = t.getBoundingClientRect(), pad = 8
    Object.assign(ring.style, {left: `${r.left - pad}px`, top: `${r.top - pad}px`, width: `${r.width + pad * 2}px`, height: `${r.height + pad * 2}px`})
    const below = r.bottom + 180 < innerHeight
    bub.style.top = below ? `${r.bottom + pad + 12}px` : `${Math.max(12, r.top - pad - 12 - bub.offsetHeight)}px`
    bub.style.left = `${Math.min(Math.max(12, r.left), innerWidth - bub.offsetWidth - 12)}px`
  }
  function show() {
    el.querySelector(".tour__text").textContent = steps[i].text
    el.querySelector(".tour__count").textContent = `${i + 1} / ${steps.length}`
    el.querySelector(".tour__next").textContent = i === steps.length - 1 ? "시작하기" : "다음"
    place()
  }
  el.querySelector(".tour__next").addEventListener("click", () => { if (++i >= steps.length) endTour(); else show() })
  const skip = () => { endTour(); laterHint(view) }   // 건너뛰면 다시 볼 곳(사용법 보기)을 잠깐 알려 준다
  el.querySelector(".tour__skip").addEventListener("click", skip)
  const key = e => { if (e.key === "Escape") skip() }
  window.addEventListener("resize", place); document.addEventListener("keydown", key)
  cur = {el, view, place, key}
  show()
}
