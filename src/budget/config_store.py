# -*- coding: utf-8 -*-
"""지사구성·예산과목구성 JSON 영속화. 연도별(및 과목은 손익/자본별)로 저장·자동 로드."""
import json
import os

DEPT_GROUPS = ["본사", "중대형CHP", "소형CHP", "DH"]
SIMUI_THRESHOLD_THOUSAND = 50000

_SEED_DEPTS = {
    "본사": ["플랜트기술처", "안전처", "통합운영처", "건설처", "미래사업처"],
    "중대형CHP": ["동탄지사", "화성지사", "파주지사", "광교지사", "판교지사", "삼송지사", "대구지사", "청주지사"],
    "소형CHP": ["수원사업소", "광주전남지사", "강남지사"],
    "DH": ["중앙지사", "고양사업소", "용인지사", "분당사업소", "세종지사", "김해사업소", "양산지사", "평택지사"],
}


def seed_dept_config():
    out = []
    for g in DEPT_GROUPS:
        for name in _SEED_DEPTS[g]:
            out.append({"이름": name, "그룹": g, "포함": True})
    return out


def _dept_path(config_dir, year):
    return os.path.join(config_dir, f"지사구성_{year}.json")


def load_dept_config(config_dir, year):
    path = _dept_path(config_dir, year)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return seed_dept_config()


def save_dept_config(config_dir, year, items):
    os.makedirs(config_dir, exist_ok=True)
    with open(_dept_path(config_dir, year), "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)


SEED_ITEMS = {
    "손익": [
        {"과목": "수선유지비-건물/구축물", "대분류": "수선유지비", "심의대상": True},
        {"과목": "수선유지비-열원정기점검", "대분류": "수선유지비", "심의대상": False},
        {"과목": "수선유지비-열원경상정비", "대분류": "수선유지비", "심의대상": False},
        {"과목": "수선유지비-열원정기유지보수", "대분류": "수선유지비", "심의대상": False},
        {"과목": "수선유지비-열원보완개선및기타", "대분류": "수선유지비", "심의대상": True},
        {"과목": "수선유지비-비저장품(보수자재)", "대분류": "수선유지비", "심의대상": False},
        {"과목": "수선유지비-소모품(자재공기구)", "대분류": "수선유지비", "심의대상": False},
        {"과목": "지급수수료-열원점검수수료", "대분류": "지급수수료", "심의대상": False},
    ],
    "자본": [
        {"과목": "건물", "대분류": "자산", "심의대상": False},
        {"과목": "구축물", "대분류": "자산", "심의대상": False},
        {"과목": "기계장치", "대분류": "자산", "심의대상": False},
        {"과목": "공구와기구-열원시설공기구", "대분류": "자산", "심의대상": False},
        {"과목": "저장품-열원(보수)", "대분류": "예비품", "심의대상": False},
        {"과목": "건설중인자산-재생고온부품", "대분류": "예비품", "심의대상": False},
        {"과목": "건설중인자산-자산화예비품", "대분류": "예비품", "심의대상": False},
        {"과목": "외주비-열원정기점검", "대분류": "A급정비", "심의대상": False},
        {"과목": "외주비-열원공사비", "대분류": "건설공사", "심의대상": False},
        {"과목": "재료비-열원자재비", "대분류": "건설공사", "심의대상": False},
        {"과목": "외주비-열원기술용역비", "대분류": "건설공사", "심의대상": False},
    ],
}


def seed_item_config(budget):
    return [dict(x, 포함=True) for x in SEED_ITEMS[budget]]


def _item_path(config_dir, year, budget):
    return os.path.join(config_dir, f"과목구성_{year}_{budget}.json")


def load_item_config(config_dir, year, budget):
    path = _item_path(config_dir, year, budget)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return seed_item_config(budget)


def save_item_config(config_dir, year, budget, items):
    os.makedirs(config_dir, exist_ok=True)
    with open(_item_path(config_dir, year, budget), "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
