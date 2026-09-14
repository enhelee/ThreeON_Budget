import { state } from "../state.js"
import { esc } from "../util.js"

// ─────────────────────────────────────────────────────────────
// 5번 탭 — 중장기 전망 (#/forecast)
//
// 전망은 아직 별도 앱(Streamlit, 팀공유 v2)이 담당한다. 그것을 같은 화면 안에
// iframe 으로 끌어와 «주소 하나 · 로그인 한 번»을 완성한다.
//
//   - 대상 주소는 서버가 정한다(FORECAST_URL → /healthz). 배포에서는 같은
//     호스트의 /forecast 이므로 상대경로이고, 로컬 개발에서는 :8501 절대경로다.
//   - ?embed=true 로 Streamlit 자체 툴바·푸터·메뉴를 숨긴다.
//   - /forecast 접근 허용은 Caddy forward_auth 가 /api/auth/verify 로 확인한다.
//     즉 이 앱에 로그인돼 있으면 iframe 도 그대로 열린다(기본인증 팝업 없음).
//
// 세션이 끊긴 경우 iframe 안에 401 화면이 그려지는데, 그걸 그대로 두면 사용자는
// 무슨 일인지 알 수 없다. 그래서 여기서 먼저 확인해 안내로 바꾼다 —
// 다만 확인에 api() 를 쓰지 않는다. api() 는 401 을 만나면 게이트를 띄우므로,
// iframe 하나 때문에 작업공간 전체가 로그인 화면으로 튕겨 나가게 된다.
//
// Phase 6 에서 전망 기능을 이 앱으로 흡수하면 이 파일의 iframe 은 사라진다.
// ─────────────────────────────────────────────────────────────

const LOAD_TIMEOUT_MS = 15000        // Streamlit 첫 기동이 느릴 수 있어 넉넉히 잡는다

/** iframe 이 가리킬 주소 — 서버가 준 FORECAST_URL 에 embed 플래그를 붙인다.
 *
 * ⚠ 경로는 반드시 «/» 로 끝나야 한다.
 *   슬래시가 없으면 Streamlit 이 307 로 «/forecast/» 로 되돌려 보내는데, 그 Location 이
 *   상대경로가 아니라 Host 헤더로 만든 **절대 URL** 이고 스킴이 http 다(전망 앱은 앞단에서
 *   TLS 가 끝났다는 사실을 모른다). https 로 열린 우리 화면에서 그 주소를 따라가려 하면
 *   혼합 콘텐츠로 차단되어 iframe 도 fetch 도 함께 실패한다.
 *
 *   실측(2026-09-15 배포): 5번 탭은 "연결하지 못했습니다" 인데, 같은 앱을 새 탭에서
 *   «/forecast/?embed=true» 로 열면 정상 표시됐다 — 차이는 슬래시 하나뿐이었다.
 *   로컬에서도 «/forecast?embed=true» 가 307 Location: http://…/forecast/?embed=true 였다.
 */
export function forecastUrl() {
  const raw = state.health?.forecast_url || "/forecast"
  const [path, query] = raw.split("?")
  const base = path.endsWith("/") ? path : path + "/"
  return base + "?" + (query ? query + "&embed=true" : "embed=true")
}

function notice(title, body, {tone = "warn"} = {}) {
  const ring = tone === "warn" ? "border-amber-300 bg-amber-50" : "border-slate-300 bg-slate-50"
  const head = tone === "warn" ? "text-amber-900" : "text-slate-800"
  return `
    <div class="rounded-2xl border ${ring} px-6 py-8 text-center">
      <p class="font-bold ${head}">${esc(title)}</p>
      <p class="mx-auto mt-2 max-w-30 text-sm leading-6 text-slate-600">${esc(body)}</p>
      <a class="btn-secondary mt-5 inline-flex" href="${forecastUrl()}" target="_blank" rel="noopener">새 탭에서 전망 앱 열기</a>
    </div>`
}

export function renderForecast() {
  return `
  <div class="space-y-6">
    <section class="flex flex-col gap-3 xl:flex-row xl:items-end xl:justify-between">
      <div>
        <p class="text-sm font-semibold text-blue-700">STAGE 04</p>
        <h2 class="mt-1 text-2xl font-bold tracking-tight text-slate-950">중장기 예산 전망</h2>
        <p class="section-help max-w-30 leading-6">예산 표준화(3단계)와 2026~2035년 중장기 예산(4단계)입니다. 「통계·내보내기 → 팀 연계 → 결과 JSON」을 이 앱의 «예산 실적 집계 → 사업 실적 연결»에 올리면 검토가 끝난 매칭 실적이 입력으로 이어집니다.</p>
      </div>
      <a class="btn-secondary shrink-0" href="${forecastUrl()}" target="_blank" rel="noopener">새 탭에서 열기</a>
    </section>

    <article id="forecastPanel" class="panel overflow-hidden">
      <div id="forecastWrap" class="relative w-full" style="height:calc(100vh - 17rem);min-height:34rem">
        <iframe id="forecastFrame" src="${forecastUrl()}" title="중장기 예산 전망"
                class="h-full w-full border-0" referrerpolicy="same-origin"></iframe>
        <div id="forecastOverlay" class="absolute inset-0 grid place-items-center bg-white">
          <div class="text-center">
            <div class="spinner mx-auto"></div>
            <p class="mt-3 text-sm font-semibold text-slate-700">전망 앱을 불러오는 중…</p>
            <p class="mt-1 text-xs text-slate-500">첫 기동은 수 초 걸릴 수 있습니다.</p>
          </div>
        </div>
      </div>
    </article>
  </div>`
}

/** 화면을 그린 뒤 iframe 의 성패를 지켜본다. router.renderPage() 가 부른다. */
export function mountForecast() {
  const panel = document.getElementById("forecastPanel")
  const frame = document.getElementById("forecastFrame")
  const overlay = document.getElementById("forecastOverlay")
  if (!panel || !frame) return

  let settled = false
  const ok = () => { settled = true; if (overlay) overlay.remove() }
  const fail = (title, body, tone) => {
    if (settled) return
    settled = true
    panel.outerHTML = notice(title, body, {tone})
  }

  // ⚠ load 이벤트는 성공의 근거가 못 된다.
  //   서버가 죽어 있어도 브라우저는 자기 오류 페이지를 iframe 에 싣고 load 를 쏜다.
  //   (실측: 전망 앱을 내린 채로 열어도 load 가 발생해 빈 흰 화면만 남았다.)
  //   그래서 load 는 «로딩 오버레이를 걷는» 용도로만 쓰고, 성패는 아래에서 따로 판정한다.
  frame.addEventListener("load", () => { if (overlay) overlay.remove() })

  // 응답이 아주 없는 경우(연결은 되는데 회신이 없는 경우)의 최후 보루.
  setTimeout(() => fail(
    "전망 앱을 불러오지 못했습니다",
    "전망 앱이 기동 중이거나 응답하지 않습니다. 잠시 뒤 다시 시도하거나 새 탭에서 열어 확인하세요.",
  ), LOAD_TIMEOUT_MS)

  // 주소를 직접 두드려 성패를 가른다.
  //   배포: 같은 출처(/forecast)라 상태코드를 그대로 읽는다 — 401 이면 세션 만료.
  //   로컬: :8501 은 교차 출처라 상태코드를 읽을 수 없다. no-cors 로 «도달 여부»만 본다
  //         (죽어 있으면 reject, 살아 있으면 opaque 응답).
  const target = forecastUrl()
  const crossOrigin = /^https?:\/\//i.test(target) && !target.startsWith(location.origin)
  fetch(target, crossOrigin ? {mode: "no-cors", cache: "no-store"} : {cache: "no-store"})
    .then(res => {
      if (res.type === "opaque") { ok(); return }        // 교차 출처 — 도달 확인까지가 한계
      if (res.status === 401 || res.status === 403) {
        fail("로그인 세션이 만료되었습니다",
             "전망 앱은 이 앱의 로그인 세션으로 열립니다. 다른 화면으로 이동하면 로그인 창이 나타납니다.")
      } else if (!res.ok) {
        fail("전망 앱을 불러오지 못했습니다",
             `전망 앱이 ${res.status} 로 응답했습니다. 잠시 뒤 다시 시도하거나 새 탭에서 열어 확인하세요.`)
      } else {
        ok()
      }
    })
    .catch(() => fail(
      "전망 앱에 연결하지 못했습니다",
      "전망 앱이 내려가 있거나 기동 중입니다. 잠시 뒤 다시 시도하거나 새 탭에서 열어 확인하세요."))

  // 세션이 끊긴 것을 더 빨리, 두 환경 모두에서 알아채기 위한 확인.
  // ⚠ api() 가 아니라 fetch — api() 는 401 에서 게이트를 띄우므로 화면 전체가 튕긴다.
  fetch("/api/auth/status")
    .then(r => r.json())
    .then(st => {
      if (st.enabled && !st.logged_in) {
        fail("로그인 세션이 만료되었습니다",
             "전망 앱은 이 앱의 로그인 세션으로 열립니다. 다른 화면으로 이동하면 로그인 창이 나타납니다.")
      }
    })
    .catch(() => {})            // 상태 조회 실패는 위의 판정에 맡긴다
}
