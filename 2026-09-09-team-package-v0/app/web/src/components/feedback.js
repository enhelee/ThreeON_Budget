import { $ } from "../util.js"
import { CHAR_IMG } from "./char_images.js"

export function toast(msg) {
  const t = $("#toast");
  t.textContent = msg; t.classList.remove("hidden");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => t.classList.add("hidden"), 4500);
}

// 로딩(4단계, 2026-10-28 가안): 온도계 수은이 차오르는 카드 + 그 일을 맡은 캐릭터 얼굴. 문구로 담당을 고른다.
const BUSY_WHO = [[/전망|백테스트|가정|산출|표준금액/, "yc"], [/검토|대조|차이/, "gt"]]
export function busy(on, text) {
  const msg = text || "처리 중...";
  $("#busyText").textContent = msg;
  const who = (BUSY_WHO.find(([re]) => re.test(msg)) || [, "mt"])[1];
  $("#busyChar").src = CHAR_IMG[who].head;
  $("#busy").classList.toggle("hidden", !on);
  $("#busy").classList.toggle("grid", on);
}
