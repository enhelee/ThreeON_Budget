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
    assert "수선유지비-열원보완개선및기타" in names
    assert "수선유지비-열원보완및개선" not in names
    simui = {x["과목"] for x in pl if x["심의대상"]}
    assert simui == {"수선유지비-건물/구축물", "수선유지비-열원보완개선및기타"}
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
