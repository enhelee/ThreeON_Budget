import pandas as pd
import pytest
import budget_actual_summary as bas


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    site_type_map = pd.DataFrame([
        {"사업장": "9001", "표시명": "화성지사", "지사유형": "중대형CHP", "적용시작연도": 1900},
        {"사업장": "700001", "표시명": "화성지사", "지사유형": "중대형CHP", "적용시작연도": 1900},
        # get_current_site_type()은 get_site_display_name()이 반환한 "표시명"을 다시
        # site_type_map의 "사업장" 컬럼으로 조회한다(운영 환경의 기본 시드 데이터가 이 형태다) -
        # 그래서 표시명 자체를 "사업장"으로 하는 행도 있어야 지사유형이 조회된다.
        {"사업장": "화성지사", "표시명": "화성지사", "지사유형": "중대형CHP", "적용시작연도": 1900},
    ])
    site_type_map.to_csv(tmp_path / "site_type_map.csv", index=False)
    monkeypatch.chdir(tmp_path)
    yield tmp_path


def test_budget_by_site_type_account_aggregates_and_normalizes(isolated):
    budget_df = pd.DataFrame([
        {"예산귀속 \n부서코드": "700001", "예산과목": "수선유지비-열원경상정비", "연예산 합계": 100.0},
        {"예산귀속 \n부서코드": "700001", "예산과목": "수선유지비-열원경상정비", "연예산 합계": 50.0},
        {"예산귀속 \n부서코드": "700001", "예산과목": "기계장치", "연예산 합계": 30.0},
    ])
    result = bas.budget_by_site_type_account(budget_df)
    row = result[result["계정과목"] == "수선유지비-열원경상정비"].iloc[0]
    assert row["지사유형"] == "중대형CHP"
    assert row["손익자본구분"] == "손익"
    assert row["배정"] == pytest.approx(150.0)

    row2 = result[result["계정과목"] == "기계장치"].iloc[0]
    assert row2["손익자본구분"] == "자본"
    assert row2["배정"] == pytest.approx(30.0)


def test_budget_by_site_type_account_empty_returns_empty_frame():
    result = bas.budget_by_site_type_account(pd.DataFrame())
    assert result.empty
    assert list(result.columns) == ["지사유형", "계정과목", "손익자본구분", "배정"]


def test_actual_by_site_type_account_aggregates(isolated):
    actual_df = pd.DataFrame([
        {"사업장명": "화성지사", "지사유형": "중대형CHP", "계정과목": "수선유지비-열원경상정비", "금액": 40.0},
        {"사업장명": "화성지사", "지사유형": "중대형CHP", "계정과목": "수선유지비-열원경상정비", "금액": 60.0},
    ])
    result = bas.actual_by_site_type_account(actual_df)
    row = result.iloc[0]
    assert row["지사유형"] == "중대형CHP"
    assert row["계정과목"] == "수선유지비-열원경상정비"
    assert row["실적"] == pytest.approx(100.0)


def test_merge_budget_actual_computes_remainder_and_rate():
    budget_summary = pd.DataFrame([
        {"지사유형": "중대형CHP", "계정과목": "수선유지비-열원경상정비", "손익자본구분": "손익", "배정": 100.0},
    ])
    actual_summary = pd.DataFrame([
        {"지사유형": "중대형CHP", "계정과목": "수선유지비-열원경상정비", "손익자본구분": "손익", "실적": 80.0},
    ])
    merged = bas.merge_budget_actual(budget_summary, actual_summary)
    row = merged.iloc[0]
    assert row["잔액"] == pytest.approx(20.0)
    assert row["실적률(%)"] == pytest.approx(80.0)


def test_merge_budget_actual_handles_actual_only_and_budget_only_rows():
    budget_summary = pd.DataFrame([
        {"지사유형": "중대형CHP", "계정과목": "A", "손익자본구분": "손익", "배정": 100.0},
    ])
    actual_summary = pd.DataFrame([
        {"지사유형": "중대형CHP", "계정과목": "B", "손익자본구분": "손익", "실적": 50.0},
    ])
    merged = bas.merge_budget_actual(budget_summary, actual_summary)
    a_row = merged[merged["계정과목"] == "A"].iloc[0]
    b_row = merged[merged["계정과목"] == "B"].iloc[0]
    assert a_row["실적"] == 0.0
    assert a_row["실적률(%)"] == pytest.approx(0.0)
    assert b_row["배정"] == 0.0
    assert pd.isna(b_row["실적률(%)"])  # 배정이 0이면 실적률을 나눌 수 없다(float 컬럼이라 NaN으로 저장됨)


def test_site_type_summary_table_has_totals_column():
    merged = pd.DataFrame([
        {"지사유형": "중대형CHP", "계정과목": "A", "손익자본구분": "손익", "배정": 100_000_000.0, "실적": 80_000_000.0, "잔액": 20_000_000.0, "실적률(%)": 80.0},
        {"지사유형": "소형CHP", "계정과목": "A", "손익자본구분": "손익", "배정": 50_000_000.0, "실적": 50_000_000.0, "잔액": 0.0, "실적률(%)": 100.0},
    ])
    table = bas.site_type_summary_table(merged)
    assert "합계" in table.columns
    budget_row = table.loc[("손익예산", "배정")]
    assert budget_row["중대형CHP"] == pytest.approx(1.0)  # 1억원
    assert budget_row["소형CHP"] == pytest.approx(0.5)
    assert budget_row["합계"] == pytest.approx(1.5)


def test_account_detail_table_sorts_by_budget_descending():
    merged = pd.DataFrame([
        {"지사유형": "중대형CHP", "계정과목": "작은계정", "손익자본구분": "손익", "배정": 10_000_000.0, "실적": 5_000_000.0},
        {"지사유형": "중대형CHP", "계정과목": "큰계정", "손익자본구분": "손익", "배정": 90_000_000.0, "실적": 90_000_000.0},
    ])
    table = bas.account_detail_table(merged, "손익")
    assert table.index.tolist() == ["큰계정", "작은계정"]
    assert table.loc["큰계정", "실적률(%)"] == pytest.approx(100.0)


def test_account_detail_table_empty_category_returns_empty():
    merged = pd.DataFrame([
        {"지사유형": "중대형CHP", "계정과목": "A", "손익자본구분": "손익", "배정": 1.0, "실적": 1.0},
    ])
    table = bas.account_detail_table(merged, "자본")
    assert table.empty
