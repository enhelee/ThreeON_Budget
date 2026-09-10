from year_status import (
    add_year, set_year_result, get_visible_cells,
    next_addable_year, prev_addable_year, clear_year_data, remove_year,
)


def test_add_year_creates_empty_entry():
    status = add_year({}, 2024)
    assert status == {"2024": {"uploaded": False, "error_count": 0, "row_count": 0}}


def test_add_year_does_not_overwrite_existing():
    status = {"2024": {"uploaded": True, "error_count": 1, "row_count": 10}}
    status = add_year(status, 2024)
    assert status["2024"]["uploaded"] is True


def test_set_year_result_marks_uploaded():
    status = set_year_result({}, 2024, row_count=100, error_count=2, errors=[{"row": 1}])
    assert status["2024"]["uploaded"] is True
    assert status["2024"]["row_count"] == 100
    assert status["2024"]["error_count"] == 2


def test_next_and_prev_addable_year_empty_status():
    assert next_addable_year({}) == 2016
    assert prev_addable_year({}) == 2016


def test_next_and_prev_addable_year_with_existing():
    status = {"2020": {}, "2022": {}}
    assert next_addable_year(status) == 2023
    assert prev_addable_year(status) == 2019


def test_get_visible_cells_groups_old_years():
    status = {str(y): {"uploaded": True, "error_count": 0} for y in range(2016, 2023)}
    cells = get_visible_cells(status, visible_recent=4)
    assert cells[0]["type"] == "group"
    assert cells[0]["years"] == [2016, 2017, 2018]
    assert [c["year"] for c in cells[1:]] == [2019, 2020, 2021, 2022]


def test_get_visible_cells_state_reflects_errors():
    status = {
        "2024": {"uploaded": False},
        "2025": {"uploaded": True, "error_count": 3},
        "2026": {"uploaded": True, "error_count": 0},
    }
    cells = get_visible_cells(status, visible_recent=4)
    states = {c["year"]: c["state"] for c in cells}
    assert states[2024] == "empty"
    assert states[2025] == "warning"
    assert states[2026] == "done"


def test_clear_year_data_resets_but_keeps_key():
    status = clear_year_data({"2024": {"uploaded": True, "row_count": 5, "error_count": 1}}, 2024)
    assert status["2024"] == {"uploaded": False, "error_count": 0, "row_count": 0}


def test_remove_year_deletes_key():
    status = remove_year({"2024": {}, "2025": {}}, 2024)
    assert status == {"2025": {}}
