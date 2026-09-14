import { navigate } from "./router.js"
import { hideGate, rememberView, showGate } from "./views/gate.js"
import { state } from "./state.js"
import { $ } from "./util.js"

export async function api(path, opts = {}) {
  const res = await fetch(path, opts);
  if (!res.ok) {
    let msg = res.statusText;
    try { msg = (await res.json()).detail || msg; } catch {}
    if (res.status === 401 && msg === "login_required") {
      rememberView(state.view);
      showGate("세션이 없거나 만료되었습니다. 다시 로그인하세요.");
      throw new Error("로그인이 필요합니다.");
    }
    throw new Error(msg);
  }
  return res.json();
}

// ───────────────────────── 인증(공용 비밀번호 + 작업자 이름) ─────────────────────────

export async function checkAuth() {
  const st = await (await fetch("/api/auth/status")).json();
  state.auth = st;
  const badge = $("#operatorBadge"), lo = $("#logoutBtn");
  if (st.enabled) {
    if (!st.logged_in) { showGate(); return false; }
    badge.textContent = `작업자 · ${st.operator}`; badge.classList.remove("hidden"); lo.classList.remove("hidden");
  }
  hideGate();                       // 인증됨 · 또는 인증 자체가 꺼진 사내망 모드
  return true;
}

export async function doLogin() {
  const name = $("#gateName").value.trim(), pw = $("#gatePw").value;
  if (!name) { $("#gateMsg").textContent = "작업자 이름을 입력하세요."; return; }
  try {
    await api("/api/login", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({password: pw, name})});
    try { localStorage.setItem("budget_operator", name); } catch {}
    await checkAuth();              // 여기서 hideGate() 까지 처리된다
    // 401 로 튕기기 전에 보던 화면이 있으면 그리로 돌아간다.
    const back = state.returnView; state.returnView = null;
    await navigate(back || state.view || "home");
  } catch (err) { $("#gateMsg").textContent = err.message; }
}

// ───────────────────────── 데이터 로드 ─────────────────────────
