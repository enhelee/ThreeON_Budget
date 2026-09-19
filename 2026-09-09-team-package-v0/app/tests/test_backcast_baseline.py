# -*- coding: utf-8 -*-
"""표준화 역산 — 성질(불변식)과 실데이터 기준선.

Phase 6-3. 원래 계획은 설계서 §5 의 「23년만으로 산출한 벤치마크로 23년 실적을
역산」을 게이트로 삼는 것이었다. **실측해 보니 그 게이트는 공허하다** — v2 알고리즘은
지사×과목 단위 합계를 쓰므로, 한 해만 넣으면 표준금액이 곧 그 해 금액이 되어
역산 오차가 구조적으로 정확히 0이 된다. 통과가 보장된 시험은 아무것도 증명하지 않는다.
(설계서 §2.3 의 「설비 1기당 · 중위수 · MAD 절사」 정의였다면 공허하지 않았겠지만,
 채택된 기준선은 v2 구현이다.)

2023년 수기 분석본(정답지)이 없다는 것도 확인됐다(사용자 2026-09-19). 그래서 게이트를
「정답과 일치」가 아니라 **「지금 알고리즘이 내는 값을 기록해 두고, 바뀌면 드러나게」**
로 바꾼다. 알고리즘 고도화는 서버에서 이어 간다는 것이 사용자 결정이므로, 그때
무엇이 얼마나 달라졌는지 즉시 보이는 것이 지금 할 수 있는 가장 쓸모 있는 일이다.

  앞쪽 — 합성 데이터 성질 테스트. 어디서나 돈다.
  뒤쪽 — 실데이터 기준선. 개발자 PC 의 budget.db 가 있을 때만 돈다.

측정 근거와 해석: docs/superpowers/specs/2026-09-19-표준화-기준선.md
"""
import os

import pandas as pd
import pytest

from budget import benchmark

EMPTY_GRADE = pd.DataFrame(columns=["사업장", "연도", "등급"])


def _actuals(rows):
    return pd.DataFrame(rows, columns=["사업장", "연도", "예산과목", "금액"])


def _backcast(bench, actuals, year):
    """표준금액을 그 해 실적으로 되돌려 지사별로 합친다."""
    b = bench.set_index(["사업장", "예산과목"])["표준금액"]
    a = actuals[actuals["연도"] == year].groupby(["사업장", "예산과목"])["금액"].sum()
    j = pd.DataFrame({"실적": a}).join(pd.DataFrame({"역산": b}), how="left").fillna(0.0)
    g = j.groupby(level=0)[["실적", "역산"]].sum()
    return g[g["실적"] != 0]


# ── 성질 ─────────────────────────────────────────────────────────────────────

def test_single_year_backcast_is_identity_so_the_planned_gate_is_vacuous():
    """한 해만 넣으면 역산이 항등이 된다 — 설계서가 말한 게이트가 공허한 이유.

    이 사실을 테스트로 박제해 둔다. 나중에 표준금액 정의를 바꾸면(설비 단위 분모·
    중위수·절사) 이 테스트가 깨질 것이고, 그때가 곧 「게이트를 되살릴 수 있다」는 신호다.
    """
    act = _actuals([
        ("화성지사", 2023, "수선유지비-열원경상정비", 1000.0),
        ("화성지사", 2023, "기계장치", 500.0),
        ("강남지사", 2023, "수선유지비-열원경상정비", 300.0),
    ])
    g = _backcast(benchmark.compute_standard_amounts(act, EMPTY_GRADE), act, 2023)
    assert (g["역산"] - g["실적"]).abs().max() == pytest.approx(0.0)


def test_two_years_pick_only_recent_or_three_year_average():
    """마감 연도가 둘뿐이면 방식은 두 가지로만 갈린다(정비등급 이력이 없을 때).

    변동이 작으면 최근실적, 아니면 3개년 평균이다. 「등급별 평균」은 등급 이력이
    있어야 나오고, 「5개년 평균」은 5개년이 있어야 나온다. 표본이 얇다는 사실이
    방식 선택에 그대로 드러난다 — 설계서 §2.4 가 걱정한 지점이다.
    """
    act = _actuals([
        ("화성지사", 2023, "수선유지비-열원경상정비", 1000.0),
        ("화성지사", 2025, "수선유지비-열원경상정비", 1050.0),   # 변동 작음
        ("강남지사", 2023, "기계장치", 100.0),
        ("강남지사", 2025, "기계장치", 900.0),                   # 변동 큼
    ])
    bench = benchmark.compute_standard_amounts(act, EMPTY_GRADE)
    by_site = dict(zip(bench["사업장"], bench["산출방식"]))
    assert by_site["화성지사"] == "최근실적"
    assert by_site["강남지사"] == "3개년 평균"
    assert set(bench["산출방식"]) <= {"최근실적", "3개년 평균"}


def test_missing_combinations_do_not_become_zero_rows():
    """없는 (지사×과목)은 행을 만들지 않는다 — 결측을 0으로 채우지 않는다.

    연계규격 §1 의 「결측은 None 유지」와 같은 이유다. 0 으로 채우면 4단계가
    「실적이 0이었다」로 읽어 10개년 전망을 끌어내린다.
    """
    act = _actuals([
        ("화성지사", 2023, "수선유지비-열원경상정비", 1000.0),
        ("강남지사", 2023, "기계장치", 500.0),
    ])
    bench = benchmark.compute_standard_amounts(act, EMPTY_GRADE)
    assert len(bench) == 2
    assert not ((bench["사업장"] == "화성지사") & (bench["예산과목"] == "기계장치")).any()


def test_output_is_structurally_sound():
    """음수 없음 · 모집단 밖 과목 없음 · (지사,과목,등급) 유일."""
    act = _actuals([
        ("화성지사", 2023, "수선유지비-열원경상정비", 1000.0),
        ("화성지사", 2025, "수선유지비-열원경상정비", 1200.0),
        ("화성지사", 2023, "듣도보도못한과목", 999.0),          # 구성 밖 → 빠져야 한다
    ])
    bench = benchmark.compute_standard_amounts(act, EMPTY_GRADE)
    assert (bench["표준금액"] >= 0).all()
    assert bench["예산과목"].isin(benchmark.ALL_ACCOUNTS).all()
    assert not bench.duplicated(["사업장", "예산과목", "등급"]).any()


# ── 실데이터 기준선 ──────────────────────────────────────────────────────────
#
# 개발자 PC 의 budget.db(2023·2025 분석 이력)가 있을 때만 돈다. 저장소에는 없다.
# 숫자는 2026-09-19 측정값이며, 폭을 넉넉히 두되 «크게 달라지면 걸리게» 잡았다.

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REAL_DB = os.path.join(APP_DIR, "data", "budget.db")
KEEP = ("계획집행", "신규", "신규(소액집행)")

pytestmark_real = pytest.mark.skipif(
    not os.path.exists(REAL_DB), reason="개발자 PC 의 budget.db 없음")


@pytest.fixture()
def real_actuals():
    from budget import db as dbm
    conn = dbm.connect(REAL_DB)
    rows = []
    try:
        for year in ("2023", "2025"):
            for budget in ("손익", "자본"):
                run = dbm.latest_run(conn, year, budget)
                if not run:
                    pytest.skip(f"{year}년 {budget} 분석 이력 없음")
                for dept, item, amt, gubun in conn.execute(
                        "SELECT 처지사,예산과목,실적금액,구분 FROM biz_line WHERE run_id=?",
                        (run["id"],)):
                    if gubun in KEEP and amt:
                        rows.append({"사업장": dept, "연도": int(year),
                                     "예산과목": item, "금액": float(amt)})
    finally:
        conn.close()
    return pd.DataFrame(rows)


@pytestmark_real
def test_real_population_shape(real_actuals):
    """모집단 규모 — 자료가 통째로 바뀌면 여기서 먼저 걸린다."""
    total = real_actuals["금액"].sum()
    assert 2.4e8 < total < 3.1e8, f"모집단 합계 {total:,.0f}천원 (기준 276,248,733)"
    assert real_actuals["사업장"].nunique() >= 20


@pytestmark_real
def test_real_benchmark_baseline(real_actuals):
    """2026-09-19 기준선: 벤치마크 203행 · 최근실적 91 / 3개년 평균 112."""
    bench = benchmark.compute_standard_amounts(real_actuals, EMPTY_GRADE)
    assert 180 <= len(bench) <= 230, f"벤치마크 {len(bench)}행 (기준 203)"
    assert (bench["표준금액"] >= 0).all()
    assert not bench.duplicated(["사업장", "예산과목", "등급"]).any()
    assert bench["예산과목"].isin(benchmark.ALL_ACCOUNTS).all()

    share = (bench["산출방식"] == "최근실적").mean()
    assert 0.30 <= share <= 0.60, f"최근실적 비중 {share:.0%} (기준 45%)"
    assert set(bench["산출방식"]) <= {"최근실적", "3개년 평균"}


@pytestmark_real
@pytest.mark.parametrize("year,total_band,median_cap", [
    (2023, 20.0, 30.0),      # 측정 +9.15% · 지사 중위 21.0%
    (2025, 20.0, 25.0),      # 측정 -6.44% · 지사 중위 14.8%
])
def test_real_backcast_error_stays_in_band(real_actuals, year, total_band, median_cap):
    """두 해로 산출한 표준금액을 각 해로 되돌렸을 때의 오차 — 지금 값을 기록해 둔다.

    이 숫자가 「맞다」는 뜻이 아니다. 정답지가 없으므로 맞는지는 알 수 없다.
    알고리즘을 고도화할 때 **얼마나 달라졌는지** 보이게 하는 것이 목적이다.
    """
    bench = benchmark.compute_standard_amounts(real_actuals, EMPTY_GRADE)
    g = _backcast(bench, real_actuals, year)
    total_err = (g["역산"].sum() - g["실적"].sum()) / g["실적"].sum() * 100
    site_err = ((g["역산"] - g["실적"]) / g["실적"] * 100).abs()
    assert abs(total_err) < total_band, f"{year} 전사 오차 {total_err:+.2f}%"
    assert site_err.median() < median_cap, f"{year} 지사 중위 오차 {site_err.median():.1f}%"
