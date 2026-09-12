from budget import org_structure

def test_build_dept_columns_order_and_filter():
    dept_config = [
        {"이름": "플랜트기술처", "그룹": "본사", "포함": True},
        {"이름": "안전처", "그룹": "본사", "포함": False},
        {"이름": "화성지사", "그룹": "중대형CHP", "포함": True},
        {"이름": "판교지사", "그룹": "DH", "포함": True},
        {"이름": "강남지사", "그룹": "소형CHP", "포함": False},
    ]
    cols = org_structure.build_dept_columns(dept_config)
    groups = [c["그룹"] for c in cols]
    assert groups == ["본사", "중대형CHP", "DH"]  # 소형CHP는 포함된 지사 없어 제외
    assert cols[0]["지사"] == ["플랜트기술처"]
    assert cols[1]["지사"] == ["화성지사"]

def test_build_item_rows_grouping_and_simui():
    item_config = [
        {"과목": "수선유지비-건물/구축물", "대분류": "수선유지비", "심의대상": True, "포함": True},
        {"과목": "수선유지비-열원경상정비", "대분류": "수선유지비", "심의대상": False, "포함": True},
        {"과목": "지급수수료-열원점검수수료", "대분류": "지급수수료", "심의대상": False, "포함": True},
        {"과목": "제외과목", "대분류": "수선유지비", "심의대상": False, "포함": False},
    ]
    rows = org_structure.build_item_rows(item_config)
    assert [r["대분류"] for r in rows] == ["수선유지비", "지급수수료"]
    assert len(rows[0]["과목들"]) == 2
    assert rows[0]["과목들"][0] == {"과목": "수선유지비-건물/구축물", "심의대상": True}
