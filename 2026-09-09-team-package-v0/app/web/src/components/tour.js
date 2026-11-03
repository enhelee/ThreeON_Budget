import { esc } from "../util.js"
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
  standard: [
    {sel: ".std-heat thead", text: "지사마다 정비등급별로 «한 해에 보통 얼마 드는지»(표준금액)를 모은 표예요. 줄은 지사, 칸은 정비등급이에요."},
    {sel: ".std-cell button", text: "칸 하나에 굵은 숫자는 총액, 막대는 손익(파랑)+자본(회청), 아래 작은 숫자는 손익·자본이에요. 단위는 백만원이고, 마우스를 올리면 천원까지 보여요."},
    {sel: ".std-cell button", text: "칸을 누르면 그 지사·등급의 과목별 숫자가 나오는 «5-1 표준화 세부»로 가요."},
    {sel: ".std-about", text: "어느 해 실적으로 만들었는지, 물가 환산은 어떻게 했는지는 «이 표 읽는 법»을 펼쳐 봐요."},
    {sel: '[data-action="std-full"]', text: "표가 옆으로 길면 «전체보기»를 눌러요. 새 창에 표만 크게 열려요."},
  ],
  forecast: [
    {sel: "[data-fcbase]", text: "전망 기준연도예요. 이 해부터 10년을 전망하고, 가정은 기준연도마다 따로 저장돼요."},
    {sel: '[data-action="fc-add-base"]', text: "새 해 전망을 시작할 땐 «＋기준연도»를 눌러요. 직전 기준연도의 가정을 그대로 복사해 만들어요."},
    {sel: ".fc-tabs", text: "«기준정보(가정)»에서 정비등급·투자계획 같은 가정을 넣고, «중장기 전망»에서 결과 표를 봐요."},
    // items = [이름, 설명] — 말풍선 안에 이름 칸 | 설명 칸 두 열로(2026-11-03 grace: 묶음 9개가 각각 무엇인지)
    {sel: ".fc-mtabs", text: "가정은 9개 묶음으로 나뉘어 있어요. 저장 안 한 표가 있는 묶음엔 점이 찍혀요.", items: [
      ["참고 엑셀·대조", "재무팀 예산표준화 엑셀을 가져와 등급과 규칙을 읽고, 앱 계산과 나란히 비교해요."],
      ["정비등급", "지사·설비별로 해마다 어떤 정비(MI·HGPI·CI 등)를 하는지 적어요. 표준금액이 이 등급을 따라가요."],
      ["고온부품", "고온부품 재생·신품구매 계획 금액과 물가 팩터(해마다 오르는 비율)를 넣어요."],
      ["설비용량·신규표준", "지사별 설비용량(MW)과, 새 지사·설비를 비슷한 지사 금액에서 용량만큼 환산하는 규칙이에요."],
      ["지사 연혁·구조변화", "해마다 지사의 그룹·설비 구성과, 어느 해부터 실적을 쓸지 같은 변화를 적어요."],
      ["정기계약·CRI·투자", "LTSA 같은 정기계약, CRI 규칙, 투자계획·투자비 실적이에요. 표준화 대신 정해진 금액을 그대로 넣어요."],
      ["본사 배분·임시사업", "본사 원가와 일시적 사업을 배분비율로 지사에 나눠요."],
      ["지사 돌발사업", "지사별로 특정 해·과목에 더할 일회성 사업이에요."],
      ["학습 기간·물가 환산·백테스트", "표준금액을 몇 년 치 실적으로 만들지, 과거 실적을 물가로 환산할지 정하고, 그 방법이 과거에 얼마나 맞았는지 검증해요."],
    ]},
    {sel: ".info-btn", text: "표 제목 옆 i 를 누르면 그 표가 무엇이고 계산에 어떻게 쓰이는지 설명이 나와요."},
    {sel: "#fcSaveBtn", text: "표를 고친 뒤엔 «저장»을 눌러야 전망에 반영돼요."},
    {sel: "[data-fcsite]", text: "지사를 고르면 그 지사의 과목별 10개년 전망이 나와요. 처음엔 전사 합계예요."},
    {sel: "[data-fcrange]", text: "«예측 범위 보기»를 켜면 칸마다 과거 실적 범위(최소~최대)도 같이 보여요."},
    {sel: '[data-fcexport="longterm"]', text: "재무팀 중장기예산 양식에 결과를 채워 엑셀로 내려받아요."},
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
    <p class="tour__text"></p><div class="tour__list" hidden></div><div class="tour__foot"><span class="tour__count"></span>
    <button type="button" class="tour__skip">건너뛰기</button><button type="button" class="tour__next btn-primary"></button></div></div>`
  document.body.appendChild(el)
  let i = 0
  const ring = el.querySelector(".tour__ring"), bub = el.querySelector(".tour__bubble")
  function place() {
    const t = document.querySelector(steps[i].sel)
    if (!t) return endTour()
    t.scrollIntoView({block: "center", behavior: "instant"})
    const pad = 8, h = bub.offsetHeight
    let r = t.getBoundingClientRect()
    // 말풍선이 위에도 아래에도 안 들어가면(긴 목록) 대상을 화면 위쪽으로 올리고 아래에 띄운다 — 대상을 가리지 않게
    if (r.bottom + pad + 12 + h > innerHeight && r.top - pad - 12 - h < 12) { window.scrollBy(0, r.top - 96); r = t.getBoundingClientRect() }
    Object.assign(ring.style, {left: `${r.left - pad}px`, top: `${r.top - pad}px`, width: `${r.width + pad * 2}px`, height: `${r.height + pad * 2}px`})
    const below = r.bottom + pad + 12 + h < innerHeight || r.top - pad - 12 - h < 12
    bub.style.top = below ? `${r.bottom + pad + 12}px` : `${Math.max(12, r.top - pad - 12 - bub.offsetHeight)}px`
    bub.style.left = `${Math.min(Math.max(12, r.left), innerWidth - bub.offsetWidth - 12)}px`
  }
  function show() {
    el.querySelector(".tour__text").textContent = steps[i].text.replace(/([.?!]) +/g, "$1\n")   // 문장마다 줄 바꿈(2026-11-03 grace)
    const list = el.querySelector(".tour__list"), items = steps[i].items || []
    list.hidden = !items.length
    list.innerHTML = items.map(([k, v]) => `<b>${esc(k)}</b><span>${esc(v)}</span>`).join("")
    bub.classList.toggle("tour__bubble--wide", items.length > 0)
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
