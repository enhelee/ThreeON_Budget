import { state } from "../state.js"
import { esc, fmt } from "../util.js"

// ─────────────────────────────────────────────────────────────
// 5번 탭 «중장기 전망» 한눈에 보기 — 세 단계로 확대해 들어간다(발표 화면처럼).
//
//   ① 10년 지도  행 × 연도 히트맵. 전사 합계면 행 = 지사, 지사를 고르면 행 = 예산과목.
//   ② 연도 구성  고른 해의 예산과목 막대 — 비중·전년 대비.
//   ③ 과목 추이  고른 과목의 10년 막대 — 전사면 지사별 10년 누계도.
//
//   누를 때마다 누른 자리를 기점으로 확대(.fv-zoom-in)·축소(.fv-zoom-out) 애니메이션(custom.css).
//   «발표 모드»는 화면 전체로 띄우고 ←→ 로 연도, ↑ 로 한 단계 위로.
//   금액은 억원(천원 ÷ 100,000)으로 보이고 정확한 천원은 마우스를 올리면 보인다. 아래 상세 표는 천원 그대로.
//   상태는 state.fc.viz, 핸들러는 forecast_actions.js(data-fv*).
// ─────────────────────────────────────────────────────────────

export const FV_LEVELS = ["map", "year", "acct"]
// 크기 = 파랑 한 색 옅음→짙음(dataviz 순차 팔레트 100~700). 0 은 회색.
const SEQ = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
// 기준연도 대비 증감 = 파랑(감소) ↔ 회색 ↔ 빨강(증가). [하한%, 색, 흰 글자]
const CHG = [[-Infinity, "#256abf", true], [-30, "#9ec5f4", false], [-10, "#F0EFEC", false],
             [10, "#F6C1BA", false], [30, "#E8796C", false], [100, "#B42318", true]]
const CHG_LABEL = ["-30% 미만", "-30~-10%", "±10%", "+10~30%", "+30~100%", "+100% 초과"]
const BAR = "#256abf", BAR_SOFT = "#9ec5f4", BAR_HI = "#0d366b"

const eok = v => { const x = v / 1e5; return x === 0 ? "0" : Math.abs(x) >= 100 ? fmt(x) : x.toFixed(1) }
const pct = (a, b) => b > 0 ? (a / b - 1) * 100 : (a > 0 ? Infinity : 0)
const pctTxt = p => !isFinite(p) ? "신규" : `${p >= 0 ? "+" : ""}${p.toFixed(1)}%`
const yv = (r, y) => r[String(y)] || 0
const sum = a => a.reduce((s, v) => s + v, 0)

function seqCell(v, max) {
  if (!v) return {bg: "#F5F5F5", dark: false}
  const i = Math.min(SEQ.length - 1, Math.floor(Math.sqrt(v / max) * SEQ.length))   // 제곱근 눈금 — 작은 지사도 보이게
  return {bg: SEQ[i], dark: i >= 3}
}
function chgCell(p) {
  let c = CHG[0]
  for (const x of CHG) if (p >= x[0]) c = x
  return {bg: c[1], dark: c[2]}
}

/** 지금 범위(전사/지사)의 데이터 묶음 — 행·연도·합계. 메인 화면 전망 패널(home.js)도 쓴다. */
export function fvModel(t, site, isTotal) {
  const years = t.years.map(Number)
  const acctRows = (isTotal ? t.total_rows : (t.tables[site] || []))
    .map(r => ({key: r.예산과목, vals: years.map(y => yv(r, y))}))
    .filter(r => sum(r.vals) > 0)
  acctRows.forEach(r => { r.total = sum(r.vals) })
  acctRows.sort((a, b) => b.total - a.total)
  const mapRows = isTotal
    ? t.sites.map(s => {
        const rs = t.tables[s] || []
        const vals = years.map(y => sum(rs.map(r => yv(r, y))))
        return {key: s, vals, total: sum(vals)}
      }).filter(r => r.total > 0).sort((a, b) => b.total - a.total)
    : acctRows
  const yearTot = years.map((_, i) => sum(acctRows.map(r => r.vals[i])))
  return {years, acctRows, mapRows, yearTot}
}

function stepper(v, m, scope) {
  const steps = [["map", `① 10년 지도 · ${scope}`, true],
                 ["year", `② ${v.year}년 구성`, true],
                 ["acct", `③ ${v.acct || "과목"} 추이`, !!v.acct]]
  return `<nav class="flex flex-wrap items-center gap-1.5" aria-label="확대 단계">${steps.map(([k, l, ok], i) =>
    `${i ? '<span class="text-tri" aria-hidden="true">›</span>' : ""}<button class="fv-step ${v.level === k ? "fv-step-on" : ""}" data-fvlevel="${k}" ${ok ? "" : "disabled"} aria-current="${v.level === k ? "step" : "false"}">${esc(l)}</button>`).join("")}</nav>`
}

function kpis(m, scope) {
  const n = m.years.length, first = m.yearTot[0], last = m.yearTot[n - 1]
  const cagr = first > 0 && n > 1 ? ((last / first) ** (1 / (n - 1)) - 1) * 100 : null
  const peak = m.yearTot.indexOf(Math.max(...m.yearTot))
  const top = m.acctRows[0]
  const tot = sum(m.yearTot)
  const card = (k, val, sub) => `<div class="rounded-control bg-subtle px-4 py-3"><p class="text-xs font-semibold text-sub">${k}</p><p class="mt-1 text-xl font-bold text-ink">${val}</p>${sub ? `<p class="text-xs text-tri">${sub}</p>` : ""}</div>`
  return `<div class="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
    ${card(`${esc(scope)} ${m.years[0]}~${m.years[n - 1]}년 누계`, `${eok(tot)}<span class="ml-1 text-xs font-semibold text-tri">억원</span>`, "")}
    ${card("연평균 증감", cagr === null ? "-" : pctTxt(cagr), `${m.years[0]}년 ${eok(first)}억원 → ${m.years[n - 1]}년 ${eok(last)}억원`)}
    ${card("가장 많은 해", `${m.years[peak]}년`, `${eok(m.yearTot[peak])}억원`)}
    ${card(`${esc(scope)} 가장 큰 과목`, top ? esc(top.key) : "-", top ? `${m.years[0]}~${m.years[n - 1]}년 ${eok(top.total)}억원 · ${(top.total / tot * 100).toFixed(0)}%` : "")}
  </div>`
}

/** 지금 보는 범위 꼬리표 — 전사는 검정, 지사는 브랜드 빨강. 단계 제목 앞에 붙여 «어느 지사의 숫자인지» 늘 보이게. */
const scopeTag = (scope, isTotal, big) => `<span class="fv-tag ${isTotal ? "fv-tag-total" : ""} ${big ? "fv-tag-big" : ""}"><span class="fv-tag-dot" aria-hidden="true"></span>${esc(scope)}</span>`

// ① 10년 지도 ───────────────────────────────────────────────
function mapView(v, m, isTotal, scope) {
  if (!m.mapRows.length) return '<p class="py-10 text-center text-sm text-tri">0 이 아닌 전망이 없습니다.</p>'
  const max = Math.max(...m.mapRows.flatMap(r => r.vals))
  const maxY = Math.max(...m.yearTot)
  const cols = `grid-template-columns:minmax(8rem,12rem) repeat(${m.years.length},minmax(3.6rem,1fr)) 5.5rem`
  // 왼쪽 위 칸 = 위 막대가 무엇의 합계인지(전사 합계 / ○○지사 합계)와 단위
  const corner = `<div class="fv-corner"><span class="fv-corner-k">${isTotal ? "전사 합계" : `${esc(scope)} 합계`}</span><span class="text-[11px] font-semibold text-sub">연도별 →</span></div>`
  const head = `${corner}${m.years.map((y, i) => `<button class="fv-colhead" data-fvlevel="year" data-fvyear="${y}" title="${isTotal ? "전사" : esc(scope)} ${y}년 합계 ${fmt(m.yearTot[i])} 천원 — 눌러서 과목 구성 보기">
      <span class="fv-colbar"><span style="height:${maxY ? m.yearTot[i] / maxY * 100 : 0}%"></span></span>
      <span class="text-[11px] font-semibold text-sub">${eok(m.yearTot[i])}억원</span><span class="text-xs font-bold text-ink">${y}</span></button>`).join("")}
    <div aria-hidden="true"></div>
    <div class="fv-rowcap">${isTotal ? "지사명" : "예산과목"}</div>
    <div class="fv-rowcap fv-totcap">10년 합계 <span class="font-semibold text-sub">(억원)</span></div>`
  const body = m.mapRows.map(r => {
    const base = r.vals[0]
    const label = isTotal
      ? `<button class="fv-rowhead" data-fvsite="${esc(r.key)}" data-fvlevel="map" title="${esc(r.key)} 지도로 확대">${esc(r.key)}</button>`
      : `<button class="fv-rowhead" data-fvlevel="acct" data-fvacct="${esc(r.key)}" title="${esc(r.key)} 10년 추이">${esc(r.key)}</button>`
    const cells = r.vals.map((val, i) => {
      const p = pct(val, base)
      const c = v.mode === "chg" ? chgCell(i === 0 ? 0 : p) : seqCell(val, max)
      const go = isTotal ? `data-fvsite="${esc(r.key)}" data-fvlevel="year" data-fvyear="${m.years[i]}"`
                         : `data-fvlevel="acct" data-fvacct="${esc(r.key)}" data-fvyear="${m.years[i]}"`
      const txt = v.mode === "chg" && i > 0 ? (isFinite(p) ? `${p >= 0 ? "+" : ""}${p.toFixed(0)}%` : "신규") : eok(val)
      return `<button class="fv-cell" ${go} style="background:${c.bg};color:${c.dark ? "#FFFFFF" : "#0D0D0D"}"
        title="${esc(r.key)} · ${m.years[i]}년 · ${fmt(val)} 천원${i ? ` · ${m.years[0]}년 대비 ${pctTxt(p)}` : ""}">${txt}</button>`
    }).join("")
    return `${label}${cells}<div class="self-center pr-1 text-right text-xs font-semibold text-ink">${eok(r.total)}</div>`
  }).join("")
  const legend = v.mode === "chg"
    ? CHG.map((c, i) => `<span class="inline-flex items-center gap-1"><span class="h-3 w-5 rounded-sm" style="background:${c[1]}"></span>${CHG_LABEL[i]}</span>`).join("")
    : `<span>작음</span>${SEQ.map(c => `<span class="h-3 w-5 rounded-sm" style="background:${c}"></span>`).join("")}<span>큼</span><span class="ml-2 inline-flex items-center gap-1"><span class="h-3 w-5 rounded-sm" style="background:#F5F5F5;outline:1px solid #E5E5E5"></span>0</span>`
  return `
    <div class="flex flex-wrap items-center justify-between gap-3">
      <p class="text-sm text-sub">${isTotal ? "지사 · 칸을 누르면 상세 자료로 변경됩니다." : "행 = 예산과목 · 칸이나 과목 이름을 누르면 그 과목의 10년 추이로, 연도를 누르면 그 해 구성으로 확대"}</p>
      <div class="flex gap-1" role="group" aria-label="색 기준">
        <button class="fv-step ${v.mode !== "chg" ? "fv-step-on" : ""}" data-fvmode="amt">금액</button>
        <button class="fv-step ${v.mode === "chg" ? "fv-step-on" : ""}" data-fvmode="chg">${m.years[0]}년 대비 증감</button>
      </div>
    </div>
    <div class="mt-2 overflow-x-auto px-1.5 py-2"><div class="fv-grid" style="${cols};min-width:${12 * 16 + m.years.length * 62 + 90}px">${head}${body}</div></div>
    <div class="mt-3 flex flex-wrap items-center gap-1.5 text-xs text-sub">${legend}</div>`
}

/** 기준연도 값이 어디서 왔는지 — 그 해 계획본이 없으면 표준금액으로 대체된다(forecast 표 notes). */
export function baseYearRule(t) {
  if (t?.notes?.budget_plan_missing) return `기준연도 ${t.base_year} = 표준금액(계획본 없음)`
  return "기준연도 = 계획본 + 본사배분"
}

// ② 연도 구성 ───────────────────────────────────────────────
function yearView(v, m, isTotal, scope) {
  const i = Math.max(0, m.years.indexOf(v.year))
  const rows = m.acctRows.map(r => ({key: r.key, val: r.vals[i], prev: i ? r.vals[i - 1] : null})).filter(r => r.val > 0).sort((a, b) => b.val - a.val)
  const tot = m.yearTot[i], max = rows[0]?.val || 1
  const chips = `<div class="flex flex-wrap gap-1.5" role="group" aria-label="연도">${m.years.map(y => `<button class="fv-chip ${y === v.year ? "fv-chip-on" : ""}" data-fvlevel="year" data-fvyear="${y}">${y}</button>`).join("")}</div>`
  const delta = i ? `<span class="${tot >= m.yearTot[i - 1] ? "text-err" : "text-ok"}">전년 대비 ${pctTxt(pct(tot, m.yearTot[i - 1]))}</span>` : `<span class="text-tri">${esc(baseYearRule(state.fc.table))}</span>`
  return `
    <div class="fv-headline">${scopeTag(scope, isTotal, true)}<h4 class="fv-headline-t">${v.year}년 예산과목 구성</h4></div>
    <div class="mt-3">${chips}</div>
    <div class="mt-5 flex flex-wrap items-baseline gap-x-4 gap-y-1"><p class="font-hanan text-3xl font-semibold text-ink"><span class="text-sub">${esc(scope)} ${v.year}년 합계</span> ${eok(tot)}<span class="ml-1 text-base text-sub">억원</span></p><p class="text-sm font-semibold">${delta}</p><p class="ml-auto text-xs font-semibold text-sub">단위 억원 · 비중 · 전년 대비</p></div>
    <div class="mt-4 space-y-1.5">${rows.length ? rows.map(r => {
      const p = r.prev === null ? null : pct(r.val, r.prev)
      return `<button class="fv-barrow" data-fvlevel="acct" data-fvacct="${esc(r.key)}" title="${esc(r.key)} · ${fmt(r.val)} 천원 — 눌러서 10년 추이">
        <span class="truncate text-left text-sm font-semibold text-ink">${esc(r.key)}</span>
        <span class="fv-bartrack"><span style="width:${r.val / max * 100}%;background:${BAR}"></span></span>
        <span class="text-right text-sm font-bold text-ink">${eok(r.val)}억원</span>
        <span class="text-right text-xs text-sub">${(r.val / tot * 100).toFixed(1)}%</span>
        <span class="text-right text-xs ${p === null ? "text-tri" : p > 0.05 ? "text-err" : p < -0.05 ? "text-ok" : "text-tri"}">${p === null ? "-" : (p > 0.05 ? "▲ " : p < -0.05 ? "▼ " : "") + pctTxt(p)}</span></button>`
    }).join("") : '<p class="py-8 text-center text-sm text-tri">이 해에는 금액이 없습니다.</p>'}</div>
    <p class="mt-3 text-xs text-tri">막대 = 금액 · 오른쪽 = 그 해 비중 · 전년 대비 증감. 과목을 누르면 10년 추이로 확대합니다.</p>`
}

// ③ 과목 추이 ───────────────────────────────────────────────
function acctView(v, m, t, isTotal, scope) {
  const r = m.acctRows.find(x => x.key === v.acct)
  const pick = `<label class="block"><span class="field-label">예산과목</span><select class="control" data-fvacctsel>${m.acctRows.map(x => `<option value="${esc(x.key)}" ${x.key === v.acct ? "selected" : ""}>${esc(x.key)}</option>`).join("")}</select></label>`
  if (!r) return `${pick}<p class="py-8 text-center text-sm text-tri">이 범위에는 그 과목 금액이 없습니다.</p>`
  const n = m.years.length, W = 960, H = 300, L = 12, R = 12, T = 34, B = 40
  const max = Math.max(...r.vals) || 1, bw = (W - L - R) / n
  const sel = m.years.indexOf(v.year), peak = r.vals.indexOf(max)
  const show = new Set([0, n - 1, sel, peak])
  let s = `<text x="${L}" y="12" font-size="12" font-weight="600" fill="#5D5D5D">(단위 억원)</text><line x1="${L}" x2="${W - R}" y1="${H - B}" y2="${H - B}" stroke="#C9C9C9"/>`
  r.vals.forEach((val, i) => {
    const h = val / max * (H - T - B), x = L + i * bw + bw * .18, w = bw * .64, y = H - B - h
    const fill = i === sel ? BAR_HI : i === 0 ? BAR_SOFT : BAR
    s += `<g class="clickable" data-fvlevel="year" data-fvyear="${m.years[i]}"><title>${esc(r.key)} · ${m.years[i]}년 · ${fmt(val)} 천원${i ? ` · 전년 대비 ${pctTxt(pct(val, r.vals[i - 1]))}` : " · 기준연도"} (클릭: 그 해 구성)</title>
      <rect x="${L + i * bw}" y="${T - 20}" width="${bw}" height="${H - T - B + 20}" fill="transparent"/>
      ${h > 0 ? `<path d="M${x},${H - B} V${y + Math.min(4, h)} q0,-4 4,-4 h${w - 8} q4,0 4,4 V${H - B} Z" fill="${fill}"/>` : ""}
      ${show.has(i) ? `<text x="${x + w / 2}" y="${y - 8}" text-anchor="middle" font-size="13" font-weight="700" fill="#0D0D0D">${eok(val)}억원</text>` : ""}
      <text x="${x + w / 2}" y="${H - B + 18}" text-anchor="middle" font-size="12" font-weight="${i === sel ? 700 : 500}" fill="${i === sel ? "#0D0D0D" : "#5D5D5D"}">${m.years[i]}</text>
      ${i === 0 ? `<text x="${x + w / 2}" y="${H - B + 33}" text-anchor="middle" font-size="10" fill="#767676">기준연도</text>` : ""}</g>`
  })
  const first = r.vals[0], last = r.vals[n - 1]
  const cagr = first > 0 ? ((last / first) ** (1 / (n - 1)) - 1) * 100 : null
  let bySite = ""
  if (isTotal) {
    const list = t.sites.map(st => {
      const row = (t.tables[st] || []).find(x => x.예산과목 === r.key)
      return {site: st, total: row ? sum(m.years.map(y => yv(row, y))) : 0}
    }).filter(x => x.total > 0).sort((a, b) => b.total - a.total)
    const top = list.slice(0, 8), rest = list.slice(8), mx = top[0]?.total || 1
    bySite = `<div class="mt-6"><h4 class="text-sm font-bold text-ink">${esc(r.key)} · 지사별 10년 누계 <span class="font-semibold text-sub">(억원) — 누르면 그 지사로 확대</span></h4>
      <div class="mt-2 space-y-1.5">${top.map(x => `<button class="fv-barrow fv-barrow-site" data-fvsite="${esc(x.site)}" data-fvlevel="acct" title="${esc(x.site)} · ${fmt(x.total)} 천원">
        <span class="truncate text-left text-sm font-semibold text-ink">${esc(x.site)}</span><span class="fv-bartrack"><span style="width:${x.total / mx * 100}%;background:${BAR}"></span></span>
        <span class="text-right text-sm font-bold text-ink">${eok(x.total)}억원</span><span class="text-right text-xs text-sub">${(x.total / r.total * 100).toFixed(1)}%</span></button>`).join("")}
      ${rest.length ? `<p class="text-xs text-tri">외 ${rest.length}곳 ${eok(sum(rest.map(x => x.total)))}억원</p>` : ""}</div></div>`
  }
  return `
    <div class="fv-headline">${scopeTag(scope, isTotal, true)}<h4 class="fv-headline-t">${esc(r.key)}</h4><span class="text-sm font-semibold text-sub">10년 추이</span></div>
    <div class="mt-4 flex flex-wrap items-end justify-between gap-3">${pick}
      <div class="flex flex-wrap gap-4 text-sm"><span><span class="text-sub">10년 누계</span> <b class="text-ink">${eok(r.total)}억원</b></span><span><span class="text-sub">연평균</span> <b class="text-ink">${cagr === null ? "-" : pctTxt(cagr)}</b></span><span><span class="text-sub">${esc(scope)} ${m.years[sel] ?? ""}년</span> <b class="text-ink">${eok(r.vals[sel] || 0)}억원</b></span></div></div>
    <div class="mt-4 overflow-x-auto"><svg viewBox="0 0 ${W} ${H}" class="w-full min-w-[560px]" role="img" aria-label="${esc(r.key)} 10년 추이">${s}</svg></div>
    <p class="text-xs text-tri">단위 억원 · 짙은 막대 = 고른 해 · 옅은 막대 = 기준연도(계획본) · 막대를 누르면 그 해 구성으로</p>
    ${bySite}`
}

/** 전망 표 위에 붙는 시각화 패널. t = /api/forecast/table 응답, site = 지사 이름(전사면 isTotal). */
export function fcVizHtml(t, site, isTotal) {
  if (!t?.years?.length) return ""
  const m = fvModel(t, site, isTotal)
  const v = state.fc.viz
  if (!m.years.includes(v.year)) v.year = m.years[Math.min(1, m.years.length - 1)]
  if (v.level === "acct" && !m.acctRows.some(r => r.key === v.acct)) v.acct = m.acctRows[0]?.key || ""
  const scope = isTotal ? "전사" : site
  const group = !isTotal && state.fc.data?.site_groups?.[site]
  const body = v.level === "year" ? yearView(v, m, isTotal, scope) : v.level === "acct" ? acctView(v, m, t, isTotal, scope) : mapView(v, m, isTotal, scope)
  const anim = v.anim ? `fv-${v.anim}` : ""
  return `
  <section class="panel p-5 sm:p-6 ${v.present ? "fv-present" : ""}" id="fvPanel">
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div class="fv-scope ${isTotal ? "fv-scope-total" : ""}">
        <p class="text-xs font-semibold text-sub">한눈에 보기 · 지금 보는 범위</p>
        <p class="fv-scope-name font-hanan">${isTotal ? `전사 합계<span class="fv-scope-sub">${t.sites.length}개 지사</span>` : `${esc(site)}${group ? `<span class="fv-scope-sub">${esc(group)}</span>` : ""}`}</p>
        <p class="text-xs font-semibold text-sub">${m.years[0]}~${m.years[m.years.length - 1]}년 · 단위 <b class="text-ink">억원</b></p>
      </div>
      <div class="flex flex-wrap gap-2">
        ${!isTotal ? `<button class="btn-secondary min-h-[36px] px-4 text-xs" data-fvsite="__total__" data-fvlevel="map">↖ 전사로</button>` : ""}
        <button class="btn-secondary min-h-[36px] px-4 text-xs" data-action="fv-present">${v.present ? "발표 모드 끝내기" : "▶ 발표 모드"}</button>
      </div>
    </div>
    <div class="mt-3">${stepper(v, m, scope)}</div>
    <div class="mt-4">${kpis(m, scope)}</div>
    <div class="fv-stage mt-6 ${anim}" data-fvstage style="--fv-o:${v.origin || "50% 50%"}">${body}</div>
    ${v.present ? '<p class="mt-6 text-center text-xs text-tri">← → 연도 · ↑ 한 단계 위로 · Esc 끝내기</p>' : ""}
  </section>`
}
