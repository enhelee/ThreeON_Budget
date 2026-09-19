# -*- coding: utf-8 -*-
"""전망 상태(3·4단계) 표 9종 — 스키마·기준연도 분리·라운드트립·v2 CSV 이관·지사 해석기.

Phase 6-5. v2 가 CWD 에 CSV 로 두던 상태 9종을 DB 표로 옮긴다. 전부
**전망 기준연도(base_year)** 축을 갖는다(사용자 결정 2026-09-19) — v2 는
BASE_YEAR=2026 이 상수여서 그 상태가 사실상 «26년 기준 한 벌»이었고, 27년
전망을 시작할 때 26년 가정이 덮여 사라지는 길을 막는다.

라운드트립 기준은 «v2 의 load_* 가 돌려주던 DataFrame 과 같은 컬럼·dtype» 이다.
그래야 6-2·6-4 에서 옮긴 계산부에 그대로 넣을 수 있다.
"""
import math

import pandas as pd
import pytest

from budget import config_store
from budget import db as dbm
from budget import forecast_calc
from budget import forecast_store as fs


@pytest.fixture()
def conn(tmp_path):
    c = dbm.connect(str(tmp_path / "t.db"))
    yield c
    c.close()


def _cols(conn, table):
    return [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]


# ---------------------------------------------------------------- 스키마
def test_all_nine_forecast_tables_have_base_year(conn):
    for t in fs.TABLES:
        assert "base_year" in _cols(conn, t), t
    assert len(fs.TABLES) == 9


# ---------------------------------------------------------------- 정비등급 이력
def test_grade_history_round_trip_keeps_v2_columns_and_types(conn):
    df = pd.DataFrame({"사업장": ["화성지사", "화성지사"], "연도": ["2026", 2027], "등급": ["간이", "TI"]})
    saved = fs.save_grade_history(conn, "2026", df)
    loaded = fs.load_grade_history(conn, "2026")
    assert list(loaded.columns) == ["사업장", "연도", "등급"]
    assert loaded["연도"].tolist() == [2026, 2027]
    assert loaded["연도"].dtype.kind == "i"
    assert loaded["등급"].tolist() == ["간이", "TI"]
    pd.testing.assert_frame_equal(saved, loaded)


def test_grade_history_empty_has_v2_columns(conn):
    loaded = fs.load_grade_history(conn, "2026")
    assert loaded.empty
    assert list(loaded.columns) == ["사업장", "연도", "등급"]


def test_base_years_are_isolated(conn):
    fs.save_grade_history(conn, "2026", pd.DataFrame(
        [{"사업장": "화성지사", "연도": 2027, "등급": "TI"}]))
    fs.save_grade_history(conn, "2027", pd.DataFrame(
        [{"사업장": "화성지사", "연도": 2027, "등급": "MI"}]))
    assert fs.load_grade_history(conn, "2026")["등급"].tolist() == ["TI"]
    assert fs.load_grade_history(conn, "2027")["등급"].tolist() == ["MI"]
    # 한 해를 갈아 끼워도 다른 해는 그대로다
    fs.save_grade_history(conn, "2027", pd.DataFrame(columns=["사업장", "연도", "등급"]))
    assert fs.load_grade_history(conn, "2027").empty
    assert len(fs.load_grade_history(conn, "2026")) == 1


def test_grade_history_save_keeps_last_duplicate(conn):
    """같은 (사업장,연도)가 두 번 오면 뒤의 것이 이긴다 — 화면이 편집본을 통째로 보낼 때
    옛 행과 새 행이 섞여 오는 경우다."""
    df = pd.DataFrame([{"사업장": "화성지사", "연도": 2027, "등급": "TI"},
                       {"사업장": "화성지사", "연도": 2027, "등급": "MI"}])
    loaded = fs.save_grade_history(conn, "2026", df)
    assert loaded["등급"].tolist() == ["MI"]


# ---------------------------------------------------------------- 산출방식·수정값
def test_method_map_round_trip(conn):
    df = pd.DataFrame([{"사업장": "화성지사", "예산과목": "기계장치", "방식": "최근실적"}])
    fs.save_method_map(conn, "2026", df)
    loaded = fs.load_method_map(conn, "2026")
    assert list(loaded.columns) == ["사업장", "예산과목", "방식"]
    assert loaded.iloc[0].tolist() == ["화성지사", "기계장치", "최근실적"]
    assert list(fs.load_method_map(conn, "2027").columns) == ["사업장", "예산과목", "방식"]


def test_overrides_round_trip_keeps_grade_and_amount(conn):
    df = pd.DataFrame([{"사업장": "화성지사", "예산과목": "기계장치", "등급": "표준", "표준금액": 1234.5}])
    fs.save_overrides(conn, "2026", df)
    loaded = fs.load_overrides(conn, "2026")
    assert list(loaded.columns) == ["사업장", "예산과목", "등급", "표준금액"]
    assert loaded.iloc[0]["등급"] == "표준"
    assert loaded.iloc[0]["표준금액"] == pytest.approx(1234.5)
    assert loaded["표준금액"].dtype.kind == "f"


# ---------------------------------------------------------------- 팩터
def test_factors_seed_default_inflation_on_first_read_and_persist(conn):
    """v2 load_factors 는 파일이 없으면 물가상승률 1.5% 를 돌려줬다. 여기서는 시드를
    DB 에 고정한다(dept_config 와 같은 이유 — 나중에 시드를 고쳐도 과거 기준연도가
    조용히 바뀌지 않는다)."""
    factors = fs.load_factors(conn, "2026")
    assert list(factors.columns) == ["팩터명", "연간비율", "활성"]
    assert factors.iloc[0]["팩터명"] == "물가상승률"
    assert factors.iloc[0]["연간비율"] == pytest.approx(0.015)
    assert factors.iloc[0]["활성"] is True or factors.iloc[0]["활성"] == True  # noqa: E712
    n = conn.execute("SELECT COUNT(*) FROM forecast_factor WHERE base_year='2026'").fetchone()[0]
    assert n == 1


def test_factors_round_trip_keeps_bool_and_order(conn):
    df = pd.DataFrame([
        {"팩터명": "물가상승률", "연간비율": 0.02, "활성": True},
        {"팩터명": "노후화", "연간비율": 0.05, "활성": False},
    ])
    fs.save_factors(conn, "2026", df)
    loaded = fs.load_factors(conn, "2026")
    assert loaded["팩터명"].tolist() == ["물가상승률", "노후화"]
    assert loaded["활성"].tolist() == [True, False]
    assert loaded["활성"].dtype == bool
    # 계산부가 그대로 받는다
    assert forecast_calc.year_multiplier(2027, loaded) == pytest.approx(1.02)


# ---------------------------------------------------------------- 고온부품
def test_hot_parts_round_trip(conn):
    df = pd.DataFrame([{"사업장": "화성지사", "연도": 2027, "항목": "고온부품재생", "금액": 5000}])
    fs.save_hot_parts(conn, "2026", df)
    loaded = fs.load_hot_parts(conn, "2026")
    assert list(loaded.columns) == ["사업장", "연도", "항목", "금액"]
    assert loaded.iloc[0]["연도"] == 2027 and loaded["연도"].dtype.kind == "i"
    assert loaded.iloc[0]["금액"] == pytest.approx(5000.0) and loaded["금액"].dtype.kind == "f"


# ---------------------------------------------------------------- 본사 원가분배
def _hq_master_wide():
    return pd.DataFrame([
        {"대분류": "플랜트", "중분류": "경상정비", "세부내역": "중대형", "26년예산": 1000,
         "화성지사": 600, "동탄지사": 400},
        {"대분류": "정기점검", "중분류": "", "세부내역": "", "26년예산": 300,
         "화성지사": 300, "동탄지사": 0},
    ], columns=["대분류", "중분류", "세부내역", "26년예산", "화성지사", "동탄지사"])


def test_hq_master_wide_table_round_trips_with_column_order(conn):
    """v2 마스터는 지사가 열인 넓은 표다. DB 에는 긴 표로 두고 읽을 때 되돌린다 —
    계산부(hq_amount_by_site_account)가 넓은 표를 받기 때문이다."""
    wide = _hq_master_wide()
    fs.save_hq_master(conn, "2026", wide)
    loaded = fs.load_hq_master(conn, "2026")
    assert list(loaded.columns) == list(wide.columns)
    assert loaded["화성지사"].tolist() == [600.0, 300.0]
    assert loaded["26년예산"].tolist() == [1000.0, 300.0]
    assert loaded["대분류"].tolist() == ["플랜트", "정기점검"]
    assert forecast_calc.hq_amount_by_site_account(loaded) == forecast_calc.hq_amount_by_site_account(wide)


def test_hq_master_empty_uses_base_year_budget_column(conn):
    assert list(fs.load_hq_master(conn, "2026").columns) == ["대분류", "중분류", "세부내역", "26년예산"]
    assert list(fs.load_hq_master(conn, "2027").columns) == ["대분류", "중분류", "세부내역", "27년예산"]


def test_hq_amount_by_site_account_ignores_any_year_budget_column():
    """27년 기준연도의 마스터는 «27년예산» 열을 갖는다. v2 는 «26년예산» 만 제외했으므로
    그대로면 27년예산이 지사로 잡혀 합계가 두 배가 된다."""
    wide = _hq_master_wide().rename(columns={"26년예산": "27년예산"})
    amt = forecast_calc.hq_amount_by_site_account(wide)
    assert amt[("화성지사", "수선유지비-열원경상정비")] == 600
    assert ("27년예산", "수선유지비-열원경상정비") not in amt
    assert not any(k[0].endswith("년예산") for k in amt)


def test_hq_ratio_round_trip(conn):
    df = pd.DataFrame([{"사업장": "화성지사", "계약체결금액": 6000}, {"사업장": "동탄지사", "계약체결금액": 4000}])
    fs.save_hq_ratio(conn, "2026", df)
    loaded = fs.load_hq_ratio(conn, "2026")
    assert list(loaded.columns) == ["사업장", "계약체결금액"]
    assert dict(zip(loaded["사업장"], loaded["계약체결금액"])) == {"화성지사": 6000.0, "동탄지사": 4000.0}


def test_hq_temp_projects_append_and_load(conn):
    fs.append_hq_temp_project(conn, "2026", "긴급공사", "기계장치", 2027, 1000)
    fs.append_hq_temp_project(conn, "2026", "긴급공사2", "기계장치", 2028, 2000)
    loaded = fs.load_hq_temp_projects(conn, "2026")
    assert list(loaded.columns) == ["사업명", "예산과목", "연도", "금액"]
    assert loaded["사업명"].tolist() == ["긴급공사", "긴급공사2"]
    assert loaded["연도"].tolist() == [2027, 2028]
    # 통째 저장은 갈아 끼운다
    fs.save_hq_temp_projects(conn, "2026", loaded.iloc[:1])
    assert fs.load_hq_temp_projects(conn, "2026")["사업명"].tolist() == ["긴급공사"]


# ---------------------------------------------------------------- 돌발사업
def test_surprise_projects_append_and_load(conn):
    fs.append_surprise_project(conn, "2026", "화성지사", 2029, "기계장치", 500, "돌발 고장")
    loaded = fs.load_surprise_projects(conn, "2026")
    assert list(loaded.columns) == ["사업장", "연도", "예산과목", "금액", "사유"]
    row = loaded.iloc[0]
    assert (row["사업장"], row["연도"], row["예산과목"], row["금액"], row["사유"]) == \
        ("화성지사", 2029, "기계장치", 500.0, "돌발 고장")
    assert fs.load_surprise_projects(conn, "2027").empty


# ---------------------------------------------------------------- 기준연도 관리
def test_list_base_years_unions_all_tables(conn):
    assert fs.list_base_years(conn) == []
    fs.save_hq_ratio(conn, "2027", pd.DataFrame([{"사업장": "화성지사", "계약체결금액": 1}]))
    fs.append_surprise_project(conn, "2026", "화성지사", 2029, "기계장치", 1, "")
    assert fs.list_base_years(conn) == ["2026", "2027"]


def test_copy_base_year_copies_all_nine_and_replaces_target(conn):
    fs.save_grade_history(conn, "2026", pd.DataFrame([{"사업장": "화성지사", "연도": 2027, "등급": "TI"}]))
    fs.save_method_map(conn, "2026", pd.DataFrame([{"사업장": "화성지사", "예산과목": "기계장치", "방식": "최근실적"}]))
    fs.save_overrides(conn, "2026", pd.DataFrame([{"사업장": "화성지사", "예산과목": "기계장치", "등급": "표준", "표준금액": 1.0}]))
    fs.save_factors(conn, "2026", pd.DataFrame([{"팩터명": "물가상승률", "연간비율": 0.03, "활성": True}]))
    fs.save_hot_parts(conn, "2026", pd.DataFrame([{"사업장": "화성지사", "연도": 2027, "항목": "신품구매", "금액": 1.0}]))
    fs.save_hq_master(conn, "2026", _hq_master_wide())
    fs.save_hq_ratio(conn, "2026", pd.DataFrame([{"사업장": "화성지사", "계약체결금액": 1.0}]))
    fs.append_hq_temp_project(conn, "2026", "a", "기계장치", 2027, 1.0)
    fs.append_surprise_project(conn, "2026", "화성지사", 2027, "기계장치", 1.0, "x")
    # 대상 연도에 있던 것은 지워진다
    fs.append_surprise_project(conn, "2027", "동탄지사", 2030, "기계장치", 9.0, "old")

    fs.copy_base_year(conn, "2026", "2027")

    assert fs.load_grade_history(conn, "2027")["등급"].tolist() == ["TI"]
    assert fs.load_method_map(conn, "2027")["방식"].tolist() == ["최근실적"]
    assert fs.load_overrides(conn, "2027")["표준금액"].tolist() == [1.0]
    assert fs.load_factors(conn, "2027")["연간비율"].tolist() == [0.03]
    assert fs.load_hot_parts(conn, "2027")["항목"].tolist() == ["신품구매"]
    pd.testing.assert_frame_equal(fs.load_hq_master(conn, "2027"), fs.load_hq_master(conn, "2026"))
    assert fs.load_hq_ratio(conn, "2027")["계약체결금액"].tolist() == [1.0]
    assert fs.load_hq_temp_projects(conn, "2027")["사업명"].tolist() == ["a"]
    assert fs.load_surprise_projects(conn, "2027")["사유"].tolist() == ["x"]
    # 원본은 그대로
    assert fs.load_surprise_projects(conn, "2026")["사유"].tolist() == ["x"]


def test_base_year_is_untouched_until_someone_writes(conn):
    """읽기만 한 기준연도(팩터 시드가 자동으로 심긴 상태)는 «손대지 않은 것»이다 —
    화면을 한 번 열었다는 이유로 연도 복사가 막히면 안 된다(copy-year 409 가드와 같은 논리)."""
    assert fs.base_year_is_untouched(conn, "2026")
    fs.load_factors(conn, "2026")
    assert fs.base_year_is_untouched(conn, "2026")
    fs.append_surprise_project(conn, "2026", "화성지사", 2027, "기계장치", 1.0, "x")
    assert not fs.base_year_is_untouched(conn, "2026")


# ---------------------------------------------------------------- v2 CSV 이관
def test_import_v2_csv_dir_reads_every_state_file_present(conn, tmp_path):
    """v2 가 CWD 에 두던 CSV 9종을 한 기준연도로 들여온다. 없는 파일은 건너뛴다."""
    (tmp_path / "site_year_grade.csv").write_text("사업장,연도,등급\n화성지사,2027,TI\n", encoding="utf-8")
    (tmp_path / "standardization_method_map.csv").write_text(
        "사업장,예산과목,방식\n화성지사,기계장치,최근실적\n", encoding="utf-8")
    (tmp_path / "longterm_factors.csv").write_text("팩터명,연간비율,활성\n물가상승률,0.02,True\n", encoding="utf-8")
    (tmp_path / "hq_master_table.csv").write_text(
        "대분류,중분류,세부내역,26년예산,화성지사\n플랜트,경상정비,중대형,1000,600\n", encoding="utf-8")
    (tmp_path / "surprise_projects.csv").write_text(
        "사업장,연도,예산과목,금액,사유\n화성지사,2029,기계장치,500,돌발\n", encoding="utf-8")

    report = fs.import_v2_csv_dir(conn, "2026", str(tmp_path))

    assert report == {"site_grade": 1, "benchmark_method": 1, "forecast_factor": 1,
                      "hq_master": 1, "forecast_surprise": 1}
    assert fs.load_grade_history(conn, "2026")["등급"].tolist() == ["TI"]
    assert fs.load_factors(conn, "2026")["연간비율"].tolist() == [0.02]
    assert fs.load_hq_master(conn, "2026")["화성지사"].tolist() == [600.0]
    assert fs.load_surprise_projects(conn, "2026")["사유"].tolist() == ["돌발"]
    # 파일이 없던 표는 비어 있다(팩터는 위에서 들여왔으니 시드가 아니다)
    assert fs.load_hot_parts(conn, "2026").empty


# ---------------------------------------------------------------- 지사 해석기 (6-4 훅에 끼우는 것)
def _seed_dept_master(conn, year="2026"):
    conn.execute("INSERT INTO dept_master(year,부서코드,부서명,처지사) VALUES(?,?,?,?)",
                 (year, "3070100", "화성지사 기술부", "화성지사"))
    conn.execute("INSERT INTO dept_master(year,부서코드,부서명,처지사) VALUES(?,?,?,?)",
                 (year, "3080100", "동탄지사 기술부", "동탄지사"))
    conn.commit()


def test_site_display_resolver_exact_prefix_and_unmapped(conn):
    _seed_dept_master(conn)
    resolve = fs.make_site_display_resolver(conn, "2026")
    assert resolve("3070100") == "화성지사"          # 정확히 일치
    assert resolve(3070100.0) == "화성지사"          # 엑셀에서 온 float
    assert resolve("3070") == "화성지사"             # 손익센터 4자리 → 앞자리 공유
    assert resolve("화성지사") == "화성지사"          # 이미 지사명(dept_config 에 있음)
    assert resolve("2020") == "미매핑(2020번대)"     # 아무 데도 없는 4자리 코드
    assert resolve("ABC") == "ABC"                   # 숫자 코드가 아니면 그대로


def test_site_type_resolver_uses_dept_config_of_that_year(conn):
    resolve = fs.make_site_type_resolver(conn, "2023")
    assert resolve("양산지사") == "DH"                # 2023 년엔 DH
    assert fs.make_site_type_resolver(conn, "2025")("양산지사") == "중대형CHP"
    assert resolve("없는지사") == "미매핑"


def test_bind_site_resolvers_patches_forecast_calc_hooks(conn, monkeypatch):
    monkeypatch.setattr(forecast_calc, "get_site_display_name", forecast_calc.get_site_display_name)
    monkeypatch.setattr(forecast_calc, "get_current_site_type", forecast_calc.get_current_site_type)
    _seed_dept_master(conn)
    fs.bind_site_resolvers(conn, "2026")
    assert forecast_calc.get_site_display_name("3070100") == "화성지사"
    assert forecast_calc.get_current_site_type("화성지사") == "중대형CHP"
    # 계산부가 훅을 통해 지사명을 얻는다
    budget_df = pd.DataFrame([{"예산과목": "기계장치", "예산귀속 \n부서코드": "3070100", "연예산 합계": 10.0}])
    assert forecast_calc.budget_amount_by_site_account(budget_df) == {("화성지사", "기계장치"): 10.0}
