# -*- coding: utf-8 -*-
"""연동규격 어댑터(spec_io) 테스트. 합성 데이터 위주 + 실파일은 skipif."""
import os

import pandas as pd
import pytest

from budget import spec_io

ROOT = r"C:\Users\User\Desktop\중장기 예산 소요 전망"
ZRFM2 = os.path.join(ROOT, "zrfm2.XLSX")
REAL_PLAN = os.path.join(ROOT, "양식1_월별_템플릿(25년 계획분)_R1.xlsx")


# ── 읽기: 규격 CSV → 내부 모델 (단위 환산·컬럼 매핑) ─────────────────────
def test_read_data_csv_maps_and_converts_unit(tmp_path):
    p = tmp_path / "data_2025.csv"
    pd.DataFrame([
        {"거래처명": "1298505943", "사업장": "2023", "전기일": "2025-01-01",
         "전표헤더텍스트": "동탄 3호기 정기점검", "금액": 25947300,
         "계정과목": "수선유지비-열원정기점검"},
    ], columns=spec_io.DATA_COLUMNS).to_csv(p, index=False, encoding="utf-8-sig")

    df = spec_io.read_data_csv(str(p))
    r = df.iloc[0]
    assert r["금액원"] == 25947300
    assert r["금액천원"] == 25947.3            # 원 → 천원
    assert r["예산과목원문"] == "수선유지비-열원정기점검"
    assert r["사업명"] == "동탄 3호기 정기점검"
    assert r["사업장코드"] == "2023" and r["지사원문"] == "2023"


def test_read_budget_csv_maps_and_converts_unit(tmp_path):
    p = tmp_path / "budget_2025.csv"
    pd.DataFrame([
        {spec_io.BUDGET_COL_사업명: "강남지사 열병합 정비",
         spec_io.BUDGET_COL_예산과목: "수선유지비-열원정기점검",
         spec_io.BUDGET_COL_연예산: 534633000,          # 원
         spec_io.BUDGET_COL_부서코드: "2023001",
         spec_io.BUDGET_COL_부서명: "강남지사",
         spec_io.BUDGET_COL_예산코드: "60909008",
         spec_io.BUDGET_COL_속성: "제조",
         spec_io.BUDGET_COL_주관부서: "플랜트기술처"},
    ], columns=spec_io.BUDGET_COLUMNS).to_csv(p, index=False, encoding="utf-8-sig")

    df = spec_io.read_budget_csv(str(p))
    r = df.iloc[0]
    assert r["연예산"] == 534633.0                       # 원 → 천원
    assert r["처지사"] == "강남지사"
    assert r["예산과목"] == "수선유지비-열원정기점검"
    assert r["부서코드"] == "2023001"


# ── 쓰기: 내부 결과 → 규격 CSV ───────────────────────────────────────────
def _synthetic_annotated():
    return pd.DataFrame([
        {"거래처코드": "1298505943", "사업장코드": "2023", "전기일": "2025-01-01",
         "사업명": "동탄 3호기 LTSA 부품", "금액원": 25947300,
         "과목정규": "수선유지비-열원정기점검", "매칭사업명": "동탄 정비사업",
         "매칭확신도": 0.87},
        {"거래처코드": "1000000001", "사업장코드": "3070", "전기일": "2025-02-02",
         "사업명": "보안 카메라 교체", "금액원": 500000,
         "과목정규": "기계장치", "매칭사업명": "[신규]", "매칭확신도": 0.0},
    ])


def test_write_matched_csv_headers_and_gap(tmp_path):
    p = tmp_path / "matched_2025.csv"
    spec_io.write_matched_csv(_synthetic_annotated(), str(p))
    out = pd.read_csv(p, dtype=str)
    assert list(out.columns) == spec_io.MATCHED_SPEC_COLUMNS
    assert out["사업코드"].isna().all()                  # 사업코드 gap → 공란
    assert out.iloc[0]["금액"] == "25947300"             # 원 단위 유지
    assert out.iloc[0]["계정과목"] == "수선유지비-열원정기점검"


def test_write_classified_default_unclassified(tmp_path):
    p = tmp_path / "classified_2025.csv"
    spec_io.write_classified_csv(_synthetic_annotated(), str(p))
    out = pd.read_csv(p, dtype=str)
    assert list(out.columns) == spec_io.CLASSIFIED_COLUMNS
    assert (out["투자유형_확정"] == spec_io.UNCLASSIFIED).all()


def test_write_classified_with_classifier_hook(tmp_path):
    p = tmp_path / "classified_2025.csv"

    def clf(text):
        return "LTSA" if text and "LTSA" in text else spec_io.UNCLASSIFIED

    spec_io.write_classified_csv(_synthetic_annotated(), str(p), classifier=clf)
    out = pd.read_csv(p, dtype=str)
    assert out.iloc[0]["투자유형_확정"] == "LTSA"
    assert out.iloc[1]["투자유형_확정"] == spec_io.UNCLASSIFIED


def test_classifier_invalid_value_falls_back(tmp_path):
    p = tmp_path / "classified_2025.csv"
    spec_io.write_classified_csv(_synthetic_annotated(), str(p),
                                 classifier=lambda t: "존재하지않는유형")
    out = pd.read_csv(p, dtype=str)
    assert (out["투자유형_확정"] == spec_io.UNCLASSIFIED).all()  # 8종 아니면 미분류


# ── 부서코드(앞3자리) 매핑 (규격 §6-3) ──────────────────────────────────
def test_dept_map_from_budget_and_resolve():
    budget = pd.DataFrame([
        {"부서코드": "2023001", "처지사": "강남지사"},
        {"부서코드": "3070100", "처지사": "동탄지사"},
    ])
    m = spec_io.dept_map_from_budget(budget)
    assert m["202"] == "강남지사" and m["307"] == "동탄지사"
    assert spec_io.resolve_dept_by_code("2023", m) == "강남지사"   # 손익센터 4자리, 앞3 일치
    assert spec_io.resolve_dept_by_code("9999", m) is None


def test_budget_column_names_have_newline():
    # 규격 §3-2: 부서 칸 이름에 줄바꿈(\n) 포함 — 정확히 유지되어야 함
    assert "\n" in spec_io.BUDGET_COL_부서코드
    assert "\n" in spec_io.BUDGET_COL_부서명


# ── 실파일 E2E (없으면 skip) ─────────────────────────────────────────────
@pytest.mark.skipif(not os.path.exists(ZRFM2), reason="zrfm2 없음")
def test_write_data_csv_from_real_zrfm2(tmp_path):
    p = tmp_path / "data_2025.csv"
    spec_io.write_data_csv(ZRFM2, str(p), year="2025")
    out = pd.read_csv(p, dtype=str)
    assert list(out.columns) == spec_io.DATA_COLUMNS
    assert len(out) > 0
    # 금액이 원 단위(큰 값)인지 — 천원 아님
    amts = pd.to_numeric(out["금액"], errors="coerce").dropna().abs()
    assert amts.max() > 100000


@pytest.mark.skipif(not os.path.exists(REAL_PLAN), reason="계획본 없음")
def test_write_budget_csv_from_real_plan(tmp_path):
    p = tmp_path / "budget_2025.csv"
    spec_io.write_budget_csv(REAL_PLAN, str(p))
    out = pd.read_csv(p, dtype=str)
    assert list(out.columns) == spec_io.BUDGET_COLUMNS
    assert len(out) > 0
