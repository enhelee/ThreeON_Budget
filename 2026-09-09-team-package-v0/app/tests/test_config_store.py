import math

from budget import config_store

def test_seed_dept_config_is_year_aware():
    """양산지사는 2023년 DH, 2025년 중대형CHP 다 — 둘 다 맞고 연도가 다를 뿐이다.

    2023년에는 발전설비 건설 중이라 공식적으로 DH지사였고, 준공 후
    중대형CHP지사가 되었다. 연도 축 없는 시드 하나로는 담을 수 없다.
    """
    g2023 = {i["이름"]: i["그룹"] for i in config_store.seed_dept_config("2023")}
    g2025 = {i["이름"]: i["그룹"] for i in config_store.seed_dept_config("2025")}
    assert g2023["양산지사"] == "DH"
    assert g2025["양산지사"] == "중대형CHP"
    # 대구·청주도 같은 시기에 올라갔다
    assert g2023["대구지사"] == "소형CHP"
    assert g2025["대구지사"] == "중대형CHP"


def test_seed_dept_config_unknown_year_uses_nearest_past():
    """시드에 없는 연도는 가장 가까운 과거 연도를 쓴다."""
    g2026 = {i["이름"]: i["그룹"] for i in config_store.seed_dept_config("2026")}
    assert g2026["양산지사"] == "중대형CHP"      # 2025 를 물려받는다
    g2020 = {i["이름"]: i["그룹"] for i in config_store.seed_dept_config("2020")}
    assert g2020["양산지사"] == "DH"             # 과거가 없으면 가장 이른 시드


def test_seed_dept_config_shape():
    items = config_store.seed_dept_config("2025")
    assert len(items) == 24
    assert all(i["그룹"] in config_store.DEPT_GROUPS for i in items)
    names = [i["이름"] for i in items]
    assert "플랜트기술처" in names and "화성지사" in names and "평택지사" in names
    assert all(i["포함"] is True for i in items)


def test_seed_item_config_pl_and_capital():
    pl = config_store.seed_item_config("2025", "손익")
    cap = config_store.seed_item_config("2025", "자본")
    assert len(pl) == 8
    assert len(cap) == 11
    names = {x["과목"] for x in pl}
    assert "수선유지비-열원보완및개선" in names  # 25년 개명된 표기
    simui = {x["과목"] for x in pl if x["심의대상"]}
    assert simui == {"수선유지비-건물/구축물", "수선유지비-열원보완및개선"}
    assert all(not x["심의대상"] for x in cap)


def test_to_bool_defaults():
    assert config_store.to_bool(None, True) is True
    assert config_store.to_bool(math.nan, False) is False
    assert config_store.to_bool("FALSE", True) is False
    assert config_store.to_bool(0, True) is False


def test_seed_item_alias_matches_team_v2_aliases():
    # 팀 v2 앱 builtin_categories.ACCOUNT_NAME_ALIASES와 동일해야 두 앱의 과목 정규화가 일치한다
    alias = config_store.seed_item_alias()
    assert alias["수선유지비-열원보완개선및기타"] == "수선유지비-열원보완및개선"
    assert alias["건가-외주비-열원정기점검"] == "외주비-열원정기점검"
    from budget import normalize
    assert normalize.normalize_item("건가-외주비-열원정기점검", alias) == "외주비-열원정기점검"
