"""
손익예산실적집계표(양식2) / 자본예산실적집계표(양식3)의 '(작성불필요)종합표' 시트에
이미 들어있는 예산과목 목록을 그대로 코드에 내장해서 사용한다.
이렇게 하면 별도의 손익/자본 매핑 화면 없이도 예산과목만 보면 자동으로 구분된다.
"""

# 예산과목명이 데이터 소스에 따라 다르게 표기되는 경우가 있어(예: 예산계획과 실적데이터가 서로 다른 표기 사용),
# 여러 표기를 하나의 정식 명칭으로 정규화한다. {실제로 나타날 수 있는 표기: 정식 명칭}
ACCOUNT_NAME_ALIASES = {
    "수선유지비-열원보완개선및기타": "수선유지비-열원보완및개선",
    "건가-외주비-열원정기점검": "외주비-열원정기점검",
}


def normalize_account_name(name) -> str:
    """예산과목/계정과목 표기를 정식 명칭으로 통일한다. 별칭이 아니면 그대로(공백만 정리) 반환."""
    if name is None:
        return name
    s = str(name).strip()
    return ACCOUNT_NAME_ALIASES.get(s, s)


PROFIT_LOSS_ACCOUNTS = {
    "수선유지비-건물/구축물",
    "수선유지비-열원정기점검",
    "수선유지비-열원경상정비",
    "수선유지비-열원정기유지보수",
    "수선유지비-열원보완및개선",
    "지급수수료-열원점검수수료",
}

CAPITAL_ACCOUNTS = {
    "기계장치",
    "공구와기구-열원시설공기구",
    "저장품-열원(보수)",
    "건설중인자산-재생고온부품",
    "건설중인자산-자산화예비품",
    "외주비-열원정기점검",
    "외주비-열원공사비",
    "재료비-열원자재비",
    "외주비-열원기술용역비",
    "건물",
    "구축물",
    "외주비-기타",
}


def get_category_for_account(account) -> str:
    """예산과목(계정과목) 문자열을 받아 '손익' / '자본' / '미매핑'을 반환한다."""
    if account is None:
        return "미매핑"
    normalized = normalize_account_name(account)
    if normalized in PROFIT_LOSS_ACCOUNTS:
        return "손익"
    if normalized in CAPITAL_ACCOUNTS:
        return "자본"
    return "미매핑"
