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


def test_learn_key_collapses_installment_and_period_markers():
    """회차·월·분기·연도 마커만 다른 반복 전표는 같은 학습키로 모인다.
    → 한 번 사람이 확정하면 다음 해 같은 계약 전표가 자동확정(재검토 방지)."""
    lk = normalize.learn_key
    # 회차만 다른 LTSA 기성 → 동일 키
    assert lk("가스터빈 LTSA 29회 기성(원화-고정비)") == lk("가스터빈 LTSA 33회 기성(원화-고정비)")
    # 월만 다른 소방 용역 → 동일 키
    assert lk("24년 소방 용역 12월") == lk("25년 소방 용역 3월")
    # 연도·월만 다른 비용인식 → 동일 키
    assert lk("GT LTSA '25년 2월 비용인식") == lk("GT LTSA '24년 11월 비용역인식")
    # 서로 다른 사업은 여전히 구분된다
    assert lk("가스터빈 LTSA 1회 기성") != lk("스팀터빈 정비 1회 기성")
    assert lk(None) is None
