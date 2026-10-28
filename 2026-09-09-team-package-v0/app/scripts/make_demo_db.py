# -*- coding: utf-8 -*-
"""시연용 더미 DB — 실데이터 사본을 «하나의 치환표»로 바꾸고 분석을 다시 돌린다(경진대회 D).

최종기획서 «3. 사용 데이터 더미데이터화 검토»에 적은 방법 그대로:
  · 지사명 코드화(지사A~S) — 지사·사업소 이름과 그 지명(«화성»→지사C)·열원 지명(«상암»→지점가)을 같은 표로 바꾼다
  · 금액 × 0.8~1.2 무작위 계수 — 지사마다 계수 하나, 계획과 전표에 같은 계수(총액 보존 구조 유지)
  · 전표번호 재부여(같은 번호끼리는 같은 새 번호) · 거래처코드 삭제 · 전표 글자 속 업체명 치환
  · 기준정보는 코드 체계 유지, 지사·부서명만 치환 · 학습·이력에도 같은 치환표 · 작업자명 가명
  · 분석 결과(run·match_line·biz_line)는 지우고 바뀐 계획·전표로 앱의 분석을 다시 돌린다
본사 처 이름(플랜트기술처 등)은 그대로 둔다 — 매칭 규칙(본사 배분)이 그 이름을 쓴다.

사용(실데이터 사본에만 — 운영 DB 에 붙이지 말 것):
  python scripts/make_demo_db.py --src <실데이터 사본.db> --out <더미 폴더> [--seed 2026] [--unlock 2025]
  → <더미 폴더>/budget.db (시연용) · 치환표.xlsx (실명이 들어 있다 — 공유하지 말 것) · 점검 결과 출력
"""
import argparse
import json
import os
import random
import re
import shutil
import sqlite3
import string
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

import pandas as pd  # noqa: E402

from budget import db as dbm, pipeline_db  # noqa: E402

# 지사 이름에 없지만 전표·사업명에 자주 나오는 열원·설비 지명(운영 사본에서 빈도로 찾았다).
EXTRA_PLACES = ["세종누리", "동수원", "동남권", "광양항", "상암", "수서", "일원", "가락", "장안", "난지",
                "동백", "문정", "신안", "강릉", "서초", "함백", "누리"]
# 설비 제조사 등 업체명(낱말 경계로만 바꾼다 — «GE» 가 «GEAR» 안에서 바뀌지 않게)
VENDORS = ["한국안전기술협회", "한전KPS", "Siemens", "지멘스", "Emerson", "Hitachi", "두산", "ABB", "GE"]
_CORP = re.compile(r"(\(주\)|㈜)[가-힣A-Za-z0-9]+|주식회사\s*[가-힣A-Za-z0-9]+")   # (주)한빛 · ㈜한빛 · 주식회사 한빛
_CORP_AFTER = re.compile(r"[가-힣A-Za-z0-9]+(\(주\)|㈜)")                 # 한빛(주) — 띄어 쓴 앞 낱말은 업체명이 아닐 수 있다
# 지명이 일반 낱말 안에 든 경우 — 바꾸면 안 된다(«비용인식»의 «용인», «확대구축»의 «대구»). 운영 사본에서 찾았다.
#   «비용인식»은 학습 키에서 지우는 표기라(normalize._INSTALLMENT) 깨지면 학습 매칭이 달라진다.
PROTECT = ["비용역인식", "비용 역인식", "비용인식", "비용 인식", "확대구축", "대구매", "중앙제어", "중앙 제어",
           "일원화", "일원관리", "일원 관리"]
_PROTECT_RE = re.compile("|".join(re.escape(w) for w in sorted(PROTECT, key=len, reverse=True)))
KOR = "가나다라마바사아자차카타파하거너더러머버서어저처커터퍼허"
# 글자를 바꾸지 않는 열(날짜·코드·경로 등)
SKIP_COLS = {"at", "created_at", "uploaded_at", "locked_at", "unlocked_at", "updated_at", "method", "path",
             "전기일", "연도", "year", "base_year", "budget", "계정코드", "예산코드", "부서코드", "사업장코드",
             "source", "source_year", "kind", "그룹", "속성", "등급", "구분"}
GENERIC_OPS = {"테스트", "검증자", "홍길동", "메모리측정", "침입테스트", "배포검증"}   # 사람 이름이 아닌 작업자 표기
DERIVED = ("run", "match_line", "biz_line")      # 분석 결과 — 지우고 다시 만든다
AMOUNT = {"plan_row": ("처지사", ["연예산"]), "manual_biz": ("처지사", ["연예산"]),
          "reference_actual": ("사업장", ["금액"]), "reference_standard": ("사업장", ["표준금액"]),
          "regular_contract": ("사업장", ["금액"]), "cri_rule": ("사업장", ["기준단가"]),
          "benchmark_rule": ("사업장", ["조정액"]), "forecast_hot_parts": ("사업장", ["금액"]),
          "investment_plan": ("사업장", ["금액"]), "hq_master": ("열", ["금액"]),
          "benchmark_override": ("사업장", ["표준금액"]), "forecast_surprise": ("사업장", ["금액"])}


def build_mapping(conn, seed):
    """치환표 — (원문 → 더미) 목록(긴 것부터) · 지사 계수 · 작업자 가명."""
    rng = random.Random(seed)
    rows = conn.execute("SELECT 이름, 그룹, MIN(순서) FROM dept_config GROUP BY 이름, 그룹 ORDER BY MIN(순서), 이름").fetchall()
    sites = [n for n, g, _ in rows if g != "본사"]
    hqs = [n for n, g, _ in rows if g == "본사"]
    letters = string.ascii_uppercase
    pairs, site_map = [], {}
    for i, name in enumerate(sites):
        code = letters[i] if i < 26 else f"{letters[i // 26 - 1]}{letters[i % 26]}"
        site_map[name] = f"지사{code}"
        pairs.append((name, f"지사{code}"))
        stem = re.sub(r"(지사|사업소)$", "", name)
        if stem and stem != name:
            pairs.append((stem, f"지사{code}"))      # 전표 «지사원문»에 «파주»만 적힌 행이 많다 — 같은 이름이어야 지사로 정규화된다
    for i, p in enumerate(EXTRA_PLACES):
        pairs.append((p, f"지점{KOR[i % len(KOR)]}"))
    pairs.sort(key=lambda kv: -len(kv[0]))
    factor = {name: round(rng.uniform(0.8, 1.2), 4) for name in sites + hqs}
    ops = [r[0] for r in conn.execute("SELECT DISTINCT operator FROM audit_log WHERE operator IS NOT NULL ORDER BY operator")]
    op_map = {o: f"작업자{i + 1}" for i, o in enumerate(ops)}
    return {"pairs": pairs, "site_map": site_map, "factor": factor, "global": round(rng.uniform(0.8, 1.2), 4),
            "operators": op_map}


def make_text_fn(mapping):
    pat = re.compile("|".join(re.escape(a) for a, _ in mapping["pairs"]))
    rep = dict(mapping["pairs"])
    vendor = re.compile("|".join(rf"(?<![A-Za-z]){re.escape(v)}(?![A-Za-z])" for v in VENDORS))
    vrep = {v: f"제조사{KOR[i]}" for i, v in enumerate(VENDORS)}

    keep = _PROTECT_RE

    def text(s):
        if not isinstance(s, str) or not s:
            return s
        held = []
        s = keep.sub(lambda m: held.append(m.group(0)) or f"§§{len(held) - 1}§§", s)
        s = _CORP.sub("(주)업체", s)
        s = _CORP_AFTER.sub("업체(주)", s)
        s = vendor.sub(lambda m: vrep[m.group(0)], s)
        s = pat.sub(lambda m: rep[m.group(0)], s)
        return re.sub(r"§§(\d+)§§", lambda m: held[int(m.group(1))], s)
    return text


def _site_factor(mapping, name):
    if not name:
        return mapping["global"]
    if name in mapping["factor"]:
        return mapping["factor"][name]
    for site, k in mapping["factor"].items():         # «(CHP)광교지사 고객지원부» · «파주» 같은 원문
        stem = re.sub(r"(지사|사업소)$", "", site)
        if site in str(name) or (stem != site and len(stem) >= 2 and stem in str(name)):
            return k
    return mapping["global"]


def transform(conn, mapping):
    text = make_text_fn(mapping)
    # 전표 → 처지사(최신 분석) — 금액 계수를 계획과 맞추려고. 원문 지사로는 본사 배분 전표의 처지사를 모른다.
    erp_site = dict(conn.execute(
        "SELECT erp_row_id, 처지사정규 FROM match_line WHERE run_id IN"
        " (SELECT MAX(id) FROM run GROUP BY year, budget)").fetchall())
    for t in DERIVED:
        conn.execute(f'DELETE FROM "{t}"')
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'"
                                         " AND name NOT LIKE 'sqlite_%'")]
    voucher_no = {}
    for t in tables:
        cols = [(r[1], (r[2] or "").upper(), r[5]) for r in conn.execute(f'PRAGMA table_info("{t}")')]
        names = [c for c, _, _ in cols]
        df = pd.read_sql_query(f'SELECT * FROM "{t}"', conn)
        if df.empty:
            continue
        site_col, amt_cols = AMOUNT.get(t, (None, []))
        if t == "erp_row":
            k = [_site_factor(mapping, erp_site.get(int(i)) or w) for i, w in zip(df["id"], df["지사원문"])]
            df["금액원"] = (df["금액원"].astype(float) * pd.Series(k)).round(0)
            df["금액천원"] = df["금액원"] / 1000.0
            df["거래처코드"] = None
            for v in sorted(df["전표번호"].dropna().astype(str).unique()):
                voucher_no.setdefault(v, f"D{len(voucher_no) + 1:08d}")
            df["전표번호"] = df["전표번호"].map(lambda v: voucher_no.get(str(v)) if pd.notna(v) else v)
        elif amt_cols and site_col in df.columns:
            k = df[site_col].map(lambda s: _site_factor(mapping, s))
            for c in amt_cols:
                if c in df.columns:
                    df[c] = pd.to_numeric(df[c], errors="coerce") * k
        if t == "biz_edit" and "fields_json" in df.columns:
            def scale_fields(row):
                try:
                    f = json.loads(row["fields_json"] or "{}")
                except ValueError:
                    return row["fields_json"]
                if f.get("연예산") not in (None, ""):
                    f["연예산"] = float(f["연예산"]) * _site_factor(mapping, row["처지사"])
                return json.dumps(f, ensure_ascii=False)
            df["fields_json"] = df.apply(scale_fields, axis=1)
        if t == "audit_log":
            df["operator"] = df["operator"].map(lambda o: mapping["operators"].get(o, o))
        for c, typ, _ in cols:
            if c in SKIP_COLS or c == "operator" or "BLOB" in typ:
                continue
            if df[c].dtype == object or pd.api.types.is_string_dtype(df[c]):
                df[c] = df[c].astype(object).map(text)
        conn.execute(f'DELETE FROM "{t}"')
        ph = ",".join("?" * len(names))
        q = f'INSERT OR REPLACE INTO "{t}" ({",".join(chr(34) + n + chr(34) for n in names)}) VALUES ({ph})'
        conn.executemany(q, [tuple(None if (isinstance(v, float) and v != v) else v for v in r)
                             for r in df[names].itertuples(index=False, name=None)])
    # 코드에 박힌 지사 별칭(config_store.SEED_DEPT_ALIAS, «서울남부지사 → 강남지사» 등)은 실명을 가리킨다.
    #   DB 별칭이 기본값보다 우선하므로, 같은 별칭을 치환한 이름으로 DB 에 넣는다(전표 원문도 치환돼 있어 치환된 키면 된다).
    from budget import config_store
    for src, dst in config_store.SEED_DEPT_ALIAS.items():
        for key in {text(src)}:
            conn.execute("INSERT OR REPLACE INTO alias(종류, 원표기, 정규표기) VALUES('dept', ?, ?)", (key, text(dst)))
    # 데이터셋 총액은 바뀐 행으로 다시
    conn.execute("UPDATE dataset SET total_amount = (SELECT SUM(금액천원) FROM erp_row e WHERE e.dataset_id = dataset.id)"
                 " WHERE kind != 'plan'")
    conn.execute("UPDATE dataset SET total_amount = (SELECT SUM(연예산) FROM plan_row p WHERE p.dataset_id = dataset.id)"
                 " WHERE kind = 'plan'")
    conn.commit()
    return voucher_no


def reanalyze(conn):
    """바뀐 계획·전표로 분석을 다시 — 연도·예산마다(학습표·재배정·사업 수정은 치환된 그대로 쓴다)."""
    years = sorted({r[0] for r in conn.execute("SELECT year FROM dataset")})
    out = []
    with tempfile.TemporaryDirectory() as d:
        for y in years:
            for b in ("손익", "자본"):
                try:
                    res = pipeline_db.run_actual_db(conn, d, y, b, make_files=False)
                except ValueError as e:              # 그 해 계획·전표가 없으면 건너뛴다
                    out.append((y, b, f"건너뜀: {e}"))
                    continue
                out.append((y, b, res["요약"]))
    return out


def leftovers(conn, mapping):
    """치환 뒤 남은 원문 지명·작업자명 — 0 이어야 한다."""
    people = [o for o in mapping["operators"] if re.fullmatch(r"[가-힣]{2,4}", o) and o not in GENERIC_OPS]
    words = [a for a, _ in mapping["pairs"]] + people
    hits = {}
    for (t,) in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"):
        cols = [r[1] for r in conn.execute(f'PRAGMA table_info("{t}")') if r[1] not in SKIP_COLS]
        for c in cols:
            for (v,) in conn.execute(f'SELECT DISTINCT "{c}" FROM "{t}" WHERE typeof("{c}")=\'text\''):
                v = _PROTECT_RE.sub("", v)          # 일부러 지킨 낱말(«비용인식» 등) 안의 지명은 세지 않는다
                for w in words:
                    if w and w in v:
                        hits[(t, c, w)] = hits.get((t, c, w), 0) + 1
    return hits


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--src", required=True, help="실데이터 SQLite 사본(읽기만 — 복사해서 바꾼다)")
    ap.add_argument("--out", required=True, help="더미 DB 를 둘 폴더(저장소 밖)")
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--unlock", nargs="*", default=[], help="시연에서 재배정할 연도 — 마감을 풀어 둔다(예: 2025)")
    a = ap.parse_args()
    os.environ.pop("DATABASE_URL", None)
    os.makedirs(a.out, exist_ok=True)
    dst = os.path.join(a.out, "budget.db")
    if os.path.abspath(dst) == os.path.abspath(a.src):
        sys.exit("--out 은 원본과 다른 폴더여야 합니다.")
    shutil.copyfile(a.src, dst)
    conn = sqlite3.connect(dst)
    mapping = build_mapping(conn, a.seed)
    transform(conn, mapping)
    results = reanalyze(conn)
    for y in a.unlock:                       # 시연의 «재배정 1클릭» 장면은 마감 안 된 연도에서만 된다
        conn.execute("DELETE FROM year_lock WHERE year=?", (str(y),))
    conn.commit()
    conn.execute("VACUUM")
    for y, b, s in results:
        print(y, b, s if isinstance(s, str) else {k: s.get(k) for k in list(s)[:8]})
    left = leftovers(conn, mapping)
    print("남은 원문 지명·작업자명:", sum(left.values()), "건" + ("" if not left else f" — {list(left)[:10]}"))
    with pd.ExcelWriter(os.path.join(a.out, "치환표.xlsx")) as w:
        pd.DataFrame(mapping["pairs"], columns=["원문", "더미"]).to_excel(w, sheet_name="지명", index=False)
        pd.DataFrame([{"지사": k, "더미": mapping["site_map"].get(k, k), "금액 계수": v}
                      for k, v in mapping["factor"].items()]).to_excel(w, sheet_name="금액 계수", index=False)
        pd.DataFrame(list(mapping["operators"].items()), columns=["원문", "가명"]).to_excel(w, sheet_name="작업자", index=False)
    print("완료:", dst)


if __name__ == "__main__":
    main()
