"""Test 모드 화면들의 '만들기' 버튼으로 생성한 결과가 앱을 재시작해도 남아있게 하는 공용 헬퍼.

각 화면은 자신의 입력 데이터(공유 실적 DataFrame + 관련 파일들)로 지문(fingerprint)을 만들어
파일로 저장해둔다. 다음에 화면을 열었을 때 현재 지문과 저장된 지문이 같으면 이미 '작성됨'으로
보고 다시 계산을 요구하지 않는다.

지문만 저장하는 것으로는 부족하다 - st.cache_data는 프로세스 메모리에만 남기 때문에, 앱을
재시작하면(지문은 그대로라도) 캐시가 비어 첫 호출은 여전히 다시 계산된다. 그래서 실제로 "다시
계산하지 않으려면" 계산 결과 자체(artifact)도 파일로 저장해뒀다가 지문이 같으면 그걸 그대로
불러와야 한다 - save_artifact()/load_artifact()가 그 역할이다(pickle, DataFrame이든 dict든 그대로
저장 가능). 지문이 다르면(데이터가 바뀌었으면) 상태 표시에 안내한다.
"""
import os
import json
import pickle
import pandas as pd

BUILD_STATE_DIR = "test_data"  # longterm_forecast.TEST_DATA_DIR과 동일한 폴더(순환 임포트를 피하려고 상수를 그대로 반복)


def fingerprint(df: pd.DataFrame = None, paths: tuple = ()) -> str:
    """df(있으면 내용 기반 해시) + paths(각 파일의 절대경로와 mtime)를 합쳐 지문 문자열을 만든다.
    df 내용이 바뀌거나(새로 업로드/수정) paths의 어느 파일이든 새로 저장되면(mtime 변경) 지문이 달라진다."""
    parts = []
    if df is not None:
        if df.empty:
            parts.append("empty")
        else:
            try:
                parts.append(str(int(pd.util.hash_pandas_object(df, index=True).sum())))
            except Exception:
                parts.append(f"len={len(df)}")
    for p in paths:
        if os.path.exists(p):
            parts.append(f"{os.path.abspath(p)}:{os.path.getmtime(p)}")
        else:
            parts.append(f"{os.path.abspath(p)}:missing")
    return "|".join(parts)


def _state_path(name: str) -> str:
    return os.path.join(BUILD_STATE_DIR, f"{name}_build_state.json")


def load_build_fingerprint(name: str) -> str:
    path = _state_path(name)
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f).get("fingerprint")
    except Exception:
        return None


def save_build_fingerprint(name: str, fp: str):
    os.makedirs(BUILD_STATE_DIR, exist_ok=True)
    with open(_state_path(name), "w", encoding="utf-8") as f:
        json.dump({"fingerprint": fp}, f)


def _artifact_path(name: str) -> str:
    return os.path.join(BUILD_STATE_DIR, f"{name}_artifact.pkl")


def save_artifact(name: str, obj):
    """계산 결과(DataFrame, dict of DataFrame 등 - pickle 가능한 아무 객체)를 파일로 저장한다."""
    os.makedirs(BUILD_STATE_DIR, exist_ok=True)
    with open(_artifact_path(name), "wb") as f:
        pickle.dump(obj, f)


def load_artifact(name: str):
    """저장해둔 계산 결과를 그대로 불러온다. 없거나 손상됐으면 None(호출부가 다시 계산해야 함)."""
    path = _artifact_path(name)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "rb") as f:
            return pickle.load(f)
    except Exception:
        return None
