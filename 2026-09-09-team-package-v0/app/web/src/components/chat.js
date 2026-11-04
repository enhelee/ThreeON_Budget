import { api } from "../api.js"
import { state, viewMeta } from "../state.js"
import { esc } from "../util.js"
import { HELP, NAMES } from "./characters.js"

// ─────────────────────────────────────────────────────────────
// 캐릭터 챗봇 — 오른쪽 대화 패널(2026-10-27, 1단계: 사용법·화면 이동·진행 상황)
//
// 오른쪽 아래 실적이(도움말 버튼)를 누르면 열린다. 답은 서버 규칙 엔진(/api/chat)이 만든다 —
// 숫자는 DB 에서 읽은 값만, 외부 전송 없음. 대화는 이 탭 안에서만 들고 있다(서버에 저장하지 않음).
//
// 그림은 char_images.js 한 곳(assets/characters/*.webp) — 파일을 갈아 끼우면 패널·버튼이 함께 바뀐다.
// 패널은 #page 밖(#chatHost)에 있어 화면을 옮겨도 대화가 남는다.
// ─────────────────────────────────────────────────────────────

import { CHAR_IMG } from "./char_images.js"

const ROLE = {mt: "실적·이동", gt: "표준·검토", yc: "전망", hj: "사용법"}

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
      <input id="chatInput" class="control" maxlength="300" autocomplete="off" placeholder="${VOICE_OK ? "예: 검토 대기로 가 줘 · 🎤 로 말해도 돼요" : "예: 마감은 어떻게 해?"}" aria-label="질문" ${chat.busy ? "disabled" : ""}>
      ${VOICE_OK ? `<button type="button" class="chat-mic${voice.on ? " chat-mic--on" : ""}" data-chat-mic
        aria-pressed="${voice.on}" aria-label="${voice.on ? "듣기 멈추기" : "말로 묻기"}" title="말로 묻기(내장 마이크 · 브라우저 음성 인식)" ${chat.busy ? "disabled" : ""}>🎤</button>` : ""}
      <button class="btn-primary" type="submit" ${chat.busy ? "disabled" : ""}>보내기</button>
    </form>
    ${voice.note ? `<p class="chat-voice-note" role="status">${esc(voice.note)}</p>` : ""}
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
  voice.rec?.stop()
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

async function send(q, {voice: byVoice = false} = {}) {
  q = (q || "").trim()
  if (!q || chat.busy) return
  chat.busy = true
  chat.log.push({role: "me", text: byVoice ? `🎤 ${q}` : q}, {role: "bot", thinking: true})
  render()
  let card
  try {
    const r = await api("/api/chat", {method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({question: q, context: {view: state.view, year: state.year, voice: byVoice}})})
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

// ── 말로 묻기(2026-11-03 grace: 브라우저 기본 음성 기능으로) ──────────────────
// 브라우저에 들어 있는 음성 인식(Web Speech API · SpeechRecognition)을 쓴다 — 따로 받는 라이브러리·모델·API 키 없음.
// 크롬·엣지·사파리에서 되고(파이어폭스는 없어서 🎤 를 그리지 않는다), 내장 마이크를 그대로 쓴다.
// ⚠ 크롬·엣지는 목소리를 브라우저 회사(구글·MS) 서버에서 글자로 바꾼다 — grace 가 알고 고른 방식(11/3).
// 알아들은 말은 글자 질문과 똑같이 보내고, 서버가 한 글자 틀린 앱 낱말을 고쳐 알아듣는다(engine.voice_fix).
const SR = window.SpeechRecognition || window.webkitSpeechRecognition
const VOICE_OK = !!SR
const voice = {on: false, busy: false, rec: null, note: ""}

const setNote = t => { voice.note = t; render() }

// 크롬은 크롬 설정에서 고른 마이크로 음성 인식을 한다 — 거기에 가상 장치(BlackHole·Zoom 등)가 잡혀 있으면
// 소리가 하나도 안 들어가 «no-speech»만 난다(11/3 grace 맥북: 크롬=BlackHole, 맥 기본=내장 마이크).
// 그래서 진짜 마이크를 직접 골라 그 소리를 음성 인식에 넘긴다(start(track), 크롬 137+). 못 하면 예전처럼.
const VIRTUAL_MIC = /virtual|blackhole|zoom|soundflower|loopback|cable|teams|vb-audio|obs|krisp/i

async function realMicTrack() {
  if (!navigator.mediaDevices?.getUserMedia) return null
  let s = await navigator.mediaDevices.getUserMedia({audio: true})      // 허락 + 이름 보이게
  const first = s.getAudioTracks()[0]
  if (first && !VIRTUAL_MIC.test(first.label)) return first
  s.getTracks().forEach(t => t.stop())
  const ins = (await navigator.mediaDevices.enumerateDevices()).filter(d => d.kind === "audioinput")
  const pick = ins.find(d => d.deviceId === "default" && !VIRTUAL_MIC.test(d.label))
    || ins.find(d => /built-?in|내장|마이크|microphone/i.test(d.label) && !VIRTUAL_MIC.test(d.label))
    || ins.find(d => !VIRTUAL_MIC.test(d.label))
  if (!pick) return null
  s = await navigator.mediaDevices.getUserMedia({audio: {deviceId: {exact: pick.deviceId}}})
  return s.getAudioTracks()[0] || null
}

async function toggleVoice() {
  if (voice.on) { voice.rec?.stop(); return }
  if (chat.busy) return
  let track = null
  try { track = await realMicTrack() } catch (e) {
    if (e?.name === "NotAllowedError") { setNote(/system/i.test(e.message) ? "맥 설정에서 브라우저의 마이크가 꺼져 있어요(시스템 설정 → 개인정보 보호 및 보안 → 마이크)." : "마이크를 쓰려면 허락이 필요해요(주소창 왼쪽 아이콘 → 마이크 허용)."); return }
  }
  const rec = new SR()
  rec.lang = "ko-KR"
  rec.interimResults = true
  rec.continuous = false
  rec.maxAlternatives = 1
  let heard = ""
  rec.onresult = e => {
    let interim = ""
    heard = ""
    for (const r of e.results) (r.isFinal ? (heard += r[0].transcript) : (interim += r[0].transcript))
    const inp = document.getElementById("chatInput")
    if (inp) inp.value = heard + interim                    // 듣는 대로 입력칸에 보여 준다
  }
  rec.onerror = e => {
    voice.note = e.error === "not-allowed" || e.error === "service-not-allowed"
      ? "마이크를 쓰려면 허락이 필요해요(주소창 왼쪽 아이콘 → 마이크 허용)."
      : e.error === "no-speech" ? "말소리를 못 들었어요. 🎤 를 다시 누르고 말해 주세요."
      : e.error === "audio-capture" ? "마이크를 찾지 못했어요. 컴퓨터 마이크가 켜져 있는지 확인해 주세요."
      : e.error === "network" ? "음성 인식 서버에 닿지 못했어요(인터넷 연결 확인). 글자로 물어봐 주세요."
      : e.error === "aborted" ? "" : `음성 인식이 멈췄어요(${e.error}). 글자로 물어봐 주세요.`
  }
  rec.onend = () => {
    track?.stop()
    voice.on = false
    voice.rec = null
    const q = heard.trim()
    if (!q) { render(); return }
    voice.note = ""
    const inp = document.getElementById("chatInput")
    if (inp) inp.value = ""
    send(q, {voice: true})
  }
  voice.on = true
  voice.rec = rec
  voice.note = "듣고 있어요… 말을 마치면 알아서 보내요. (🎤 를 다시 누르면 바로 멈춤)"
  render()
  try {
    if (track) { try { rec.start(track) } catch { track.stop(); track = null; rec.start() } } else rec.start()
  } catch { track?.stop(); voice.on = false; voice.rec = null; setNote("음성 인식을 시작하지 못했어요.") }
}

// 패널 안 이벤트는 여기서만 — main.js 의 큰 위임 핸들러와 섞지 않는다.
export function initChat() {
  const host = document.getElementById("chatHost")
  if (!host) return
  host.addEventListener("click", e => {
    if (e.target.closest("[data-chat-close]")) { closeChat(); return }
    if (e.target.closest("[data-chat-mic]")) { toggleVoice(); return }
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
