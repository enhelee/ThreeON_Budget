// 가짜 데이터로 parseBudget/netting/matchToBudget 단위 검증 (실데이터 불필요)
import { createRequire } from "module";
const require = createRequire(import.meta.url);
const P = require("../src/pipeline.js");
const C = require("../src/constants.js");

let pass = 0, fail = 0;
const ok = (cond, msg) => { if (cond) { pass++; } else { fail++; console.log("  ❌", msg); } };

// ── parseBudget: 25년 레이아웃(본부·중점전략 있음) ──
const B25 = [
  ["※ 유의사항"],
  [],
  ["주관부서명", "예산귀속 부서코드", "본부", "예산귀속 부서명(처.지사)", "예산귀속 부서명(부)", "속성", "예산코드", "예산과목", "기준", "중점전략", "사업명", "산출내역", "연예산 합계"],
  ["플랜트기술처", "3040001", "본부", "용인지사", "용인지사 고객지원부", "제조", "60909009", "수선유지비-열원보완및개선", "기준", "", "노후 전동밸브 개체", "", 800],
  ["플랜트기술처", "3040001", "본부", "용인지사", "용인지사 고객지원부", "제조", "60909009", "수선유지비-열원보완및개선", "기준", "", "노후 진동감시설비 개체", "", 500],
];
const b25 = P.parseBudget(B25);
ok(b25.length === 2, "25년 레이아웃 2줄 파싱 (실제: " + b25.length + ")");
ok(b25[0].acct === "60909009" && b25[0].dept === "3040001", "25년 예산코드/부서코드 추출");
ok(b25[0].biz === "노후 전동밸브 개체" && b25[0].annual === 800, "25년 사업명/연예산 추출");

// ── parseBudget: 26년 레이아웃(본부·중점전략 없음) ──
const B26 = [
  ["※ 유의사항"],
  [],
  ["주관부서명", "예산귀속 부서코드", "예산귀속 부서명(처.지사)", "예산귀속 부서명(부)", "속성", "예산코드", "예산과목", "사업명", "산출내역", "연예산 합계"],
  ["플랜트기술처", "3040001", "용인지사", "용인지사 고객지원부", "제조", "60909009", "수선유지비-열원보완및개선", "노후 전동밸브 개체", "", 800],
];
const b26 = P.parseBudget(B26);
ok(b26.length === 1 && b26[0].acct === "60909009" && b26[0].annual === 800, "26년 레이아웃도 동일 추출 (헤더 기반)");

// ── matchToBudget: 매칭/신규/실적없음 ──
// 가짜 netting 결과 (dept 3040001, acct 60909009)
const cleaned = [
  { dept: "3040001", acct: "60909009", acctName: "수선유지비-열원보완및개선", ledger: "손익", bucket: "boan", deptName: "용인지사", text: "노후 전동밸브 개체", amount: 800, n: 2, docNos: [] },
  { dept: "3040001", acct: "60909009", acctName: "수선유지비-열원보완및개선", ledger: "손익", bucket: "boan", deptName: "용인지사", text: "계획에 없던 새 사업", amount: 300, n: 1, docNos: [] },
];
const { rows, stats } = P.matchToBudget(cleaned, b25, C);
const matched = rows.find((r) => r.biz === "노후 전동밸브 개체");
const shingyu = rows.find((r) => r.biz === "계획에 없던 새 사업");
const noAct = rows.find((r) => r.biz === "노후 진동감시설비 개체");
ok(matched && matched.actual === 800 && matched.flag === "매칭", "완전일치 사업 → 실적 800 매칭");
ok(shingyu && shingyu.actual === 300 && shingyu.flag === "신규", "예산에 없는 실적 → 신규 300");
ok(noAct && noAct.actual === 0 && noAct.flag === "실적없음", "실적 없는 예산 사업 → 0");

// ── 경상정비: 지사당 1줄 통합 ──
const gRaw = [
  ["h", "b", "c", "d", "e", "f", "g", "t", "i", "j", "k", "l", "m", "n", "o", "p"], // header
  ["제조", "60909007", "수선유지비-열원경상정비", "", "", "D1", 100, "정비A", "용인", "", "", "", "", "", "", "3040001"],
  ["제조", "60909007", "수선유지비-열원경상정비", "", "", "D2", 200, "정비B", "용인", "", "", "", "", "", "", "3040001"],
];
const gClean = P.netting(P.parseRaw(gRaw));
ok(gClean.length === 1 && gClean[0].amount === 300, "경상정비 지사당 1줄 통합 (실제: " + gClean.length + "줄, " + (gClean[0] && gClean[0].amount) + ")");

// ── netting 상계: 같은 전표 합0 제거 ──
const nRaw = [
  ["h", "b", "c", "d", "e", "f", "g", "t", "i", "j", "k", "l", "m", "n", "o", "p"],
  ["제조", "60909008", "수선유지비-열원정기유지보수", "", "", "D9", 500, "사업X", "용인", "", "", "", "", "", "", "3040001"],
  ["제조", "60909008", "수선유지비-열원정기유지보수", "", "", "D9", -500, "사업X 역인식", "용인", "", "", "", "", "", "", "3040001"],
];
const nClean = P.netting(P.parseRaw(nRaw));
ok(nClean.length === 0, "같은 전표 합0 → 상계 제거 (실제 남은: " + nClean.length + ")");

// ── 종합표 격자: 칸 배치 / 소계 / 합계 ──
const jClean = [
  { dept: "3040001", acct: "60909009", ledger: "손익", amount: 100 }, // 용인지사(DH)
  { dept: "2020001", acct: "60909009", ledger: "손익", amount: 50 },  // 강남지사(소형CHP)
  { dept: "3050001", acct: "20704001", ledger: "자본", amount: 200 }, // 화성지사(중대형CHP)
];
const jPl = P.buildJonghapAOA(jClean, "손익", C);
const nameRow = jPl[1];
const colIdx = (nm) => nameRow.indexOf(nm);
const rowByName = (aoa, nm) => aoa.find((r) => r[1] === nm);
const rBoan = rowByName(jPl, "수선유지비-열원보완개선및기타");
ok(rBoan[colIdx("용인지사")] === 100, "종합표: 용인지사 칸 = 100");
ok(rBoan[colIdx("강남지사")] === 50, "종합표: 강남지사 칸 = 50");
const totIdx = jPl[0].indexOf("합계");
ok(rBoan[totIdx] === 150, "종합표: 보완개선 행 합계 = 150 (실제: " + rBoan[totIdx] + ")");
// DH 소계 = 100, 소형CHP 소계 = 50
const dhSub = jPl[0].indexOf("DH 소계");
ok(rBoan[dhSub] === 100, "종합표: DH 소계 = 100");
const plTot = rowByName(jPl, "");  // "계" subtotal row (gu="")
// 손익예산 계 (total)
const rGrand = jPl.find((r) => r[0] === "손익예산 계");
ok(rGrand[totIdx] === 150, "종합표: 손익예산 계 합계 = 150");

const jCap = P.buildJonghapAOA(jClean, "자본", C);
const rGigye = rowByName(jCap, "기계장치");
const capNameRow = jCap[1];
ok(rGigye[capNameRow.indexOf("화성지사")] === 200, "종합표(자본): 화성지사 기계장치 = 200");
ok(jCap.find((r) => r[0] === "자본예산 합계")[jCap[0].indexOf("합계")] === 200, "종합표(자본): 자본예산 합계 = 200");
// 건물·구축물 행이 존재하는지 (누락됐던 것)
ok(rowByName(jCap, "건물") && rowByName(jCap, "구축물"), "종합표(자본): 건물·구축물 행 포함");

console.log(`\n단위 테스트: ${pass} 통과 / ${fail} 실패`);
process.exit(fail ? 1 : 0);
