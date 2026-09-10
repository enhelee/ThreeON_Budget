// 단일 HTML 빌드: SheetJS + constants + pipeline + UI 를 전부 인라인 → 예산실적정리.html
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";
const __dirname = path.dirname(fileURLToPath(import.meta.url));

const read = (p) => fs.readFileSync(path.join(__dirname, p), "utf8");
const xlsx = read("vendor/xlsx.full.min.js");
const constants = read("src/constants.js");
const pipeline = read("src/pipeline.js");
const reconcile = read("src/reconcile.js");
const corrections = read("src/corrections.js");
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
  <p class="sub">ERP raw 데이터를 예산과 대조해 실적 집계표(양식2·양식3)를 자동으로 채워 내려받습니다. 모든 처리는 이 브라우저 안에서만 이뤄지며 인터넷·서버 전송이 없습니다.</p>

  <div class="card">
    <h2>1. 파일 올리기</h2>
    <div class="uploads">
      <label class="up"><span class="lbl">ERP raw data <em>(필수)</em></span><input type="file" id="fRaw" accept=".xlsx,.xls"><span class="note">실적의 원천 데이터</span></label>
      <label class="up"><span class="lbl">양식3 · 자본예산 실적 집계표 <em class="opt">(최종 실적금액 포함)</em></span><input type="file" id="fCap" accept=".xlsx,.xls"><span class="note">이 파일의 종합표 틀·계획을 그대로 읽어 실적을 채웁니다</span></label>
      <label class="up"><span class="lbl">양식2 · 손익예산 실적 집계표 <em class="opt">(최종 실적금액 포함)</em></span><input type="file" id="fPl" accept=".xlsx,.xls"><span class="note">이 파일의 종합표 틀·계획을 그대로 읽어 실적을 채웁니다</span></label>
      <label class="up"><span class="lbl">보정 사전 <em class="opt">(선택)</em></span><input type="file" id="fCorr" accept=".xlsx,.xls"><span class="note">이전에 담당자가 고친 [지사·과목·전표텍스트→올바른사업명] 표. 있으면 자동 적용</span></label>
    </div>
    <label class="up">로컬 보정 JSON (선택)<input type="file" id="fPrivate" accept=".json"></label>
    <label><input type="checkbox" id="matchFinalActual" checked> 실적집계표의 최종 실적금액으로 대조·합산하기</label>
    <p><label><input type="checkbox" id="builtinCorrections" checked> 로컬에서 불러온 보정 JSON 적용</label></p>
    <p class="hint">보정사전을 먼저 적용하고 같은 지사·예산과목에서 최종 실적금액을 대조합니다. 예비품·저장품·고온부품은 같은 지사·과목·전기일의 양수와 음수를 먼저 합산합니다. 날짜가 다르면 합치지 않으며 전기일이 없으면 검토로 남깁니다. 기성·역인식은 계약별 순액으로 합산하며, 기계·전기·제어의 통합계약은 확인된 보정 범위에서만 함께 반영합니다. 보정의 사업명과 금액이 맞지 않으면 검토로 남깁니다. 보정의 금액차이·제외 사유는 보정 반영내역에서 확인할 수 있습니다. 다른 연도 검증 시 기본 보정을 끌 수 있습니다.</p>
    <button id="run" class="primary">집계표 생성</button>
    <div id="msg" class="msg"></div>
  </div>

  <div class="card" id="resultCard" style="display:none">
    <h2>2. 결과</h2><button id="exportJson">팀 점검용 결과 JSON 다운로드</button>
    <div id="stats" class="stats"></div>
    <div class="downloads">
      <button data-dl="pl">양식2 · 손익 집계표 내려받기</button>
      <button data-dl="cap">양식3 · 자본 집계표 내려받기</button>
      <button data-dl="amount" class="ghost">금액 일치·묶음 내역 내려받기</button>
      <button data-dl="spares" class="ghost">예비품 전기일별 합산 내려받기</button>
      <button data-dl="corrections" class="ghost">보정 반영·제외 내역 내려받기</button>
      <button data-dl="review" class="ghost">netting 검토표 내려받기</button>
      <button data-dl="checklist" class="ghost">검토목록(보정사전 초안) 내려받기</button>
    </div>
    <p class="hint">※ 계획대비실적: 업로드한 집계표의 <b>사업명 줄은 그대로</b> 두고 <b>실적(B)만</b> raw에서 채웁니다. 금액 대조에서 일치하지 않은 전표는 맨 아래에 <b>(미배분·검토)</b>로 남고, 여러 사업을 묶은 근거는 금액 일치·묶음 내역에서 확인할 수 있습니다.</p>
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
${reconcile}
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
