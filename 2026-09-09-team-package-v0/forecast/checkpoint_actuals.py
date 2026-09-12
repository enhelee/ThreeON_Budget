"""사업별 배정 JSON → 연간 표준화/예측 실적. 원전표와 배정을 중복 합산하지 않는다."""
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import hashlib
import json
import os
from pathlib import Path
import unicodedata
import uuid
import pandas as pd
from builtin_categories import normalize_account_name

STORE = Path('checkpoint_data')
COLUMNS = ['사업장', '연도', '예산과목', '금액', '사업명', '원장', '묶음ID', '집계표 원본행']

def _text(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError('지사·과목·사업명·묶음ID가 비어 있습니다.')
    return unicodedata.normalize('NFC', value).strip()

def _won(value, multiplier=1000):
    if isinstance(value, bool):
        raise ValueError('금액 형식 오류')
    try:
        amount = Decimal(str(value)) * multiplier
        if not amount.is_finite():
            raise ValueError('유한한 금액이 필요합니다.')
        rounded = amount.quantize(Decimal('1'), rounding=ROUND_HALF_UP)
        if abs(amount-rounded) > Decimal('0.01') or abs(rounded) > 9_000_000_000_000_000:
            raise ValueError('원 단위 금액을 확인하세요.')
        return int(rounded)
    except (InvalidOperation, TypeError) as exc:
        raise ValueError('금액 형식 오류') from exc

def _scope(ledger, org, account):
    if ledger not in ('손익', '자본'):
        raise ValueError('손익/자본 원장 정보가 필요합니다.')
    return ledger, _text(org).replace(' ', ''), normalize_account_name(_text(account))

def _rows(rec, key, header, length):
    rows = rec.get(key)
    if not isinstance(rows, list) or not rows or not isinstance(rows[0], list) or rows[0][:len(header)] != header:
        raise ValueError(f'{key}: 지원하지 않는 표 형식입니다.')
    if any(not isinstance(row, list) or len(row) != length for row in rows):
        raise ValueError(f'{key}: 열 수가 맞지 않습니다.')
    return rows[1:]

def prepare_result(content, year):
    if isinstance(year, bool) or not isinstance(year, int) or not 1900 <= year <= 2200:
        raise ValueError('실적 연도를 확인하세요.')
    try:
        data = json.loads(content)
    except (ValueError, TypeError) as exc:
        raise ValueError('JSON 결과 파일을 확인하세요.') from exc
    if not isinstance(data, dict) or data.get('schemaVersion') != 1 or data.get('amountUnit') != 'KRW_THOUSAND' or data.get('amountMatching') is not True:
        raise ValueError('최종 실적금액 대조 모드의 결과 JSON이 필요합니다.')
    if data.get('sourceYears') != [year]:
        raise ValueError('원천 전기일 연도와 선택 연도가 다르거나 여러 연도가 섞였습니다. 최신 HTML에서 단일 연도 결과를 다시 생성하세요.')
    if not isinstance(data.get('sourceTotals'), list) or not data['sourceTotals']:
        raise ValueError('원천 합계가 없는 이전 결과입니다. 최신 HTML에서 다시 내보내세요.')
    rec = data.get('reconciliation')
    if not isinstance(rec, dict):
        raise ValueError('대조 내역이 없습니다.')
    groups = _rows(rec, 'groups', ['묶음ID', '원장', '지사', '예산과목', '처리방법', '전표 합계(천원)'], 13)
    details = _rows(rec, 'details', ['묶음ID', '원장', '지사', '예산과목', '집계표 원본행', '사업명', '기준 실적(천원)', '반영 실적(천원)'], 8)
    excludes = _rows(rec, 'exclusions', ['원장', '지사', '예산과목', '전표텍스트', '제외 금액(천원)'], 8)
    group_map, group_sum, seen_projects, records = {}, defaultdict(int), set(), []
    for row in groups:
        gid = _text(row[0])
        if gid in group_map:
            raise ValueError('같은 묶음이 두 번 들어 있습니다.')
        group_map[gid] = (_scope(*row[1:4]), _won(row[5]))
    for row in details:
        gid, ledger, org, account, source_row, biz, reference, allocated = row
        scope = _scope(ledger, org, account)
        if gid not in group_map or scope != group_map[gid][0]:
            raise ValueError('묶음과 사업의 지사·과목이 다릅니다.')
        if not isinstance(source_row, int) or isinstance(source_row, bool) or source_row < 1:
            raise ValueError('집계표 원본행 ID가 필요합니다.')
        identity = (*scope, source_row)
        if identity in seen_projects:
            raise ValueError('같은 사업행의 중복 배정입니다.')
        seen_projects.add(identity)
        value = _won(allocated)
        group_sum[gid] += value
        records.append(dict(zip(COLUMNS, [scope[1], year, scope[2], value, _text(biz), ledger, gid, source_row])))
    for gid, (_, value) in group_map.items():
        if gid not in group_sum or group_sum[gid] != value:
            raise ValueError('묶음 원천금액과 사업 배정 합계가 일치하지 않습니다.')
    if not records:
        raise ValueError('연결할 사업 배정 결과가 없습니다.')
    source_totals, assigned, excluded = defaultdict(int), defaultdict(int), defaultdict(int)
    for item in data['sourceTotals']:
        if not isinstance(item, dict):
            raise ValueError('원천 합계 형식 오류')
        scope = _scope(item.get('ledger'), item.get('org') or '(지사 미확인)', item.get('account') or '(과목 미확인)')
        source_totals[scope] += _won(item.get('amountWon'), 1)
    for scope, value in group_map.values():
        assigned[scope] += value
    for row in excludes:
        excluded[_scope(*row[:3])] += _won(row[4])
    if (set(assigned) | set(excluded)) - set(source_totals):
        raise ValueError('배정/제외한 지사·과목의 원천 합계가 없습니다.')
    reconciliation = []
    for scope, source in sorted(source_totals.items()):
        reconciliation.append(dict(zip(['원장','사업장','예산과목','원천순액(원)','연결금액(원)','제외금액(원)','미배정순액(원)'],
            [*scope, source, assigned[scope], excluded[scope], source-assigned[scope]-excluded[scope]])))
    return data, pd.DataFrame(records, columns=COLUMNS), pd.DataFrame(reconciliation)

def save_result(content, year):
    data, frame, summary = prepare_result(content, year)
    payload = json.dumps(data, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    digest = hashlib.sha256(payload).hexdigest()
    STORE.mkdir(parents=True, exist_ok=True)
    record = {'year':year, 'sha256':digest, 'savedAt':datetime.now(timezone.utc).isoformat(), 'result':data}
    # 버전 파일은 덮어쓰지 않음. 연도별 포인터만 원자적으로 갱신.
    version = STORE / f'{year}-{digest}.json'
    if not version.exists():
        with version.open('x', encoding='utf-8') as f:
            json.dump(record, f, ensure_ascii=False)
    pointer = STORE / f'active-{year}.json'
    temporary = STORE / f'.{uuid.uuid4().hex}.tmp'
    temporary.write_text(json.dumps({'year':year,'file':version.name}), encoding='utf-8')
    os.replace(temporary, pointer)
    return frame, summary

def load_saved():
    frames, summaries = [], []
    for path in sorted(STORE.glob('active-*.json')):
        pointer = json.loads(path.read_text(encoding='utf-8'))
        name = pointer['file']
        if Path(name).name != name:
            raise ValueError('잘못된 저장 경로입니다.')
        record = json.loads((STORE/name).read_text(encoding='utf-8'))
        if pointer['year'] != record['year']:
            raise ValueError('저장 연도가 일치하지 않습니다.')
        payload = json.dumps(record['result'], ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        if hashlib.sha256(payload).hexdigest() != record['sha256']:
            raise ValueError('저장한 실적 파일이 변경되었습니다.')
        _, frame, summary = prepare_result(payload, record['year'])
        summary.insert(0, '연도', record['year'])
        frames.append(frame); summaries.append(summary)
    return (pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=COLUMNS),
            pd.concat(summaries, ignore_index=True) if summaries else pd.DataFrame())
