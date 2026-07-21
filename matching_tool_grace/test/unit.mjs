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

// ── 유사도 매칭: 전표헤더텍스트 ↔ 사업명 (글자 조금 달라도 매칭) ──
const budFuzzy = [
  { dept: "2020001", acct: "60909002", acctName: "수선유지비-열원정기점검", ledger: "손익",
    biz: "2025년 강남지사 열병합발전시설 정기점검 보수공사(기계_일원)", annual: 534633,
    hqDept: "", deptName: "강남지사", teamName: "", attr: "제조" },
  { dept: "2020001", acct: "60909002", acctName: "수선유지비-열원정기점검", ledger: "손익",
    biz: "2025년 강남지사 동남권 열공급시설 정기점검 보수공사(기계분야)", annual: 297000,
    hqDept: "", deptName: "강남지사", teamName: "", attr: "제조" },
];
const cleanFuzzy = [
  // 전표 표기(연도·괄호·띄어쓰기 다름) → 1번 사업에 붙어야
  { dept: "2020001", acct: "60909002", acctName: "수선유지비-열원정기점검", ledger: "손익", bucket: "common", deptName: "강남", text: "강남 열병합발전시설 정기점검 보수공사 기계 일원", amount: 538881, n: 3, docNos: [] },
  // 전혀 다른 건 → 신규
  { dept: "2020001", acct: "60909002", acctName: "수선유지비-열원정기점검", ledger: "손익", bucket: "common", deptName: "강남", text: "옥상 방수 도장 공사", amount: 9999, n: 1, docNos: [] },
];
const rF = P.matchToBudget(cleanFuzzy, budFuzzy, C).rows;
const m1 = rF.find((r) => r.biz.includes("열병합발전시설 정기점검"));
ok(m1 && m1.actual === 538881 && m1.flag === "매칭", "유사도: 열병합 정기점검 전표 → 해당 사업 매칭 (실제: " + (m1 && m1.actual) + "/" + (m1 && m1.flag) + ")");
const m2 = rF.find((r) => r.biz.includes("동남권 열공급시설"));
ok(m2 && m2.actual === 0 && m2.flag === "실적없음", "유사도: 실적 없는 사업 → 0/실적없음");
const mNew = rF.find((r) => r.biz === "옥상 방수 도장 공사");
ok(mNew && mNew.flag === "신규", "유사도: 무관한 전표 → 신규");
// 유사도 함수 스모크
ok(P.diceSim("정기점검 보수공사", "정기점검보수공사") > 0.8, "diceSim: 띄어쓰기만 다르면 높은 유사도");
ok(P.diceSim("터보냉동기 유지보수", "옥상 방수 도장") < 0.2, "diceSim: 무관 텍스트 낮은 유사도");

// ── fillJonghap: 파일의 분류를 그대로 따르는지 (양산을 중대형에 둔 틀) ──
const jongTmpl = [
  ["구분", "예산과목", "", "", "중대형CHP", "", "합계"],
  ["", "", "동탄지사", "양산지사", "소계", "수원사업소", "합계"],
  ["자산", "기계장치", 0, 0, 0, 0, 0],
  ["자본예산 합계", "", 0, 0, 0, 0, 0],
];
const jClean2 = [
  { dept: "3100001", acct: "20704001", ledger: "자본", amount: 100 }, // 동탄
  { dept: "4020001", acct: "20704001", ledger: "자본", amount: 300 }, // 양산
  { dept: "3030001", acct: "20704001", ledger: "자본", amount: 20 },  // 수원
];
const filledJ = P.fillJonghap(jongTmpl, jClean2, "자본", C);
const gigyeRow = filledJ.find((r) => r[1] === "기계장치");
ok(gigyeRow[2] === 100 && gigyeRow[3] === 300, "fillJonghap: 동탄100·양산300 각 칸");
ok(gigyeRow[4] === 400, "fillJonghap: 첫 소계 = 동탄+양산 = 400 (양산이 파일상 중대형이므로 함께 합산)");
ok(gigyeRow[6] === 420, "fillJonghap: 합계 = 420");
const capTotRow = filledJ.find((r) => r[0] === "자본예산 합계");
ok(capTotRow[6] === 420, "fillJonghap: 자본예산 합계 행 = 420");

// ── parseChipPlan + matchPlanToActual: 집계표 계획을 읽어 실적 채움 ──
const chipAOA = [
  ["연번", "예산과목", "속성", "주관부서명", "예산귀속 부서명(처.지사)", "예산귀속 부서명(팀)", "사업명", "연예산(A)", "최종 실적금액(B)"],
  ["예시)", "수선유지비-건물/구축물", "", "", "", "", "미반영 신규사업의 경우 행추가", 0, ""],
  [1, "수선유지비-열원경상정비", "제조", "플랜트", "강남지사", "강남 고객지원부", "경상정비 A", 900, ""],
  [2, "수선유지비-열원보완개선및기타", "제조", "플랜트", "강남지사", "강남 고객지원부", "노후 전동밸브 개체", 500, ""],
];
const planParsed = P.parseChipPlan(chipAOA, C);
ok(planParsed.length === 2, "parseChipPlan: 예시행 제외 2줄 (실제: " + planParsed.length + ")");
ok(planParsed[0].acct === "60909007" && planParsed[0].deptName === "강남지사", "parseChipPlan: 과목명→코드, 지사명 인식");
const clA = [
  { dept: "2020001", acct: "60909007", ledger: "손익", amount: 1000, text: "경상정비 통합", bucket: "gyeongsang" },
  { dept: "2020001", acct: "60909009", ledger: "손익", amount: 500, text: "노후 전동밸브 개체 보수", bucket: "boan" },
];
const mp = P.matchPlanToActual(clA, planParsed, C);
const rG = mp.rows.find((r) => r.biz === "경상정비 A");
ok(rG && rG.actual === 1000 && rG.flag === "매칭", "matchPlanToActual: 경상정비 지사통합 실적 → 계획 줄에 (실제: " + (rG && rG.actual) + ")");
const rB = mp.rows.find((r) => r.biz === "노후 전동밸브 개체");
ok(rB && rB.actual === 500 && rB.flag === "매칭", "matchPlanToActual: 유사 사업명 실적 매칭");

console.log(`\n단위 테스트: ${pass} 통과 / ${fail} 실패`);
process.exit(fail ? 1 : 0);
