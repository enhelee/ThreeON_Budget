// 최종 실적금액이 있는 집계표와 RAW를 대조한다. 예측용 텍스트 매칭과 구분.
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.BUDGET_RECONCILE = factory();
})(typeof self !== 'undefined' ? self : this, function () {
  const norm = x => String(x == null ? '' : x).normalize('NFC').replace(/\s/g, '');
  const won = x => Math.round((Number(x) || 0) * 1000);
  // 결과 표의 천원 표시를 기준으로 비교한다. 실제 원 단위 차이는 기록·보존한다.
  const same = (a, b) => Math.round(a / 1000) === Math.round(b / 1000);
  const maintenance = t => /정기.*(점검|보수)|정비공사|부속설비.*점검/.test(norm(t));
  const textKey = t => norm(t).replace(/[()\[\]（）]/g, '').toLowerCase();
  const control = t => /제어|컨트롤러|\bdcs\b/i.test(String(t));
  const sum = a => a.reduce((s, x) => s + x.value, 0);
  const isSpareItem = t => t.bucket === 'rule3' || (t.bucket === 'boan' && !norm(t.text)) || /예비품|저장품|고온부품|불출|자재.*환입|환입.*자재/.test(norm(t.text));
  function dateKey(value) {
    if (value == null || value === '') return '';
    if (Object.prototype.toString.call(value) === '[object Date]') return Number.isFinite(value.getTime()) ? value.toISOString().slice(0, 10) : '';
    if (typeof value === 'string' && /^\d{1,5}(?:\.\d+)?$/.test(value.trim())) return dateKey(Number(value));
    if (typeof value === 'number' && Number.isFinite(value) && value > 0 && value < 100000) {
      return new Date(Date.UTC(1899, 11, 30) + Math.floor(value) * 86400000).toISOString().slice(0, 10);
    }
    const s = String(value).trim(), m = s.match(/^(\d{4})[-/.년 ]\s*(\d{1,2})[-/.월 ]\s*(\d{1,2})(?:일|\s.*|T.*)?$/) || s.match(/^(\d{4})(\d{2})(\d{2})$/);
    if (!m) return '';
    const key = m[1] + '-' + m[2].padStart(2, '0') + '-' + m[3].padStart(2, '0');
    const parsed = new Date(key + 'T00:00:00Z');
    return Number.isFinite(parsed.getTime()) && parsed.toISOString().slice(0, 10) === key ? key : '';
  }
  // 지사·과목 내부에서만 사용. 변동비/Extra Work/연료전지를 고정비와 섞지 않는다.
  function family(text, isPlan) {
    const t = norm(text).toLowerCase();
    if (/ltsa|장기유지보수/.test(t)) {
      if (/extra|변동|\bci\b/.test(t)) return '';
      if (/연료전지/.test(t)) return '연료전지 LTSA';
      if (/가스터빈|gt/.test(t) && (!isPlan || /고정/.test(t))) return '가스터빈 LTSA 고정비';
      return '';
    }
    if (/소방/.test(t) && /점검|용역/.test(t) && !/공사|구매|보완|개선|자재/.test(t)) return '소방 점검용역';
    return '';
  }

  // 양수 부분집합. 유일한 조합일 때만 사용하며 탐색 한도를 넘으면 미확정으로 둔다.
  function uniqueSubset(entries, target, minCount = 2) {
    const a = entries.filter(x => x.value > 0 && x.value <= target + 999)
      .sort((x, y) => y.value - x.value);
    if (a.length < minCount || a.length > 24 || target <= 0) return { items: null, limited: a.length > 24 };
    const suffix = new Array(a.length + 1).fill(0);
    for (let i = a.length - 1; i >= 0; i--) suffix[i] = suffix[i + 1] + a[i].value;
    let visits = 0, limited = false;
    const hits = [], hitKeys = new Set();
    function search(i, total, selected) {
      if (++visits > 200000) { limited = true; return; }
      if (hits.length > 1 || limited) return;
      if (selected.length >= minCount && same(total, target)) {
        const key = selected.map(x => x.id).sort().join('|');
        if (!hitKeys.has(key)) { hitKeys.add(key); hits.push(selected.slice()); }
      }
      if (i === a.length || total > target + 999 || total + suffix[i] < target - 999) return;
      search(i + 1, total + a[i].value, selected.concat(a[i]));
      search(i + 1, total, selected);
    }
    search(0, 0, []);
    // 같은 부분집합이 뒤의 제외 경로에서 반복 발견되는 것을 제거.
    const distinct = new Map(hits.map(h => [h.map(x => x.id).sort().join('|'), h]));
    return { items: !limited && distinct.size === 1 ? [...distinct.values()][0] : null,
      ambiguous: distinct.size > 1, limited };
  }

  function fill(aoa, cleaned, ledger, C, correctionCases = []) {
    const grid = aoa.map(r => (r || []).slice());
    const hr = grid.findIndex((r, i) => i < 10 && r.map(norm).some(h => h.includes('사업명')) && r.map(norm).some(h => h.includes('예산과목')));
    if (hr < 0) throw new Error(ledger + ' 집계표에서 사업명·예산과목 헤더를 찾을 수 없습니다.');
    const h = grid[hr].map(norm);
    const ci = { biz: h.findIndex(x => x.includes('사업명')), acct: h.findIndex(x => x.includes('예산과목')),
      org: h.findIndex(x => x.includes('부서명(처') || x.includes('처.지사')), actual: h.findIndex(x => x.includes('실적')) };
    if (ci.org < 0 || ci.actual < 0) throw new Error(ledger + ' 집계표에 지사와 최종 실적금액 열이 필요합니다.');
    const groups = new Map(), plans = [], items = [], matches = [], log = [], detail = [], corrections = [], exclusions = [], spareDates = [], spareSources = [];
    const get = (org, acct) => { const k = JSON.stringify([norm(org), acct]); if (!groups.has(k)) groups.set(k, { org: norm(org), acct, plans: [], items: [] }); return groups.get(k); };
    for (let r = hr + 1; r < grid.length; r++) {
      const row = grid[r], acct = C.resolveAcctCode(row[ci.acct]), biz = String(row[ci.biz] || '').trim();
      if (!acct || !biz || biz.includes('미반영') || String(row[0]).includes('예시')) continue;
      const p = { id: 'p' + r, r, biz, org: norm(row[ci.org]), acct, acctName: row[ci.acct], value: won(row[ci.actual]), used: false };
      plans.push(p); get(p.org, acct).plans.push(p); row[ci.actual] = 0;
    }
    for (const x of cleaned) {
      if (x.ledger !== ledger || (x.bucket === 'gyeongsang' && !x.spareDateGroup) || (!x.amount && !x.spareDateGroup)) continue;
      const it = { ...x, id: 't' + items.length, value: Math.round(x.amount), used: false };
      items.push(it); get(it.org, it.acct).items.push(it);
    }
    function apply(g, txs, ps, method, allowDifference = false) {
      if (txs.some(t => t.spareDateGroup) && (txs.length !== 1 || !dateKey(txs[0].date))) throw new Error('예비품은 유효한 전기일 묶음 하나씩 배정해야 합니다.');
      if (txs.some(t => t.used) || ps.some(p => p.used)) throw new Error('중복 배정');
      const total = txs.reduce((s, t) => s + t.value, 0), expected = ps.reduce((s, p) => s + p.value, 0);
      if (!allowDifference && !same(total, expected)) throw new Error('합계 불일치');
      const id = ledger + '-' + (matches.length + 1);
      const sorted = ps.slice().sort((a, b) => Math.abs(b.value) - Math.abs(a.value));
      // 천원 비교로 생긴 잔차는 첫 사업에 더해 RAW 원 금액 합계를 보존한다.
      for (let j = 0; j < sorted.length; j++) {
        const p = sorted[j], allocation = p.value + (j === 0 ? total - expected : 0);
        p.used = true; grid[p.r][ci.actual] = allocation / 1000;
        detail.push([id, ledger, g.org, p.acctName, p.r + 1, p.biz, p.value / 1000, allocation / 1000]);
      }
      const name = ps.length === 1 ? ps[0].biz : ps.map(p => p.biz).join(' / ');
      for (const t of txs) {
        t.used = true;
        log.push([t.org, t.acctName, t.text, t.value / 1000, ps.length === 1 ? name : '', 1,
          method + ' (' + id + ')' + (ps.length > 1 ? ' — 묶음배분 시트 참조' : ''), t.date, (t.docNos || []).join(','), t.lossCenter, '']);
      }
      matches.push([id, ledger, g.org, ps[0].acctName, method, total / 1000, expected / 1000,
        (total - expected) / 1000, txs.length, ps.length, name,
        txs.map(t => t.text || '(빈 텍스트)').join(' / '), txs.flatMap(t => t.docNos || []).join(',')]);
    }
    for (const g of groups.values()) {
      // RAW 단계에서 묶은 예비품 전기일 순액을 먼저 대조한다. 날짜 사이의 부분합은 금지.
      const sparePlans = g.plans.filter(p => C.bucketOf(g.acct) === 'rule3' || /예비품|저장품|고온부품|자재.*(대체|불출|환입)/.test(norm(p.biz)));
      const proposals = new Map();
      for (const t of g.items.filter(t => t.spareDateGroup)) {
        let reason = '', ps = [];
        if (!g.org) reason = '지사 미확인';
        else if (!dateKey(t.date)) reason = '전기일 누락·형식 확인';
        else if (!t.value) { t.used = true; t.spareStatus = '상쇄(0원)'; }
        else {
          const exclude = correctionCases.some(c => norm(c.org) === g.org && c.acct === g.acct && c.action === 'exclude' && c.texts.some(s => (t.sourceItems || []).some(x => textKey(x.text) === textKey(s.text))));
          const hits = sparePlans.filter(p => p.value && same(p.value, t.value));
          if (exclude) reason = '예비품 제외 보정은 전기일 묶음의 원천 범위 확인 필요';
          else if (hits.length === 1) ps = hits;
          else if (hits.length > 1) reason = '같은 전기일 순액에 맞는 사업이 복수';
          else {
            const subset = uniqueSubset(sparePlans, t.value);
            if (subset.items) ps = subset.items;
            else reason = subset.limited ? '예비품 사업 조합 탐색 한도·검토필요' : subset.ambiguous ? '예비품 사업 합산 조합이 복수' : '해당 전기일 순액과 일치하는 예비품 사업 없음';
          }
        }
        proposals.set(t, { ps, reason });
      }
      for (const [t, proposal] of proposals) {
        let { ps, reason } = proposal;
        if (ps.length && [...proposals].some(([other, candidate]) => other !== t && candidate.ps.some(p => ps.includes(p)))) {
          reason = '서로 다른 전기일 묶음이 같은 사업과 일치·검토필요'; ps = [];
        }
        if (ps.length) {
          apply(g, [t], ps, '예비품 전기일별 순액 일치');
          t.spareStatus = '반영'; t.spareTargets = ps.map(p => p.biz); t.spareMatchID = matches[matches.length - 1][0];
        } else if (!t.used) { t.held = true; t.holdReason = reason; t.spareStatus = '검토필요'; }
        const source = t.sourceItems || [];
        spareDates.push([t.spareGroupId, ledger, g.org, t.acctName, dateKey(t.date), source.length,
          source.filter(x => x.amount > 0).reduce((s, x) => s + x.amount, 0) / 1000,
          source.filter(x => x.amount < 0).reduce((s, x) => s + x.amount, 0) / 1000,
          t.value / 1000, ps.length ? sum(ps) / 1000 : '', ps.length ? (t.value - sum(ps)) / 1000 : '',
          (t.spareTargets || []).join(' / '), t.spareStatus, reason || (t.value ? '같은 지사·과목·전기일 전체 순액 대조' : '같은 전기일에서 전액 상쇄'), source.map(x => x.sourceRow).join(','), t.spareMatchID || '']);
        for (const x of source) spareSources.push([t.spareGroupId, ledger, g.org, t.acctName, dateKey(x.date), x.sourceRow, x.text, x.amount / 1000, x.docNo, String(x.date == null ? '' : x.date)]);
      }
      // 날짜 순액이 맞지 않는 예비품 사업을 일반 금액/정기점검 합산이 가져가지 못하게 한다.
      for (const p of sparePlans) if (!p.used) p.held = true;
      if (!g.org || !g.plans.length) continue;
      // 사람이 적은 보정부터 처리. 미해결 보정은 다른 자동 규칙이 덮어쓰지 않는다.
      for (const c of correctionCases.filter(c => norm(c.org) === g.org && c.acct === g.acct)) {
        const dated = g.items.filter(t => t.spareDateGroup && c.texts.some(s => (t.sourceItems || []).some(x => textKey(s.text) === textKey(x.text))));
        if (dated.length) {
          // 과거 보정의 여러 날짜 합산보다 최신 전기일 규칙을 우선한다.
          const applied = dated.every(t => t.spareStatus === '반영' || t.spareStatus === '상쇄(0원)');
          corrections.push([c.id, ledger, g.org, g.plans[0].acctName, c.label, applied ? '전기일 기준 반영' : '검토필요', dated.length, '', '', '',
            [...new Set(dated.flatMap(t => t.spareTargets || []))].join(' / '), '예비품은 날짜별로 재계산·예비품전기일 시트 참조: ' + dated.map(t => t.spareGroupId).join(','), c.texts.map(t => t.sourceRow || '').join(','), dated.map(t => t.spareMatchID || '').filter(Boolean).join(','), c.origin || '업로드 보정']);
          continue;
        }
        const txs = g.items.filter(t => !t.used && c.texts.some(s => textKey(s.text) === textKey(t.text)));
        let ps = c.targets.flatMap(name => g.plans.filter(p => textKey(p.biz) === textKey(name)));
        if (c.targets.length === 1 && ps.length > 1) {
          const exact = ps.filter(p => !p.used && !p.held && same(p.value, sum(txs)));
          if (exact.length === 1) ps = exact;
        }
        const sourceOK = txs.length === c.texts.length && c.texts.every(s => txs.some(t => textKey(s.text) === textKey(t.text) && (s.amountThousand == null || same(t.value, won(s.amountThousand)))));
        const targetOK = ps.length === c.targets.length && !ps.some(p => p.used || p.held);
        const referenceOK = !c.referenceAmounts || c.targets.every((name, i) => ps.some(p => textKey(p.biz) === textKey(name) && p.value === won(c.referenceAmounts[i])));
        const bounded = Number.isSafeInteger(c.toleranceWon) && c.toleranceWon >= 0;
        const permitted = bounded && Math.abs(sum(txs) - sum(ps)) <= c.toleranceWon;
        let status, reason, groupID = '';
        if (!txs.length) { status = '대상 전표 없음'; reason = '원천에 동일 지사·과목·텍스트가 없음'; }
        else if (!sourceOK || txs.some(t => t.held)) { status = '검토필요'; reason = '보정 당시 전표 수·금액과 다르거나 다른 보정과 충돌'; }
        else if (c.action === 'exclude') {
          for (const t of txs) {
            t.used = true; t.excluded = true;
            exclusions.push([ledger, g.org, t.acctName, t.text, t.value / 1000, c.label, c.id, (t.docNos || []).join(',')]);
            log.push([t.org, t.acctName, t.text, t.value / 1000, '제외', 1, '담당자 보정 제외 (' + c.id + ')', t.date, (t.docNos || []).join(','), t.lossCenter, '']);
          }
          status = '제외 반영'; reason = '담당자가 지정한 전표만 제외·원금은 제외내역에 보존';
        } else if (!targetOK) { status = '검토필요'; reason = '같은 지사·과목에서 집계표 사업명을 유일하게 찾지 못함 또는 중복 배정'; }
        else if (!referenceOK) { status = '검토필요'; reason = '금액 차이를 허용한 보정 당시 집계표 금액과 다름'; }
        else if (bounded ? !permitted : c.requireAmount && !same(sum(txs), sum(ps))) { status = '검토필요'; reason = '보정의 합계 일치 또는 담당자 허용차이 조건 불충족'; }
        else {
          apply(g, txs, ps, '보정사전 ' + c.id + (same(sum(txs), sum(ps)) ? ' 금액 일치' : permitted ? ' 담당자 허용차이 내 반영' : ' 연결 반영·금액차이 확인'), permitted || !c.requireAmount);
          groupID = matches[matches.length - 1][0]; status = '반영'; reason = same(sum(txs), sum(ps)) ? '기존 집계표 사업명에 연결' : '원천금액으로 반영하고 집계표와의 차이는 별도 확인';
          if (permitted && sum(txs) !== sum(ps)) reason = '담당자 허용차이 '+c.toleranceWon+'원 이내·원천 순액 보존·차이는 최대금액 사업행에 반영(개별 정산 확인 아님)';
        }
        if (status === '검토필요') {
          txs.forEach(t => { t.held = true; t.holdReason = c.id + ': ' + reason; });
          ps.filter(p => !p.used).forEach(p => { p.held = true; });
        }
        corrections.push([c.id, ledger, g.org, g.plans[0].acctName, c.label, status, txs.length, sum(txs) / 1000, ps.length ? sum(ps) / 1000 : '', ps.length ? (sum(txs) - sum(ps)) / 1000 : '', ps.map(p => p.biz).join(' / '), reason, c.texts.map(t => t.sourceRow || '').join(','), groupID, c.origin || '업로드 보정']);
      }
      const availableItems = () => g.items.filter(t => !t.used && !t.held);
      const availablePlans = () => g.plans.filter(p => !p.used && !p.held);
      // 담당자 제외분이 기존 집계표에 포함된 경우, 정상 계약의 원천 실적을 따로 보존.
      for (const c of correctionCases.filter(c => norm(c.org) === g.org && c.acct === g.acct && c.relatedTarget)) {
        const excluded = g.items.filter(t => t.excluded && c.texts.some(s => textKey(s.text) === textKey(t.text)));
        const ps = availablePlans().filter(p => textKey(p.biz) === textKey(c.relatedTarget));
        const txs = availableItems().filter(t => c.regularTextContains && norm(t.text).includes(norm(c.regularTextContains)));
        if (excluded.length === c.texts.length && ps.length === 1 && txs.length && same(sum(txs) + sum(excluded), sum(ps))) {
          apply(g, txs, ps, '담당자 제외분 차감 후 합계 일치 (' + c.id + ')·집계표 수정 확인', true);
        }
      }
      // 같은 계약군의 전체 순액. 양수 기성과 음수 역인식을 함께 계산한다.
      // 총액만 같은 다른 용역을 섞지 않으며, 후보가 하나일 때만 자동 적용한다.
      for (const f of new Set(availablePlans().map(p => family(p.biz, true)).filter(Boolean))) {
        const ps = availablePlans().filter(p => family(p.biz, true) === f);
        const txs = availableItems().filter(t => family(t.text, false) === f);
        if (ps.length === 1 && txs.length > 1 && same(sum(txs), sum(ps))) apply(g, txs, ps, f + ' 순액 합산 일치');
      }
      // 1:1: 같은 금액 후보·전표가 서로 유일할 때만 배정한다.
      const pair = () => {
        let changed = false;
        for (const t of availableItems().sort((a, b) => Math.abs(b.value) - Math.abs(a.value))) {
          const hits = availablePlans().filter(p => p.value && same(t.value, p.value));
          if (hits.length !== 1) continue;
          if (availableItems().filter(x => same(x.value, hits[0].value)).length !== 1) continue;
          apply(g, [t], hits, '최종 실적금액 일치'); changed = true;
        }
        return changed;
      };
      pair();
      // 정기점검 및 빈텍스트 입고: 전표 한 건에 해당하는 사업들의 유일한 합산 조합.
      for (const t of availableItems().filter(t => t.value > 0).sort((a, b) => b.value - a.value)) {
        const isMaintenance = maintenance(t.text);
        if (!isMaintenance && !t.fixedRow && norm(t.text)) continue;
        const pool = availablePlans().filter(p => p.value > 0 && (!isMaintenance || (maintenance(p.biz) && control(p.biz) === control(t.text))));
        const found = uniqueSubset(pool, t.value);
        if (found.items) apply(g, [t], found.items, isMaintenance ? '정기점검 합산 일치' : '입고 사업 합산 일치');
      }
      pair();
      // N:1: 같은 날짜(예비품 등) 또는 정기점검 전표 묶음의 합이 사업 하나와 일치.
      for (const p of availablePlans().filter(p => p.value > 0).sort((a, b) => b.value - a.value)) {
        const pools = new Map();
        for (const t of availableItems().filter(t => t.value > 0)) {
          if (maintenance(p.biz) && control(t.text) !== control(p.biz)) continue;
          if (t.date != null && t.date !== '') { const k = 'date:' + t.date; if (!pools.has(k)) pools.set(k, []); pools.get(k).push(t); }
        }
        if (maintenance(p.biz)) pools.set('maintenance', availableItems().filter(t => t.value > 0 && maintenance(t.text) && control(p.biz) === control(t.text)));
        const solutions = new Map(); let limited = false;
        for (const pool of pools.values()) {
          const found = uniqueSubset(pool, p.value);
          if (found.limited || found.ambiguous) limited = true;
          if (found.items) solutions.set(found.items.map(t => t.id).sort().join('|'), found.items);
        }
        if (!limited && solutions.size === 1) apply(g, [...solutions.values()][0], [p], '전표 합산 일치');
      }
      pair();
      // 정기점검·정기유지보수는 같은 지사·같은 과목의 남은 전체 합계도 대조한다.
      // 개별 배분이 확정됐다고 표시하지 않고 하나의 금액 일치 묶음으로 기록한다.
      if (/정기점검|정기유지보수/.test(g.plans[0].acctName)) {
        const txs = availableItems();
        const ps = availablePlans().filter(p => p.value);
        // 사용자 승인 방식인 과목 잔여합계 대조는 유지하되 제어/비제어 점검을 섞지 않는다.
        // 이 결과는 합계 묶음이며 전표별 세부사업 배정의 검증을 뜻하지 않는다.
        const checkPlans = ps.filter(p => maintenance(p.biz));
        const mixedControl = checkPlans.some(p => control(p.biz)) && checkPlans.some(p => !control(p.biz));
        if (!g.items.some(t => t.held) && !mixedControl && txs.length && ps.length && same(sum(txs), sum(ps))) {
          apply(g, txs, ps, '정기점검·유지보수 잔여 합계 일치');
        }
      }
    }
    const remaining = items.filter(t => !t.used);
    for (const t of remaining) {
      const row = new Array(grid[hr].length).fill('');
      row[ci.org] = t.org || ''; row[ci.acct] = t.acctName; row[ci.biz] = '(미배분·검토) ' + (t.text || '(빈 텍스트)'); row[ci.actual] = t.value / 1000; grid.push(row);
      log.push([t.org, t.acctName, t.text, t.value / 1000, '', 0, t.holdReason || '금액 미일치 또는 복수 조합·확인요망', t.date, (t.docNos || []).join(','), t.lossCenter, '']);
    }
    const differences = plans.filter(p => !p.used && p.value).map(p => [ledger, p.org, p.acctName, p.r + 1, p.biz, p.value / 1000, '대응 전표 미확정']);
    return { aoa: grid, log, matches, detail, differences, corrections, exclusions, spareDates, spareSources,
      stats: { planRows: plans.length, filled: plans.filter(p => p.used).length, unplanned: remaining.length,
        excludedWon: sum(items.filter(t => t.excluded)), matchedWon: sum(items.filter(t => t.used && !t.excluded)), inputWon: sum(items), groups: matches.length } };
  }
  return { fill, uniqueSubset, dateKey, isSpareItem };
});
