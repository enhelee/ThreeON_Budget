import { CHAR_IMG } from "./char_images.js"
import { state } from "../state.js"

// ─────────────────────────────────────────────────────────────
// 실적이 등장 — 처음 보는 사람이 오른쪽 아래 «물어보기»를 못 보고 지나치지 않게(2026-11-03 grace).
// 메인 화면에 들어올 때마다(11/3 grace: 하루 한 번 → 매번): 가운데에 크게 나와 인사 → 오른쪽 아래로 날아가 앉는다.
// 메인 안에서 다시 그릴 때(자료 받은 뒤 등)는 다시 나오지 않는다 — 다른 화면에서 메인으로 «들어올» 때만.
// 누르면 바로 대화가 열리고, Esc·바깥을 누르면 바로 자리로 간다.
// ─────────────────────────────────────────────────────────────

const HOLD_MS = 2600, FLY_MS = 750, START_DELAY_MS = 900   // 입구(gate) 퇴장 650ms 뒤에 시작

let started = false, lastView = ""

/** 화면을 그릴 때마다 부른다. 메인으로 막 들어왔을 때만 등장한다(입구 화면이 떠 있으면 들어온 뒤에). */
export function maybeFabIntro(openChat) {
  const entered = state.view === "home" && lastView !== "home"
  if (document.getElementById("appShell")?.hidden) return     // 입구 뒤 — 들어온 뒤 다시 불린다
  lastView = state.view
  if (!entered || started) return
  started = true
  const busyOn = () => !document.getElementById("busy")?.classList.contains("hidden")   // «화면을 불러오는 중…»
  const go = () => {
    if (state.view !== "home" || document.getElementById("appShell")?.hidden) { started = false; return }
    if (busyOn()) { setTimeout(go, 300); return }        // 불러오기 창 위에 겹치지 않게 끝날 때까지
    play(openChat, () => { started = false })
  }
  setTimeout(go, START_DELAY_MS)
}

function play(openChat, onDone) {
  const calm = matchMedia("(prefers-reduced-motion: reduce)").matches
  const box = document.createElement("div")
  box.className = "fab-intro"
  box.innerHTML = `<button class="fab-intro__char" type="button" aria-label="실적이에게 물어보기">
      <img src="${CHAR_IMG.mt.full}" alt="">
    </button>
    <div class="fab-intro__bub" role="status">
      <p class="fab-intro__hi">안녕하세요, 실적이예요!</p>
      <p>궁금한 건 언제든 저한테 물어보세요.</p>
      <p>🎤 말로 물어봐도 돼요.</p>
      <p class="fab-intro__where">저는 오른쪽 아래에 있을게요 ↘</p>
    </div>`
  document.body.append(box)
  document.body.classList.add("fab-intro-on")   // 진짜 버튼은 날아와 앉을 때까지 숨김

  let done = false, timer = 0
  const finish = (open = false) => {
    if (done) return
    done = true
    clearTimeout(timer)
    document.removeEventListener("keydown", onKey, true)
    if (open) { land(); openChat?.(); return }
    fly()
  }
  let landed = false
  const land = () => {
    if (landed) return
    landed = true
    onDone()
    box.remove()
    document.body.classList.remove("fab-intro-on")
    const btn = document.querySelector(".help-fab__btn")
    if (!btn || calm) return
    btn.classList.add("help-fab__btn--hello")
    setTimeout(() => btn.classList.remove("help-fab__btn--hello"), 2400)
  }
  const fly = () => {
    const img = box.querySelector(".fab-intro__char img")
    const dest = document.querySelector(".help-fab__img")
    if (calm || !img || !dest || !img.animate) { land(); return }
    const a = img.getBoundingClientRect(), b = dest.getBoundingClientRect()
    if (!b.width) { land(); return }
    const dx = (b.left + b.width / 2) - (a.left + a.width / 2)
    const dy = (b.top + b.height / 2) - (a.top + a.height / 2)
    const s = b.width / a.width
    box.classList.add("fab-intro--fly")
    img.animate([{transform: "none"}, {transform: `translate(${dx}px, ${dy}px) scale(${s})`}],
                {duration: FLY_MS, easing: "cubic-bezier(.5,-0.2,.3,1.2)", fill: "forwards"})
      .finished.then(land, land)
    // 탭이 뒤로 가 있으면 애니메이션이 멈춰 finished 가 안 올 수 있다 — 그래도 버튼이 숨은 채 남지 않게
    setTimeout(land, FLY_MS + 400)
  }
  const onKey = e => { if (e.key === "Escape") finish() }

  box.addEventListener("click", e => finish(!!e.target.closest(".fab-intro__char, .fab-intro__bub")))
  document.addEventListener("keydown", onKey, true)
  timer = setTimeout(() => finish(), calm ? HOLD_MS + 1000 : HOLD_MS)
}
