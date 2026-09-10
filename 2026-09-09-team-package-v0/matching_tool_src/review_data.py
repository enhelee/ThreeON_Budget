"""Checkpoint exchange format. Monetary columns retain their explicit thousand-KRW unit."""
import json

TABLES = {
    'groups': '금액일치 묶음', 'details': '사업별 배정',
    'corrections': '보정 적용', 'exclusions': '제외 내역',
    'differences': '대응 전표 미확정', 'spareDates': '예비품 날짜',
    'spareSources': '예비품 원천',
}

def load_result(content):
    data = json.loads(content)
    if data.get('schemaVersion') != 1 or data.get('amountUnit') != 'KRW_THOUSAND':
        raise ValueError('지원하지 않는 결과 형식 또는 금액 단위입니다.')
    if data.get('amountMatching') is not True:
        raise ValueError('최종 실적금액 대조 모드로 생성한 결과를 올려주세요.')
    source = data.get('reconciliation')
    if not isinstance(source, dict):
        raise ValueError('대조 내역이 없습니다.')
    for key in TABLES:
        rows = source.get(key)
        if not isinstance(rows, list) or not rows or not all(isinstance(r, list) for r in rows):
            raise ValueError(f'{key}: 표가 없거나 형식이 잘못되었습니다.')
        if not all(isinstance(c, str) for c in rows[0]):
            raise ValueError(f'{key}: 열 이름 형식이 잘못되었습니다.')
        if any(len(r) != len(rows[0]) for r in rows[1:]):
            raise ValueError(f'{key}: 열 개수가 일치하지 않습니다.')
    return source
