from budget import normalize

PLAN_DEPTS = {
    "플랜트기술처", "안전처", "통합운영처", "건설처", "미래사업처",
    "동탄지사", "화성지사", "파주지사", "광교지사", "판교지사", "삼송지사",
    "대구지사", "청주지사", "수원사업소", "광주전남지사", "강남지사",
    "중앙지사", "고양사업소", "용인지사", "분당사업소", "세종지사",
    "김해사업소", "양산지사", "평택지사",
}
DEPT_ALIAS = {
    "판교사업소": "판교지사", "분당지사": "분당사업소",
    "서울중앙지사": "중앙지사", "대구우드칩": "대구지사", "미래개발원": "미래사업처",
}


def test_item_alias():
    m = {"수선유지비-열원보완및개선": "수선유지비-열원보완개선및기타"}
    assert normalize.normalize_item("수선유지비-열원보완및개선", m) == "수선유지비-열원보완개선및기타"
    assert normalize.normalize_item("수선유지비-건물/구축물", m) == "수선유지비-건물/구축물"
    assert normalize.normalize_item(None, m) is None


def test_dept_exact_and_paren_strip():
    assert normalize.normalize_dept("화성지사", PLAN_DEPTS, DEPT_ALIAS) == "화성지사"
    assert normalize.normalize_dept("중앙지사(상암)", PLAN_DEPTS, DEPT_ALIAS) == "중앙지사"
    assert normalize.normalize_dept("강남(동남권)", PLAN_DEPTS, DEPT_ALIAS) == "강남지사"


def test_dept_prefix_rule():
    assert normalize.normalize_dept("대구", PLAN_DEPTS, DEPT_ALIAS) == "대구지사"
    assert normalize.normalize_dept("고양(KINTEX)", PLAN_DEPTS, DEPT_ALIAS) == "고양사업소"
    assert normalize.normalize_dept("수원(RPS 태양광)", PLAN_DEPTS, DEPT_ALIAS) == "수원사업소"


def test_dept_override():
    assert normalize.normalize_dept("판교사업소", PLAN_DEPTS, DEPT_ALIAS) == "판교지사"
    assert normalize.normalize_dept("분당지사", PLAN_DEPTS, DEPT_ALIAS) == "분당사업소"
    assert normalize.normalize_dept("서울중앙지사", PLAN_DEPTS, DEPT_ALIAS) == "중앙지사"


def test_dept_unmapped_returns_none():
    # 로컬 맵에 없으면 None (실제 앱은 SEED_DEPT_ALIAS로 매핑)
    assert normalize.normalize_dept("본　　사", PLAN_DEPTS, DEPT_ALIAS) is None


def test_dept_from_text_j_column():
    assert normalize.dept_from_text("(CHP)광교지사 고객지원부", PLAN_DEPTS) == "광교지사"
    assert normalize.dept_from_text("(지사공통)강남지사 고객지원부", PLAN_DEPTS) == "강남지사"
    assert normalize.dept_from_text("본사 총무부", PLAN_DEPTS) is None
