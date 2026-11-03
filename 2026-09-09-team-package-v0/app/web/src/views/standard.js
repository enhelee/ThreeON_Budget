import { emptyState } from "../components/widgets.js"
import { state } from "../state.js"
import { esc, fmt } from "../util.js"
import { computingHtml, gradeKey, header, restateNote, SAME_GRADES } from "./forecast.js"

// ─────────────────────────────────────────────────────────────
// 5번 — 표준화 한눈에 보기  (#/standard)
//
// 지사 × 정비등급 표준금액을 한 장의 표로. 칸마다 손익 · 자본 · 총액을 한꺼번에 보인다(2026-11-03 팀장).
//   숫자(굵게) = 총액 · 막대 = 손익(파랑) + 자본(회청) 누적, 길이는 가장 큰 칸의 총액 대비 · 아래 작은 숫자 = 손익·자본.
//   자료는 5-1 표준화 세부와 같은 /api/forecast/benchmark(state.fc.bench) — 과목별 줄을 지사·등급으로 더한다.
//   HGPI 와 TI 는 같은 등급이라 한 칸(HGPI/TI)으로 묶는다(forecast.js SAME_GRADES). 서버 계산이 이미
//   TI 를 HGPI 로 합쳐 내지만, 혹시 두 이름이 다 오면(옛 결과) 더하지 않고 평균을 낸다(칸 설명에 적는다).
//   칸을 누르면 그 지사·등급으로 거른 5-1 세부 표로 간다(forecast_actions.js data-stdcell).
//
//   단위: 자료는 천원, 칸에는 백만원으로 줄여 적는다(칸이 좁아서). 마우스를 올리면 천원 그대로.
// ─────────────────────────────────────────────────────────────

// 메인 화면과 같은 확정 팔레트(custom.css --chart-*): 손익 파랑 · 자본 회청
const COLOR = {손익: "var(--chart-profit)", 자본: "var(--chart-capital)"}
const GROUPS = ["중대형CHP", "소형CHP", "DH", "본사"]
// 가스터빈 등급(큰 정비 → 작은 정비) 다음 스팀터빈 A·B·C, 등급 이력이 없으면 «표준»
// (BSI 는 일시적 등급이라 서버가 표준금액을 만들지 않는다 — forecast_calc.DROP_GRADES)
const GRADE_ORDER = ["MI", "HGPI/TI", "CI", "간이", "A", "B", "C", "표준", "정비제외"]

function gradeRank(g) {
  if (GRADE_ORDER.includes(g)) return GRADE_ORDER.indexOf(g)
  const tok = String(g).split(/[^0-9A-Za-z가-힣]+/).find(Boolean) || ""
  const i = GRADE_ORDER.indexOf(gradeKey(tok))
  return i < 0 ? GRADE_ORDER.length : i
}

const mil = v => fmt(v / 1000)          // 천원 → 백만원

/** bench.rows → {sites, grades, cell: {"지사|등급": {손익, 자본, 총액, n, names}}, max}
 *  등급은 묶은 이름(HGPI/TI). 한 칸에 원래 이름이 둘 이상이면 이름별 합의 평균. max = 가장 큰 칸의 총액. */
export function stdMatrix(rows, siteGroups = {}) {
  const byName = {}, gradeSet = new Set(), siteSet = new Set()
  for (const r of rows) {
    const g = gradeKey(r.등급)
    const k = `${r.사업장}|${g}`
    const names = byName[k] || (byName[k] = {})
    const c = names[r.등급] || (names[r.등급] = {손익: 0, 자본: 0, n: 0})
    const v = Number(r.표준금액 || 0)
    if (r.구분 === "자본") c.자본 += v; else c.손익 += v
    c.n += 1
    gradeSet.add(g); siteSet.add(r.사업장)
  }
  const cell = {}
  for (const [k, names] of Object.entries(byName)) {
    const list = Object.values(names), d = list.length
    const 손익 = list.reduce((s, c) => s + c.손익, 0) / d, 자본 = list.reduce((s, c) => s + c.자본, 0) / d
    cell[k] = {손익, 자본, 총액: 손익 + 자본, n: Math.max(...list.map(c => c.n)), names: Object.keys(names)}
  }
  const grades = [...gradeSet].sort((a, b) => gradeRank(a) - gradeRank(b) || String(a).localeCompare(String(b)))
  const gi = s => { const i = GROUPS.indexOf(siteGroups[s]); return i < 0 ? GROUPS.length : i }
  const sites = [...siteSet].sort((a, b) => gi(a) - gi(b))   // 안정 정렬 — 그룹 안에서는 서버 순서 그대로
  const max = Math.max(0, ...Object.values(cell).map(c => c.총액))
  return {sites, grades, cell, max}
}

const chip = kind => `<i class="std-chip" style="background:${COLOR[kind]}" aria-hidden="true"></i>`

function legend() {
  return `<div class="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-sub">
    <span><b class="text-ink">굵은 숫자</b> = 총액</span>
    <span>${chip("손익")}손익</span><span>${chip("자본")}자본</span>
    <span>막대 길이 = 총액(가장 큰 칸 대비)</span><span>단위 백만원</span></div>`
}

/** 칸 하나 — 총액 숫자 · 손익+자본 누적 막대 · 손익·자본 숫자. 음수·0 조각은 막대에서 뺀다. */
function cellHtml(site, grade, c, max) {
  const 손 = Math.max(0, c.손익), 자 = Math.max(0, c.자본)
  const w = max > 0 && 손 + 자 > 0 ? Math.max(4, Math.round(100 * (손 + 자) / max)) : 0
  const avg = c.names.length > 1 ? `\n(${c.names.join("·")} 두 이름이 있어 평균)` : ""
  const tip = `${site} · ${grade}\n총액 ${fmt(c.총액)} 천원\n손익 ${fmt(c.손익)} 천원\n자본 ${fmt(c.자본)} 천원\n과목 ${c.n}개${avg} — 눌러서 세부 보기`
  const bar = w ? `<span class="std-bar" style="width:${w}%">${손 ? `<i style="flex:${손};background:${COLOR.손익}"></i>` : ""}${자 ? `<i style="flex:${자};background:${COLOR.자본}"></i>` : ""}</span>` : ""
  return `<td class="std-cell"><button type="button" data-stdcell="${esc(`${site}|${grade}`)}" title="${esc(tip)}" aria-label="${esc(tip.replace(/\n/g, ", "))}">
    <span class="std-tot">${mil(c.총액)}</span>${bar}
    <span class="std-sub">${chip("손익")}${mil(c.손익)}<span class="std-sep"></span>${chip("자본")}${mil(c.자본)}</span></button></td>`
}

/** 지사 이름 옆 작은 딱지(수원 «2029년 준공 후 중대형CHP 편입 예정») — /api/forecast/benchmark site_notes */
export const siteTag = (site, notes) => notes?.[site] ? `<span class="std-tag" title="${esc(notes[site])}">${esc(notes[site])}</span>` : ""

function table(m, siteGroups, notes) {
  let lastGroup = null
  const body = m.sites.map(site => {
    const g = siteGroups[site] || "기타"
    const groupRow = g !== lastGroup
      ? `<tr><th class="std-group" colspan="${m.grades.length + 1}" scope="colgroup">${esc(g)}</th></tr>` : ""
    lastGroup = g
    const cells = m.grades.map(grade => {
      const c = m.cell[`${site}|${grade}`]
      return c ? cellHtml(site, grade, c, m.max) : `<td class="std-cell std-cell--none" aria-label="${esc(site)} ${esc(grade)} 없음">·</td>`
    }).join("")
    return `${groupRow}<tr><th class="std-site" scope="row">${esc(site)}${siteTag(site, notes)}</th>${cells}</tr>`
  }).join("")
  return `<div class="overflow-x-auto"><table class="std-heat">
    <thead><tr><th class="std-site" scope="col">지사 / 정비등급</th>${m.grades.map(g => `<th scope="col">${esc(g)}</th>`).join("")}</tr></thead>
    <tbody>${body}</tbody></table></div>`
}

function stdBody() {
  const b = state.fc.bench
  if (!b) return state.fc.benchLoading ? computingHtml("표준화 결과를 계산하는 중… 처음 계산은 시간이 걸려요") : emptyState("표준화 결과를 불러오지 못했습니다.")
  if (!b.rows.length) return emptyState("아직 표준금액이 없습니다 — 실적을 분석·마감하거나 «중장기 예측 › 기준정보»에서 표준화 참고 엑셀을 가져오세요.")
  const siteGroups = state.fc.data?.site_groups || {}
  const m = stdMatrix(b.rows, siteGroups)
  const used = (b.years_used || []).map(String)
  const closed = used.filter(y => !y.endsWith("(참고)"))
  const ref = used.filter(y => y.endsWith("(참고)")).map(y => parseInt(y, 10)).sort((x, y) => x - y)
  const basis = `마감 연도 ${closed.join("·") || "없음"}${ref.length ? ` · 참고 실적 ${ref[0]}${ref.length > 1 ? `~${ref[ref.length - 1]}` : ""}` : ""}`
  const same = Object.entries(SAME_GRADES).map(([k, list]) => `${list.join("·")} 는 같은 등급(${k})`).join(" · ")
  return `
  <article class="panel overflow-hidden">
    <div class="border-b border-line p-5 sm:p-6">
      <h3 class="section-title">지사 × 정비등급 표준금액 · 손익 · 자본 · 총액</h3>
      <p class="section-help">${esc(basis)}${restateNote(b) ? ` · <b class="text-ink">${esc(restateNote(b))}</b>` : ""} · 지사 ${m.sites.length}곳 · 정비등급 ${m.grades.length}종 · 칸 = 그 지사가 그 등급인 해의 과목 표준금액 합 · ${esc(same)} · 칸을 누르면 «표준화 세부»</p>
      <div class="mt-3">${legend()}</div>
    </div>
    ${table(m, siteGroups, b.site_notes)}
  </article>`
}

export function renderStandard() {
  return `
  <div class="space-y-6">
    ${header({stage: "STAGE 5", title: "표준화 — 정비등급별 표준금액", tabs: false})}
    ${stdBody()}
  </div>`
}
