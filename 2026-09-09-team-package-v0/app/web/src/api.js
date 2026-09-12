import { navigate } from "./router.js"
import { state } from "./state.js"
import { $ } from "./util.js"

export async function api(path, opts = {}) {
  const res = await fetch(path, opts);
  if (!res.ok) {
    let msg = res.statusText;
    try { msg = (await res.json()).detail || msg; } catch {}
    if (res.status === 401 && msg === "login_required") {
      showLogin("세션이 없거나 만료되었습니다. 다시 로그인하세요.");
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
    if (!st.logged_in) { showLogin(); return false; }
    badge.textContent = `작업자 · ${st.operator}`; badge.classList.remove("hidden"); lo.classList.remove("hidden");
  }
  return true;
}

export function showLogin(msg) {
  $("#loginOverlay").classList.remove("hidden");
  $("#loginMsg").textContent = msg || "";
  try { const saved = localStorage.getItem("budget_operator"); if (saved && !$("#loginName").value) $("#loginName").value = saved; } catch {}
  setTimeout(() => ($("#loginName").value ? $("#loginPw") : $("#loginName")).focus(), 50);
}

export async function doLogin() {
  const name = $("#loginName").value.trim(), pw = $("#loginPw").value;
  if (!name) { $("#loginMsg").textContent = "작업자 이름을 입력하세요."; return; }
  try {
    await api("/api/login", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({password: pw, name})});
    $("#loginOverlay").classList.add("hidden"); $("#loginPw").value = "";
    try { localStorage.setItem("budget_operator", name); } catch {}
    await checkAuth();
    await navigate(state.view || "home");
  } catch (err) { $("#loginMsg").textContent = err.message; }
}

// ───────────────────────── 데이터 로드 ─────────────────────────
