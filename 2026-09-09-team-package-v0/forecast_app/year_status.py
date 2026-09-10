"""
연도별 업로드 현황 관리
- 상태는 JSON 파일에 저장 (year_status.json)
- 화면에는 항상 5칸만 표시: [오래된 연도 그룹] + [최근 4개년 개별]
- '다음 연도 추가' 버튼을 눌러야만 새 연도 칸이 생김
"""
import json
import os

STATUS_PATH = "year_status.json"


def load_status() -> dict:
    if not os.path.exists(STATUS_PATH):
        return {}
    with open(STATUS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_status(status: dict):
    with open(STATUS_PATH, "w", encoding="utf-8") as f:
        json.dump(status, f, ensure_ascii=False, indent=2)


def add_year(status: dict, year: int) -> dict:
    """새 연도 칸을 추가한다 (아직 데이터는 없는 상태로)"""
    key = str(year)
    if key not in status:
        status[key] = {"uploaded": False, "error_count": 0, "row_count": 0}
    return status


def set_year_result(status: dict, year: int, row_count: int, error_count: int, errors: list) -> dict:
    """업로드 처리 후 결과를 반영한다"""
    key = str(year)
    status[key] = {
        "uploaded": True,
        "row_count": row_count,
        "error_count": error_count,
        "errors": errors,
    }
    return status


def get_visible_cells(status: dict, visible_recent: int = 4) -> list:
    """
    화면에 보여줄 5칸을 계산한다.
    반환: [{"type": "group", "label": "2016~2021", "years": [2016,...,2021]},
           {"type": "year", "year": 2022, "state": "done"/"warning"/"empty"}, ...]
    최근 N개년(visible_recent)은 개별로, 그 이전은 하나의 그룹 칸으로 묶는다.
    """
    years = sorted(int(y) for y in status.keys())
    if not years:
        return []

    recent_years = years[-visible_recent:]
    old_years = years[:-visible_recent]

    cells = []
    if old_years:
        cells.append({
            "type": "group",
            "label": f"{old_years[0]}~{old_years[-1]}",
            "years": old_years,
        })

    for y in recent_years:
        info = status[str(y)]
        if not info.get("uploaded"):
            state = "empty"
        elif info.get("error_count", 0) > 0:
            state = "warning"
        else:
            state = "done"
        cells.append({"type": "year", "year": y, "state": state})

    return cells


def next_addable_year(status: dict) -> int:
    """추가 가능한 다음 연도(현재 등록된 최댓값 + 1)를 반환"""
    if not status:
        return 2016  # 초기값(운영 시 조정 가능)
    return max(int(y) for y in status.keys()) + 1


def prev_addable_year(status: dict) -> int:
    """추가 가능한 이전 연도(현재 등록된 최솟값 - 1)를 반환. 과거 데이터를 나중에 채워넣을 때 사용."""
    if not status:
        return 2016
    return min(int(y) for y in status.keys()) - 1


def clear_year_data(status: dict, year: int) -> dict:
    """해당 연도를 '미업로드' 상태로 되돌린다 (칸은 유지, 다시 업로드 가능)"""
    key = str(year)
    if key in status:
        status[key] = {"uploaded": False, "error_count": 0, "row_count": 0}
    return status


def remove_year(status: dict, year: int) -> dict:
    """해당 연도 칸 자체를 완전히 삭제한다 (잘못 추가한 연도를 없앨 때)"""
    key = str(year)
    status.pop(key, None)
    return status