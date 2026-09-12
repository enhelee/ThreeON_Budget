import { esc, rateVal } from "../util.js"

export function rateBadge(p, a) {
  const r = rateVal(p, a);
  if (r === null) return '<span class="badge bg-slate-100 text-slate-600">-</span>';
  const cls = r >= 95 ? "bg-blue-50 text-blue-700" : r >= 85 ? "bg-emerald-50 text-emerald-700" : "bg-amber-50 text-amber-700";
  return `<span class="badge ${cls}">${r.toFixed(1)}%</span>`;
}

export function confBadge(c) {
  if (c === null || c === undefined) return '<span class="badge bg-slate-100 text-slate-600">신규</span>';
  const n = Number(c);
  const label = n >= 0.99 ? (n >= 1 ? "수동 1.00" : "학습 0.99") : n.toFixed(2);
  const cls = n >= 0.8 ? "bg-emerald-50 text-emerald-700" : "bg-amber-50 text-amber-700";
  return `<span class="badge ${cls}">${label}</span>`;
}

export function gubunBadge(g) {
  const map = {"계획집행": "bg-blue-50 text-blue-700", "미시행": "bg-slate-100 text-slate-500",
               "신규": "bg-amber-50 text-amber-700", "신규(소액집행)": "bg-amber-50 text-amber-700",
               "미매핑": "bg-slate-100 text-red-600"};
  return `<span class="badge ${map[g] || "bg-slate-100 text-slate-600"}">${esc(g)}</span>`;
}
