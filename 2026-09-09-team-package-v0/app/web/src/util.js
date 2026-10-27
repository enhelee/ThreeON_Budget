export const $ = s => document.querySelector(s);

export const esc = v => String(v ?? "").replace(/[&<>'"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#039;",'"':"&quot;"}[c]));

export const fmt = v => (v === null || v === undefined || isNaN(v)) ? "-" : Math.round(v).toLocaleString("ko-KR");

export const fmtRate = (p, a) => p > 0 ? (a / p * 100).toFixed(1) + "%" : "-";

export const rateVal = (p, a) => p > 0 ? a / p * 100 : null;

// 오늘 날짜(사용자 PC 기준) — "2026-10-27"
export const today = () => {
  const d = new Date();
  const p2 = n => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p2(d.getMonth() + 1)}-${p2(d.getDate())}`;
};

// 메인 머리용 — "2026년 10월 27일 (화)"
export const todayLong = () => {
  const d = new Date();
  return `${d.getFullYear()}년 ${d.getMonth() + 1}월 ${d.getDate()}일 (${"일월화수목금토"[d.getDay()]})`;
};
