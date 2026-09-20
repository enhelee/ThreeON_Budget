// 단일 HTML 빌드: SheetJS + constants + pipeline + UI 를 전부 인라인 → 예산실적정리.html
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";
const __dirname = path.dirname(fileURLToPath(import.meta.url));

const read = (p) => fs.readFileSync(path.join(__dirname, p), "utf8");
const xlsx = read("vendor/xlsx.full.min.js");
const constants = read("src/constants.js");
const corrections = read("src/corrections.js");
const pipeline = read("src/pipeline.js");
const ui = read("src/ui.js");
const css = read("src/ui.css");

const html = `<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>예산 실적 자동 집계 (2025년)</title>
<style>
${css}
</style>
</head>
<body>
<div class="wrap">
  <h1>예산 실적 자동 집계 <span class="badge">2025년 기준</span></h1>
  <p class="sub">ERP raw 데이터 + 예산계획(양식2·양식3)만으로 사업별 실적을 자동 산출합니다. 실적 파일은 필요 없습니다. 모든 처리는 이 브라우저 안에서만 이뤄지며 인터넷·서버 전송이 없습니다.</p>

  <div class="card">
    <h2>1. 파일 올리기</h2>
    <div class="uploads">
      <label class="up"><span class="lbl">ERP raw data <em>(필수)</em></span><input type="file" id="fRaw" accept=".xlsx,.xls"><span class="note">실적의 원천 데이터</span></label>
      <label class="up"><span class="lbl">양식3 · 자본 <b>예산계획</b> <em class="opt">(사업 목록)</em></span><input type="file" id="fCap" accept=".xlsx,.xls"><span class="note">사업 목록·연예산을 여기서 읽어 실적을 채웁니다. <b>실적 칸은 비워두세요</b>(양식3 집계표에서 실적만 지운 것)</span></label>
      <label class="up"><span class="lbl">양식2 · 손익 <b>예산계획</b> <em class="opt">(사업 목록)</em></span><input type="file" id="fPl" accept=".xlsx,.xls"><span class="note">사업 목록·연예산을 여기서 읽어 실적을 채웁니다. <b>실적 칸은 비워두세요</b>(양식2 집계표에서 실적만 지운 것)</span></label>
      <label class="up"><span class="lbl">보정 사전 <em class="opt">(한 번만 올리면 기억됨)</em></span><input type="file" id="fCorr" accept=".xlsx,.xls"><span class="note">담당자가 고친 [지사·과목·전표텍스트→올바른사업명] 표. <b>한 번 올리면 이 브라우저가 기억</b>해서 다음부턴 자동 적용됩니다</span></label>
    </div>
    <div class="corrbar"><span id="corrStatus" class="note"></span> <button id="corrClear" class="ghost" type="button" style="display:none">저장된 보정 지우기</button></div>
    <button id="run" class="primary">집계표 생성</button>
    <div id="msg" class="msg"></div>
  </div>

  <div class="card" id="resultCard" style="display:none">
    <h2>2. 결과</h2>
    <div id="stats" class="stats"></div>
    <div class="downloads">
      <button data-dl="pl">양식2 · 손익 집계표 내려받기</button>
      <button data-dl="cap">양식3 · 자본 집계표 내려받기</button>
      <button data-dl="review" class="ghost">netting 검토표 내려받기</button>
      <button data-dl="checklist" class="ghost">검토목록(보정사전 초안) 내려받기</button>
      <button data-dl="matched">matched_연도.csv 내려받기 (팀 파이프라인 연동)</button>
    </div>
    <p class="hint">※ 계획대비실적: 업로드한 집계표의 <b>사업명 줄은 그대로</b> 두고 <b>실적(B)만</b> raw에서 채웁니다. 계획에 아예 없는 (조직×과목)의 실적은 맨 아래에 <b>(계획미반영)</b> 집계 줄로 표시됩니다.</p>
  </div>

  <footer>단일 파일 · 오프라인 동작 · SheetJS 인라인</footer>
</div>

<script>
${xlsx}
</script>
<script>
${constants}
</script>
<script>
${corrections}
</script>
<script>
${pipeline}
</script>
<script>
${ui}
</script>
</body>
</html>`;

fs.writeFileSync(path.join(__dirname, "예산실적정리.html"), html);
const kb = (Buffer.byteLength(html) / 1024).toFixed(0);
console.log("빌드 완료: 예산실적정리.html (" + kb + " KB)");
