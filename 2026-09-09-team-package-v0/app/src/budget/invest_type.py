# -*- coding: utf-8 -*-
"""투자유형 — «무엇 때문에 쓰는 돈인가» 축 (2026-10-14, 팀장 요청 «투자유형까지 나눠서 예측»).

예산과목(수선유지비·기계장치 …)은 회계 분류라 «노후설비를 바꾸는 돈인지, AX/DX 개선인지»가 안 보인다.
사람이 해마다 «실적 분석» 엑셀에서 1억 이상 사업에 붙여 온 투자유형 라벨(자본 10종, 손익 25년 40종,
설비개선 세부 11종)을 아래 공통 분류표 하나로 묶고, 그 라벨을 학습 데이터로 써서 나머지 사업도 분류한다.

분류 3단계: 대분류(정기/비정기) → 투자유형(13) → 세부.
분류 출처 4가지(신뢰 순):
  과목규칙  예산과목만 보면 유형이 정해지는 것(정기점검·경상정비·재생고온부품 …)
  사람      실적 분석 엑셀에 사람이 붙인 라벨(같은 «사업명 예산과목»)
  낱말규칙  사업명에 LTSA·고온부품·돌발·노후 같은 낱말
  모델      그 밖 — 학습 모델(투자유형_사업명) 예측, 신뢰도 함께
분류표는 팀 확정 전 초안이다(확인 필요 항목은 NOTE 참고).
"""
import os
import re
import unicodedata
from collections import defaultdict

import openpyxl
import pandas as pd

from . import config_store, ml_registry, normalize

# ── 분류표 ────────────────────────────────────────────────────────────────

TAXONOMY = [
    # 대분류, 투자유형, 세부(예), 예측 방법, 필요한 자료
    ("정기", "정기점검·정비", ["열원 정기점검", "A급·MI 정비", "수처리·유체커플링·공기압축기"],
     "정비등급 일정 × 등급별 표준금액", "정비등급 이력·정기점검 일정"),
    ("정기", "LTSA", ["GT LTSA", "연료전지 LTSA"], "계약 계획 그대로", "LTSA 계약 계획"),
    ("정기", "고온부품·재생정비", ["고온부품 재생", "신품 구매"], "고온부품 발주 계획 그대로", "고온부품 계획"),
    ("정기", "설비 유지보수 용역", ["소방", "무정전", "항온항습", "굴뚝", "태양광", "승강기", "가스감지기", "냉수냉방", "수질"],
     "최근 3개년 평균 × 물가", "실적"),
    ("정기", "법정검사·진단·검교정", ["법정검사", "검교정", "진단", "환경측정", "안전검사", "보건"],
     "법정 주기 × 단가 (또는 3개년 평균 × 물가)", "실적(·검사 주기표)"),
    ("정기", "경상정비", ["경상정비"], "최근실적 × 물가", "실적"),
    ("정기", "예비품·저장품", ["자산화예비품", "저장품"], "등급별 표준금액", "정비등급 일정"),
    ("정기", "자재·공기구", ["자재구매", "공기구 구매", "예비품 대체"], "최근 3개년 평균 × 물가", "실적"),
    ("비정기", "노후설비 교체", ["기계", "전기", "제어", "분산제어"],
     "설치연도·내용연수로 교체 시기 (없으면 과거 평균)", "설비대장(설치연도·내용연수)"),
    ("비정기", "설비개선", ["AX/DX", "GX", "안전강화", "환경강화", "운영안정성", "설비안정성", "정비효율향상",
                         "수익개선", "보안강화", "교육강화", "근무환경개선"],
     "중장기 투자계획(정책 목표) + 과거 비율", "투자계획"),
    ("비정기", "돌발복구", ["돌발복구"], "과거 평균(예비비 성격)", "실적"),
    ("비정기", "건물·구축물 보수", ["도장", "방수", "보수공사"], "주기 × 면적·단가 (또는 5개년 평균)", "실적"),
    ("비정기", "기타", ["기타"], "과거 평균", "실적"),
]
TYPES = [t[1] for t in TAXONOMY]
TYPE_GROUP = {t[1]: t[0] for t in TAXONOMY}

# 사람 라벨(실적 분석 K열) → (투자유형, 세부). 자본 «X/노후설비»는 세부가 앞쪽 X.
RAW_MAP = {
    # 자본
    "정기점검": ("정기점검·정비", None), "LTSA": ("LTSA", None), "재생정비": ("고온부품·재생정비", "고온부품 재생"),
    "기계/노후설비": ("노후설비 교체", "기계"), "전기/노후설비": ("노후설비 교체", "전기"),
    "제어/노후설비": ("노후설비 교체", "제어"), "분산제어/노후설비": ("노후설비 교체", "분산제어"),
    "설비개선": ("설비개선", None), "돌발복구": ("돌발복구", None), "기타": ("기타", None),
    # 손익 23·24
    "노후설비": ("노후설비 교체", None), "정기사업": ("정기점검·정비", "정기사업"), "환경": ("법정검사·진단·검교정", "환경측정"),
    # 손익 25 (40종)
    "열원": ("정기점검·정비", "열원 정기점검"), "수처리": ("정기점검·정비", "수처리"), "유체커플링": ("정기점검·정비", "유체커플링"),
    "공기압축기": ("정기점검·정비", "공기압축기"),
    "소방": ("설비 유지보수 용역", "소방"), "무정전": ("설비 유지보수 용역", "무정전"), "항온항습": ("설비 유지보수 용역", "항온항습"),
    "굴뚝": ("설비 유지보수 용역", "굴뚝"), "태양광": ("설비 유지보수 용역", "태양광"), "승강기": ("설비 유지보수 용역", "승강기"),
    "가스감지기": ("설비 유지보수 용역", "가스감지기"), "냉수냉방": ("설비 유지보수 용역", "냉수냉방"), "수질": ("설비 유지보수 용역", "수질"),
    "자동화": ("설비 유지보수 용역", "자동화"), "가스엔진": ("설비 유지보수 용역", "가스엔진"), "SRF": ("설비 유지보수 용역", "SRF"),
    "CP": ("설비 유지보수 용역", "CP"), "밸브": ("설비 유지보수 용역", "밸브"),
    "법정검사": ("법정검사·진단·검교정", "법정검사"), "검교정": ("법정검사·진단·검교정", "검교정"), "진단": ("법정검사·진단·검교정", "진단"),
    "안전": ("법정검사·진단·검교정", "안전검사"), "보건": ("법정검사·진단·검교정", "보건"), "수수료": ("법정검사·진단·검교정", "수수료"),
    "용역": ("법정검사·진단·검교정", "용역"),
    "경상정비": ("경상정비", None), "분산제어": ("경상정비", "분산제어"),
    "도장": ("건물·구축물 보수", "도장"), "방수": ("건물·구축물 보수", "방수"), "보수공사": ("건물·구축물 보수", "보수공사"),
    "자재구매": ("자재·공기구", "자재구매"), "공기구구매": ("자재·공기구", "공기구 구매"), "예비품대체": ("자재·공기구", "예비품 대체"),
    "공사": ("설비개선", None),
}
# 팀 확정 때 짚을 것 — 화면·문서에 그대로 보여준다
NOTE = {
    "정기사업": "손익 «열원보완개선» 안의 정기사업 — 정기점검·정비로 봤는데 성격 확인 필요",
    "공사": "손익 «열원보완개선» 안의 «공사» 27건 — 설비개선으로 봤는데 노후교체일 수도",
    "환경": "지급수수료의 «환경»(측정 수수료) — 법정검사 계열로 봤음. 자본 «환경강화»(설비개선 세부)와 다름",
    "안전": "지급수수료의 «안전»(검사) — 법정검사 계열로 봤음",
}

# 예산과목만으로 유형이 정해지는 것(과목규칙). 여기 없는 과목(기계장치·보완개선·정기유지보수·외주비 공사 등)은 모델이 나눈다.
ITEM_RULE = {
    "수선유지비-열원정기점검": ("정기점검·정비", "열원 정기점검"),
    "외주비-열원정기점검": ("정기점검·정비", "A급·MI 정비"),
    "건설중인자산-재생고온부품": ("고온부품·재생정비", "고온부품 재생"),
    "수선유지비-열원경상정비": ("경상정비", None),
    "수선유지비-건물/구축물": ("건물·구축물 보수", None),
    "지급수수료-열원점검수수료": ("법정검사·진단·검교정", None),
    "건설중인자산-자산화예비품": ("예비품·저장품", "자산화예비품"),
    "저장품-열원(보수)": ("예비품·저장품", "저장품"),
    "공구와기구-열원시설공기구": ("자재·공기구", "공기구 구매"),
    "건물": ("건물·구축물 보수", None), "구축물": ("건물·구축물 보수", None),
}

# 사업명에 이 낱말이 있으면 유형이 거의 정해진다(모델이 LTSA 8건을 0건 맞혔다 — 표본이 적어서).
# 사람 라벨이 있으면 사람이 이긴다. 순서대로 먼저 맞는 것.
KEYWORD_RULE = [
    (re.compile(r"LTSA|장기\s*유지보수\s*계약", re.I), "LTSA"),
    (re.compile(r"고온\s*부품|재생\s*정비"), "고온부품·재생정비"),
    (re.compile(r"돌발"), "돌발복구"),
    (re.compile(r"노후"), "노후설비 교체"),
]

TYPE_MODEL = "투자유형_사업명"
DETAIL_MODEL = "투자유형세부_사업명"
_WS = re.compile(r"\s+")


def text_of(사업명, 예산과목):
    """모델 입력 — 팀 v2 와 같은 «사업명 예산과목»."""
    return f"{_WS.sub(' ', str(사업명 or '')).strip()} {str(예산과목 or '').strip()}".strip()


def keyword_type(text):
    for pat, t in KEYWORD_RULE:
        if pat.search(str(text or "")):
            return t
    return None


def map_raw(raw, detail=None):
    """사람 라벨 → (투자유형, 세부). 모르는 라벨은 (None, None)."""
    key = str(raw or "").strip()
    t, d = RAW_MAP.get(key, (None, None))
    det = str(detail or "").strip() or None
    return t, (det or d)


# ── 실적 분석 엑셀 → 라벨 ───────────────────────────────────────────────────

def labels_from_workbook(path):
    """«(YY년) 손익|자본예산 실적|계획 분석» 엑셀 1개 → 라벨 행 DataFrame.

    열: 연도·예산·지사·예산과목·사업명·금액·원라벨·원세부·투자유형·세부·text
    사업명이 있는 머리글 행을 찾고, 그 아래에서 투자유형 열(K, 11번째)이 찬 행만 쓴다.
    금액은 «최종 실적금액(B)»(I열) — 계획 분석 파일은 연예산.
    """
    name = unicodedata.normalize("NFC", os.path.basename(path))
    m = re.search(r"\((\d{2})년\)", name)
    year = 2000 + int(m.group(1)) if m else None
    budget = "손익" if "손익" in name else "자본"
    alias = config_store.seed_item_alias()
    out = []
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        for ws in wb.worksheets:
            rows = ws.iter_rows(values_only=True)
            head = None
            for i, r in enumerate(rows):
                if i > 6:
                    break
                if any(isinstance(v, str) and "사업명" in v for v in r):
                    head = r
                    break
            if head is None:
                continue
            for r in rows:
                if len(r) < 11 or not isinstance(r[10], str) or not r[10].strip() or not r[6]:
                    continue
                raw, det = r[10].strip(), (r[12].strip() if len(r) > 12 and isinstance(r[12], str) else "")
                t, d = map_raw(raw, det)
                item = normalize.normalize_item(r[1], alias) if r[1] else ""
                amt = r[8] if isinstance(r[8], (int, float)) else 0.0
                out.append({"연도": year, "예산": budget, "지사": str(r[4] or "").strip(), "예산과목": item,
                            "사업명": str(r[6]).strip(), "금액": float(amt), "원라벨": raw, "원세부": det or None,
                            "투자유형": t, "세부": d, "text": text_of(r[6], item)})
    finally:
        wb.close()
    return pd.DataFrame(out)


def labels_from_files(paths):
    frames = [labels_from_workbook(p) for p in paths]
    frames = [f for f in frames if len(f)]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def store_labels(conn, labels, actor=None):
    """라벨을 두 모델의 학습데이터로 넣는다(사람 확정). 같은 text·label 은 add_examples 가 걸러낸다."""
    ok = labels[labels["투자유형"].notna()]
    n1 = ml_registry.add_examples(conn, TYPE_MODEL, list(zip(ok["text"], ok["투자유형"])),
                                  source="실적분석", actor=actor, confirmed=True)
    det = ok[ok["세부"].notna()]
    n2 = ml_registry.add_examples(conn, DETAIL_MODEL, list(zip(det["text"], det["투자유형"] + "/" + det["세부"])),
                                  source="실적분석", actor=actor, confirmed=True)
    return {"투자유형": n1, "세부": n2, "모르는 라벨": sorted(set(labels.loc[labels["투자유형"].isna(), "원라벨"]))}


# ── 사업 분류 ────────────────────────────────────────────────────────────────

def _human_lookup(conn):
    """학습데이터의 사람 확정 라벨 {text: 투자유형}."""
    df = ml_registry.examples_frame(conn, TYPE_MODEL)
    if df.empty:
        return {}
    df = df[df["confirmed"].astype(int) == 1]
    return dict(zip(df["text"], df["label"]))


def classify_frame(conn, df, item_col="예산과목", name_col="사업명"):
    """사업 행 DataFrame 에 투자유형·대분류·분류출처·신뢰도 열을 붙여 돌려준다."""
    df = df.copy()
    texts = [text_of(n, i) for n, i in zip(df[name_col], df[item_col])]
    human = _human_lookup(conn)
    _, model = ml_registry.load_active_model(conn, TYPE_MODEL)
    pred, conf = ([None] * len(df), [None] * len(df))
    if model is not None and len(df):
        pred, conf = ml_registry.predict(model, texts)
    types, srcs, confs = [], [], []
    for i, (item, t) in enumerate(zip(df[item_col], texts)):
        kw = keyword_type(t)
        if item in ITEM_RULE:
            types.append(ITEM_RULE[item][0]); srcs.append("과목규칙"); confs.append(1.0)
        elif t in human:
            types.append(human[t]); srcs.append("사람"); confs.append(1.0)
        elif kw:
            types.append(kw); srcs.append("낱말규칙"); confs.append(1.0)
        elif pred[i] is not None:
            types.append(pred[i]); srcs.append("모델"); confs.append(conf[i])
        else:
            types.append("미분류"); srcs.append("미분류"); confs.append(None)
    df["투자유형"] = types
    df["대분류"] = [TYPE_GROUP.get(t, "미분류") for t in types]
    df["분류출처"] = srcs
    df["분류신뢰도"] = confs
    return df


# 실적 분석에 쓰는 구분 — 계획집행·신규만 돈이 실제로 나갔다
KEEP = ("계획집행", "신규")


def actuals_by_type(conn, years=None):
    """마감(또는 지정) 연도 최신 분석의 사업별 실적 → 투자유형 분류 행."""
    from . import db as dbm
    years = [str(y) for y in (years or sorted(dbm.locked_years(conn)))]
    rows = []
    for y in years:
        for budget in ("손익", "자본"):
            run = dbm.latest_run(conn, y, budget)
            if not run:
                continue
            for dept, item, name, amt, gubun in conn.execute(
                    "SELECT 처지사,예산과목,사업명,실적금액,구분 FROM biz_line WHERE run_id=?", (run["id"],)):
                if gubun in KEEP and amt:
                    rows.append({"연도": int(y), "예산": budget, "지사": dept, "예산과목": item,
                                 "사업명": name, "금액": float(amt)})
    df = pd.DataFrame(rows, columns=["연도", "예산", "지사", "예산과목", "사업명", "금액"])
    return classify_frame(conn, df) if len(df) else df.assign(투자유형=[], 대분류=[], 분류출처=[], 분류신뢰도=[])


def summary_by_type(df):
    """연도 × 투자유형 합계(천원)와 분류 출처 비율."""
    if df.empty:
        return {"years": [], "rows": [], "sources": {}}
    years = sorted(df["연도"].unique())
    piv = df.pivot_table(index="투자유형", columns="연도", values="금액", aggfunc="sum", fill_value=0.0)
    rows = []
    for t in TYPES + ["미분류"]:
        if t not in piv.index:
            continue
        rows.append({"대분류": TYPE_GROUP.get(t, "미분류"), "투자유형": t,
                     **{str(y): float(piv.loc[t, y]) if y in piv.columns else 0.0 for y in years}})
    src = df.groupby("분류출처")["금액"].sum()
    return {"years": [int(y) for y in years], "rows": rows,
            "sources": {k: float(v) for k, v in (src / src.sum()).items()}}


def forecast_by_type(conn, base_year, forecast_total_rows, actual_rows):
    """과목별 전망을 투자유형으로 나눈다.

    과목규칙 과목은 그 유형으로 통째로, 나머지(기계장치·보완개선·정기유지보수 등)는 마감 연도 실적에서
    그 과목이 투자유형별로 나뉜 비율대로 나눈다(과거 비율 배분 — 1차 방법).
    전망 표의 과목 이름(«기계장치_기타기계장치» 등)은 실적 과목으로 되돌려 비율을 찾는다.
    """
    share = defaultdict(lambda: defaultdict(float))
    for r in actual_rows.itertuples():
        share[r.예산과목][r.투자유형] += r.금액
    years = [k for k in (forecast_total_rows[0].keys() if forecast_total_rows else []) if k != "예산과목"]
    out = defaultdict(lambda: defaultdict(float))
    for row in forecast_total_rows:
        label = row["예산과목"]
        item = FORECAST_TO_ITEM.get(label, label)
        if label in FORECAST_RULE:
            dist = {FORECAST_RULE[label]: 1.0}
        elif item in ITEM_RULE:
            dist = {ITEM_RULE[item][0]: 1.0}
        elif share.get(item):
            tot = sum(share[item].values())
            dist = {t: v / tot for t, v in share[item].items()} if tot else {"미분류": 1.0}
        else:
            dist = {"미분류": 1.0}
        for y in years:
            for t, w in dist.items():
                out[t][y] += float(row[y]) * w
    rows = [{"대분류": TYPE_GROUP.get(t, "미분류"), "투자유형": t, **{y: out[t][y] for y in years}}
            for t in TYPES + ["미분류"] if t in out and any(out[t].values())]
    return {"base_year": str(base_year), "years": years, "rows": rows}


# 전망 표(forecast_calc) 의 과목 라벨 → 실적 과목 / 바로 정해지는 유형
FORECAST_TO_ITEM = {
    "기계장치_기타기계장치": "기계장치", "기계장치_고온부품재생": "기계장치",
    "건설중인자산_재생고온부품": "건설중인자산-재생고온부품", "건물/구축물": "건물",
    "비저장품(보수자재)": "수선유지비-비저장품(보수자재)", "소모품(자재공기구)": "수선유지비-소모품(자재공기구)",
}
FORECAST_RULE = {
    "기계장치_고온부품재생": "고온부품·재생정비",       # 고온부품 계획(+LTSA) 그대로
    "비저장품(보수자재)": "자재·공기구", "소모품(자재공기구)": "자재·공기구",
    "투자비": "설비개선",                               # 열원공사비 등 — 팀 확인 필요
}


# ── 화면·내보내기 ─────────────────────────────────────────────────────────────

def _model_info(conn, name):
    for m in ml_registry.list_models(conn, name):
        if m["active"]:
            return {"version": m["version"], "trained_at": m["trained_at"], "n_samples": m["n_samples"],
                    "n_classes": m["n_classes"], "cv_accuracy": (m["metrics"] or {}).get("cv_accuracy")}
    return None


def report(conn, base_year):
    """«투자유형별» 탭 한 화면치 — 분류표·과거 실적·전망·분류 출처·모델 상태."""
    from . import pipeline_forecast as pf
    actual = actuals_by_type(conn)
    fc = pf.run_forecast(conn, base_year)
    return {
        "base_year": str(base_year),
        "taxonomy": [{"대분류": g, "투자유형": t, "세부": d, "예측방법": how, "필요자료": need}
                     for g, t, d, how, need in TAXONOMY],
        "notes": [{"라벨": k, "내용": v} for k, v in NOTE.items()],
        "actual": summary_by_type(actual),
        "forecast": forecast_by_type(conn, base_year, fc["total_rows"], actual),
        "model": {"투자유형": _model_info(conn, TYPE_MODEL), "세부": _model_info(conn, DETAIL_MODEL),
                  "examples": ml_registry.example_stats(conn, TYPE_MODEL)},
    }


def type_rows(conn, year, 투자유형, limit=300):
    """그 해 그 유형으로 분류된 사업(금액 큰 순) — 행을 눌렀을 때 펼치는 목록."""
    df = actuals_by_type(conn, [year])
    if df.empty:
        return []
    df = df[df["투자유형"] == 투자유형].sort_values("금액", ascending=False).head(limit)
    return [{"예산": r.예산, "지사": r.지사, "예산과목": r.예산과목, "사업명": r.사업명, "금액": float(r.금액),
             "분류출처": r.분류출처, "분류신뢰도": r.분류신뢰도} for r in df.itertuples()]


def export_workbook(conn, base_year):
    """분류표 · 과거 실적 · 전망 · 사업별 분류(마감 연도 전체) 네 시트 xlsx bytes."""
    import io
    rep = report(conn, base_year)
    detail = actuals_by_type(conn)
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        pd.DataFrame([{**t, "세부": ", ".join(t["세부"])} for t in rep["taxonomy"]]).to_excel(w, sheet_name="분류표", index=False)
        pd.DataFrame(rep["actual"]["rows"]).to_excel(w, sheet_name="과거실적_투자유형별(천원)", index=False)
        pd.DataFrame(rep["forecast"]["rows"]).to_excel(w, sheet_name="전망_투자유형별(천원)", index=False)
        detail.to_excel(w, sheet_name="사업별_분류", index=False)
    return buf.getvalue()
