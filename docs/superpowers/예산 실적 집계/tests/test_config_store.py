import json
import math
import os

from budget import config_store

def test_seed_dept_config_groups_and_order():
    items = config_store.seed_dept_config()
    assert all(i["그룹"] in config_store.DEPT_GROUPS for i in items)
    names = [i["이름"] for i in items]
    assert "플랜트기술처" in names
    assert "화성지사" in names
    assert "평택지사" in names
    assert all(i["포함"] is True for i in items)

def test_dept_config_save_and_load_roundtrip(tmp_path):
    cfg_dir = str(tmp_path)
    items = config_store.load_dept_config(cfg_dir, "2026")
    assert len(items) == len(config_store.seed_dept_config())  # 저장 전에는 시드
    items[0]["포함"] = False
    items[0]["그룹"] = "DH"
    config_store.save_dept_config(cfg_dir, "2026", items)
    reloaded = config_store.load_dept_config(cfg_dir, "2026")
    assert reloaded[0]["포함"] is False
    assert reloaded[0]["그룹"] == "DH"

def test_seed_item_config_pl_and_capital():
    pl = config_store.seed_item_config("손익")
    cap = config_store.seed_item_config("자본")
    assert len(pl) == 8
    assert len(cap) == 11
    names = {x["과목"] for x in pl}
    assert "수선유지비-열원보완및개선" in names  # 25년 개명된 표기
    simui = {x["과목"] for x in pl if x["심의대상"]}
    assert simui == {"수선유지비-건물/구축물", "수선유지비-열원보완및개선"}
    assert all(not x["심의대상"] for x in cap)

def test_item_config_save_and_load_roundtrip(tmp_path):
    cfg_dir = str(tmp_path)
    items = config_store.load_item_config(cfg_dir, "2026", "자본")
    items.append({"과목": "신규자본과목", "대분류": "자산", "심의대상": False, "포함": True})
    config_store.save_item_config(cfg_dir, "2026", "자본", items)
    reloaded = config_store.load_item_config(cfg_dir, "2026", "자본")
    assert any(x["과목"] == "신규자본과목" for x in reloaded)
    # 손익 파일과 분리 저장되는지 확인
    pl_reloaded = config_store.load_item_config(cfg_dir, "2026", "손익")
    assert not any(x["과목"] == "신규자본과목" for x in pl_reloaded)


def test_item_config_nan_is_sanitized(tmp_path):
    """st.data_editor가 만든 NaN 체크박스 값이 JSON에 새지 않고 기본값으로 정규화된다.

    NaN은 파이썬에서 truthy라 그대로 두면 '실적반영' 판정이 뒤집히고,
    비표준 토큰 `NaN`이 들어간 JSON은 다른 도구가 읽지 못한다.
    """
    cfg_dir = str(tmp_path)
    items = [
        {"과목": "기계장치", "대분류": "자산", "심의대상": float("nan"),
         "포함": float("nan"), "실적반영": float("nan")},
        {"과목": "외주비-열원공사비", "대분류": "건설공사", "심의대상": False,
         "포함": True, "실적반영": False},
    ]
    config_store.save_item_config(cfg_dir, "2023", "자본", items)
    raw = open(os.path.join(cfg_dir, "과목구성_2023_자본.json"), encoding="utf-8").read()
    assert "NaN" not in raw
    json.loads(raw)                                   # 표준 JSON으로 파싱 가능

    reloaded = config_store.load_item_config(cfg_dir, "2023", "자본")
    assert reloaded[0]["심의대상"] is False            # 누락 → 기본 False
    assert reloaded[0]["포함"] is True                 # 누락 → 기본 True
    assert reloaded[0]["실적반영"] is True             # 누락 → 기본 True
    assert reloaded[1]["실적반영"] is False            # 명시적 False는 보존


def test_to_bool_defaults():
    assert config_store.to_bool(None, True) is True
    assert config_store.to_bool(math.nan, False) is False
    assert config_store.to_bool("FALSE", True) is False
    assert config_store.to_bool(0, True) is False
