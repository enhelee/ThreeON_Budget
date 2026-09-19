# -*- coding: utf-8 -*-
"""연도별 기준정보 표 — 스키마·연도 분리·시드·복사."""
import pytest

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
