import { esc, rateVal } from "../util.js"

// 상태 배지 — 색은 «의미»만 전한다(한난 토큰: info·ok·warn·err, 중립은 subtle/sub).
// 브랜드 빨강(--brand)은 여기서 쓰지 않는다 — 오류(err, 적갈)와 섞이면 뜻이 흐려진다.

export function rateBadge(p, a) {
  const r = rateVal(p, a);
  if (r === null) return '<span class="badge bg-subtle text-sub">-</span>';
  // 80~120% 정상 · 80% 미만 미달 · 120% 초과 초과 — 차이 사유(±20%p) 기준과 같은 선(2026-10-26 사용자 결정)
  const cls = r > 120 ? "bg-err-bg text-err" : r >= 80 ? "bg-ok-bg text-ok" : "bg-warn-bg text-warn";
  return `<span class="badge ${cls}">${r.toFixed(1)}%</span>`;
}

export function confBadge(c) {
  if (c === null || c === undefined) return '<span class="badge bg-subtle text-sub">신규</span>';
  const n = Number(c);
  const label = n >= 0.99 ? (n >= 1 ? "수동 1.00" : "학습 0.99") : n.toFixed(2);
  const cls = n >= 0.8 ? "bg-ok-bg text-ok" : "bg-warn-bg text-warn";
  return `<span class="badge ${cls}">${label}</span>`;
}

export function gubunBadge(g) {
  const map = {"계획집행": "bg-info-bg text-info", "미시행": "bg-subtle text-sub",
               "신규": "bg-warn-bg text-warn", "신규(소액집행)": "bg-warn-bg text-warn",
               "미매핑": "bg-err-bg text-err"};
  return `<span class="badge ${map[g] || "bg-subtle text-sub"}">${esc(g)}</span>`;
}
