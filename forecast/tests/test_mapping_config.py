import pandas as pd
import mapping_config
from mapping_config import (
    _code_prefix3, _find_by_prefix, _best_prefix_match, _resolve_site_type,
    get_site_type, get_site_display_name, get_current_site_type, apply_mappings,
)


def test_code_prefix3_on_four_digit_code():
    assert _code_prefix3("3070") == "307"


def test_code_prefix3_handles_excel_float_suffix():
    assert _code_prefix3("3070.0") == "307"


def test_code_prefix3_none_for_non_four_digit():
    assert _code_prefix3("동탄지사") is None
    assert _code_prefix3("123") is None


def test_find_by_prefix_matches_same_branch_family():
    assert _find_by_prefix(["3070", "4010"], "3071") == "3070"


def test_find_by_prefix_no_match_returns_none():
    assert _find_by_prefix(["3070"], "9999") is None


def test_get_site_type_uses_latest_applicable_year():
    site_map = pd.DataFrame([
        {"사업장": "3070", "지사유형": "소형CHP", "적용시작연도": 1900},
        {"사업장": "3070", "지사유형": "중대형CHP", "적용시작연도": 2020},
    ])
    lookup = _resolve_site_type(site_map)
    assert get_site_type(lookup, "3070", 2015) == "소형CHP"
    assert get_site_type(lookup, "3070", 2020) == "중대형CHP"
    assert get_site_type(lookup, "3070", 2025) == "중대형CHP"


def test_get_site_type_unmapped_when_unknown():
    lookup = _resolve_site_type(pd.DataFrame(columns=["사업장", "지사유형", "적용시작연도"]))
    assert get_site_type(lookup, "9999", 2025) == "미매핑"


def test_get_site_display_name_exact_match(tmp_path, monkeypatch):
    site_path = tmp_path / "site_type_map.csv"
    pd.DataFrame([{"사업장": "3070", "표시명": "판교지사", "지사유형": "중대형CHP", "적용시작연도": 1900}]).to_csv(site_path, index=False)
    monkeypatch.setattr(mapping_config, "SITE_TYPE_PATH", str(site_path))
    monkeypatch.setattr(mapping_config, "DEPT_MASTER_PATH", str(tmp_path / "no_such_dept.csv"))
    assert get_site_display_name("3070.0") == "판교지사"


def test_get_site_display_name_prefix_match_against_registered_code(tmp_path, monkeypatch):
    site_path = tmp_path / "site_type_map.csv"
    pd.DataFrame([{"사업장": "2020", "표시명": "동남권지사", "지사유형": "DH", "적용시작연도": 1900}]).to_csv(site_path, index=False)
    monkeypatch.setattr(mapping_config, "SITE_TYPE_PATH", str(site_path))
    monkeypatch.setattr(mapping_config, "DEPT_MASTER_PATH", str(tmp_path / "no_such_dept.csv"))
    assert get_site_display_name("2023.0") == "동남권지사"


def test_get_site_display_name_groups_unregistered_codes_by_prefix(tmp_path, monkeypatch):
    monkeypatch.setattr(mapping_config, "SITE_TYPE_PATH", str(tmp_path / "site_type_map.csv"))
    monkeypatch.setattr(mapping_config, "DEPT_MASTER_PATH", str(tmp_path / "no_such_dept.csv"))
    assert get_site_display_name("2023.0") == get_site_display_name("2020.0") == get_site_display_name("2021")


def test_get_site_display_name_passthrough_for_non_code_values(tmp_path, monkeypatch):
    monkeypatch.setattr(mapping_config, "SITE_TYPE_PATH", str(tmp_path / "site_type_map.csv"))
    monkeypatch.setattr(mapping_config, "DEPT_MASTER_PATH", str(tmp_path / "no_such_dept.csv"))
    assert get_site_display_name("동남권HRSGTUBE") == "동남권HRSGTUBE"


def test_best_prefix_match_prefers_longer_shared_prefix():
    # '4020'은 '4020001'과 4자리 모두 일치하므로, 같은 '402' 접두만 공유하는
    # '4022004'보다 우선 선택되어야 한다 (양산지사 vs 김해사업소 같은 실제 충돌 사례).
    codes = ["4020001", "4022004"]
    assert _best_prefix_match(codes, "4020") == "4020001"
    assert _best_prefix_match(codes, "4022") == "4022004"


def test_best_prefix_match_minimum_three_digits():
    assert _best_prefix_match(["4020001"], "402") == "4020001"
    assert _best_prefix_match(["4020001"], "40") is None
    assert _best_prefix_match(["4020001"], "999") is None


def test_resolve_site_type_excludes_unfilled_placeholder_rows():
    """실제 버그 재현: '사업장 코드 가져오기'로 등록만 하고 표시명을 안 채운(=표시명이 코드 그대로인)
    행이 지사유형 기본값(예: 중대형CHP)을 갖고 있으면, 그 값이 그대로 lookup에 들어가면 안 된다."""
    site_map = pd.DataFrame([
        {"사업장": "4040.0", "표시명": "4040.0", "지사유형": "중대형CHP", "적용시작연도": 1900},  # placeholder
        {"사업장": "세종지사", "표시명": "세종지사", "지사유형": "DH", "적용시작연도": 1900},  # 정식 등록
    ])
    lookup = _resolve_site_type(site_map)
    assert "4040.0" not in lookup  # placeholder는 lookup에서 빠져야 한다
    assert lookup["세종지사"][0][1] == "DH"


def test_resolve_site_type_keeps_rows_without_display_name_column():
    """'표시명' 컬럼 자체가 없는 site_map(예: 옛 형식/테스트용)은 placeholder 판단을 할 수 없으니
    전부 그대로 유지해야 한다(하위 호환)."""
    site_map = pd.DataFrame([{"사업장": "3070", "지사유형": "소형CHP", "적용시작연도": 1900}])
    lookup = _resolve_site_type(site_map)
    assert "3070" in lookup


def test_get_current_site_type_falls_back_to_display_name_when_code_is_placeholder_only(tmp_path, monkeypatch):
    """실제 버그 재현: 원시 코드가 placeholder로만 등록돼 있으면(잘못된 기본 유형 포함), 코드 직접
    조회가 아니라 표시명으로 다시 풀어서 올바른 유형(DH)을 찾아야 한다."""
    site_path = tmp_path / "site_type_map.csv"
    pd.DataFrame([
        {"사업장": "4040.0", "표시명": "4040.0", "지사유형": "중대형CHP", "적용시작연도": 1900},  # placeholder, 유형이 틀림
        {"사업장": "세종지사", "표시명": "세종지사", "지사유형": "DH", "적용시작연도": 1900},
    ]).to_csv(site_path, index=False)
    dept_path = tmp_path / "dept_code_master.csv"
    pd.DataFrame([{"부서코드": "4040", "부서명": "세종지사 관리부", "처, 지사": "세종지사"}]).to_csv(dept_path, index=False)
    monkeypatch.setattr(mapping_config, "SITE_TYPE_PATH", str(site_path))
    monkeypatch.setattr(mapping_config, "DEPT_MASTER_PATH", str(dept_path))

    assert get_current_site_type("4040.0") == "DH"  # 중대형CHP(잘못된 placeholder 값)가 아니어야 한다


def test_apply_mappings_uses_display_name_fallback_for_placeholder_codes(tmp_path, monkeypatch):
    """apply_mappings()(정식 classified_*.csv 파이프라인)도 같은 폴백을 적용해야 한다."""
    site_path = tmp_path / "site_type_map.csv"
    pd.DataFrame([
        {"사업장": "4040.0", "표시명": "4040.0", "지사유형": "중대형CHP", "적용시작연도": 1900},
        {"사업장": "세종지사", "표시명": "세종지사", "지사유형": "DH", "적용시작연도": 1900},
    ]).to_csv(site_path, index=False)
    dept_path = tmp_path / "dept_code_master.csv"
    pd.DataFrame([{"부서코드": "4040", "부서명": "세종지사 관리부", "처, 지사": "세종지사"}]).to_csv(dept_path, index=False)
    monkeypatch.setattr(mapping_config, "SITE_TYPE_PATH", str(site_path))
    monkeypatch.setattr(mapping_config, "DEPT_MASTER_PATH", str(dept_path))

    df = pd.DataFrame([{"사업장": "4040.0", "연도": 2025, "계정과목": "기계장치", "금액": 100.0}])
    out = apply_mappings(df)
    assert out.iloc[0]["지사유형"] == "DH"


def test_get_site_display_name_resolves_4digit_code_against_7digit_dept_master(tmp_path, monkeypatch):
    """실적의 손익센터(4자리)와 예산의 부서코드(6~7자리)는 자릿수가 달라도 매칭되어야 한다."""
    dept_path = tmp_path / "dept_code_master.csv"
    pd.DataFrame([
        {"부서코드": "3100001", "부서명": "동탄지사 고객지원부", "처, 지사": "동탄지사"},
        {"부서코드": "4020001", "부서명": "양산지사 고객지원부", "처, 지사": "양산지사"},
        {"부서코드": "4022004", "부서명": "김해사업소 고객지원부", "처, 지사": "김해사업소"},
    ]).to_csv(dept_path, index=False)
    monkeypatch.setattr(mapping_config, "SITE_TYPE_PATH", str(tmp_path / "site_type_map.csv"))
    monkeypatch.setattr(mapping_config, "DEPT_MASTER_PATH", str(dept_path))

    assert get_site_display_name("3100.0") == "동탄지사"
    assert get_site_display_name("4020") == "양산지사"
    assert get_site_display_name("4022") == "김해사업소"


def test_load_site_type_map_does_not_reread_file_when_unchanged(tmp_path, monkeypatch):
    """실제 버그였던 성능 문제 재현: get_site_display_name()/get_current_site_type()가 실적 데이터
    수천 행에 .apply()로 호출되면서 매 행마다 site_type_map.csv를 다시 읽으면 대시보드 첫 계산이
    오래 걸린다. 파일이 안 바뀌었으면 여러 번 호출해도 실제 read_csv는 한 번만 일어나야 한다."""
    site_path = tmp_path / "site_type_map.csv"
    pd.DataFrame([{"사업장": "700001", "표시명": "화성지사", "지사유형": "중대형CHP", "적용시작연도": 1900}]) \
        .to_csv(site_path, index=False)
    monkeypatch.setattr(mapping_config, "SITE_TYPE_PATH", str(site_path))
    mapping_config._site_type_map_cache.clear()

    read_calls = []
    original_read_csv = pd.read_csv

    def _counting_read_csv(path, *args, **kwargs):
        read_calls.append(path)
        return original_read_csv(path, *args, **kwargs)

    monkeypatch.setattr(pd, "read_csv", _counting_read_csv)

    for _ in range(50):
        mapping_config.load_site_type_map()
    assert len(read_calls) == 1

    # 파일이 실제로 바뀌면(mtime 변경) 다시 읽어야 한다.
    import time
    import os
    time.sleep(0.05)
    pd.DataFrame([{"사업장": "700002", "표시명": "동탄지사", "지사유형": "중대형CHP", "적용시작연도": 1900}]) \
        .to_csv(site_path, index=False)
    os.utime(site_path, (os.path.getmtime(site_path) + 1, os.path.getmtime(site_path) + 1))

    updated = mapping_config.load_site_type_map()
    assert len(read_calls) == 2
    assert "700002" in updated["사업장"].tolist()


def test_get_site_display_name_does_not_reread_files_per_row(tmp_path, monkeypatch):
    """get_site_display_name()을 실적 데이터처럼 여러 행에 반복 호출해도(.apply() 시나리오)
    site_type_map.csv/dept_code_master.csv를 행마다 다시 읽지 않아야 한다."""
    site_path = tmp_path / "site_type_map.csv"
    pd.DataFrame([{"사업장": "700001", "표시명": "화성지사", "지사유형": "중대형CHP", "적용시작연도": 1900}]) \
        .to_csv(site_path, index=False)
    dept_path = tmp_path / "dept_code_master.csv"
    pd.DataFrame([{"부서코드": "7000010", "부서명": "화성지사 관리부", "처, 지사": "화성지사"}]).to_csv(dept_path, index=False)
    monkeypatch.setattr(mapping_config, "SITE_TYPE_PATH", str(site_path))
    monkeypatch.setattr(mapping_config, "DEPT_MASTER_PATH", str(dept_path))
    mapping_config._site_type_map_cache.clear()
    mapping_config._dept_master_cache.clear()

    read_calls = []
    original_read_csv = pd.read_csv

    def _counting_read_csv(path, *args, **kwargs):
        read_calls.append(path)
        return original_read_csv(path, *args, **kwargs)

    monkeypatch.setattr(pd, "read_csv", _counting_read_csv)

    codes = ["700001", "9999", "700001", "9999"] * 25  # 미매핑 코드도 섞어 폴백 경로까지 반복 호출
    for code in codes:
        get_site_display_name(code)

    assert len(read_calls) <= 2  # site_type_map.csv 1회 + dept_code_master.csv 1회
