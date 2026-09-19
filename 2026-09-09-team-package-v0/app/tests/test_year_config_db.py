# -*- coding: utf-8 -*-
"""연도별 기준정보 표 — 스키마·연도 분리·시드·복사."""
import pytest

from budget import config_store
from budget import db as dbm


@pytest.fixture()
def conn(tmp_path):
    c = dbm.connect(str(tmp_path / "t.db"))
    dbm.init_db(c)
    yield c
    c.close()


def _cols(conn, table):
    return [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]


def test_year_scoped_tables_exist(conn):
    assert "year" in _cols(conn, "dept_config")
    assert "year" in _cols(conn, "item_config")
    assert "year" in _cols(conn, "item_master")
    assert "year" in _cols(conn, "dept_master")


def test_alias_table_has_no_year(conn):
    """별칭은 표기 흔들림 보정이라 연도가 바뀌어도 유효하다."""
    cols = _cols(conn, "alias")
    assert "year" not in cols
    assert set(cols) >= {"종류", "원표기", "정규표기"}


def test_legacy_master_rows_are_copied_to_each_year(conn):
    """연도 없이 쌓인 마스터를 기존 연도마다 한 벌씩 복제한다.

    이관의 성공 기준은 «동작이 하나도 바뀌지 않는 것»이다(설계 §3.3).
    복사해 두면 어느 연도를 열어도 이관 직후에는 지금과 같은 결과가 나온다.
    """
    conn.execute("INSERT INTO dataset(kind,year,label,uploaded_at) VALUES('plan','2023','x','t')")
    conn.execute("INSERT INTO dataset(kind,year,label,uploaded_at) VALUES('plan','2025','x','t')")
    conn.execute("INSERT INTO item_master(계정코드,과목명) VALUES('60909002','수선유지비-열원정기점검')")
    conn.execute("INSERT INTO dept_master(부서코드,부서명,처지사) VALUES('D1','기술부','화성지사')")
    conn.commit()

    dbm.migrate_masters_to_years(conn)

    years = {r[0] for r in conn.execute("SELECT DISTINCT year FROM item_master")}
    assert years == {"2023", "2025"}
    assert conn.execute("SELECT COUNT(*) FROM dept_master WHERE year='2025'").fetchone()[0] == 1
    # 두 번 돌려도 늘어나지 않는다
    dbm.migrate_masters_to_years(conn)
    assert conn.execute("SELECT COUNT(*) FROM item_master").fetchone()[0] == 2


# ── Task 3: config_store 가 DB 에서 읽고 쓴다 ────────────────────────────────

def test_load_seeds_when_empty_then_persists(conn):
    """비어 있으면 시드를 심고, 그 뒤로는 DB 값을 읽는다."""
    rows = config_store.load_dept_config(conn, "2025")
    assert {r["이름"]: r["그룹"] for r in rows}["양산지사"] == "중대형CHP"
    assert conn.execute(
        "SELECT COUNT(*) FROM dept_config WHERE year='2025'").fetchone()[0] == 24


def test_years_are_independent(conn):
    """2023 을 고쳐도 2025 가 흔들리지 않는다 — 완전 사본을 택한 이유다."""
    config_store.load_dept_config(conn, "2023")
    config_store.load_dept_config(conn, "2025")
    rows = config_store.load_dept_config(conn, "2023")
    for r in rows:
        if r["이름"] == "화성지사":
            r["그룹"] = "DH"
    config_store.save_dept_config(conn, "2023", rows)

    g2023 = {r["이름"]: r["그룹"] for r in config_store.load_dept_config(conn, "2023")}
    g2025 = {r["이름"]: r["그룹"] for r in config_store.load_dept_config(conn, "2025")}
    assert g2023["화성지사"] == "DH"
    assert g2025["화성지사"] == "중대형CHP"


def test_alias_is_shared_across_years(conn):
    config_store.save_alias(conn, "dept", {"경남지사(양산RPS 태양광)": "양산지사"})
    assert config_store.load_dept_alias(conn)["경남지사(양산RPS 태양광)"] == "양산지사"


def test_item_config_is_year_and_budget_scoped(conn):
    """과목 구성은 (연도, 손익/자본) 두 축으로 갈린다."""
    cap = config_store.load_item_config(conn, "2025", "자본")
    cap.append({"과목": "신규자본과목", "대분류": "자산", "심의대상": False, "포함": True})
    config_store.save_item_config(conn, "2025", "자본", cap)

    assert any(x["과목"] == "신규자본과목"
               for x in config_store.load_item_config(conn, "2025", "자본"))
    assert not any(x["과목"] == "신규자본과목"
                   for x in config_store.load_item_config(conn, "2025", "손익"))
    assert not any(x["과목"] == "신규자본과목"
                   for x in config_store.load_item_config(conn, "2023", "자본"))


def test_item_config_bool_fields_survive_roundtrip(conn):
    """NaN 체크박스 값이 DB 에 새지 않고 기본값으로 정규화된다.

    NaN 은 파이썬에서 truthy 라 그대로 두면 '실적반영' 판정이 뒤집힌다.
    파일 시절 JSON 에 비표준 토큰이 새던 문제의 DB 판이다.
    """
    items = [
        {"과목": "기계장치", "대분류": "자산", "심의대상": float("nan"),
         "포함": float("nan"), "실적반영": float("nan")},
        {"과목": "외주비-열원공사비", "대분류": "건설공사", "심의대상": False,
         "포함": True, "실적반영": False},
    ]
    config_store.save_item_config(conn, "2023", "자본", items)
    reloaded = config_store.load_item_config(conn, "2023", "자본")
    assert reloaded[0]["심의대상"] is False
    assert reloaded[0]["포함"] is True
    assert reloaded[0]["실적반영"] is True
    assert reloaded[1]["실적반영"] is False


def test_saved_order_is_preserved(conn):
    """구성 순서는 종합표의 지사 열·과목 행 순서다 — 저장한 차례대로 읽혀야 한다."""
    rows = config_store.load_dept_config(conn, "2025")
    reordered = list(reversed(rows))
    config_store.save_dept_config(conn, "2025", reordered)
    assert [r["이름"] for r in config_store.load_dept_config(conn, "2025")] == \
        [r["이름"] for r in reordered]
