# -*- coding: utf-8 -*-
"""지사구성/과목구성 config를 종합표 레이아웃(열/행 그룹)으로 변환."""
from .config_store import DEPT_GROUPS


def build_dept_columns(dept_config):
    by_group = {g: [] for g in DEPT_GROUPS}
    for item in dept_config:
        if item.get("포함") and item.get("그룹") in by_group:
            by_group[item["그룹"]].append(item["이름"])
    return [{"그룹": g, "지사": by_group[g]} for g in DEPT_GROUPS if by_group[g]]


def build_item_rows(item_config):
    order = []
    by_cat = {}
    for item in item_config:
        if not item.get("포함"):
            continue
        cat = item["대분류"]
        if cat not in by_cat:
            by_cat[cat] = []
            order.append(cat)
        by_cat[cat].append({"과목": item["과목"], "심의대상": bool(item.get("심의대상"))})
    return [{"대분류": c, "과목들": by_cat[c]} for c in order]
