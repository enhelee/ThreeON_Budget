import { api } from "../api.js"
import { state, viewMeta } from "../state.js"
import { esc } from "../util.js"
import { HELP, NAMES } from "./characters.js"

// ─────────────────────────────────────────────────────────────
// 캐릭터 챗봇 — 오른쪽 대화 패널(2026-10-27, 1단계: 사용법·화면 이동·진행 상황)
//
// 오른쪽 아래 매칭이(도움말 버튼)를 누르면 열린다. 답은 서버 규칙 엔진(/api/chat)이 만든다 —
// 숫자는 DB 에서 읽은 값만, 외부 전송 없음. 대화는 이 탭 안에서만 들고 있다(서버에 저장하지 않음).
//
// 그림은 char_images.js 한 곳(assets/characters/*.webp) — 파일을 갈아 끼우면 패널·버튼이 함께 바뀐다.
// 패널은 #page 밖(#chatHost)에 있어 화면을 옮겨도 대화가 남는다.
// ─────────────────────────────────────────────────────────────

import { CHAR_IMG } from "./char_images.js"

const ROLE = {mt: "실적·이동", gt: "검토", yc: "전망", hj: "사용법"}

// open 은 state.chatOpen 에도 비춘다 — 도움말 버튼(characters.js)이 aria-expanded 를 그리게.
const chat = {open: false, busy: false, log: [], suggestions: []}

export const chatIsOpen = () => chat.open
const setOpen = v => { chat.open = v; state.chatOpen = v }

function img(who, mood = "head") {
  const set = CHAR_IMG[who] || CHAR_IMG.mt
  return set[mood] || set.head
}

function botHtml(card) {
  const who = card.who || "mt"
  const table = card.table && card.table.length > 1
    ? `<table class="chat-table"><thead><tr>${card.table[0].map(h => `<th>${esc(h)}</th>`).join("")}</tr></thead>
       <tbody>${card.table.slice(1).map(r => `<tr>${r.map(c => `<td>${esc(c)}</td>`).join("")}</tr>`).join("")}</tbody></table>`
    : ""
  const links = (card.links || []).map(l =>
    `<button class="chat-go" data-chat-go="${esc(l.hash)}" data-chat-focus="${esc(l.focus || "")}">${esc(l.label)}</button>`).join("")
  const ask = (card.ask || []).map(q => `<button class="chat-chip" data-chat-q="${esc(q)}">${esc(q)}</button>`).join("")
  const dl = card.download ? `<a class="chat-go" href="${esc(card.download.url)}" download>${esc(card.download.label)} ⤓</a>` : ""
  const lines = (card.lines || []).length
    ? `<ol class="chat-lines">${card.lines.map(s => `<li>${esc(s)}</li>`).join("")}</ol>` : ""
  return `<div class="chat-bot chat-bot--${who}">
    <img class="chat-av" src="${img(who, card.mood === "wow" ? "wow" : "head")}" alt="">
    <div class="chat-bub">
      <p class="chat-who">${esc(NAMES[who] || "")}</p>
      ${card.ctx ? `<p class="chat-ctx">${esc(card.ctx)}</p>` : ""}
      <p class="chat-text">${esc(card.text || "")}</p>${lines}${table}
      ${links || dl ? `<div class="chat-links">${links}${dl}</div>` : ""}
      ${ask ? `<div class="chat-ask">${ask}</div>` : ""}
      ${card.source ? `<p class="chat-src">${esc(card.source)}</p>` : ""}
    </div></div>`
}

function render() {
  const host = document.getElementById("chatHost")
  if (!host) return
  document.body.classList.toggle("chat-open", chat.open)
  if (!chat.open) { host.innerHTML = ""; return }
  const cast = ["mt", "gt", "yc", "hj"].map(w =>
    `<span class="chat-cast__item"><img src="${img(w)}" alt="">${esc(NAMES[w])} ${ROLE[w]}</span>`).join("")
  const log = chat.log.map(m => m.role === "me"
    ? `<div class="chat-me">${esc(m.text)}</div>`
    : m.thinking
      ? `<div class="chat-bot chat-bot--mt"><img class="chat-av" src="${img("mt", "think")}" alt="생각 중">
           <div class="chat-bub"><p class="chat-who">${esc(NAMES.mt)}</p><span class="chat-think" aria-label="답을 만드는 중"><i></i><i></i><i></i></span></div></div>`
      : botHtml(m.card)).join("")
  const sugg = chat.suggestions.map(q => `<button class="chat-chip" data-chat-q="${esc(q)}">${esc(q)}</button>`).join("")
  host.innerHTML = `<aside class="chat-panel" role="dialog" aria-label="ThreeON 대화" aria-modal="false">
    <header class="chat-head">
      <img src="${img("mt")}" alt="">
      <div><p class="chat-title">ONDO 탐험대</p><p class="chat-sub">숫자는 앱 계산에서만 가져와요 · 외부 전송 없음</p></div>
      <button class="chat-x" data-chat-close aria-label="대화 닫기">×</button>
    </header>
    <div class="chat-cast">${cast}</div>
    <div class="chat-log" id="chatLog" aria-live="polite">${log}</div>
    ${sugg ? `<div class="chat-sugg">${sugg}</div>` : ""}
    <form class="chat-form" data-chat-form>
      <input id="chatInput" class="control" maxlength="300" autocomplete="off" placeholder="예: 마감은 어떻게 해?" aria-label="질문" ${chat.busy ? "disabled" : ""}>
      <button class="btn-primary" type="submit" ${chat.busy ? "disabled" : ""}>보내기</button>
    </form>
  </aside>`
  const lg = document.getElementById("chatLog")
  if (lg) lg.scrollTop = lg.scrollHeight
}

async function loadSuggestions() {
  try { chat.suggestions = (await api(`/api/chat/suggestions?view=${encodeURIComponent(state.view)}`)).suggestions || [] }
  catch { chat.suggestions = [] }
}

function greeting() {
  const title = viewMeta[state.view] || "이 화면"
  return {who: "mt", text: `«${title}» 화면이에요. 이 화면에서는 이렇게 해요.`, lines: HELP[state.view] || [],
          ask: [], source: "", links: []}
}

export async function openChat() {
  setOpen(true)
  if (!chat.log.length) chat.log.push({role: "bot", card: greeting()})
  render()
  await loadSuggestions()
  render()
  document.getElementById("chatInput")?.focus()
}

export function closeChat() {
  setOpen(false)
  render()
  document.querySelector(".help-fab__btn")?.focus()
}

export const toggleChat = () => (chat.open ? closeChat() : openChat())

/** 화면을 옮기면 추천 질문만 그 화면 것으로 바꾼다(대화는 남긴다). */
export async function chatOnViewChange() {
  if (!chat.open) return
  await loadSuggestions()
  render()
}

// ── 이동 + 짚어 주기 ─────────────────────────────────────────
// 화면은 비동기로 그려지므로(자료를 받은 뒤 다시 그림) 요소가 생길 때까지 잠깐 기다린다.
// 끝내 없으면(마감 연도라 버튼이 없음 등) 조용히 넘어간다 — 이동은 이미 됐다.
const SPOT_WAIT_MS = 6000, SPOT_SHOW_MS = 4500
let spotTimer = 0

function findVisible(selector) {
  for (const one of selector.split(",").map(x => x.trim()).filter(Boolean)) {
    const el = [...document.querySelectorAll(one)].find(e => e.offsetParent !== null || e.getClientRects().length)
    if (el) return el
  }
  return null
}

function spotlight(selector) {
  if (!selector) return
  clearTimeout(spotTimer)
  document.querySelectorAll(".chat-spot").forEach(e => e.classList.remove("chat-spot"))
  const started = Date.now()
  const tick = () => {
    const el = findVisible(selector)
    if (!el) { if (Date.now() - started < SPOT_WAIT_MS) spotTimer = setTimeout(tick, 200); return }
    const calm = matchMedia("(prefers-reduced-motion: reduce)").matches
    el.scrollIntoView({block: "center", behavior: calm ? "auto" : "smooth"})
    el.classList.add("chat-spot")
    spotTimer = setTimeout(() => el.classList.remove("chat-spot"), SPOT_SHOW_MS)
  }
  spotTimer = setTimeout(tick, 150)
}

function goTo(hash, focus) {
  if (hash && location.hash !== hash) location.hash = hash   // hashchange → router.navigate
  spotlight(focus)
}

async function send(q) {
  q = (q || "").trim()
  if (!q || chat.busy) return
  chat.busy = true
  chat.log.push({role: "me", text: q}, {role: "bot", thinking: true})
  render()
  let card
  try {
    const r = await api("/api/chat", {method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({question: q, context: {view: state.view, year: state.year}})})
    card = r.answer
    if (r.suggestions?.length) chat.suggestions = r.suggestions
  } catch (e) {
    card = {who: "mt", mood: "wow", text: `지금은 답을 못 했어요. (${e.message || "오류"})`, links: []}
  }
  chat.log.pop()
  chat.log.push({role: "bot", card})
  chat.busy = false
  render()
  document.getElementById("chatInput")?.focus()
  if (card.go) goTo(card.go, "")            // «열어줘» — 버튼 없이 바로 옮긴다
}

// 패널 안 이벤트는 여기서만 — main.js 의 큰 위임 핸들러와 섞지 않는다.
export function initChat() {
  const host = document.getElementById("chatHost")
  if (!host) return
  host.addEventListener("click", e => {
    if (e.target.closest("[data-chat-close]")) { closeChat(); return }
    const q = e.target.closest("[data-chat-q]")
    if (q) { send(q.dataset.chatQ); return }
    const go = e.target.closest("[data-chat-go]")
    if (go && go.dataset.chatGo) { goTo(go.dataset.chatGo, go.dataset.chatFocus); return }
  })
  host.addEventListener("submit", e => {
    if (!e.target.closest("[data-chat-form]")) return
    e.preventDefault()
    const inp = document.getElementById("chatInput")
    const q = inp?.value
    if (inp) inp.value = ""
    send(q)
  })
  host.addEventListener("keydown", e => {
    if (e.key === "Escape") { e.stopPropagation(); closeChat() }
  })
}
