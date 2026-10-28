// ─────────────────────────────────────────────────────────────
// 로그인 화면 왼쪽 장면의 움직임 (views/gate.js) — 2026-10-28 grace 결정(B안: 전체 화면 + 떠 있는 카드).
//
// ① 인트로(약 2.5초): 흩어진 점들이 날아와 «ONDO» 글자가 된다(ON 은 CI 빨강).
//    글자는 카드에 가리지 않게 카드 왼쪽 빈 곳 가운데에 쓴다.
// ② 글자가 왼쪽 아래로 쓸려 내려가며 사라지고, 같은 자리에서 데이터 흐름이 시작된다.
// ③ 흐름: 점들이 매칭이 → 검토미 → 예측이를 차례로 지나며 메인 그래프 색(파랑 → 산호 → 회청)으로 바뀐다.
//    초당 약 90개·최대 1400개, 반짝임·빛 꼬리·큰 점 빛 번짐(10/28 «더 있어 보이게»).
//
// 지키는 것
// - 누르거나 키를 치면 ①②를 건너뛴다(입력 칸 포커스는 건드리지 않는다).
// - 움직임 줄이기 설정 · 좁은 화면(<1024px)은 그리지 않는다 — CSS 기본 상태(캐릭터·문구)가 곧 마지막 장면.
// - stopIntro() 가 그리기·이벤트를 모두 걷는다. 로그인하면 hideGate() 가 부른다.
// 숫자(금액·건수)는 그리지 않는다 — 게이트 원칙.
// ─────────────────────────────────────────────────────────────

const RED = [254, 0, 9], GRAY = [150, 165, 190], WHITE = [230, 236, 245]
const BLUE = [157, 179, 224], PEACH = [229, 143, 121], SLATE = [173, 183, 201]   // 메인 그래프 팔레트(10/28)
const rgba = (c, a) => `rgba(${c[0]},${c[1]},${c[2]},${a})`
const mix = (a, b, t) => a.map((v, i) => v + (b[i] - v) * t)
const rnd = (a, b) => a + Math.random() * (b - a)

let run = null

export function stopIntro() {
  if (!run) return
  cancelAnimationFrame(run.raf)
  run.off()
  run.scene.classList.remove("is-intro")
  run = null
}

export function startIntro(scene) {
  stopIntro()
  if (!scene) return
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches
  if (reduce || window.innerWidth < 1024) return
  const cv = scene.querySelector("canvas")
  const ctx = cv?.getContext("2d")
  if (!ctx) return

  let W = 0, H = 0, logo = [], flow = [], spawn = 0, phase = "logo", t0 = performance.now(), last = t0, flowAt = 0
  const chars = [...scene.querySelectorAll(".gate-char")]

  function size() {
    const r = scene.getBoundingClientRect(), dpr = Math.min(window.devicePixelRatio || 1, 2)
    W = r.width; H = r.height
    cv.width = W * dpr; cv.height = H * dpr
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  }

  // «ONDO» 글자 모양의 점 목표 — 화면 밖 캔버스에 글자를 쓰고 픽셀을 훑는다
  function logoTargets() {
    const o = document.createElement("canvas"), c = o.getContext("2d")
    o.width = Math.ceil(W); o.height = Math.ceil(H)
    const card = document.querySelector(".gate-card")?.getBoundingClientRect()
    const room = card && card.left > W * 0.4 ? card.left : W   // 카드 왼쪽 빈 곳
    const cx = room / 2, fs = Math.min(room * 0.3, H * 0.3)
    c.font = `800 ${fs}px Pretendard, system-ui, sans-serif`
    c.textAlign = "center"; c.textBaseline = "middle"; c.fillStyle = "#fff"
    c.fillText("ONDO", cx, H * 0.45)
    const split = cx - c.measureText("ONDO").width / 2 + c.measureText("ON").width
    const d = c.getImageData(0, 0, o.width, o.height).data, gap = Math.max(4, Math.round(fs / 34)), pts = []
    for (let y = 0; y < o.height; y += gap) for (let x = 0; x < o.width; x += gap)
      if (d[(y * o.width + x) * 4 + 3] > 128) pts.push({x: rnd(0, W), y: rnd(0, H), vx: 0, vy: 0, tx: x, ty: y, c: x < split ? RED : WHITE})
    return pts
  }

  // 흐름 길: 왼쪽 아래 → 세 캐릭터 가운데 → 카드 뒤로 (Catmull-Rom) — 카드 오른쪽으로 다시 새어 나오지 않게
  function pathPoints() {
    const s = scene.getBoundingClientRect(), card = document.querySelector(".gate-card")?.getBoundingClientRect()
    return [[-40, H * 0.92], ...chars.map(el => {
      const r = el.getBoundingClientRect()
      return [r.left - s.left + r.width / 2, r.top - s.top + r.height * 0.45]
    }), [card && card.left > W * 0.4 ? card.left + 60 : W + 40, H * 0.35]]
  }
  function at(K, u) {
    const i = Math.min(K.length - 2, Math.floor(u)), t = u - i
    const p0 = K[Math.max(0, i - 1)], p1 = K[i], p2 = K[i + 1], p3 = K[Math.min(K.length - 1, i + 2)]
    const f = (a, b, c, d) => 0.5 * (2 * b + (-a + c) * t + (2 * a - 5 * b + 4 * c - d) * t * t + (-a + 3 * b - 3 * c + d) * t * t * t)
    return [f(p0[0], p1[0], p2[0], p3[0]), f(p0[1], p1[1], p2[1], p3[1])]
  }
  const STOPS = [GRAY, BLUE, PEACH, SLATE, SLATE]
  const colorAt = u => { const i = Math.min(3, Math.floor(u)); return mix(STOPS[i], STOPS[i + 1], Math.min(1, (u - i) * 3)) }

  function toFlow() {
    if (phase !== "logo") return
    phase = "sweep"; flowAt = performance.now()
  }

  function frame(now) {
    const dt = Math.min(50, now - last), k = dt / 16; last = now
    if (phase === "logo" && now - t0 > 2500) toFlow()
    if (phase === "sweep" && now - flowAt > 900) { phase = "flow"; scene.classList.remove("is-intro") }

    if (phase !== "flow") {
      ctx.fillStyle = "rgba(11,16,32,.35)"; ctx.fillRect(0, 0, W, H)
      const fade = phase === "sweep" ? Math.max(0, 1 - (now - flowAt) / 900) : 1
      for (const p of logo) {
        if (phase === "logo") { p.vx += (p.tx - p.x) * 0.012 * k; p.vy += (p.ty - p.y) * 0.012 * k }
        else { const dx = -40 - p.x, dy = H * 0.92 - p.y, d = Math.hypot(dx, dy) || 1; p.vx += dx / d * 2 * k; p.vy += dy / d * 2 * k }
        p.vx *= 0.86; p.vy *= 0.86; p.x += p.vx * k; p.y += p.vy * k
        ctx.fillStyle = rgba(p.c, 0.9 * fade); ctx.fillRect(p.x, p.y, 2, 2)
      }
    } else {
      // 꼬리: 지난 프레임을 조금씩 지워 점 뒤에 짧은 빛 꼬리를 남긴다. 캔버스는 투명이라 destination-out 으로 지운다(뒤 빛 번짐 배경을 가리지 않게).
      ctx.globalCompositeOperation = "destination-out"; ctx.fillStyle = "rgba(0,0,0,.26)"; ctx.fillRect(0, 0, W, H)
      ctx.globalCompositeOperation = "lighter"                           // 겹친 점은 더 밝게 — 흐름이 빛의 띠처럼 보인다
      const K = pathPoints()
      spawn += 0.09 * dt                                                 // 초당 약 90개(2026-10-28 grace: 양이 적어 허전하다)
      while (spawn >= 1 && flow.length < 1400) {
        spawn--
        flow.push({u: 0, v: rnd(0.00022, 0.00036), o: rnd(-1, 1) + rnd(-1, 1) * 0.5, r: rnd(0.7, 2.6), tw: rnd(0, 6.3)})
      }
      spawn = Math.min(spawn, 1)
      for (const p of flow) {
        p.u += p.v * dt
        const a = at(K, p.u), b = at(K, Math.min(4, p.u + 0.01)), ang = Math.atan2(b[1] - a[1], b[0] - a[0])
        const spread = 44 * (0.12 + 0.88 * Math.sin(Math.PI * (p.u % 1)))   // 캐릭터 가까이에서 좁아진다
        const x = a[0] - Math.sin(ang) * p.o * spread, y = a[1] + Math.cos(ang) * p.o * spread
        const c = colorAt(p.u), al = 0.55 + 0.45 * Math.sin(now / 320 + p.tw)  // 반짝임
        if (p.r > 1.7) { ctx.fillStyle = rgba(c, 0.10 * al); ctx.beginPath(); ctx.arc(x, y, p.r * 3.4, 0, 7); ctx.fill() }   // 큰 점엔 빛 번짐
        ctx.fillStyle = rgba(c, 0.9 * al)
        ctx.beginPath(); ctx.arc(x, y, p.r, 0, 7); ctx.fill()
      }
      ctx.globalCompositeOperation = "source-over"
      flow = flow.filter(p => p.u < 4)
    }
    if (run) run.raf = requestAnimationFrame(frame)
  }

  const onResize = () => { size(); if (phase === "logo") logo = logoTargets() }
  const onSkip = () => toFlow()
  window.addEventListener("resize", onResize)
  scene.addEventListener("pointerdown", onSkip)
  document.addEventListener("keydown", onSkip)

  size(); logo = logoTargets()
  scene.classList.add("is-intro")
  run = {scene, raf: requestAnimationFrame(frame), off() {
    window.removeEventListener("resize", onResize)
    scene.removeEventListener("pointerdown", onSkip)
    document.removeEventListener("keydown", onSkip)
    ctx.clearRect(0, 0, W, H)
  }}
}
