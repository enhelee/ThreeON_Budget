# HTML/JS 단일 파일 전환 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 현재 Streamlit(Python) 기반 예산 분석 앱을, 인터넷/설치 없이 브라우저에서 더블클릭만으로 동작하는 단일 `index.html` 파일로 전환한다.

**Architecture:** 순수 로직(연도 현황 계산, 검증 규칙, 키워드 분류, 나이브베이즈 분류기, 저장소)은 Node.js의 내장 테스트 러너(`node --test`)로 TDD하며 브라우저와 Node 양쪽에서 동작하는 UMD 스타일 모듈(`web/src/*.js`)로 작성한다. UI 계층(`web/src/ui.js`)은 DOM을 직접 다루므로 브라우저에서 수동으로 검증한다. `build.js`가 템플릿 + 벤더 라이브러리(SheetJS) + 내장 데이터 + 모든 소스 파일을 하나의 `<script>`로 이어붙여 최종 `index.html`을 만든다.

**Tech Stack:** 순수 JavaScript(ES2017+), Node.js 내장 `node:test`/`node:assert`, SheetJS(xlsx.mini.min.js, 벤더링), localStorage. 빌드 도구·번들러·npm 의존성 없음.

## Global Constraints

- 최종 산출물은 프로젝트 루트의 `index.html` 파일 하나이며, 실행 시 외부 네트워크 요청을 전혀 만들지 않는다(폐쇄망 요건).
- 어떤 단계에서도 `npm install`이 필요하지 않다 (Node 내장 테스트 러너만 사용).
- 기존 Python 파일(`app.py`, `classify.py` 등)은 참고용으로 그대로 둔다. 새 웹앱 코드는 `web/`, `scripts/`, `build.js`, 최종 산출물 `index.html`에만 위치한다.
- 저장소의 `data_2016.csv`, `classified_2016.csv`, `training_data.csv`, `year_status.json`은 해커톤용 샘플/더미 데이터로 확인되었으므로 그대로 커밋·내장(embed)해도 된다.
- 화면 문구는 기존 Streamlit 앱(`app.py`)의 한국어 문구를 최대한 그대로 재사용한다.
- 로컬 저장 키는 `budget_app_state_v1` 하나로 통일한다.

---

## Task 1: CSV 파서/직렬화 모듈

**Files:**
- Create: `web/src/csv.js`
- Test: `web/test/csv.test.js`

**Interfaces:**
- Produces: `Csv.parseCsv(text: string) -> Array<Object>` (첫 줄을 헤더로 사용), `Csv.toCsv(rows: Array<Object>, columns?: string[]) -> string`

- [ ] **Step 1: 디렉터리 생성 및 실패하는 테스트 작성**

```bash
mkdir -p web/src web/test
```

`web/test/csv.test.js`:
```js
const test = require('node:test');
const assert = require('node:assert/strict');
const Csv = require('../src/csv.js');

test('parseCsv parses simple rows into objects keyed by header', () => {
  const text = 'text,label\n노후 설비,노후설비개체\n정기점검 공사,정기사업\n';
  const rows = Csv.parseCsv(text);
  assert.deepEqual(rows, [
    { text: '노후 설비', label: '노후설비개체' },
    { text: '정기점검 공사', label: '정기사업' },
  ]);
});

test('parseCsv handles quoted fields containing commas', () => {
  const text = 'text,label\n"보강, 개선 공사",운영안정성 제고\n';
  const rows = Csv.parseCsv(text);
  assert.deepEqual(rows, [{ text: '보강, 개선 공사', label: '운영안정성 제고' }]);
});

test('toCsv quotes fields that contain commas', () => {
  const csv = Csv.toCsv([{ text: '보강, 개선', label: 'x' }], ['text', 'label']);
  assert.equal(csv, 'text,label\n"보강, 개선",x');
});

test('toCsv and parseCsv round-trip', () => {
  const rows = [{ text: 'a,b', label: 'L1' }, { text: 'c"d', label: 'L2' }];
  const csv = Csv.toCsv(rows, ['text', 'label']);
  const parsed = Csv.parseCsv(csv);
  assert.deepEqual(parsed, rows);
});
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `node --test web/test/csv.test.js`
Expected: FAIL — `Cannot find module '../src/csv.js'`

- [ ] **Step 3: 구현 작성**

`web/src/csv.js`:
```js
(function (global) {
  function parseCsv(text) {
    const rows = [];
    let row = [];
    let field = '';
    let inQuotes = false;
    const pushField = () => { row.push(field); field = ''; };
    const pushRow = () => { rows.push(row); row = []; };

    for (let i = 0; i < text.length; i++) {
      const c = text[i];
      if (inQuotes) {
        if (c === '"') {
          if (text[i + 1] === '"') { field += '"'; i++; }
          else { inQuotes = false; }
        } else {
          field += c;
        }
      } else if (c === '"') {
        inQuotes = true;
      } else if (c === ',') {
        pushField();
      } else if (c === '\n') {
        pushField(); pushRow();
      } else if (c === '\r') {
        // ignore, \n follows
      } else {
        field += c;
      }
    }
    if (field.length > 0 || row.length > 0) { pushField(); pushRow(); }
    if (rows.length > 0 && rows[rows.length - 1].length === 1 && rows[rows.length - 1][0] === '') {
      rows.pop();
    }

    if (rows.length === 0) return [];
    const header = rows[0];
    return rows.slice(1).map((r) => {
      const obj = {};
      header.forEach((h, idx) => { obj[h] = r[idx] === undefined ? '' : r[idx]; });
      return obj;
    });
  }

  function csvField(value) {
    const s = value === undefined || value === null ? '' : String(value);
    if (/[",\n]/.test(s)) {
      return '"' + s.replace(/"/g, '""') + '"';
    }
    return s;
  }

  function toCsv(rows, columns) {
    if (rows.length === 0 && !columns) return '';
    const cols = columns || Object.keys(rows[0]);
    const lines = [cols.join(',')];
    for (const row of rows) {
      lines.push(cols.map((c) => csvField(row[c])).join(','));
    }
    return lines.join('\n');
  }

  const api = { parseCsv, toCsv };
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  } else {
    global.Csv = api;
  }
})(typeof window !== 'undefined' ? window : globalThis);
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `node --test web/test/csv.test.js`
Expected: PASS (4 tests)

- [ ] **Step 5: 커밋**

```bash
git add web/src/csv.js web/test/csv.test.js
git commit -m "feat(web): add CSV parse/stringify module"
```

---

## Task 2: 연도별 현황판 로직 (`year_status.py` 포팅)

**Files:**
- Create: `web/src/yearStatus.js`
- Test: `web/test/yearStatus.test.js`

**Interfaces:**
- Produces: `YearStatus.addYear(status, year) -> status`, `YearStatus.setYearResult(status, year, rowCount, errorCount, errors) -> status`, `YearStatus.getVisibleCells(status, visibleRecent=4) -> Array<Cell>`, `YearStatus.nextAddableYear(status) -> number`, `YearStatus.prevAddableYear(status) -> number`
  - `Cell` = `{type:'group', label, years}` 또는 `{type:'year', year, state: 'done'|'warning'|'empty'}`

- [ ] **Step 1: 실패하는 테스트 작성**

`web/test/yearStatus.test.js`:
```js
const test = require('node:test');
const assert = require('node:assert/strict');
const YearStatus = require('../src/yearStatus.js');

test('addYear adds a new empty year if missing', () => {
  const result = YearStatus.addYear({}, 2016);
  assert.deepEqual(result, { '2016': { uploaded: false, error_count: 0, row_count: 0 } });
});

test('addYear does not overwrite an existing year', () => {
  const status = { '2016': { uploaded: true, row_count: 5, error_count: 0 } };
  const result = YearStatus.addYear(status, 2016);
  assert.deepEqual(result, status);
});

test('setYearResult stores upload results', () => {
  const errors = [{ row: 2, level: 'warning', type: '연도 불일치', detail: 'x' }];
  const result = YearStatus.setYearResult({}, 2016, 10, 1, errors);
  assert.deepEqual(result['2016'], { uploaded: true, row_count: 10, error_count: 1, errors });
});

test('getVisibleCells returns empty array for empty status', () => {
  assert.deepEqual(YearStatus.getVisibleCells({}), []);
});

test('getVisibleCells groups years older than the recent window', () => {
  const status = {};
  for (let y = 2016; y <= 2022; y++) {
    status[String(y)] = { uploaded: y % 2 === 0, error_count: y === 2020 ? 1 : 0, row_count: 1 };
  }
  const cells = YearStatus.getVisibleCells(status, 4);
  assert.equal(cells[0].type, 'group');
  assert.deepEqual(cells[0].years, [2016, 2017, 2018]);
  assert.equal(cells.length, 5);
  assert.deepEqual(cells.slice(1).map((c) => c.year), [2019, 2020, 2021, 2022]);
});

test('getVisibleCells marks state done/warning/empty correctly', () => {
  const status = {
    '2022': { uploaded: false, error_count: 0, row_count: 0 },
    '2023': { uploaded: true, error_count: 2, row_count: 5 },
    '2024': { uploaded: true, error_count: 0, row_count: 5 },
  };
  const cells = YearStatus.getVisibleCells(status, 4);
  const states = Object.fromEntries(cells.map((c) => [c.year, c.state]));
  assert.equal(states[2022], 'empty');
  assert.equal(states[2023], 'warning');
  assert.equal(states[2024], 'done');
});

test('nextAddableYear defaults to 2016 when empty, else max+1', () => {
  assert.equal(YearStatus.nextAddableYear({}), 2016);
  assert.equal(YearStatus.nextAddableYear({ '2016': {}, '2019': {} }), 2020);
});

test('prevAddableYear defaults to 2016 when empty, else min-1', () => {
  assert.equal(YearStatus.prevAddableYear({}), 2016);
  assert.equal(YearStatus.prevAddableYear({ '2016': {}, '2019': {} }), 2015);
});
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `node --test web/test/yearStatus.test.js`
Expected: FAIL — module not found

- [ ] **Step 3: 구현 작성**

`web/src/yearStatus.js`:
```js
(function (global) {
  function addYear(status, year) {
    const key = String(year);
    const next = Object.assign({}, status);
    if (!(key in next)) {
      next[key] = { uploaded: false, error_count: 0, row_count: 0 };
    }
    return next;
  }

  function setYearResult(status, year, rowCount, errorCount, errors) {
    const key = String(year);
    const next = Object.assign({}, status);
    next[key] = { uploaded: true, row_count: rowCount, error_count: errorCount, errors: errors };
    return next;
  }

  function getVisibleCells(status, visibleRecent) {
    visibleRecent = visibleRecent === undefined ? 4 : visibleRecent;
    const years = Object.keys(status).map(Number).sort((a, b) => a - b);
    if (years.length === 0) return [];

    const recentYears = years.slice(Math.max(0, years.length - visibleRecent));
    const oldYears = years.slice(0, Math.max(0, years.length - visibleRecent));

    const cells = [];
    if (oldYears.length > 0) {
      cells.push({ type: 'group', label: `${oldYears[0]}~${oldYears[oldYears.length - 1]}`, years: oldYears });
    }

    for (const y of recentYears) {
      const info = status[String(y)];
      let state;
      if (!info.uploaded) state = 'empty';
      else if ((info.error_count || 0) > 0) state = 'warning';
      else state = 'done';
      cells.push({ type: 'year', year: y, state });
    }

    return cells;
  }

  function nextAddableYear(status) {
    const keys = Object.keys(status);
    if (keys.length === 0) return 2016;
    return Math.max(...keys.map(Number)) + 1;
  }

  function prevAddableYear(status) {
    const keys = Object.keys(status);
    if (keys.length === 0) return 2016;
    return Math.min(...keys.map(Number)) - 1;
  }

  const api = { addYear, setYearResult, getVisibleCells, nextAddableYear, prevAddableYear };
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  } else {
    global.YearStatus = api;
  }
})(typeof window !== 'undefined' ? window : globalThis);
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `node --test web/test/yearStatus.test.js`
Expected: PASS (8 tests)

- [ ] **Step 5: 커밋**

```bash
git add web/src/yearStatus.js web/test/yearStatus.test.js
git commit -m "feat(web): port year status board logic to JS"
```

---

## Task 3: 키워드 규칙 분류기 (`classify.py` 포팅)

**Files:**
- Create: `web/src/classify.js`
- Test: `web/test/classify.test.js`

**Interfaces:**
- Produces: `Classify.KEYWORD_RULES: Object<label, string[]>`, `Classify.classifyWithConfidence(text) -> {label, confidence, matches}`, `Classify.classifyRows(rows, textCol='전표헤더텍스트') -> rows with 예측유형/확신도, sorted ascending by 확신도`

- [ ] **Step 1: 실패하는 테스트 작성**

`web/test/classify.test.js`:
```js
const test = require('node:test');
const assert = require('node:assert/strict');
const Classify = require('../src/classify.js');

test('classifyWithConfidence returns 미분류 when no keyword matches', () => {
  const result = Classify.classifyWithConfidence('알 수 없는 내용');
  assert.equal(result.label, '미분류');
  assert.equal(result.confidence, 0.0);
});

test('classifyWithConfidence gives high confidence for a single matching type', () => {
  const result = Classify.classifyWithConfidence('노후 변압기 개체 공사');
  assert.equal(result.label, '노후설비개체');
  assert.equal(result.confidence, 0.8);
});

test('classifyWithConfidence lowers confidence when keywords overlap types', () => {
  const result = Classify.classifyWithConfidence('노후 설비 신뢰도 개선 보강 공사');
  assert.equal(result.label, '운영안정성 제고');
  assert.equal(result.matches['노후설비개체'], 1);
  assert.equal(result.matches['운영안정성 제고'], 2);
  assert.equal(result.confidence, 0.57);
});

test('classifyRows adds prediction columns and sorts by confidence ascending', () => {
  const rows = [
    { 전표헤더텍스트: '노후 변압기 개체 공사' },
    { 전표헤더텍스트: '알 수 없는 내용' },
  ];
  const out = Classify.classifyRows(rows);
  assert.equal(out[0].예측유형, '미분류');
  assert.equal(out[1].예측유형, '노후설비개체');
});
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `node --test web/test/classify.test.js`
Expected: FAIL — module not found

- [ ] **Step 3: 구현 작성**

`web/src/classify.js`:
```js
(function (global) {
  const KEYWORD_RULES = {
    'LTSA': ['LTSA', 'OEM', '장기서비스'],
    '정기사업': ['정기점검', '정기보수', '계획예방정비', 'TA'],
    '노후설비개체': ['노후'],
    'AX/DX': ['자동화', '스마트', 'AI', 'DCS', '디지털'],
    '운영안정성 제고': ['신뢰도', '안정화', '보강', '예비설비'],
    '환경강화': ['탈황', '집진', '대기오염', '환경'],
    '교육강화': ['교육', '역량강화', '워크숍'],
    '보안강화': ['CCTV', '출입통제', '사이버보안', '방호'],
  };

  function round2(n) {
    return Math.round(n * 100) / 100;
  }

  function classifyWithConfidence(text) {
    text = String(text == null ? '' : text);
    const matches = {};
    for (const label of Object.keys(KEYWORD_RULES)) {
      let count = 0;
      for (const kw of KEYWORD_RULES[label]) {
        if (text.includes(kw)) count += 1;
      }
      if (count > 0) matches[label] = count;
    }

    const labels = Object.keys(matches);
    if (labels.length === 0) {
      return { label: '미분류', confidence: 0.0, matches: {} };
    }

    const total = labels.reduce((sum, l) => sum + matches[l], 0);
    let bestLabel = labels[0];
    for (const l of labels) {
      if (matches[l] > matches[bestLabel]) bestLabel = l;
    }
    const bestCount = matches[bestLabel];

    let confidence;
    if (labels.length === 1) {
      confidence = Math.min(0.95, 0.7 + 0.1 * bestCount);
    } else {
      confidence = round2(bestCount / total) * 0.85;
    }

    return { label: bestLabel, confidence: round2(confidence), matches };
  }

  function classifyRows(rows, textCol) {
    textCol = textCol || '전표헤더텍스트';
    const out = rows.map((row) => {
      const { label, confidence } = classifyWithConfidence(row[textCol]);
      return Object.assign({}, row, { 예측유형: label, 확신도: confidence });
    });
    out.sort((a, b) => a.확신도 - b.확신도);
    return out;
  }

  const api = { KEYWORD_RULES, classifyWithConfidence, classifyRows };
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  } else {
    global.Classify = api;
  }
})(typeof window !== 'undefined' ? window : globalThis);
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `node --test web/test/classify.test.js`
Expected: PASS (4 tests)

- [ ] **Step 5: 커밋**

```bash
git add web/src/classify.js web/test/classify.test.js
git commit -m "feat(web): port keyword-rule classifier to JS"
```

---

## Task 4: 업로드 검증 로직 (`validate_upload.py` 포팅)

**Files:**
- Create: `web/src/validateUpload.js`
- Test: `web/test/validateUpload.test.js`

**Interfaces:**
- Consumes: 없음 (독립 모듈)
- Produces: `ValidateUpload.COL_IDX`, `ValidateUpload.parseExcelDate(value) -> Date|null`, `ValidateUpload.validateUpload(rows: Array<Array>, year: number) -> {row_count, valid_row_count, critical_count, warning_count, error_count, errors, data}`
  - `rows`는 헤더 행이 제거된, 0-based 컬럼 인덱스를 갖는 배열의 배열 (SheetJS `sheet_to_json(ws, {header:1})` 결과에서 첫 행만 잘라낸 형태)

- [ ] **Step 1: 실패하는 테스트 작성**

`web/test/validateUpload.test.js`:
```js
const test = require('node:test');
const assert = require('node:assert/strict');
const { validateUpload, parseExcelDate } = require('../src/validateUpload.js');

function makeRow({ vendor = '거래처A', site = 1, date = '2016-03-01', text = '정기점검 공사', amount = 1000 } = {}) {
  const row = [];
  row[4] = vendor;
  row[6] = site;
  row[11] = date;
  row[13] = text;
  row[14] = amount;
  return row;
}

test('parseExcelDate parses ISO date strings (UTC-anchored)', () => {
  const d = parseExcelDate('2016-03-01');
  assert.equal(d.getUTCFullYear(), 2016);
});

test('parseExcelDate returns null for unparseable text', () => {
  assert.equal(parseExcelDate('이건 날짜 아님'), null);
});

test('parseExcelDate converts excel serial numbers', () => {
  const d = parseExcelDate(42461); // 2016-04-01
  assert.equal(d.getUTCFullYear(), 2016);
  assert.equal(d.getUTCMonth(), 3);
});

test('validateUpload flags missing amount as critical and skips the row', () => {
  const result = validateUpload([makeRow({ amount: '' })], 2016);
  assert.equal(result.error_count, 1);
  assert.equal(result.critical_count, 1);
  assert.equal(result.valid_row_count, 0);
  assert.equal(result.errors[0].type, '금액 없음');
});

test('validateUpload flags unparseable date as critical and skips the row', () => {
  const result = validateUpload([makeRow({ date: '이상한값' })], 2016);
  assert.equal(result.critical_count, 1);
  assert.equal(result.errors[0].type, '날짜 형식 오류');
});

test('validateUpload warns on unregistered site code but keeps the row', () => {
  const result = validateUpload([makeRow({ site: 9 })], 2016);
  assert.equal(result.warning_count, 1);
  assert.equal(result.valid_row_count, 1);
  assert.equal(result.errors[0].type, '사업장 코드 이상');
});

test('validateUpload warns when the date year does not match the selected year', () => {
  const result = validateUpload([makeRow({ date: '2018-01-01' })], 2016);
  assert.equal(result.warning_count, 1);
  assert.equal(result.errors[0].type, '연도 불일치');
  assert.equal(result.errors[0].detail, '선택연도 2016, 실제 2018');
});

test('validateUpload accepts a fully valid row with no errors', () => {
  const result = validateUpload([makeRow({})], 2016);
  assert.equal(result.error_count, 0);
  assert.equal(result.valid_row_count, 1);
  assert.equal(result.data[0].거래처명, '거래처A');
});
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `node --test web/test/validateUpload.test.js`
Expected: FAIL — module not found

- [ ] **Step 3: 구현 작성**

`web/src/validateUpload.js`:
```js
(function (global) {
  const COL_IDX = { 거래처명: 4, 사업장: 6, 전기일: 11, 전표헤더텍스트: 13, 금액: 14 };
  const VALID_SITE_CODES = new Set([1, 2, 3, 4, 5]);

  function isEmpty(v) {
    return v === null || v === undefined || v === '';
  }

  // 날짜 관련 값은 항상 UTC 기준으로 다룬다: 엑셀 시리얼 변환과 'YYYY-MM-DD' 문자열 파싱이
  // 모두 UTC 자정을 기준으로 하므로, 로컬 타임존에 따라 날짜가 하루 밀리는 것을 방지한다.
  function parseExcelDate(value) {
    if (value instanceof Date) {
      return isNaN(value.getTime()) ? null : value;
    }
    if (typeof value === 'number') {
      const ms = Math.round((value - 25569) * 86400 * 1000);
      const d = new Date(ms);
      return isNaN(d.getTime()) ? null : d;
    }
    if (typeof value === 'string' && value.trim() !== '') {
      const d = new Date(value.trim());
      return isNaN(d.getTime()) ? null : d;
    }
    return null;
  }

  function validateUpload(rows, year) {
    const errors = [];
    const parsedRows = [];

    rows.forEach((row, i) => {
      const excelRowNo = i + 2;
      const amt = row[COL_IDX.금액];
      const site = row[COL_IDX.사업장];
      const dateVal = row[COL_IDX.전기일];
      const text = row[COL_IDX.전표헤더텍스트];
      const vendor = row[COL_IDX.거래처명];

      if (isEmpty(amt)) {
        errors.push({ row: excelRowNo, level: 'critical', type: '금액 없음', detail: 'O열 값이 비어있음' });
        return;
      }

      const parsedDate = parseExcelDate(dateVal);
      if (parsedDate === null) {
        errors.push({ row: excelRowNo, level: 'critical', type: '날짜 형식 오류', detail: `L열 '${dateVal}'` });
        return;
      }

      if (!isEmpty(site) && !VALID_SITE_CODES.has(Number(site))) {
        errors.push({ row: excelRowNo, level: 'warning', type: '사업장 코드 이상', detail: `G열 값 '${Number(site)}' (미등록 코드)` });
      }

      if (parsedDate.getUTCFullYear() !== year) {
        errors.push({ row: excelRowNo, level: 'warning', type: '연도 불일치', detail: `선택연도 ${year}, 실제 ${parsedDate.getUTCFullYear()}` });
      }

      parsedRows.push({ 거래처명: vendor, 사업장: site, 전기일: parsedDate, 전표헤더텍스트: text, 금액: amt });
    });

    const criticalCount = errors.filter((e) => e.level === 'critical').length;
    const warningCount = errors.filter((e) => e.level === 'warning').length;

    return {
      row_count: rows.length,
      valid_row_count: parsedRows.length,
      critical_count: criticalCount,
      warning_count: warningCount,
      error_count: criticalCount + warningCount,
      errors,
      data: parsedRows,
    };
  }

  const api = { COL_IDX, VALID_SITE_CODES, parseExcelDate, validateUpload };
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  } else {
    global.ValidateUpload = api;
  }
})(typeof window !== 'undefined' ? window : globalThis);
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `node --test web/test/validateUpload.test.js`
Expected: PASS (8 tests)

- [ ] **Step 5: 커밋**

```bash
git add web/src/validateUpload.js web/test/validateUpload.test.js
git commit -m "feat(web): port upload validation rules to JS"
```

---

## Task 5: 나이브베이즈 분류기 + 학습 데이터 관리 (`ml_classifier.py` 대체)

**Files:**
- Create: `web/src/mlClassifier.js`
- Test: `web/test/mlClassifier.test.js`

**Interfaces:**
- Produces:
  - `MlClassifier.MIN_SAMPLES_TO_TRAIN = 20`, `MlClassifier.MIN_CLASSES_TO_TRAIN = 2`
  - `MlClassifier.extractNgrams(text) -> string[]`
  - `MlClassifier.train(examples: {text,label}[]) -> Model`
  - `MlClassifier.predict(model: Model|null, text) -> {label, confidence}`
  - `MlClassifier.crossValidate(examples, folds) -> number|null`
  - `MlClassifier.trainingSummary(examples) -> {count, per_class}`
  - `MlClassifier.canTrain(examples) -> boolean`
  - `MlClassifier.computeCvFolds(examples) -> number`

- [ ] **Step 1: 실패하는 테스트 작성**

`web/test/mlClassifier.test.js`:
```js
const test = require('node:test');
const assert = require('node:assert/strict');
const MlClassifier = require('../src/mlClassifier.js');

const EXAMPLES = [
  { text: '노후 변압기 개체 공사', label: '노후설비개체' },
  { text: '노후 배관 개체 공사', label: '노후설비개체' },
  { text: '노후 케이블 개체 공사', label: '노후설비개체' },
  { text: '정기점검 정비공사', label: '정기사업' },
  { text: '계획예방정비 수행', label: '정기사업' },
  { text: '정기보수 작업 실시', label: '정기사업' },
];

test('extractNgrams produces character n-grams sized 2 to 4', () => {
  assert.deepEqual(MlClassifier.extractNgrams('노후'), ['노후']);
});

test('train builds per-class ngram statistics', () => {
  const model = MlClassifier.train(EXAMPLES);
  assert.deepEqual(model.classes.slice().sort(), ['노후설비개체', '정기사업']);
  assert.equal(model.totalDocs, 6);
  assert.equal(model.docCountByClass['노후설비개체'], 3);
});

test('predict classifies a clear example correctly', () => {
  const model = MlClassifier.train(EXAMPLES);
  const result = MlClassifier.predict(model, '노후 밸브 개체 공사');
  assert.equal(result.label, '노후설비개체');
  assert.ok(result.confidence > 0.5);
});

test('predict returns 미분류 with zero confidence when no model exists', () => {
  const result = MlClassifier.predict(null, '아무 텍스트');
  assert.equal(result.label, '미분류');
  assert.equal(result.confidence, 0);
});

test('crossValidate returns an accuracy between 0 and 1 for separable data', () => {
  const acc = MlClassifier.crossValidate(EXAMPLES, 3);
  assert.ok(acc >= 0 && acc <= 1);
});

test('crossValidate returns null when there is not enough data for the requested folds', () => {
  assert.equal(MlClassifier.crossValidate(EXAMPLES.slice(0, 2), 5), null);
});

test('trainingSummary counts examples per label', () => {
  const summary = MlClassifier.trainingSummary(EXAMPLES);
  assert.equal(summary.count, 6);
  assert.equal(summary.per_class['노후설비개체'], 3);
  assert.equal(summary.per_class['정기사업'], 3);
});

test('canTrain requires both minimum sample count and class count', () => {
  assert.equal(MlClassifier.canTrain(EXAMPLES), false); // only 6 samples, need 20
  const many = [];
  for (let i = 0; i < 20; i++) many.push({ text: `노후 설비 ${i} 개체`, label: '노후설비개체' });
  assert.equal(MlClassifier.canTrain(many), false); // only 1 class
  many.push({ text: '정기점검 정비', label: '정기사업' });
  assert.equal(MlClassifier.canTrain(many), true);
});

test('computeCvFolds mirrors the python min(5, min-class-count, n//classes) rule', () => {
  assert.equal(MlClassifier.computeCvFolds(EXAMPLES), 3); // min(5, 3, 6//2=3) = 3
});
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `node --test web/test/mlClassifier.test.js`
Expected: FAIL — module not found

- [ ] **Step 3: 구현 작성**

`web/src/mlClassifier.js`:
```js
(function (global) {
  const N_MIN = 2;
  const N_MAX = 4;
  const MIN_SAMPLES_TO_TRAIN = 20;
  const MIN_CLASSES_TO_TRAIN = 2;

  function extractNgrams(text) {
    const s = String(text == null ? '' : text);
    const grams = [];
    for (let n = N_MIN; n <= N_MAX; n++) {
      for (let i = 0; i + n <= s.length; i++) {
        grams.push(s.slice(i, i + n));
      }
    }
    return grams;
  }

  function train(examples) {
    const classes = Array.from(new Set(examples.map((e) => e.label)));
    const ngramCountsByClass = {};
    const totalCountByClass = {};
    const docCountByClass = {};
    const vocab = new Set();

    for (const label of classes) {
      ngramCountsByClass[label] = new Map();
      totalCountByClass[label] = 0;
      docCountByClass[label] = 0;
    }

    for (const { text, label } of examples) {
      docCountByClass[label] += 1;
      const counts = ngramCountsByClass[label];
      for (const g of extractNgrams(text)) {
        vocab.add(g);
        counts.set(g, (counts.get(g) || 0) + 1);
        totalCountByClass[label] += 1;
      }
    }

    return { classes, ngramCountsByClass, totalCountByClass, docCountByClass, vocabSize: vocab.size, totalDocs: examples.length };
  }

  function scoreClasses(model, text) {
    const grams = extractNgrams(text);
    const scores = {};
    for (const label of model.classes) {
      const prior = Math.log(model.docCountByClass[label] / model.totalDocs);
      const counts = model.ngramCountsByClass[label];
      const total = model.totalCountByClass[label];
      let logLikelihood = 0;
      for (const g of grams) {
        const c = counts.get(g) || 0;
        logLikelihood += Math.log((c + 1) / (total + model.vocabSize));
      }
      scores[label] = prior + logLikelihood;
    }
    return scores;
  }

  function predict(model, text) {
    if (!model || model.classes.length === 0) {
      return { label: '미분류', confidence: 0 };
    }
    const scores = scoreClasses(model, text);
    const labels = Object.keys(scores);
    const maxScore = Math.max(...labels.map((l) => scores[l]));
    const expScores = labels.map((l) => Math.exp(scores[l] - maxScore));
    const sumExp = expScores.reduce((a, b) => a + b, 0);
    let bestLabel = labels[0];
    let bestProb = expScores[0] / sumExp;
    labels.forEach((l, idx) => {
      const prob = expScores[idx] / sumExp;
      if (prob > bestProb) { bestProb = prob; bestLabel = l; }
    });
    return { label: bestLabel, confidence: Math.round(bestProb * 100) / 100 };
  }

  function crossValidate(examples, folds) {
    if (examples.length < folds) return null;
    const buckets = Array.from({ length: folds }, () => []);
    examples.forEach((ex, i) => buckets[i % folds].push(ex));

    let correct = 0;
    let total = 0;
    for (let f = 0; f < folds; f++) {
      const testSet = buckets[f];
      const trainSet = buckets.filter((_, i) => i !== f).flat();
      if (trainSet.length === 0 || testSet.length === 0) continue;
      const model = train(trainSet);
      for (const ex of testSet) {
        const { label } = predict(model, ex.text);
        if (label === ex.label) correct += 1;
        total += 1;
      }
    }
    return total > 0 ? correct / total : null;
  }

  function trainingSummary(examples) {
    const perClass = {};
    for (const { label } of examples) {
      perClass[label] = (perClass[label] || 0) + 1;
    }
    return { count: examples.length, per_class: perClass };
  }

  function canTrain(examples) {
    const summary = trainingSummary(examples);
    return summary.count >= MIN_SAMPLES_TO_TRAIN && Object.keys(summary.per_class).length >= MIN_CLASSES_TO_TRAIN;
  }

  function computeCvFolds(examples) {
    const summary = trainingSummary(examples);
    const counts = Object.values(summary.per_class);
    if (counts.length === 0) return 0;
    const minClassCount = Math.min(...counts);
    return Math.min(5, minClassCount, Math.floor(examples.length / counts.length));
  }

  const api = {
    MIN_SAMPLES_TO_TRAIN, MIN_CLASSES_TO_TRAIN,
    extractNgrams, train, predict, crossValidate,
    trainingSummary, canTrain, computeCvFolds,
  };
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  } else {
    global.MlClassifier = api;
  }
})(typeof window !== 'undefined' ? window : globalThis);
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `node --test web/test/mlClassifier.test.js`
Expected: PASS (9 tests)

- [ ] **Step 5: 커밋**

```bash
git add web/src/mlClassifier.js web/test/mlClassifier.test.js
git commit -m "feat(web): implement in-browser naive-bayes classifier"
```

---

## Task 6: 하이브리드 분류 선택 로직 (`hybrid_classify.py` 포팅)

**Files:**
- Create: `web/src/hybridClassify.js`
- Test: `web/test/hybridClassify.test.js`

**Interfaces:**
- Consumes: `Classify.classifyRows`, `Classify.KEYWORD_RULES` (Task 3), `MlClassifier.predict`, `MlClassifier.train` (Task 5)
- Produces: `HybridClassify.classifyRows(rows, model, textCol='전표헤더텍스트') -> {rows, method: 'ml'|'rule'}`

- [ ] **Step 1: 실패하는 테스트 작성**

`web/test/hybridClassify.test.js`:
```js
const test = require('node:test');
const assert = require('node:assert/strict');
const HybridClassify = require('../src/hybridClassify.js');
const MlClassifier = require('../src/mlClassifier.js');

test('classifyRows falls back to keyword rules when no model is trained', () => {
  const rows = [{ 전표헤더텍스트: '정기점검 정비공사' }];
  const { rows: out, method } = HybridClassify.classifyRows(rows, null);
  assert.equal(method, 'rule');
  assert.equal(out[0].예측유형, '정기사업');
});

test('classifyRows uses the trained model when one is provided', () => {
  const examples = [
    { text: '노후 변압기 개체 공사', label: '노후설비개체' },
    { text: '노후 배관 개체 공사', label: '노후설비개체' },
    { text: '정기점검 정비공사', label: '정기사업' },
    { text: '계획예방정비 수행', label: '정기사업' },
  ];
  const model = MlClassifier.train(examples);
  const rows = [{ 전표헤더텍스트: '노후 케이블 개체 공사' }];
  const { rows: out, method } = HybridClassify.classifyRows(rows, model);
  assert.equal(method, 'ml');
  assert.equal(out[0].예측유형, '노후설비개체');
});
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `node --test web/test/hybridClassify.test.js`
Expected: FAIL — module not found

- [ ] **Step 3: 구현 작성**

`web/src/hybridClassify.js`:
```js
(function (global) {
  function resolveDeps() {
    if (typeof module !== 'undefined' && module.exports) {
      return { Classify: require('./classify.js'), MlClassifier: require('./mlClassifier.js') };
    }
    return { Classify: global.Classify, MlClassifier: global.MlClassifier };
  }

  function classifyRows(rows, model, textCol) {
    textCol = textCol || '전표헤더텍스트';
    const { Classify, MlClassifier } = resolveDeps();

    if (model) {
      const out = rows.map((row) => {
        const { label, confidence } = MlClassifier.predict(model, row[textCol]);
        return Object.assign({}, row, { 예측유형: label, 확신도: confidence });
      });
      out.sort((a, b) => a.확신도 - b.확신도);
      return { rows: out, method: 'ml' };
    }
    return { rows: Classify.classifyRows(rows, textCol), method: 'rule' };
  }

  const api = { classifyRows };
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  } else {
    global.HybridClassify = api;
  }
})(typeof window !== 'undefined' ? window : globalThis);
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `node --test web/test/hybridClassify.test.js`
Expected: PASS (2 tests)

- [ ] **Step 5: 커밋**

```bash
git add web/src/hybridClassify.js web/test/hybridClassify.test.js
git commit -m "feat(web): port hybrid classify method selection to JS"
```

---

## Task 7: localStorage 상태 저장소

**Files:**
- Create: `web/src/storage.js`
- Test: `web/test/storage.test.js`

**Interfaces:**
- Produces: `Storage.STORAGE_KEY = 'budget_app_state_v1'`, `Storage.defaultState() -> AppState`, `Storage.loadState(backend, embeddedDefault) -> AppState`, `Storage.saveState(backend, state) -> void`
  - `backend` = `{getItem(key)->string|null, setItem(key,value)->void}` (브라우저에서는 `window.localStorage`, 테스트에서는 Map 기반 mock)
  - `AppState` = `{yearStatus, yearData, classifiedData, trainingData, modelMeta}`

- [ ] **Step 1: 실패하는 테스트 작성**

`web/test/storage.test.js`:
```js
const test = require('node:test');
const assert = require('node:assert/strict');
const Storage = require('../src/storage.js');

function makeFakeBackend() {
  const map = new Map();
  return {
    getItem: (k) => (map.has(k) ? map.get(k) : null),
    setItem: (k, v) => map.set(k, v),
  };
}

test('loadState returns the embedded default when nothing is saved yet', () => {
  const backend = makeFakeBackend();
  const embedded = { yearStatus: { '2016': { uploaded: true } }, yearData: {}, classifiedData: {}, trainingData: [], modelMeta: null };
  assert.deepEqual(Storage.loadState(backend, embedded), embedded);
});

test('loadState returns a blank default when there is no embedded data either', () => {
  const backend = makeFakeBackend();
  assert.deepEqual(Storage.loadState(backend, null), Storage.defaultState());
});

test('saveState then loadState round-trips the saved state', () => {
  const backend = makeFakeBackend();
  const state = Storage.defaultState();
  state.trainingData.push({ text: 'a', label: 'L1' });
  Storage.saveState(backend, state);
  assert.deepEqual(Storage.loadState(backend, null), state);
});

test('loadState falls back to defaults if the saved value is corrupted JSON', () => {
  const backend = makeFakeBackend();
  backend.setItem(Storage.STORAGE_KEY, '{not valid json');
  assert.deepEqual(Storage.loadState(backend, null), Storage.defaultState());
});
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `node --test web/test/storage.test.js`
Expected: FAIL — module not found

- [ ] **Step 3: 구현 작성**

`web/src/storage.js`:
```js
(function (global) {
  const STORAGE_KEY = 'budget_app_state_v1';

  function defaultState() {
    return { yearStatus: {}, yearData: {}, classifiedData: {}, trainingData: [], modelMeta: null };
  }

  function loadState(backend, embeddedDefault) {
    const raw = backend.getItem(STORAGE_KEY);
    if (!raw) {
      return embeddedDefault ? JSON.parse(JSON.stringify(embeddedDefault)) : defaultState();
    }
    try {
      return JSON.parse(raw);
    } catch (e) {
      return embeddedDefault ? JSON.parse(JSON.stringify(embeddedDefault)) : defaultState();
    }
  }

  function saveState(backend, state) {
    backend.setItem(STORAGE_KEY, JSON.stringify(state));
  }

  const api = { STORAGE_KEY, defaultState, loadState, saveState };
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  } else {
    global.Storage = api;
  }
})(typeof window !== 'undefined' ? window : globalThis);
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `node --test web/test/storage.test.js`
Expected: PASS (4 tests)

- [ ] **Step 5: 커밋**

```bash
git add web/src/storage.js web/test/storage.test.js
git commit -m "feat(web): add localStorage-backed state persistence"
```

---

## Task 8: 기존 데이터를 내장 데이터로 변환

**Files:**
- Create: `scripts/generate_embedded_data.js`
- Create (generated, then committed): `web/data/embeddedData.js`
- Test: `web/test/embeddedData.test.js`

**Interfaces:**
- Consumes: `Csv.parseCsv` (Task 1)
- Produces: `web/data/embeddedData.js`가 export하는 객체는 `Storage`의 `AppState` 형태와 동일: `{yearStatus, yearData: {year: Row[]}, classifiedData: {year: ClassifiedRow[]}, trainingData: {text,label}[], modelMeta: null}`
  - 브라우저에서는 `window.EMBEDDED_DATA`로 노출된다.

- [ ] **Step 1: 실패하는 검증 테스트 작성** (생성 스크립트를 실행하기 전이므로 실패해야 정상)

`web/test/embeddedData.test.js`:
```js
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const DATA_PATH = path.join(__dirname, '..', 'data', 'embeddedData.js');

test('embeddedData.js exists and has the expected shape', () => {
  assert.ok(fs.existsSync(DATA_PATH), 'run scripts/generate_embedded_data.js first');
  const data = require(DATA_PATH);
  assert.ok(data.yearStatus['2016']);
  assert.equal(data.yearData['2016'].length, 310);
  assert.equal(data.classifiedData['2016'].length, 310);
  assert.equal(data.trainingData.length, 163);
  assert.equal(data.modelMeta, null);
});

test('embedded year rows have numeric amount and site fields', () => {
  const data = require(DATA_PATH);
  const row = data.yearData['2016'][0];
  assert.equal(typeof row.금액, 'number');
  assert.equal(typeof row.사업장, 'number');
});
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `node --test web/test/embeddedData.test.js`
Expected: FAIL — `web/data/embeddedData.js` 없음

- [ ] **Step 3: 생성 스크립트 작성**

`scripts/generate_embedded_data.js`:
```js
#!/usr/bin/env node
const fs = require('node:fs');
const path = require('node:path');
const Csv = require('../web/src/csv.js');

const ROOT = path.join(__dirname, '..');

function readJsonIfExists(file) {
  const p = path.join(ROOT, file);
  if (!fs.existsSync(p)) return null;
  return JSON.parse(fs.readFileSync(p, 'utf8'));
}

function readCsvIfExists(file) {
  const p = path.join(ROOT, file);
  if (!fs.existsSync(p)) return null;
  return Csv.parseCsv(fs.readFileSync(p, 'utf8'));
}

function findYearFiles(prefix) {
  return fs.readdirSync(ROOT)
    .filter((f) => f.startsWith(prefix) && f.endsWith('.csv'))
    .map((f) => {
      const match = f.match(new RegExp(`^${prefix}(\\d{4})\\.csv$`));
      return match ? { year: match[1], file: f } : null;
    })
    .filter(Boolean);
}

function normalizeYearRows(rows) {
  return rows.map((r) => ({
    거래처명: r['거래처명'],
    사업장: Number(r['사업장']),
    전기일: r['전기일'],
    전표헤더텍스트: r['전표헤더텍스트'],
    금액: Number(r['금액']),
  }));
}

function normalizeClassifiedRows(rows) {
  return rows.map((r) => ({
    거래처명: r['거래처명'],
    사업장: Number(r['사업장']),
    전기일: r['전기일'],
    전표헤더텍스트: r['전표헤더텍스트'],
    금액: Number(r['금액']),
    투자유형_확정: r['투자유형_확정'],
    확신도: Number(r['확신도']),
  }));
}

const yearStatus = readJsonIfExists('year_status.json') || {};

const yearData = {};
for (const { year, file } of findYearFiles('data_')) {
  yearData[year] = normalizeYearRows(readCsvIfExists(file));
}

const classifiedData = {};
for (const { year, file } of findYearFiles('classified_')) {
  classifiedData[year] = normalizeClassifiedRows(readCsvIfExists(file));
}

const trainingRows = readCsvIfExists('training_data.csv') || [];
const trainingData = trainingRows.map((r) => ({ text: r.text, label: r.label }));

const embedded = { yearStatus, yearData, classifiedData, trainingData, modelMeta: null };

const output = `// Auto-generated by scripts/generate_embedded_data.js — do not edit by hand.
(function (global) {
  const EMBEDDED_DATA = ${JSON.stringify(embedded, null, 2)};
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = EMBEDDED_DATA;
  } else {
    global.EMBEDDED_DATA = EMBEDDED_DATA;
  }
})(typeof window !== 'undefined' ? window : globalThis);
`;

const outPath = path.join(ROOT, 'web', 'data', 'embeddedData.js');
fs.mkdirSync(path.dirname(outPath), { recursive: true });
fs.writeFileSync(outPath, output, 'utf8');
console.log(`Wrote ${outPath}`);
console.log(`years with raw data: ${Object.keys(yearData).join(', ') || '(none)'}`);
console.log(`years with classified data: ${Object.keys(classifiedData).join(', ') || '(none)'}`);
console.log(`training examples: ${trainingData.length}`);
```

- [ ] **Step 4: 스크립트 실행**

Run: `node scripts/generate_embedded_data.js`
Expected output includes: `Wrote .../web/data/embeddedData.js`, `years with raw data: 2016`, `training examples: 163`

- [ ] **Step 5: 테스트 통과 확인**

Run: `node --test web/test/embeddedData.test.js`
Expected: PASS (2 tests)

- [ ] **Step 6: 커밋**

```bash
git add scripts/generate_embedded_data.js web/data/embeddedData.js web/test/embeddedData.test.js
git commit -m "feat(web): embed existing sample data into the JS app"
```

---

## Task 9: SheetJS(xlsx) 라이브러리 벤더링

**Files:**
- Create: `web/lib/xlsx.mini.min.js`

**Interfaces:**
- Produces: 브라우저 전역 `XLSX` 객체 (`XLSX.read`, `XLSX.utils.sheet_to_json` 등). 별도의 JS 모듈 인터페이스는 없음 — 벤더 파일을 그대로 최종 HTML에 인라인한다.

- [ ] **Step 1: 다운로드**

```bash
mkdir -p web/lib
curl -sL --max-time 30 https://cdn.sheetjs.com/xlsx-0.20.3/package/dist/xlsx.mini.min.js -o web/lib/xlsx.mini.min.js
```

- [ ] **Step 2: 무결성 확인**

```bash
wc -c web/lib/xlsx.mini.min.js
grep -c "SheetJS" web/lib/xlsx.mini.min.js
tail -c 100 web/lib/xlsx.mini.min.js
```

Expected: 파일 크기가 200000바이트 이상, `SheetJS` 문자열이 1회 이상 발견, 마지막 100바이트에 `//# sourceMappingURL=`로 시작하는 줄이 없어야 함(있다면 해당 줄을 파일에서 제거 — 오프라인 환경에서 존재하지 않는 소스맵 URL을 참조하지 않도록).

- [ ] **Step 3: 문법 검증**

Run: `node --check web/lib/xlsx.mini.min.js`
Expected: 아무 출력 없이 종료 (exit code 0) — 유효한 JS 파일임을 의미

- [ ] **Step 4: 커밋**

```bash
git add web/lib/xlsx.mini.min.js
git commit -m "chore(web): vendor SheetJS (xlsx.mini.min.js) for offline excel parsing"
```

---

## Task 10: 빌드 파이프라인 + UI 전체 구현

**Files:**
- Create: `web/template.html`
- Create: `web/src/ui.js`
- Create: `build.js`
- Modify: (없음 — 최초 생성)

**Interfaces:**
- Consumes: 모든 이전 태스크의 전역 네임스페이스 — `YearStatus`, `Classify`, `ValidateUpload`, `MlClassifier`, `HybridClassify`, `Storage`, `Csv`, `window.EMBEDDED_DATA`, `window.XLSX`
- Produces: 프로젝트 루트의 `index.html` (브라우저에서 여는 최종 산출물)

이 태스크는 DOM을 다루므로 Node 자동 테스트 대상이 아니다. "테스트"는 (a) 빌드 스크립트가 에러 없이 `index.html`을 생성하는지, (b) 생성된 스크립트가 문법적으로 유효한지, (c) 이어지는 Task 11의 수동 브라우저 검증으로 구성된다.

- [ ] **Step 1: HTML 템플릿 작성**

`web/template.html`:
```html
<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>발전플랜트 유지보수 예산 분석</title>
<style>
* { box-sizing: border-box; }
body { font-family: -apple-system, "Malgun Gothic", sans-serif; max-width: 900px; margin: 0 auto; padding: 24px; line-height: 1.5; color: #1a1a1a; }
h1 { font-size: 22px; }
h2 { font-size: 18px; margin-top: 32px; }
h3 { font-size: 15px; }
nav.tabs { display: flex; gap: 8px; margin-bottom: 24px; border-bottom: 1px solid #ddd; flex-wrap: wrap; }
nav.tabs button { padding: 10px 16px; border: none; background: none; cursor: pointer; font-size: 14px; border-bottom: 2px solid transparent; color: #333; }
nav.tabs button.active { border-bottom-color: #2563eb; font-weight: bold; color: #2563eb; }
.cell-grid { display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px; }
.cell { border: 1px solid #ddd; border-radius: 8px; padding: 12px; text-align: center; }
.cell-icon { font-size: 20px; margin-top: 6px; }
.group-detail-box { border: 1px solid #ddd; border-radius: 8px; padding: 12px; margin-top: 12px; background: #fafafa; }
.metrics { display: flex; gap: 16px; margin: 16px 0; flex-wrap: wrap; }
.metrics > div { flex: 1; min-width: 120px; border: 1px solid #eee; border-radius: 8px; padding: 12px; text-align: center; }
table { width: 100%; border-collapse: collapse; margin-top: 12px; }
th, td { border: 1px solid #ddd; padding: 6px 8px; font-size: 13px; text-align: left; }
.error-heading { color: #c62828; font-weight: bold; }
.review-row { border: 1px solid #ddd; border-radius: 8px; padding: 12px; margin-bottom: 10px; }
.conf-label { color: #666; font-size: 12px; margin: 0 0 4px; }
button { cursor: pointer; padding: 8px 14px; border-radius: 6px; border: 1px solid #2563eb; background: #2563eb; color: #fff; font-size: 14px; }
button:disabled { opacity: 0.5; cursor: not-allowed; }
select, input[type="file"] { padding: 6px; margin: 6px 0; }
</style>
</head>
<body>
<div id="app"></div>
<script>
/*__APP_SCRIPT__*/
</script>
</body>
</html>
```

- [ ] **Step 2: UI 로직 작성**

`web/src/ui.js`:
```js
(function () {
  'use strict';

  function escapeHtml(str) {
    return String(str == null ? '' : str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  const backend = window.localStorage;
  let AppState = Storage.loadState(backend, window.EMBEDDED_DATA || null);

  function persist() {
    try {
      Storage.saveState(backend, AppState);
    } catch (err) {
      alert('저장 공간이 부족하거나 저장에 실패했습니다. "전체 백업 내보내기"로 지금까지의 데이터를 꼭 파일로 백업해두세요.\n\n오류: ' + (err.message || err));
    }
  }

  function getActiveModel() {
    if (!AppState.modelMeta || AppState.trainingData.length === 0) return null;
    return MlClassifier.train(AppState.trainingData);
  }

  let currentTab = 'upload';
  let expandedGroup = null;
  let selectedUploadYear = null;
  let selectedReviewYear = null;
  let reviewChoices = {};

  function render() {
    const app = document.getElementById('app');
    app.innerHTML = `
      <h1>발전플랜트 유지보수 예산 분석</h1>
      <nav class="tabs">
        <button data-tab="upload" class="${currentTab === 'upload' ? 'active' : ''}">1단계 · 데이터 업로드</button>
        <button data-tab="review" class="${currentTab === 'review' ? 'active' : ''}">2단계 · 투자유형 분류 검토</button>
        <button data-tab="model" class="${currentTab === 'model' ? 'active' : ''}">모델 관리</button>
      </nav>
      <main id="tab-content"></main>
    `;
    app.querySelectorAll('nav.tabs button').forEach((btn) => {
      btn.addEventListener('click', () => { currentTab = btn.dataset.tab; render(); });
    });
    const content = document.getElementById('tab-content');
    if (currentTab === 'upload') renderUploadTab(content);
    else if (currentTab === 'review') renderReviewTab(content);
    else renderModelTab(content);
  }

  // ---------- 1단계: 업로드 ----------
  function renderCell(cell) {
    if (cell.type === 'group') {
      return `<div class="cell cell-group"><strong>${cell.label}</strong><br><button data-years='${JSON.stringify(cell.years)}'>펼쳐보기</button></div>`;
    }
    const icon = { done: '✅', warning: '⚠️', empty: '➖' }[cell.state];
    return `<div class="cell"><strong>${cell.year}</strong><div class="cell-icon">${icon}</div></div>`;
  }

  function renderUploadTab(content) {
    const cells = YearStatus.getVisibleCells(AppState.yearStatus, 4);
    const nextYear = YearStatus.nextAddableYear(AppState.yearStatus);
    const prevYear = YearStatus.prevAddableYear(AppState.yearStatus);
    const years = Object.keys(AppState.yearStatus).map(Number).sort((a, b) => a - b);

    if (years.length > 0) {
      selectedUploadYear = (selectedUploadYear && years.includes(selectedUploadYear)) ? selectedUploadYear : years[years.length - 1];
    }
    const already = years.length > 0 && AppState.yearStatus[String(selectedUploadYear)] && AppState.yearStatus[String(selectedUploadYear)].uploaded;

    content.innerHTML = `
      <h2>연도별 데이터 현황</h2>
      <div class="cell-grid">
        ${cells.length === 0 ? '<p>아직 등록된 연도가 없습니다. 아래에서 첫 연도를 추가하세요.</p>' : cells.map(renderCell).join('')}
      </div>
      <div id="group-detail"></div>
      <hr>
      <div class="add-year-row">
        <button id="add-next-year">＋ ${nextYear}년 칸 추가하기 (최신)</button>
        <button id="add-prev-year">＋ ${prevYear}년 칸 추가하기 (과거)</button>
      </div>
      <hr>
      <h2>신규 업로드</h2>
      ${years.length === 0 ? '<p>먼저 위에서 연도 칸을 추가해주세요.</p>' : `
        <label>연도 선택
          <select id="upload-year-select">
            ${years.map((y) => `<option value="${y}" ${y === selectedUploadYear ? 'selected' : ''}>${y}</option>`).join('')}
          </select>
        </label>
        <p>${already ? `⚠️ ${selectedUploadYear}년은 이미 데이터가 있습니다. 다시 업로드하면 덮어씁니다.` : `${selectedUploadYear}년은 아직 데이터가 없습니다.`}</p>
        <br><input type="file" id="upload-file-input" accept=".xlsx">
      `}
      <div id="upload-result"></div>
    `;

    if (expandedGroup) {
      document.getElementById('group-detail').innerHTML =
        `<div class="group-detail-box"><h3>${expandedGroup[0]}~${expandedGroup[expandedGroup.length - 1]} 개별 현황</h3>` +
        expandedGroup.map((y) => {
          const info = AppState.yearStatus[String(y)] || {};
          return `<p>${y}년 — 건수 ${info.row_count || 0} / 오류 ${info.error_count || 0}</p>`;
        }).join('') + '</div>';
    }

    content.querySelectorAll('.cell-group button').forEach((btn) => {
      btn.addEventListener('click', () => { expandedGroup = JSON.parse(btn.dataset.years); render(); });
    });
    document.getElementById('add-next-year').addEventListener('click', () => {
      AppState.yearStatus = YearStatus.addYear(AppState.yearStatus, nextYear);
      persist(); render();
    });
    document.getElementById('add-prev-year').addEventListener('click', () => {
      AppState.yearStatus = YearStatus.addYear(AppState.yearStatus, prevYear);
      persist(); render();
    });

    if (years.length > 0) {
      document.getElementById('upload-year-select').addEventListener('change', (e) => {
        selectedUploadYear = Number(e.target.value);
        render();
      });
      document.getElementById('upload-file-input').addEventListener('change', (e) => handleFileUpload(e.target.files[0]));
    }
  }

  function handleFileUpload(file) {
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (e) => {
      try {
        const data = new Uint8Array(e.target.result);
        const workbook = XLSX.read(data, { type: 'array', cellDates: true });
        const sheet = workbook.Sheets[workbook.SheetNames[0]];
        const allRows = XLSX.utils.sheet_to_json(sheet, { header: 1, raw: true });
        const dataRows = allRows.slice(1);
        const result = ValidateUpload.validateUpload(dataRows, selectedUploadYear);
        renderUploadResult(result);
      } catch (err) {
        document.getElementById('upload-result').innerHTML =
          `<p class="error-heading">파일을 읽을 수 없습니다: ${escapeHtml(String(err.message || err))}</p>`;
      }
    };
    reader.readAsArrayBuffer(file);
  }

  function renderUploadResult(result) {
    const box = document.getElementById('upload-result');
    const errorRows = result.errors.map((e) =>
      `<tr><td>${e.row}</td><td>${e.level}</td><td>${escapeHtml(e.type)}</td><td>${escapeHtml(e.detail)}</td></tr>`
    ).join('');
    box.innerHTML = `
      <div class="metrics">
        <div>총 건수<br><strong>${result.row_count}</strong></div>
        <div>유효 건수<br><strong>${result.valid_row_count}</strong></div>
        <div>오류 행<br><strong>${result.error_count}</strong></div>
      </div>
      ${result.errors.length > 0 ? `
        <p class="error-heading">검토가 필요한 행 (${result.errors.length}건)</p>
        <table><thead><tr><th>행</th><th>구분</th><th>유형</th><th>상세</th></tr></thead>
        <tbody>${errorRows}</tbody></table>
      ` : ''}
      <br><button id="save-upload-result">이 결과로 저장하기</button>
    `;
    document.getElementById('save-upload-result').addEventListener('click', () => {
      AppState.yearStatus = YearStatus.setYearResult(AppState.yearStatus, selectedUploadYear, result.row_count, result.error_count, result.errors);
      AppState.yearData[String(selectedUploadYear)] = result.data;
      persist();
      render();
    });
  }

  // ---------- 2단계: 분류 검토 ----------
  function renderReviewRow(row, idx, typeOptions) {
    const defaultChoice = typeOptions.includes(row.예측유형) ? row.예측유형 : '미분류';
    reviewChoices[idx] = defaultChoice;
    return `
      <div class="review-row">
        <p class="conf-label">전표헤더텍스트 · 확신도 ${Math.round(row.확신도 * 100)}%</p>
        <p>"${escapeHtml(row.전표헤더텍스트)}"</p>
        <select data-idx="${idx}">
          ${typeOptions.map((t) => `<option value="${escapeHtml(t)}" ${t === defaultChoice ? 'selected' : ''}>${escapeHtml(t)}</option>`).join('')}
        </select>
      </div>
    `;
  }

  function renderReviewTab(content) {
    const uploadedYears = Object.keys(AppState.yearStatus)
      .filter((y) => AppState.yearStatus[y].uploaded)
      .map(Number).sort((a, b) => b - a);

    if (uploadedYears.length === 0) {
      content.innerHTML = '<p>먼저 1단계에서 데이터를 업로드해주세요.</p>';
      return;
    }

    selectedReviewYear = (selectedReviewYear && uploadedYears.includes(selectedReviewYear)) ? selectedReviewYear : uploadedYears[0];
    const rows = AppState.yearData[String(selectedReviewYear)] || [];
    const model = getActiveModel();
    const { rows: classified, method } = HybridClassify.classifyRows(rows, model);

    const threshold = 0.7;
    const lowConf = classified.filter((r) => r.확신도 < threshold);
    const highConf = classified.filter((r) => r.확신도 >= threshold);
    reviewChoices = {};
    const typeOptions = Object.keys(Classify.KEYWORD_RULES).concat(['미분류']);

    content.innerHTML = `
      <label>연도 선택
        <select id="review-year-select">
          ${uploadedYears.map((y) => `<option value="${y}" ${y === selectedReviewYear ? 'selected' : ''}>${y}</option>`).join('')}
        </select>
      </label>
      <p>현재 분류 방식: ${method === 'ml' ? '학습된 모델' : '키워드 규칙 (아직 학습모델 없음)'}</p>
      <div class="metrics">
        <div>전체<br><strong>${classified.length}</strong></div>
        <div>확신 높음<br><strong>${highConf.length}</strong></div>
        <div>검토 필요<br><strong>${lowConf.length}</strong></div>
      </div>
      <h3>검토 필요 항목부터 (${lowConf.length}건)</h3>
      <div id="review-list">${lowConf.map((row, idx) => renderReviewRow(row, idx, typeOptions)).join('')}</div>
      <hr>
      <button id="approve-all-save">확신 높은 ${highConf.length}건 일괄 승인 + 검토 반영 저장</button>
      <button id="save-review-only">변경사항만 저장 (일괄승인 없이)</button>
    `;

    document.getElementById('review-year-select').addEventListener('change', (e) => {
      selectedReviewYear = Number(e.target.value);
      render();
    });
    content.querySelectorAll('.review-row select').forEach((sel) => {
      sel.addEventListener('change', () => { reviewChoices[Number(sel.dataset.idx)] = sel.value; });
    });
    document.getElementById('approve-all-save').addEventListener('click', () => saveReview(classified, lowConf, true));
    document.getElementById('save-review-only').addEventListener('click', () => saveReview(classified, lowConf, false));
  }

  function saveReview(classified, lowConf, approveHighConf) {
    const finalRows = classified.map((row) => Object.assign({}, row));
    lowConf.forEach((row, idx) => {
      const globalIdx = classified.indexOf(row);
      const choice = reviewChoices[idx];
      if (choice) finalRows[globalIdx].예측유형 = choice;
    });

    const renamed = finalRows.map((r) => {
      const copy = Object.assign({}, r);
      copy.투자유형_확정 = copy.예측유형;
      delete copy.예측유형;
      return copy;
    });

    AppState.classifiedData[String(selectedReviewYear)] = renamed;

    const reviewedRows = approveHighConf
      ? renamed
      : lowConf.map((row) => renamed[classified.indexOf(row)]);

    const merged = new Map(AppState.trainingData.map((e) => [e.text, e.label]));
    reviewedRows.forEach((r) => merged.set(r.전표헤더텍스트, r.투자유형_확정));
    AppState.trainingData = Array.from(merged.entries()).map(([text, label]) => ({ text, label }));

    persist();
    render();
  }

  // ---------- 모델 관리 ----------
  function renderModelTab(content) {
    const summary = MlClassifier.trainingSummary(AppState.trainingData);
    const meta = AppState.modelMeta;
    const trainable = MlClassifier.canTrain(AppState.trainingData);

    content.innerHTML = `
      <h2>전체 학습 현황</h2>
      <div class="metrics">
        <div>누적 학습데이터<br><strong>${summary.count}건</strong></div>
        <div>현재 모델 정확도(참고용)<br><strong>${meta && meta.cv_accuracy != null ? Math.round(meta.cv_accuracy * 100) + '%' : (meta ? '-' : '학습 안됨')}</strong></div>
      </div>
      ${meta ? `<p>마지막 학습: ${meta.trained_at} · 학습 당시 샘플 ${meta.n_samples}건, 유형 ${meta.n_classes}개</p>` : '<p>아직 재학습한 적이 없습니다. 지금은 키워드 규칙으로 분류 중입니다.</p>'}
      ${Object.keys(summary.per_class).length > 0
        ? `<ul>${Object.entries(summary.per_class).map(([k, v]) => `<li>${escapeHtml(k)}: ${v}건</li>`).join('')}</ul>`
        : '<p>아직 축적된 학습데이터가 없습니다.</p>'}
      <hr>
      <h2>재학습</h2>
      ${trainable
        ? '<button id="retrain-btn">지금 재학습하기</button>'
        : `<p>재학습하려면 최소 ${MlClassifier.MIN_SAMPLES_TO_TRAIN}건, ${MlClassifier.MIN_CLASSES_TO_TRAIN}개 이상 유형이 필요합니다. (현재 ${summary.count}건)</p>`}
      <div id="retrain-result"></div>
      <hr>
      <h2>학습 데이터 내보내기 · 불러오기</h2>
      <button id="export-training-btn" ${summary.count === 0 ? 'disabled' : ''}>학습 데이터 엑셀로 내보내기</button>
      <br><br>
      <label>수정한 학습 데이터 다시 업로드 (.csv, 'text'/'label' 컬럼 필요)<br>
        <input type="file" id="import-training-input" accept=".csv">
      </label>
      <div id="import-training-controls"></div>
      <hr>
      <h2>전체 백업 내보내기 · 불러오기</h2>
      <p class="conf-label">연도별 데이터, 학습데이터, 모델 학습현황을 통째로 파일 하나로 저장하거나, 다른 컴퓨터의 브라우저에 그대로 옮길 때 사용합니다.</p>
      <button id="export-backup-btn">전체 백업 내보내기</button>
      <br><br>
      <label>전체 백업 불러오기 (.json)<br>
        <input type="file" id="import-backup-input" accept=".json">
      </label>
      <div id="import-backup-result"></div>
      <hr>
      <h2>학습 취소 / 초기화</h2>
      <button id="reset-model-btn">모델만 초기화</button>
      <br><br>
      <label><input type="checkbox" id="confirm-reset-all"> 정말 전체 삭제할래요</label><br><br>
      <button id="reset-all-btn" disabled>전체 초기화</button>
    `;

    if (trainable) {
      document.getElementById('retrain-btn').addEventListener('click', () => {
        const folds = MlClassifier.computeCvFolds(AppState.trainingData);
        const cvAccuracy = folds >= 2 ? MlClassifier.crossValidate(AppState.trainingData, folds) : null;
        AppState.modelMeta = {
          trained_at: new Date().toISOString().slice(0, 16).replace('T', ' '),
          n_samples: summary.count,
          n_classes: Object.keys(summary.per_class).length,
          per_class: summary.per_class,
          cv_accuracy: cvAccuracy,
        };
        persist();
        document.getElementById('retrain-result').innerHTML =
          `<p>재학습 완료 — 샘플 ${summary.count}건, 유형 ${Object.keys(summary.per_class).length}개</p>` +
          (cvAccuracy != null ? `<p>교차검증 정확도(참고용): 약 ${Math.round(cvAccuracy * 100)}%</p>` : '');
      });
    }

    document.getElementById('export-training-btn').addEventListener('click', () => {
      downloadCsv('training_data.csv', Csv.toCsv(AppState.trainingData, ['text', 'label']));
    });

    document.getElementById('import-training-input').addEventListener('change', (e) => {
      const file = e.target.files[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = (ev) => renderImportControls(Csv.parseCsv(String(ev.target.result)));
      reader.readAsText(file, 'utf-8');
    });

    document.getElementById('export-backup-btn').addEventListener('click', () => {
      const stamp = new Date().toISOString().slice(0, 10);
      downloadJson(`budget_app_backup_${stamp}.json`, AppState);
    });

    document.getElementById('import-backup-input').addEventListener('change', (e) => {
      const file = e.target.files[0];
      if (!file) return;
      const resultBox = document.getElementById('import-backup-result');
      const reader = new FileReader();
      reader.onload = (ev) => {
        try {
          const restored = JSON.parse(String(ev.target.result));
          const required = ['yearStatus', 'yearData', 'classifiedData', 'trainingData'];
          const missing = required.filter((k) => !(k in restored));
          if (missing.length > 0) {
            throw new Error(`백업 파일에 필요한 항목이 없습니다: ${missing.join(', ')}`);
          }
          AppState = restored;
          persist();
          resultBox.innerHTML = '<p>백업을 불러왔습니다.</p>';
          render();
        } catch (err) {
          resultBox.innerHTML = `<p class="error-heading">백업 파일을 읽을 수 없습니다: ${escapeHtml(String(err.message || err))}</p>`;
        }
      };
      reader.readAsText(file, 'utf-8');
    });

    document.getElementById('reset-model-btn').addEventListener('click', () => {
      AppState.modelMeta = null;
      persist();
      render();
    });
    document.getElementById('confirm-reset-all').addEventListener('change', (e) => {
      document.getElementById('reset-all-btn').disabled = !e.target.checked;
    });
    document.getElementById('reset-all-btn').addEventListener('click', () => {
      AppState.trainingData = [];
      AppState.modelMeta = null;
      persist();
      render();
    });
  }

  function renderImportControls(rows) {
    const box = document.getElementById('import-training-controls');
    box.innerHTML = `
      <label><input type="radio" name="import-mode" value="merge" checked> 병합(같은 텍스트는 새 라벨로 갱신)</label>
      <label><input type="radio" name="import-mode" value="replace"> 전체 교체</label>
      <br><button id="apply-import-btn">업로드 내용 반영하기</button>
    `;
    document.getElementById('apply-import-btn').addEventListener('click', () => {
      const mode = box.querySelector('input[name="import-mode"]:checked').value;
      const cleaned = rows.filter((r) => r.text && r.label);
      if (mode === 'replace') {
        const merged = new Map(cleaned.map((r) => [r.text, r.label]));
        AppState.trainingData = Array.from(merged.entries()).map(([text, label]) => ({ text, label }));
      } else {
        const merged = new Map(AppState.trainingData.map((e) => [e.text, e.label]));
        cleaned.forEach((r) => merged.set(r.text, r.label));
        AppState.trainingData = Array.from(merged.entries()).map(([text, label]) => ({ text, label }));
      }
      persist();
      render();
    });
  }

  function downloadCsv(filename, csvText) {
    const blob = new Blob(['﻿' + csvText], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  }

  function downloadJson(filename, obj) {
    const blob = new Blob([JSON.stringify(obj, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  }

  // ---------- 자체 점검 (?selftest=1) ----------
  function runSelfTest() {
    const results = [];
    function check(name, fn) {
      try { fn(); results.push({ name, pass: true }); }
      catch (e) { results.push({ name, pass: false, error: String(e) }); }
    }

    check('YearStatus.getVisibleCells empty status returns []', () => {
      if (YearStatus.getVisibleCells({}).length !== 0) throw new Error('expected empty array');
    });
    check('Classify.classifyWithConfidence detects keyword type', () => {
      const r = Classify.classifyWithConfidence('노후 변압기 개체 공사');
      if (r.label !== '노후설비개체') throw new Error('got ' + r.label);
    });
    check('ValidateUpload flags missing amount', () => {
      const row = []; row[4] = 'A'; row[6] = 1; row[11] = '2016-01-01'; row[13] = 'x'; row[14] = '';
      if (ValidateUpload.validateUpload([row], 2016).critical_count !== 1) throw new Error('expected 1 critical error');
    });
    check('MlClassifier trains and predicts', () => {
      const examples = [
        { text: '노후 변압기 개체', label: 'A' }, { text: '노후 배관 개체', label: 'A' },
        { text: '정기점검 정비', label: 'B' }, { text: '정기보수 작업', label: 'B' },
      ];
      const model = MlClassifier.train(examples);
      const r = MlClassifier.predict(model, '노후 케이블 개체');
      if (r.label !== 'A') throw new Error('got ' + r.label);
    });
    check('Storage round-trips state', () => {
      const m = new Map();
      const fake = { getItem: (k) => (m.has(k) ? m.get(k) : null), setItem: (k, v) => m.set(k, v) };
      const state = Storage.defaultState();
      state.trainingData.push({ text: 'a', label: 'b' });
      Storage.saveState(fake, state);
      if (Storage.loadState(fake, null).trainingData.length !== 1) throw new Error('round trip failed');
    });

    const failed = results.filter((r) => !r.pass);
    const badge = document.createElement('div');
    badge.id = 'selftest-badge';
    badge.textContent = failed.length === 0 ? `✅ 자체 점검 통과 (${results.length}건)` : `❌ 자체 점검 실패 (${failed.length}/${results.length}건)`;
    badge.style.cssText = 'position:fixed;top:0;left:0;right:0;padding:8px;text-align:center;font-weight:bold;color:#fff;z-index:9999;background:' + (failed.length === 0 ? '#2e7d32' : '#c62828') + ';';
    document.body.prepend(badge);
    console.table(results);
  }

  document.addEventListener('DOMContentLoaded', () => {
    render();
    const params = new URLSearchParams(window.location.search);
    if (params.get('selftest') === '1') runSelfTest();
  });
})();
```

- [ ] **Step 3: 빌드 스크립트 작성**

`build.js`:
```js
#!/usr/bin/env node
const fs = require('node:fs');
const path = require('node:path');

const ROOT = __dirname;

function read(relPath) {
  return fs.readFileSync(path.join(ROOT, relPath), 'utf8');
}

const SRC_ORDER = [
  'web/lib/xlsx.mini.min.js',
  'web/src/csv.js',
  'web/src/yearStatus.js',
  'web/src/classify.js',
  'web/src/validateUpload.js',
  'web/src/mlClassifier.js',
  'web/src/hybridClassify.js',
  'web/src/storage.js',
  'web/data/embeddedData.js',
  'web/src/ui.js',
];

const script = SRC_ORDER.map((p) => `// ---- ${p} ----\n${read(p)}`).join('\n\n');
const template = read('web/template.html');
const output = template.replace('/*__APP_SCRIPT__*/', () => script);

fs.writeFileSync(path.join(ROOT, 'index.html'), output, 'utf8');
console.log('Wrote index.html (' + Math.round(output.length / 1024) + ' KB)');
```

Note: `.replace(pattern, () => script)` — 콜백 형태로 치환값을 넘기는 이유는 `script` 안에 `$&`, `$1` 같은 문자열이 우연히 포함될 경우 `String.replace`가 이를 특수 치환 패턴으로 잘못 해석하는 것을 막기 위함이다.

- [ ] **Step 4: 빌드 실행 및 검증**

```bash
node build.js
```
Expected: `Wrote index.html (NNN KB)` 출력, 프로젝트 루트에 `index.html` 생성됨

```bash
node -e "
const fs = require('fs');
const html = fs.readFileSync('index.html', 'utf8');
const match = html.match(/<script>([\s\S]*)<\/script>/);
fs.writeFileSync('/tmp/extracted_script.js', match[1]);
"
node --check /tmp/extracted_script.js
```
Expected: 아무 출력 없이 종료 (exit code 0) — 합쳐진 스크립트 전체가 유효한 JS임을 의미

- [ ] **Step 5: 커밋**

```bash
git add web/template.html web/src/ui.js build.js index.html
git commit -m "feat(web): build single-file HTML app with full UI"
```

---

## Task 11: 브라우저 수동 시나리오 검증 및 버그 수정

**Files:**
- Modify: `web/src/ui.js` (검증 중 발견된 버그가 있을 경우에만 수정)

이 태스크는 자동화된 단계가 아니라 실제 브라우저에서 앱을 구동하며 설계 문서의 5가지 시나리오를 확인하는 수동 QA다.

- [ ] **Step 1: 로컬 정적 서버로 열기**

`.claude/launch.json`이 없다면 아래 내용으로 생성(포트 8420 사용):
```json
{
  "version": "0.0.1",
  "configurations": [
    { "name": "budget-app", "runtimeExecutable": "python3", "runtimeArgs": ["-m", "http.server", "8420"], "port": 8420 }
  ]
}
```
Claude Preview의 `preview_start`로 `budget-app`을 실행하고 `http://localhost:8420/index.html`을 연다.

- [ ] **Step 2: 자체 점검 배지 확인**

`http://localhost:8420/index.html?selftest=1`로 접속. 상단에 `✅ 자체 점검 통과 (5건)` 녹색 배지가 보여야 한다. 빨간 배지가 보이면 콘솔의 `console.table` 출력을 확인해 실패한 항목을 `web/src/ui.js` 또는 관련 모듈에서 수정하고 Task 10의 빌드를 다시 실행한다.

- [ ] **Step 3: 시나리오 1 — 신규 연도 추가 → 업로드 → 검증 오류 확인**

1단계 탭에서 "＋ 2025년 칸 추가하기" 클릭 → 5칸 현황판에 2025 칸이 `➖`로 나타나는지 확인. 금액이 비어있는 행이 하나 포함된 테스트용 `.xlsx` 파일을 준비해 업로드하고, "오류 행" 카운트와 표에 "금액 없음" 항목이 뜨는지 확인 후 "이 결과로 저장하기" 클릭 → 현황판 아이콘이 `⚠️`로 바뀌는지 확인.

- [ ] **Step 4: 시나리오 2 — 분류 검토 → 일괄승인 저장 → 학습데이터 누적 확인**

2단계 탭에서 연도 2016 선택 → "검토 필요" 항목의 select에서 값 하나를 바꾸고 "확신 높은 N건 일괄 승인 + 검토 반영 저장" 클릭 → 모델 관리 탭의 "누적 학습데이터" 건수가 이전보다 늘어났는지 확인.

- [ ] **Step 5: 시나리오 3 — 재학습 → 정확도 표시 확인**

모델 관리 탭에서 (학습데이터가 20건, 2개 유형 이상이면) "지금 재학습하기" 클릭 → "재학습 완료 — 샘플 N건..." 메시지와 교차검증 정확도(%)가 표시되는지 확인. 2단계 탭으로 돌아가 "현재 분류 방식: 학습된 모델"로 바뀌었는지 확인.

- [ ] **Step 6: 시나리오 4 — 새로고침 후 데이터 유지 확인**

브라우저를 새로고침(F5)한 뒤, 방금 추가한 2025년 칸과 갱신된 학습데이터 건수가 그대로 남아있는지 확인 (localStorage 저장 확인).

- [ ] **Step 7: 시나리오 5a — 학습 데이터 내보내기/불러오기 확인**

모델 관리 탭에서 "학습 데이터 엑셀로 내보내기" 클릭 → CSV 파일이 다운로드되는지 확인. 그 파일을 "수정한 학습 데이터 다시 업로드"에 다시 올리고 "병합" 모드로 "업로드 내용 반영하기" 클릭 → 학습데이터 건수가 변하지 않아야 정상(같은 내용을 병합했으므로).

- [ ] **Step 8: 시나리오 5b — 전체 백업 내보내기 → 다른 브라우저 프로필에서 불러오기 확인**

"전체 백업 내보내기" 클릭 → `budget_app_backup_YYYY-MM-DD.json` 파일이 다운로드되는지 확인. 브라우저의 새 시크릿/프라이빗 창(= localStorage가 비어있는 새 프로필)에서 같은 `index.html`을 열어 기본 내장 데이터만 있는 상태인지 확인한 뒤, "전체 백업 불러오기"로 방금 받은 json 파일을 올리고 "백업을 불러왔습니다" 메시지와 함께 원래 창의 연도 현황·학습데이터가 그대로 재현되는지 확인.

- [ ] **Step 9: 발견된 버그 수정 및 커밋**

버그를 고쳤다면:
```bash
node build.js
git add web/src/ui.js index.html
git commit -m "fix(web): address issues found during manual scenario testing"
```
버그가 없었다면 이 태스크는 커밋 없이 종료한다.

---

## Task 12: 최종 커밋 및 GitHub push

**Files:** 없음 (git 작업만 수행)

- [ ] **Step 1: 상태 확인**

```bash
git status
git log --oneline
```

- [ ] **Step 2: 원격 저장소로 push**

```bash
git push origin main
```
Expected: `https://github.com/enhelee/ThreeON_Budget`의 `main` 브랜치에 모든 커밋이 반영됨

- [ ] **Step 3: 최종 확인**

`index.html`을 인터넷 연결 없이(에어플레인 모드 또는 Wi-Fi 끄기) 더블클릭으로 열어 정상 동작하는지 최종 확인한다.
