import { state } from "../state.js"
import { esc, fmt } from "../util.js"

// ─────────────────────────────────────────────────────────────
// 5번 탭 «시나리오 비교» (2026-10-27, 경진대회 C) — 가정 2~3벌을 나란히.
//
//   전망이 가정 한 벌로만 보이면 «믿을 수 있나»에 답이 오차율뿐이다. 손잡이 둘(물가 연 %p · 물량 %)로
//   시나리오를 만들어 10년 누계·연도별 선·지사 × 연도 차이를 같이 보면 질문이 «어떤 가정이 얼마를
//   움직이나»로 바뀐다. 첫 시나리오가 비교 기준이고, 회색 띠는 그 시나리오의 «학습 기간 실적 범위»
//   (전망 표의 예측 범위를 전사로 더한 것)다. 저장된 가정은 바꾸지 않는다(서버 GET, 캐시).
//   상태 state.fc.sc, 핸들러 forecast_actions.js(data-sc*).
// ─────────────────────────────────────────────────────────────

// 계열 색 = dataviz 기준 팔레트 앞 세 칸(세 색끼리 색약 검증 통과). 이름은 선 끝에 직접 붙인다.
export const SC_COLORS = ["#2a78d6", "#eb6834", "#1baf7a"]
// 차이(시나리오 − 기준) = 파랑(감소) ↔ 회색 ↔ 빨강(증가) — 중장기 한눈에 보기와 같은 색. [하한%, 색, 흰 글자]
const DIV = [[-Infinity, "#256abf", true], [-10, "#9ec5f4", false], [-3, "#F0EFEC", false],
             [3, "#F6C1BA", false], [10, "#E8796C", false], [25, "#B42318", true]]
const DIV_LABEL = ["-10% 미만", "-10~-3%", "±3%", "+3~10%", "+10~25%", "+25% 초과"]

const eok = v => { const x = v / 1e5; return Math.abs(x) >= 100 ? fmt(Math.round(x)) : x.toFixed(1) }
const sgnEok = v => `${v >= 0 ? "+" : "−"}${eok(Math.abs(v))}`
const sgnPct = p => `${p >= 0 ? "+" : "−"}${Math.abs(p).toFixed(1)}%`
const knob = (v, unit) => `${v > 0 ? "+" : v < 0 ? "−" : "±"}${Math.abs(v)}${unit}`

function divCell(p) {
  let c = DIV[0]
  for (const x of DIV) if (p >= x[0]) c = x
  return {bg: c[1], dark: c[2]}
}

function knobsHtml(specs) {
  return `<div class="grid gap-3 md:grid-cols-3">${specs.map((s, i) => `
    <div class="rounded-card border border-line p-4" style="border-top:3px solid ${SC_COLORS[i]}">
      <label class="block"><span class="field-label">${i === 0 ? "기준 시나리오" : `시나리오 ${i + 1}`}</span>
        <input class="control w-full" maxlength="20" data-sc-field="name" data-i="${i}" value="${esc(s.name)}"></label>
      <div class="mt-2 grid grid-cols-2 gap-2">
        <label class="block"><span class="field-label">물가 (연 %p)</span>
          <input class="control w-full" type="number" step="0.5" min="-10" max="10" data-sc-field="price" data-i="${i}" value="${s.price}"></label>
        <label class="block"><span class="field-label">물량 (%)</span>
          <input class="control w-full" type="number" step="5" min="-50" max="50" data-sc-field="volume" data-i="${i}" value="${s.volume}"></label>
      </div>
    </div>`).join("")}</div>`
}

function kpiHtml(d) {
  const base = d.scenarios[0]
  return `<div class="grid gap-3 md:grid-cols-3">${d.scenarios.map((s, i) => {
    const diff = s.sum10 - base.sum10
    return `<div class="rounded-card border border-line p-4">
      <p class="flex items-center gap-2 text-sm font-semibold text-ink"><span class="inline-block h-2.5 w-2.5 rounded-full" style="background:${SC_COLORS[i]}"></span>${esc(s.name)}</p>
      <p class="mt-1 text-xs text-tri">물가 ${knob(s.price, "%p")} · 물량 ${knob(s.volume, "%")}</p>
      <p class="mt-2 text-2xl font-bold text-ink">${eok(s.sum10)}<span class="ml-1 text-sm font-semibold text-tri">억 원 · 10년</span></p>
      <p class="text-sm ${i === 0 ? "text-tri" : diff >= 0 ? "text-err" : "text-info"}">${i === 0 ? "비교 기준" : `기준 대비 ${sgnEok(diff)}억 원 (${sgnPct(base.sum10 ? diff / base.sum10 * 100 : 0)})`}</p>
    </div>`
  }).join("")}</div>`
}

/** 한 문장 근거 — «물가 +1%p·물량 +10% → 10년 누계 +2,029억 원. 차이가 가장 큰 지사 …» */
export function scenarioSentence(d) {
  const base = d.scenarios[0]
  return d.scenarios.slice(1).map(s => {
    const diff = s.sum10 - base.sum10
    let top = null
    for (const site of d.sites) {
      const a = Object.values(s.by_site[site] || {}).reduce((x, y) => x + y, 0)
      const b = Object.values(base.by_site[site] || {}).reduce((x, y) => x + y, 0)
      if (!top || Math.abs(a - b) > Math.abs(top[1])) top = [site, a - b]
    }
    const dp = s.price - base.price, dv = s.volume - base.volume
    return `«${s.name}»(기준보다 물가 ${knob(dp, "%p")} · 물량 ${knob(dv, "%")}) → 10년 누계 ${sgnEok(diff)}억 원(${sgnPct(base.sum10 ? diff / base.sum10 * 100 : 0)})`
      + (top ? `, 차이가 가장 큰 지사는 ${top[0]}(${sgnEok(top[1])}억 원).` : ".")
  })
}

function lineChart(d) {
  const W = 760, H = 300, L = 56, R = 150, T = 16, B = 34
  const ys = d.years.map(String)
  const vals = d.scenarios.flatMap(s => ys.map(y => s.total[y]))
  const bandVals = ys.flatMap(y => d.band[y] || [])
  const lo = Math.min(...vals, ...bandVals), hi = Math.max(...vals, ...bandVals)
  const pad = (hi - lo) * 0.08 || 1
  const y0 = Math.max(0, lo - pad), y1 = hi + pad
  const x = i => L + (W - L - R) * (ys.length === 1 ? 0.5 : i / (ys.length - 1))
  const y = v => T + (H - T - B) * (1 - (v - y0) / (y1 - y0))
  const ticks = 4
  const grid = Array.from({length: ticks + 1}, (_, k) => y0 + (y1 - y0) * k / ticks)
    .map(v => `<line x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}" stroke="var(--line)" stroke-width="1"/>
      <text x="${L - 8}" y="${y(v) + 4}" text-anchor="end" font-size="11" fill="var(--tri)">${eok(v)}</text>`).join("")
  const band = ys.filter(k => d.band[k]).map(k => [ys.indexOf(k), d.band[k]])
  const bandPath = band.length > 1 ? `<path d="${band.map(([i, b], j) => `${j ? "L" : "M"}${x(i)},${y(b[1])}`).join("")}${
      band.slice().reverse().map(([i, b]) => `L${x(i)},${y(b[0])}`).join("")}Z" fill="var(--line-strong)" opacity="0.35"/>` : ""
  // 선 끝 이름표 — 겹치면 아래로 민다(세 줄뿐이라 단순 정렬로 충분)
  const ends = d.scenarios.map((s, i) => ({i, v: y(s.total[ys[ys.length - 1]])})).sort((a, b) => a.v - b.v)
  for (let k = 1; k < ends.length; k++) if (ends[k].v - ends[k - 1].v < 16) ends[k].v = ends[k - 1].v + 16
  const lines = d.scenarios.map((s, i) => {
    const pts = ys.map((k, j) => `${x(j)},${y(s.total[k])}`).join(" ")
    const lab = ends.find(e => e.i === i)
    return `<polyline points="${pts}" fill="none" stroke="${SC_COLORS[i]}" stroke-width="2" stroke-linejoin="round"/>
      ${ys.map((k, j) => `<circle cx="${x(j)}" cy="${y(s.total[k])}" r="3.5" fill="${SC_COLORS[i]}" stroke="#fff" stroke-width="2"/>`).join("")}
      <text x="${W - R + 10}" y="${lab.v + 4}" font-size="12" font-weight="600" fill="var(--ink)">${esc(s.name)}</text>
      <line x1="${W - R + 2}" x2="${W - R + 8}" y1="${lab.v}" y2="${lab.v}" stroke="${SC_COLORS[i]}" stroke-width="2"/>`
  }).join("")
  // 연도마다 세로 띠(마우스 영역) — 그 해 세 값과 범위를 툴팁으로
  const hits = ys.map((k, j) => {
    const tip = [`${k}년`, ...d.scenarios.map(s => `${s.name}: ${eok(s.total[k])}억 원`),
                 ...(d.band[k] && d.band[k][0] !== d.band[k][1] ? [`예측 범위: ${eok(d.band[k][0])}~${eok(d.band[k][1])}억 원`] : [])].join("\n")
    const w = (W - L - R) / Math.max(1, ys.length - 1)
    return `<rect x="${x(j) - w / 2}" y="${T}" width="${w}" height="${H - T - B}" fill="transparent" class="sc-hit"><title>${esc(tip)}</title></rect>
      <text x="${x(j)}" y="${H - 12}" text-anchor="middle" font-size="11" fill="var(--tri)">${k}</text>`
  }).join("")
  return `<svg viewBox="0 0 ${W} ${H}" class="w-full" role="img" aria-label="시나리오별 연도 합계 선 그래프">${grid}${bandPath}${lines}${hits}</svg>`
}

function heatmap(d) {
  const sc = state.fc.sc
  const k = Math.min(Math.max(1, sc.cmp || 1), d.scenarios.length - 1)
  const base = d.scenarios[0], s = d.scenarios[k]
  const ys = d.years.map(String)
  const rows = d.sites.map(site => {
    const a = s.by_site[site] || {}, b = base.by_site[site] || {}
    const diffs = ys.map(y => (a[y] || 0) - (b[y] || 0))
    const tot = diffs.reduce((x, v) => x + v, 0)
    const btot = ys.reduce((x, y) => x + (b[y] || 0), 0)
    return {site, diffs, base: ys.map(y => b[y] || 0), tot, btot}
  }).filter(r => r.btot > 0).sort((p, q) => Math.abs(q.tot) - Math.abs(p.tot))
  const cell = (v, bv, y, site) => {
    const p = bv ? v / bv * 100 : 0
    const c = divCell(p)
    return `<td class="px-1 py-1 text-center text-[11px] font-semibold" style="background:${c.bg};color:${c.dark ? "#fff" : "var(--ink)"}" title="${esc(`${site} ${y}년: ${sgnEok(v)}억 원 (${sgnPct(p)})`)}">${Math.abs(v) < 5e3 ? "·" : sgnEok(v)}</td>`
  }
  return `
    <div class="flex flex-wrap items-end justify-between gap-3 border-b border-line p-5">
      <div><h3 class="section-title">지사 × 연도 차이 · «${esc(s.name)}» − «${esc(base.name)}»</h3>
        <p class="section-help">칸 = 억 원(색은 기준 대비 %) · 10년 차이가 큰 지사부터 · 마우스를 올리면 정확한 값</p></div>
      ${d.scenarios.length > 2 ? `<label class="block"><span class="field-label">비교할 시나리오</span>
        <select class="control" data-sc-cmp>${d.scenarios.slice(1).map((x, i) => `<option value="${i + 1}" ${i + 1 === k ? "selected" : ""}>${esc(x.name)}</option>`).join("")}</select></label>` : ""}
    </div>
    <div class="overflow-x-auto p-5"><table class="w-full border-separate" style="border-spacing:2px">
      <thead><tr><th class="px-2 py-1 text-left text-xs text-sub">지사</th>${ys.map(y => `<th class="px-1 py-1 text-xs text-sub">${y}</th>`).join("")}<th class="px-2 py-1 text-right text-xs text-sub">10년</th></tr></thead>
      <tbody>${rows.map(r => `<tr><td class="whitespace-nowrap px-2 py-1 text-xs font-semibold text-ink">${esc(r.site)}</td>${r.diffs.map((v, j) => cell(v, r.base[j], ys[j], r.site)).join("")}
        <td class="px-2 py-1 text-right text-xs font-bold text-ink">${sgnEok(r.tot)}</td></tr>`).join("")}</tbody></table>
      <div class="mt-3 flex flex-wrap items-center gap-3 text-xs text-sub">${DIV.map((c, i) => `<span class="flex items-center gap-1"><span class="inline-block h-3 w-4 rounded-sm" style="background:${c[1]}"></span>${DIV_LABEL[i]}</span>`).join("")}</div>
    </div>`
}

export function scenarioBody() {
  const sc = state.fc.sc
  const d = sc.data
  const head = `<article class="panel p-5 sm:p-6">
      <div class="flex flex-wrap items-start justify-between gap-3">
        <div><h3 class="section-title">시나리오 비교 — 가정이 바뀌면 10년이 얼마나 움직이나</h3>
          <p class="section-help">손잡이 둘을 저장된 가정 위에 얹어 계산합니다(가정은 바뀌지 않음) · 물가 = 연 %p 가감 · 물량 = 표준금액·A급정비 금액 ± % · 단위 억 원</p></div>
        <button class="btn-primary" data-sc="run">다시 계산</button>
      </div>
      <div class="mt-4">${knobsHtml(sc.specs)}</div>
    </article>`
  if (sc.error) return `${head}<article class="panel p-6 text-sm text-err">${esc(sc.error)}</article>`
  if (sc.loading || !d) return `${head}<article class="panel p-6 text-sm text-sub">시나리오를 계산하는 중… (처음 한 번은 수십 초 걸릴 수 있어요)</article>`
  const notes = []
  if (d.notes?.actuals_empty) notes.push("마감된 연도의 분석 결과가 없어 표준금액이 비어 있습니다 — 시나리오 차이가 0 으로 보일 수 있습니다.")
  if (d.notes?.budget_plan_missing) notes.push(`${esc(d.base_year)}년 계획본이 없어 기준연도도 표준금액으로 계산합니다 — 물량 손잡이가 ${esc(d.base_year)}년에도 걸립니다.`)
  return `${head}
    ${kpiHtml(d)}
    <article class="panel p-5 sm:p-6">
      <ul class="space-y-1 text-sm text-ink">${scenarioSentence(d).map(t => `<li>· ${esc(t)}</li>`).join("")}</ul>
      ${notes.map(n => `<p class="mt-2 rounded-control bg-subtle px-3 py-2 text-xs text-sub">${n}</p>`).join("")}
    </article>
    <article class="panel overflow-hidden">
      <div class="border-b border-line p-5"><h3 class="section-title">연도별 전사 합계</h3>
        <p class="section-help">회색 띠 = «${esc(d.scenarios[0].name)}»의 예측 범위(학습 기간 실적 최소~최대 × 팩터, 표준화 과목만) · 마우스를 올리면 그 해 값</p></div>
      <div class="p-4">${lineChart(d)}</div>
    </article>
    ${d.scenarios.length > 1 ? `<article class="panel overflow-hidden">${heatmap(d)}</article>` : ""}`
}
