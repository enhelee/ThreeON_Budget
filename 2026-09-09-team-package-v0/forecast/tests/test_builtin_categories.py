from builtin_categories import normalize_account_name, get_category_for_account


def test_normalize_known_alias():
    assert normalize_account_name("수선유지비-열원보완개선및기타") == "수선유지비-열원보완및개선"


def test_normalize_passthrough_and_strips_whitespace():
    assert normalize_account_name("  기계장치  ") == "기계장치"


def test_normalize_none_returns_none():
    assert normalize_account_name(None) is None


def test_profit_loss_account_classified():
    assert get_category_for_account("수선유지비-건물/구축물") == "손익"


def test_capital_account_classified():
    assert get_category_for_account("기계장치") == "자본"


def test_alias_is_classified_via_normalization():
    assert get_category_for_account("수선유지비-열원보완개선및기타") == "손익"


def test_unknown_account_is_unmapped():
    assert get_category_for_account("존재하지않는계정") == "미매핑"


def test_none_account_is_unmapped():
    assert get_category_for_account(None) == "미매핑"
