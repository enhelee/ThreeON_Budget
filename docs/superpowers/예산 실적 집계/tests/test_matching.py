import pandas as pd
from budget import matching


def _erp():
    return pd.DataFrame([
        # 계획 사업A와 유사 (같은 과목/처지사) -> 귀속
        {"계정코드": "60909002", "예산과목원문": "수선유지비-열원정기점검", "연도": "2025",
         "전표번호": "T1", "금액원": 10_000_000, "금액천원": 10000.0,
         "사업명": "2025년 화성지사 정기점검 보수공사", "지사원문": "화성지사"},
        # 같은 계획 사업A에 추가 귀속
        {"계정코드": "60909002", "예산과목원문": "수선유지비-열원정기점검", "연도": "2025",
         "전표번호": "T2", "금액원": 5_000_000, "금액천원": 5000.0,
         "사업명": "화성지사 정기점검 보수공사 2025", "지사원문": "화성지사"},
        # 신규(계획에 유사 사업 없음)
        {"계정코드": "60909002", "예산과목원문": "수선유지비-열원정기점검", "연도": "2025",
         "전표번호": "T3", "금액원": 3_000_000, "금액천원": 3000.0,
         "사업명": "완전히 다른 긴급 임시 공사 건", "지사원문": "화성지사"},
        # 다른 예산(자본) 과목 -> 손익 실행시 제외
        {"계정코드": "20702001", "예산과목원문": "건물", "연도": "2025",
         "전표번호": "T4", "금액원": 9_000_000, "금액천원": 9000.0,
         "사업명": "신축", "지사원문": "화성지사"},
    ])


def _erp_norm(df):
    df = df.copy()
    df["과목정규"] = df["예산과목원문"]
    df["처지사정규"] = df["지사원문"]
    return df


def _plan():
    return pd.DataFrame([
        {"_row": 4, "예산과목": "수선유지비-열원정기점검", "처지사": "화성지사",
         "사업명": "화성지사 정기점검 보수공사", "연예산": 20000.0},
        {"_row": 5, "예산과목": "수선유지비-열원정기점검", "처지사": "청주지사",
         "사업명": "청주지사 정기점검", "연예산": 8000.0},  # 실적 없음 -> 미시행
    ])


def test_match_group_policy_default():
    """그룹정책(기본): 계획행 있는 그룹의 전표는 사업명 달라도 계획집행 귀속."""
    pl = {"수선유지비-열원정기점검"}
    cap = {"건물"}
    res = matching.match_actuals(_plan(), _erp_norm(_erp()), pl, pl, cap, threshold=80)

    prows = res["plan_rows"]
    # 화성지사: T1+T2+T3 모두 귀속(그룹에 계획행 존재) = 18000
    hs = [r for r in prows if r["처지사"] == "화성지사"][0]
    assert hs["실적금액"] == 18000.0
    assert hs["구분"] == "계획집행"
    assert hs["매칭전표수"] == 3
    assert hs["저유사전표수"] == 1  # T3는 사업명 미달이나 그룹정책상 귀속
    # 청주지사: ERP 없음 -> 미시행
    cj = [r for r in prows if r["처지사"] == "청주지사"][0]
    assert cj["구분"] == "미시행"
    # 신규 없음(모든 손익전표가 화성 그룹 소속), 자본 T4는 제외
    assert len(res["new_rows"]) == 0
    total = sum(r["실적금액"] for r in prows) + sum(r["실적금액"] for r in res["new_rows"])
    assert total == 18000.0


def test_small_amount_lumped_as_execution_title():
    """소액(≤2,000천원) 신규 전표는 (지사×과목)별 '집행'으로 일괄 확정."""
    erp = pd.DataFrame([
        {"계정코드": "60909002", "예산과목원문": "수선유지비-열원정기점검", "연도": "2025",
         "전표번호": "S1", "금액원": 1_500_000, "금액천원": 1500.0,
         "사업명": "잡다한 소액 A", "지사원문": "대구지사"},
        {"계정코드": "60909002", "예산과목원문": "수선유지비-열원정기점검", "연도": "2025",
         "전표번호": "S2", "금액원": 800_000, "금액천원": 800.0,
         "사업명": "잡다한 소액 B", "지사원문": "대구지사"},
    ])
    pl = {"수선유지비-열원정기점검"}
    # 대구지사에는 계획행 없음 → 신규. 둘 다 소액 → 소액집행 1행으로 묶임.
    res = matching.match_actuals(_plan(), _erp_norm(erp), pl, pl, set(),
                                 threshold=80, small_threshold=2000)
    smalls = [r for r in res["new_rows"] if r["구분"] == "신규(소액집행)"]
    assert len(smalls) == 1
    assert smalls[0]["사업명"] == "대구지사 수선유지비-열원정기점검 집행"
    assert smalls[0]["실적금액"] == 2300.0


def test_match_strict_name_policy():
    """엄격정책: 사업명 유사도 미달 전표는 신규로 분리."""
    pl = {"수선유지비-열원정기점검"}
    cap = {"건물"}
    res = matching.match_actuals(_plan(), _erp_norm(_erp()), pl, pl, cap,
                                 threshold=80, new_policy="strict_name")
    prows = res["plan_rows"]
    hs = [r for r in prows if r["처지사"] == "화성지사"][0]
    assert hs["실적금액"] == 15000.0  # T1,T2만
    assert hs["매칭전표수"] == 2
    assert len(res["new_rows"]) == 1  # T3
    assert res["new_rows"][0]["실적금액"] == 3000.0
