# -*- coding: utf-8 -*-
"""9월 HTML 엔진에서 옮긴 매칭 규칙 — IDF 사업 선택 · 구조적 과목 비례 배분."""
import pandas as pd

from budget import matching

GS = "수선유지비-열원정기유지보수"
JG = "수선유지비-열원정기점검"


def _erp(rows):
    df = pd.DataFrame([{"계정코드": None, "예산과목원문": it, "연도": "2025", "전표번호": doc,
                        "금액원": amt * 1000, "금액천원": float(amt), "사업명": text, "지사원문": dept}
                       for it, dept, doc, amt, text in rows])
    df["과목정규"] = df["예산과목원문"]
    df["처지사정규"] = df["지사원문"]
    return df


def _plan(rows):
    return pd.DataFrame([{"_row": i + 4, "예산과목": it, "처지사": d, "사업명": n, "연예산": float(b)}
                         for i, (it, d, n, b) in enumerate(rows)])


def _run(plan, erp, items, **kw):
    return matching.match_actuals(plan, erp, items, items, set(), threshold=80, **kw)


def test_sim_norm_drops_installment_markers():
    assert matching.sim_norm("2025년 3회 GT 정기점검(기성)") == "가스터빈정기점검기성"
    assert matching.sim_norm("'25년 4월분 소방 용역") == matching.sim_norm("25년 9월분 소방 용역")


def test_idf_prefers_distinctive_word_over_common_words():
    """흔한 낱말(유지보수·용역)이 같은 사업보다, 희귀 낱말(소방)이 같은 사업을 고른다."""
    plan = _plan([(GS, "화성지사", "열원설비 유지보수 용역", 500), (GS, "화성지사", "소방시설 유지보수 용역", 100)])
    erp = _erp([(GS, "화성지사", "D1", 40, "소방 점검 용역 4월분")])
    res = _run(plan, erp, {GS}, struct_distribute=False)
    got = {r["사업명"]: r["실적금액"] for r in res["plan_rows"]}
    assert got["소방시설 유지보수 용역"] == 40.0
    # 확신도는 종전 WRatio 척도 그대로(0~1)
    conf = [r["매칭확신도"] for r in res["plan_rows"] if r["실적금액"]][0]
    assert 0 < conf <= 1


def test_struct_item_distributed_by_budget_and_total_kept():
    plan = _plan([(JG, "화성지사", "1호기 정기점검", 300), (JG, "화성지사", "2호기 정기점검", 100)])
    erp = _erp([(JG, "화성지사", "D1", 1000, "보수공사"), (JG, "화성지사", "D2", 200, "자재 구입")])
    res = _run(plan, erp, {JG})
    rows = {r["사업명"]: r for r in res["plan_rows"]}
    assert rows["1호기 정기점검"]["실적금액"] == 900.0 and rows["2호기 정기점검"]["실적금액"] == 300.0
    assert all(r.get("배분") and r["구분"] == "계획집행" for r in rows.values())
    off = _run(plan, erp, {JG}, struct_distribute=False)
    assert sum(r["실적금액"] for r in off["plan_rows"]) == sum(r["실적금액"] for r in res["plan_rows"]) == 1200.0


def test_struct_skips_groups_with_manual_assignment():
    plan = _plan([(JG, "화성지사", "1호기 정기점검", 300), (JG, "화성지사", "2호기 정기점검", 100)])
    erp = _erp([(JG, "화성지사", "D1", 1000, "보수공사")])
    erp["_erp_row"] = [7]
    res = _run(plan, erp, {JG}, overrides={7: "2호기 정기점검"})
    rows = {r["사업명"]: r for r in res["plan_rows"]}
    assert rows["2호기 정기점검"]["실적금액"] == 1000.0 and not rows["2호기 정기점검"].get("배분")


def test_outsourced_a_grade_not_distributed():
    item = "외주비-열원정기점검"
    plan = _plan([(item, "화성지사", "1호기 A급정비", 300), (item, "화성지사", "2호기 A급정비", 100)])
    erp = _erp([(item, "화성지사", "D1", 50, "2호기 A급정비 기성")])
    res = _run(plan, erp, {item})
    rows = {r["사업명"]: r["실적금액"] for r in res["plan_rows"]}
    assert rows == {"1호기 A급정비": 0.0, "2호기 A급정비": 50.0}
