"""
아직 투자유형 분류 체계가 없는 예산과목의 사업명들을, 텍스트 유사도로 몇 개 그룹으로
나눠 '분류 후보'를 제안하는 도구.

- project_type_classifier.py(지도학습)와 달리 정답 라벨이 없는 상태에서 쓰는 비지도(클러스터링) 도구다.
- 결과는 어디까지나 '후보'이며, 사람이 각 그룹을 보고 이름(투자유형/투자유형세부)을 붙여야
  project_type_classifier의 학습데이터로 들어간다.
"""
import glob
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.cluster import KMeans
from project_type_classifier import is_in_scope_account


def list_budget_categories() -> list[str]:
    """budget_*.csv에 등장하는 예산과목 목록(중복 제거, 가나다순).
    지금 다루기로 한 범위(기계장치/외주비 계열)만 반환한다."""
    cats = set()
    for f in glob.glob("budget_*.csv"):
        try:
            df = pd.read_csv(f, dtype=str)
        except Exception:
            continue
        if "예산과목" in df.columns:
            cats.update(df["예산과목"].dropna().astype(str).str.strip().unique().tolist())
    return sorted(c for c in cats if c and is_in_scope_account(c))


def project_names_for_category(category: str) -> list[str]:
    """특정 예산과목에 속한 사업명 목록(중복 제거)을 모든 연도의 budget_*.csv에서 모은다."""
    names = set()
    for f in glob.glob("budget_*.csv"):
        try:
            df = pd.read_csv(f, dtype=str)
        except Exception:
            continue
        if "예산과목" not in df.columns or "사업명" not in df.columns:
            continue
        sub = df[df["예산과목"].astype(str).str.strip() == category]
        names.update(sub["사업명"].dropna().astype(str).str.strip().unique().tolist())
    return sorted(n for n in names if n)


def suggest_clusters(names: list[str], n_clusters: int, samples_per_cluster: int = 8) -> list[dict]:
    """
    사업명 목록을 텍스트 유사도(문자 n-gram)로 n_clusters개 그룹으로 나눈다.
    사람이 각 그룹을 보고 이름을 붙일 수 있도록, 그룹별 건수와 대표 예시를 함께 반환한다.
    (건수가 큰 그룹부터 정렬. 재현 가능하도록 결과가 항상 동일하게 나오게 고정한다)
    """
    if not names:
        return []
    if len(names) < 2 or n_clusters <= 1:
        return [{"cluster": 0, "count": len(names), "members": sorted(names),
                  "examples": sorted(names)[:samples_per_cluster]}]

    n_clusters = min(n_clusters, len(names))
    vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4))
    X = vec.fit_transform(names)
    km = KMeans(n_clusters=n_clusters, n_init=10, random_state=0)
    labels = km.fit_predict(X)

    groups: dict[int, list[str]] = {}
    for name, lab in zip(names, labels):
        groups.setdefault(int(lab), []).append(name)

    result = []
    for lab, members in groups.items():
        members = sorted(members)
        result.append({"cluster": lab, "count": len(members), "members": members,
                        "examples": members[:samples_per_cluster]})
    result.sort(key=lambda g: -g["count"])
    return result
