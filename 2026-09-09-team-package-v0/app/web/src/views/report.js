import { api } from "../api.js"
import { busy, toast } from "../components/feedback.js"
import { state } from "../state.js"
import { $, esc } from "../util.js"
import { renderPage } from "../router.js"

// ─────────────────────────────────────────────────────────────
// 4번 «한글 보고서» 탭 — 보고서를 종이 모양 그대로 띄우고 그 위에서 고친다.
//
// 서버가 한글 양식(hwpx)을 채워 HTML 로 그려 준다(/api/report/perf/preview). 노란 칸이 고칠 수 있는 곳,
// 나머지 숫자(합계·잔액·실적률·점유율)는 자동 계산이다. 칸을 고치고 나가면(focusout) 그 값이 입력값에
// 들어가고, 서버가 다시 채워 그린다 — 내려받는 hwpx 도 같은 채우기를 지나므로 화면과 파일이 같다.
// 고친 값은 서버에 저장하지 않는다. 내려받은 파일이 결과물이고, 탭을 다시 열면 분석 결과로 새로 채운다.
// ─────────────────────────────────────────────────────────────

const post = body => ({method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)})

// 보고서 두 종 — 같은 화면·같은 API(/api/report/{kind}/…), 양식과 채우는 규칙만 서버에서 다르다.
const KINDS = {
  perf: {tab: "집행 성과 분석", title: yy => `‘${yy}년 열원 유지보수예산 집행성과분석`,
         desc: "연초(2월) 예산분석부 송부용."},
  plan: {tab: "집행 실적 및 계획", title: yy => `[붙임2] ‘${yy}년～‘${Number(yy) + 1}년 열원시설 유지보수예산 집행실적 및 계획`,
         desc: "5월 유지보수 실적 및 계획 보고 첨부용. 과목별 숫자 한 칸을 고치면 그 숫자를 쓰는 모든 표가 같이 바뀝니다."},
}
const kindOf = () => state.reportKind || "perf"

// 보고서 연도 — 기본은 대상연도. 대상연도는 분석한 해만 고를 수 있어 2016년 같은 예전 해를 못 고른다(2026-10-29 라이브 확인)
//   → 보고서 안에서 따로 고른다(참고 엑셀 실적이 있는 해까지). 대상연도를 바꾸면 다시 대상연도를 따른다.
export const reportYear = () => state.reportPick?.base === state.year ? state.reportPick.year : state.year

export async function loadReport() {
  const y = reportYear(), kind = kindOf()
  const [inputs, years] = await Promise.all([api(`/api/report/${kind}?year=${y}`), api("/api/report-years")])
  const pv = await api(`/api/report/${kind}/preview`, post({year: y, inputs}))
  state.report = {kind, inputs: {...pv.inputs, warnings: inputs.warnings}, html: pv.html, _year: y, years}
}

/** 보고서 연도 고르기(change) — 처리했으면 true. */
export async function onReportChange(e) {
  if (!e.target.dataset.rpYear) return false
  state.reportPick = {base: state.year, year: e.target.value}
  busy(true, "불러오는 중…")
  try { await loadReport() } catch (err) { toast(err.message) } finally { busy(false) }
  renderPage()
  return true
}

let rev = 0          // 고칠 때마다 +1 — 늦게 온 앞선 응답이 그 뒤에 고친 값을 덮지 않게

/** 표 칸 안 글자가 칸보다 넓으면 그 문단만 줄여 맞춘다.
 *  한글 글꼴(휴먼명조 등)이 없는 PC 에서는 대체 글꼴이 더 넓어 옆 칸을 침범한다 — 파일에는 영향 없음. */
function fitCells(root = $("#rpDoc")) {
  if (!root) return
  // zoom 은 쓰지 않는다 — 크롬에서 고정 폭 표 안의 zoom 이 칸 폭을 1,677만 px 로 키워 문서가 통째로 깨졌다(2026-10-28).
  //   글자 크기에 곱하는 --fit 변수(hwpx_html 이 font-size:calc(…pt * var(--fit,1)) 로 낸다)를 줄인다.
  for (const p of root.querySelectorAll(".rp-tbl .rp-p")) {
    p.style.removeProperty("--fit")
    if (p.clientWidth < 8) continue                    // 아직 안 그려졌거나 숨은 칸 — 재면 엉뚱한 비율이 나온다
    const over = p.scrollWidth / p.clientWidth
    if (over > 1.01) p.style.setProperty("--fit", String(Math.max(0.6, 1 / over).toFixed(3)))
  }
}

const BULLET = /[^\s\u3000□○ㅇ◈◦▪■●◆◇·ㆍ∙※▷➢☞-]/   // 머리 기호(양식은 «○» 대신 한글 «ㅇ»도 쓴다)·빈칸이 아닌 첫 글자

/** 내어쓰기 문단 — 둘째 줄을 머리 기호(□·○·◈) 다음 첫 글자(대개 «(») 자리에 맞춘다.
 *  한글은 둘째 줄을 정해진 내어쓰기 폭에서 시작하고, 원본은 그 폭을 휴먼명조의 «□ » 폭에 맞춰 두었다.
 *  대체 글꼴은 폭이 달라 줄이 어긋났다(2026-10-29) → 그려진 뒤 첫 글자 자리를 재서 내어쓰기 폭을 그 값으로. 파일은 그대로. */
function alignHangs(root) {
  for (const p of root.querySelectorAll(".rp-p")) {
    const st = p.style
    p.dataset.ti ??= st.textIndent
    p.dataset.pl ??= st.paddingLeft
    st.textIndent = p.dataset.ti; st.paddingLeft = p.dataset.pl
    const ti = parseFloat(p.dataset.ti)
    if (!(ti < 0) || p.querySelector(".rp-tbl") || p.clientWidth < 8) continue
    const walk = document.createTreeWalker(p, NodeFilter.SHOW_TEXT)
    let node, at = -1
    while ((node = walk.nextNode())) {
      if (node.parentElement.closest(".rp-tools")) continue
      at = node.data.search(BULLET)
      if (at >= 0) break
    }
    if (at < 0) continue
    const r = document.createRange(); r.setStart(node, at); r.setEnd(node, at + 1)
    const pr = p.getBoundingClientRect(), k = pr.width / p.offsetWidth   // 종이를 줄였으면 그 비율
    const l0 = (parseFloat(p.dataset.pl) || 0) + ti                       // 첫 줄 시작(문단 왼쪽 여백)
    const w = (r.getBoundingClientRect().left - pr.left) / k - l0
    if (w <= 0 || w > p.clientWidth / 2) continue                          // 첫 글자가 첫 줄에 없다 — 그대로
    st.paddingLeft = `${(l0 + w).toFixed(2)}px`
    st.textIndent = `${(-w).toFixed(2)}px`
  }
}

/** 배분 정렬 칸(과목 이름 등) — 한글은 글자를 칸 폭에 고르게 벌린다. CSS 양쪽 정렬은 한 줄짜리 한글을
 *  벌리지 않아 왼쪽에 붙어 보였다(2026-10-29) → 남는 폭을 글자 사이 자간으로 나눈다. 넘치는 칸은 fitCells 가 줄인다. */
function distribute(root, reset) {
  for (const p of root.querySelectorAll(".rp-dist")) {
    const own = [...p.querySelectorAll("span")].filter(e => e.style.letterSpacing)   // 글자 모양의 자간(-0.04em 등)
    if (reset) {
      p.dataset.ta ??= p.style.textAlign                 // 원래 정렬(문단 모양) — 지우지 말고 되돌린다
      p.style.letterSpacing = p.style.marginRight = ""
      p.style.textAlign = p.dataset.ta
      for (const e of own) if (e.dataset.ls != null) e.style.letterSpacing = e.dataset.ls
      continue
    }
    const n = [...p.innerText.trim()].length
    if (n < 2 || p.clientWidth < 8) continue
    const r = document.createRange(); r.selectNodeContents(p)
    const rects = [...r.getClientRects()]
    const tops = rects.map(x => x.top)
    if (Math.max(...tops) - Math.min(...tops) > rects[0].height / 2) continue   // 여러 줄 — 그대로(글자 상자끼리 1px 차이는 한 줄)
    const k = p.getBoundingClientRect().width / p.offsetWidth
    const cs = getComputedStyle(p)
    const avail = p.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight)
    const used = (Math.max(...rects.map(x => x.right)) - Math.min(...rects.map(x => x.left))) / k
    const gap = (avail - used) / (n - 1)
    if (gap <= 0.5) continue
    p.style.textAlign = "left"
    p.style.letterSpacing = `${gap.toFixed(2)}px`
    for (const e of own) {
      e.dataset.ls ??= e.style.letterSpacing
      e.style.letterSpacing = `calc(${e.dataset.ls} + ${gap.toFixed(2)}px)`
    }
    p.style.marginRight = `${(-gap).toFixed(2)}px`                         // 마지막 글자 뒤 자간만큼 — 칸을 넘지 않게
  }
}

/** 그린 뒤 맞춤 — 내어쓰기 줄 → 표 칸 글자 → 배분 정렬 → 종이 폭 순서. */
function layout(root = $("#rpDoc")) {
  if (!root) return
  distribute(root, true)
  alignHangs(root)
  fitCells(root)
  distribute(root)
  fitPage()
}
document.fonts?.ready.then(() => layout())          // 글꼴이 늦게 오면 폭이 바뀐다
document.addEventListener("visibilitychange", () => { if (!document.hidden) layout() })   // 숨은 탭에서는 재는 값이 틀린다

/** 종이가 화면보다 넓으면 통째로 줄여 맞춘다 — 좁은 창에서 오른쪽이 잘려 보였다(2026-10-29).
 *  transform 은 그리기만 줄이고 칸 폭 계산은 그대로라 fitCells·한글 파일에 영향이 없다. */
function fitPage() {
  const desk = $(".rp-desk"), doc = $("#rpDoc"), page = doc?.querySelector(".rp-page")
  if (!page) return
  doc.style.transform = doc.style.marginBottom = ""
  const cs = getComputedStyle(desk)
  const avail = desk.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight)
  const w = page.offsetWidth
  if (w < 8 || avail >= w) return
  const k = Math.max(0.5, avail / w)
  doc.style.transformOrigin = "top left"
  doc.style.transform = `scale(${k.toFixed(3)})`
  doc.style.marginBottom = `${-(doc.offsetHeight * (1 - k)).toFixed(0)}px`   // 줄인 만큼 아래 빈자리를 없앤다
}
addEventListener("resize", () => { clearTimeout(fitPage.t); fitPage.t = setTimeout(fitPage, 150) })

/** 입력값이 바뀐 뒤 — 문서만 다시 받아 그 자리만 갈아 끼운다(스크롤·탭 유지). */
async function refresh() {
  const mine = ++rev
  const inp = state.report.inputs
  const pv = await api(`/api/report/${state.report.kind}/preview`, post({year: inp.year, inputs: inp}))
  if (mine !== rev) return                           // 그 사이 또 고쳤다 — 뒤 요청의 응답이 그린다
  state.report.inputs = {...pv.inputs, warnings: inp.warnings}   // 서버가 다듬은 값(라벨 떼기 등)
  state.report.html = pv.html
  const doc = $("#rpDoc")
  if (!doc) return
  // 다른 칸으로 옮겨 가는 중이었다면 다시 그린 뒤 그 칸에 커서를 돌려준다
  const ae = document.activeElement
  const back = ae && doc.contains(ae) ? ae.dataset.path : null
  doc.innerHTML = pv.html
  layout(doc)
  const el = back && doc.querySelector(`[data-path="${CSS.escape(back)}"]`)
  if (el) {
    el.focus()
    const r = document.createRange(); r.selectNodeContents(el); r.collapse(false)
    const sel = getSelection(); sel.removeAllRanges(); sel.addRange(r)
    el.dataset.orig = el.innerText
  }
}

function get(path) {
  return path.split(".").reduce((o, k) => (o == null ? o : o[k]), state.report.inputs)
}

function set(path, value) {
  const ks = path.split(".")
  const last = ks.pop()
  const o = ks.reduce((o, k) => (o[k] ??= {}), state.report.inputs)
  o[last] = value
}

/** 화면 글자 → 입력값. 숫자 칸은 쉼표·△(음수)를 읽는다. 못 읽으면 undefined(되돌림). */
function parse(kind, raw) {
  const s = String(raw).replace(/ /g, " ").trim()
  if (kind === "num") {
    if (!s) return 0
    const v = parseFloat(s.replace(/,/g, "").replace(/^△/, "-"))
    return isNaN(v) ? undefined : v
  }
  if (kind === "count") {
    const m = /\((\d+)\)/.exec(s) || /(\d+)/.exec(s)
    return m ? Number(m[1]) : undefined
  }
  if (kind === "date") {
    const m = /\d{4}\.\s*\d{1,2}\./.exec(s)
    return m ? m[0] : undefined
  }
  if (kind === "label") return s.replace(/^\(/, "").replace(/\)$/, "").trim()
  if (kind === "grade") return s === "-" ? "" : s
  return s
}

export function reportHtml() {
  const rp = state.report
  if (!rp) return `<section class="panel p-6 text-sm text-tri">불러오는 중…</section>`
  const inp = rp.inputs
  const yy = String(inp.year).slice(2)
  const K = KINDS[rp.kind]
  const warn = (inp.warnings || []).map(w => `<li>${esc(w)}</li>`).join("")
  setTimeout(() => requestAnimationFrame(() => layout()), 0)   // 그려진 뒤(다음 화면 그리기 때) 줄·칸·종이 맞춤 — HTML 문자열만 돌려주므로
  const years = [...new Set([...(rp.years || []), String(inp.year)])].sort().reverse()
  return `
    <div class="flex flex-wrap gap-2" role="tablist" aria-label="보고서 종류">${Object.entries(KINDS).map(([k, v]) => `<button class="${rp.kind === k ? "btn-primary" : "btn-secondary"}" role="tab" aria-selected="${rp.kind === k}" data-rp-act="kind" data-kind="${k}">${esc(v.tab)}</button>`).join("")}</div>
    <section class="panel p-5 sm:p-6">
      <div class="flex flex-wrap items-start justify-between gap-3">
        <div><h3 class="section-title">${esc(K.title(yy))}</h3>
          <p class="mt-1 text-sm text-sub">${esc(K.desc)} 아래 문서에서 <span class="rp-legend rp-legend--edit">노란 칸</span>을 눌러 바로 고치세요. 나머지 숫자는 따라서 다시 계산됩니다. <span class="rp-legend rp-legend--adj">모서리 표시</span>는 반올림 때문에 합계와 맞도록 1씩 맞춘 칸입니다(마우스를 올리면 실제 값).</p></div>
        <div class="flex flex-wrap items-center gap-2">
          <label class="text-sm text-sub">보고서 연도
            <select class="ml-1 rounded-lg border border-line px-2 py-1.5 text-sm" data-rp-year="1" aria-label="보고서 연도">${years.map(y => `<option value="${y}"${y === String(inp.year) ? " selected" : ""}>${y}년</option>`).join("")}</select></label>
          <button class="btn-secondary" data-rp-act="regen" title="고친 숫자로 ◈·□ 문장을 다시 씁니다(○ 원인 줄은 그대로)">숫자로 문장 다시 쓰기</button>
          <button class="btn-secondary" data-rp-act="reset" title="고친 내용을 버리고 분석 결과로 다시 채웁니다">처음 값으로</button>
          <button class="btn-primary" data-rp-act="download">한글(hwpx) 내려받기</button>
        </div>
      </div>
      ${warn ? `<ul class="mt-4 list-disc space-y-1 rounded-lg bg-warn-bg p-4 pl-8 text-sm text-warn">${warn}</ul>` : ""}
      <p class="mt-3 text-xs text-tri">○ 원인 줄은 □ 문단 끝의 «+ ○»로 늘리고 «−»로 뺍니다. 마지막 ○ 줄 끝에는 «끝.»이 자동으로 붙습니다. 고친 내용은 저장되지 않으니 다 고친 뒤 내려받으세요.</p>
    </section>
    <div class="rp-desk"><div id="rpDoc">${rp.html}</div></div>`
}

// ───────────────────────── 이벤트(main.js 가 위임) ─────────────────────────

/** 고칠 칸에서 나갈 때 — 값이 바뀌었으면 입력값에 넣고 문서를 다시 그린다. */
export async function onReportBlur(e) {
  const el = e.target.closest?.("#rpDoc [data-path]")
  if (!el || !state.report) return false
  const {path, kind} = el.dataset
  if (el.innerText === el.dataset.orig) return true    // 들어왔다 그냥 나감 — 반올림된 표시값으로 덮지 않는다
  const v = parse(kind, el.innerText)
  if (v === undefined) { toast("읽을 수 없는 값이라 되돌렸습니다."); await refresh(); return true }
  if (path.startsWith("three.")) {
    const base = path.split(".").slice(0, 3).join(".")
    if (!get(base)) set(base, {배정: 0, 실적: 0})        // 분석이 없던 해에 처음 넣는 값
  }
  set(path, v)
  try { await refresh() } catch (err) { toast(err.message) }
  return true
}

/** 칸에 들어갈 때 처음 글자를 적어 둔다(안 고치고 나가면 아무 일도 없게). */
export function onReportFocus(e) {
  const el = e.target.closest?.("#rpDoc [data-path]")
  if (el) el.dataset.orig = el.innerText
}

/** 칸에서 Enter = 입력 끝(줄바꿈 대신 — 문단 안 줄바꿈은 한글에서). */
export function onReportKey(e) {
  const el = e.target.closest?.("#rpDoc [data-path]")
  if (!el || e.key !== "Enter" || e.shiftKey) return false
  e.preventDefault()
  el.blur()
  return true
}

/** 버튼. 처리했으면 true(다시 그리기가 필요하면 그 안에서 한다). */
export async function onReportClick(e) {
  const b = e.target.closest("[data-rp-act]")
  if (!b || !state.report) return false
  const act = b.dataset.rpAct
  const tx = state.report.inputs.texts
  const kind = state.report.kind
  try {
    if (act === "kind") {
      if (b.dataset.kind === kind) return true
      state.reportKind = b.dataset.kind
      busy(true, "불러오는 중…")
      try { await loadReport() } finally { busy(false) }
      renderPage()
      return true
    }
    if (act === "add-bullet") { (tx[b.dataset.k] ??= []).push({label: "", body: ""}); await refresh(); return true }
    if (act === "del-bullet") { tx[b.dataset.k].splice(Number(b.dataset.i), 1); await refresh(); return true }
    if (act === "reset") {
      if (!confirm("고친 내용을 버리고 분석 결과로 다시 채울까요?")) return true
      busy(true, "불러오는 중…")
      try { await loadReport() } finally { busy(false) }
      const doc = $("#rpDoc")
      if (doc) { doc.innerHTML = state.report.html; layout(doc) }
      return true
    }
    const inp = state.report.inputs
    if (act === "regen") {
      const t = await api(`/api/report/${kind}/texts`, post({year: inp.year, inputs: inp}))
      for (const [k, v] of Object.entries(t)) if (!Array.isArray(v)) tx[k] = v   // ○ 원인 줄(배열)은 그대로
      await refresh()
      toast("◈·□ 문장을 지금 숫자로 다시 썼습니다 — ○ 원인 줄은 그대로입니다.")
      return true
    }
    if (act === "download") {
      busy(true, "한글 파일을 만드는 중…")
      try {
        const res = await fetch(`/api/report/${kind}/hwpx`, post({year: inp.year, inputs: inp}))
        if (!res.ok) {
          let msg = res.statusText
          try { msg = (await res.json()).detail || msg } catch {}
          throw new Error(msg)
        }
        const cd = res.headers.get("content-disposition") || ""
        const m = /filename\*=utf-8''([^;]+)/i.exec(cd)
        const url = URL.createObjectURL(await res.blob())
        const a = Object.assign(document.createElement("a"), {href: url, download: m ? decodeURIComponent(m[1]) : "report.hwpx"})
        document.body.appendChild(a); a.click(); a.remove()
        setTimeout(() => URL.revokeObjectURL(url), 10000)
      } finally { busy(false) }
      return true
    }
  } catch (err) { toast(err.message) }
  return false
}
