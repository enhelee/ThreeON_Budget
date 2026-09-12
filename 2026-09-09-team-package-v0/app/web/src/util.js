export const $ = s => document.querySelector(s);

export const esc = v => String(v ?? "").replace(/[&<>'"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#039;",'"':"&quot;"}[c]));

export const fmt = v => (v === null || v === undefined || isNaN(v)) ? "-" : Math.round(v).toLocaleString("ko-KR");

export const fmtRate = (p, a) => p > 0 ? (a / p * 100).toFixed(1) + "%" : "-";

export const rateVal = (p, a) => p > 0 ? a / p * 100 : null;
