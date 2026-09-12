import { $ } from "../util.js"

export function toast(msg) {
  const t = $("#toast");
  t.textContent = msg; t.classList.remove("hidden");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => t.classList.add("hidden"), 4500);
}

export function busy(on, text) {
  $("#busyText").textContent = text || "처리 중...";
  $("#busy").classList.toggle("hidden", !on);
  $("#busy").classList.toggle("grid", on);
}
