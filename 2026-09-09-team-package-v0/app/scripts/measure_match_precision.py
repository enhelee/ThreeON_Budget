# -*- coding: utf-8 -*-
"""전표 단위 매칭 정밀도 측정 — 사람이 확정한 귀속을 정답으로.

심사 예상 질문 1순위 «자동 매칭이 전표 하나하나를 얼마나 맞히나»에 숫자로 답한다.
DB 를 읽기만 한다(실행 이력·학습표를 쓰지 않는다). 운영 DB 에 직접 붙이지 말고
백업 사본(SQLite)에 돌린다.

정답(두 층):
  · 엄격 — 사람이 전표마다 고른 귀속(override 표, 재배정). 사람이 «틀렸다»고 판단한 전표라
    자동 매칭에는 가장 어려운 표본이다.
  · 넓게 — 마감된 연도의 최종 귀속(최신 실행의 match_line). 재배정되지 않은 전표는 사람이
    검토 후 그대로 받아들인 것으로 본다(«수용»이지 전표별 «확인»은 아니다).

예측(자동 매칭만, 재배정 없이):
  · 학습 없음   — 규칙·사업명 유사도만(첫해 도입 상태).
  · 과년도 학습 — 앞선 연도들을 마감하며 학습했다면 쌓였을 학습표(learned_before).
    그 해의 사람 판단은 보지 못한다 — «내년 첫 분석»과 같은 조건.

사용:
  python scripts/measure_match_precision.py --db <budget.db> [--years 2023 2024 2025]
                                            [--json out.json] [--check]
  --check : 지금 DB 상태 그대로(학습표 전체 + 재배정) 다시 돌려 최신 실행과 같은지 먼저 본다.

표본 검수(편향 없는 정밀도):
  python scripts/measure_match_precision.py --db <budget.db> --years 2025 --audit-sample 검수.xlsx
  (담당자가 «검수(O/X)» 칸을 채운 뒤)
  python scripts/measure_match_precision.py --audit-score 검수.xlsx
"""
import argparse
import json
import os
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

import pandas as pd  # noqa: E402

from budget import db as dbm  # noqa: E402
from budget import pipeline_actual  # noqa: E402

AUTO_CONF = dbm.LEARN_MIN_CONF        # 0.80 — 상세 화면 «자동확정»·학습 기준과 같다
ASSIGNED = ("계획집행", "신규")
BANDS = ((AUTO_CONF, 1.01, f"≥{AUTO_CONF:.2f} 자동확정"),
         (0.50, AUTO_CONF, f"0.50~{AUTO_CONF:.2f}"),
         (-1.0, 0.50, "<0.50 저확신"))


def _name(v):
    s = "" if v is None or (isinstance(v, float) and pd.isna(v)) else str(v).strip()
    return s[len("[신규] "):] if s.startswith("[신규] ") else s


def _target(o):
    return _name(o["사업명"] if isinstance(o, dict) else o)


def run_matching(conn, year, budget, learned, overrides):
    """run_actual_db 와 같은 입력으로 매칭만 — 기록·파일 없음. 반환: erp_annotated."""
    with tempfile.TemporaryDirectory() as out:
        res = pipeline_actual.run_actual_frames(
            dbm.load_plan_df(conn, year), dbm.load_erp_df(conn, year), None, conn, out,
            year, budget, overrides=overrides, learned=learned,
            biz_edits=dbm.list_biz_edits(conn, year, budget),
            attr_map=dbm.load_item_attr_map(conn, year),
            code_to_item=dbm.load_code_to_item(conn, year),
            deptcode_map=dbm.load_deptcode_map(conn, year),
            manual_biz=dbm.list_manual_biz(conn, year, budget),
            biz_deletes=dbm.list_biz_deletes(conn, year, budget), make_files=False)
    a = res["erp_annotated"]
    return pd.DataFrame({"erp_row_id": a["_erp_row"].astype(int),
                         "pred": a["매칭사업명"].map(_name),
                         "pred_구분": a["구분"],
                         "conf": pd.to_numeric(a["매칭확신도"], errors="coerce"),
                         "basis": a["매칭근거"].fillna("")})


def final_assignment(conn, year, budget):
    """정답(넓게) — 최신 실행의 귀속. 금액은 erp_row 천원."""
    run = dbm.latest_run(conn, year, budget)
    rows = conn.execute(
        "SELECT m.erp_row_id, m.매칭사업명, m.구분, e.금액천원 FROM match_line m"
        " JOIN erp_row e ON e.id = m.erp_row_id WHERE m.run_id=?", (run["id"],)).fetchall()
    df = pd.DataFrame(rows, columns=["erp_row_id", "gt", "gt_구분", "amt"])
    df["gt"] = df["gt"].map(_name)
    df["amt"] = pd.to_numeric(df["amt"], errors="coerce").fillna(0).abs()
    return df[df["gt_구분"].isin(ASSIGNED)]


def learned_before(conn, year):
    """그 해보다 앞선 연도들을 마감할 때마다 [AI 학습]을 눌렀다면 쌓였을 학습표.

    운영 학습표의 source_year 로 거르면 안 된다 — 키마다 마지막 학습만 남아 2024 학습이
    2025 학습에 덮여 사라졌다. 임시 사본에서 학습표를 비우고 제품의 learn_from_year 를
    앞 연도부터 차례로 돌려 다시 만든다(사람 확정 > 자동 확정 규칙도 그대로)."""
    prior = [r[0] for r in conn.execute(
        "SELECT DISTINCT year FROM run WHERE year < ? ORDER BY year", (str(year),))]
    if not prior:
        return {}
    with tempfile.TemporaryDirectory() as d:
        tmp = sqlite3.connect(os.path.join(d, "learn.db"))
        conn.backup(tmp)
        tmp.execute("DELETE FROM learned_match")
        for y in prior:
            dbm.learn_from_year(tmp, y)
        learned = dbm.load_learned(tmp)
        tmp.close()
    return learned


def _rate(ok, n):
    return round(100.0 * ok / n, 1) if n else None


def score(df, mask_name="전체"):
    """df: erp_row_id·gt·amt·pred·conf·human(bool). 일치율·확신도 구간별 정밀도."""
    n = len(df)
    hit = df["pred"] == df["gt"]
    out = {"표본": mask_name, "전표수": n, "일치": int(hit.sum()), "일치율%": _rate(hit.sum(), n),
           "금액가중 일치율%": _rate(df.loc[hit, "amt"].sum(), df["amt"].sum()), "구간": []}
    for lo, hi, label in BANDS:
        m = (df["conf"].fillna(-0.5) >= lo) & (df["conf"].fillna(-0.5) < hi)
        k = int(m.sum())
        out["구간"].append({"구간": label, "전표수": k, "비중%": _rate(k, n),
                           "정밀도%": _rate((hit & m).sum(), k),
                           "금액가중 정밀도%": _rate(df.loc[hit & m, "amt"].sum(), df.loc[m, "amt"].sum())})
    auto = df["conf"].fillna(-1) >= AUTO_CONF
    out["자동확정 재현율%"] = _rate((hit & auto).sum(), n)   # 전체 중 «자동확정 + 정답» 비율
    wrong = ~hit
    out["틀린 전표 중 저확신 표시%"] = _rate((wrong & ~auto).sum(), wrong.sum())
    # 매칭 근거별 — 어느 규칙이 얼마나 맞히나(틀린 «자동확정»이 어디서 나오나)
    g = df.assign(hit=hit, auto=auto, bad_auto=wrong & auto).groupby("basis")
    out["근거별"] = [{"근거": k or "(없음)", "전표수": int(v["hit"].size), "정밀도%": _rate(v["hit"].sum(), v["hit"].size),
                    "틀린 자동확정": int(v["bad_auto"].sum())}
                   for k, v in sorted(g, key=lambda kv: -kv[1]["hit"].size)]
    return out


_LEARNED = {}     # 연도 → learned_before 결과(손익·자본이 같이 쓴다)


def measure(conn, year, budget):
    gt = final_assignment(conn, year, budget)
    ov = dbm.override_map(conn, year, budget)
    human = {int(k): _target(v) for k, v in ov.items()}
    gt["human"] = gt["erp_row_id"].isin(human.keys())
    # 엄격 정답은 사람이 고른 이름 — 최종 실행과 다를 일은 없지만(재배정이 반영된 실행) 명시적으로 쓴다.
    gt.loc[gt["human"], "gt"] = gt.loc[gt["human"], "erp_row_id"].map(human)
    result = {"연도": str(year), "예산": budget, "정답 전표": len(gt), "사람 확정 전표": int(gt["human"].sum())}
    if str(year) not in _LEARNED:
        _LEARNED[str(year)] = learned_before(conn, year)
    for label, learned in (("학습 없음", {}), ("과년도 학습", _LEARNED[str(year)])):
        pred = run_matching(conn, year, budget, learned, {})
        df = gt.merge(pred, on="erp_row_id", how="left")
        df["pred"] = df["pred"].fillna("")
        result[label] = {"학습 키": len(learned), "넓게": score(df, "최종 귀속 전체"),
                         "엄격": score(df[df["human"]], "사람 확정(재배정)")}
    return result


def check_reproduces(conn, year, budget):
    """지금 상태 그대로 다시 돌리면 최신 실행과 같은가 — 측정 장치 검증."""
    gt = final_assignment(conn, year, budget)
    pred = run_matching(conn, year, budget, dbm.load_learned(conn), dbm.override_map(conn, year, budget))
    df = gt.merge(pred, on="erp_row_id", how="left")
    return int((df["pred"].fillna("") != df["gt"]).sum()), len(df)


# ── 표본 검수 — «검토 후 수용»이 아닌 «사람이 확인한» 정밀도 ─────────────────
# 넓은 정답은 재배정되지 않은 전표를 «맞다»로 친다(상한). 확신도 구간마다 무작위로 뽑은
# 전표를 담당자가 하나씩 O/X 로 보면 편향 없는 정밀도와 신뢰구간을 말할 수 있다.
AUDIT_COLS = ["번호", "예산", "확신도 구간", "전표번호", "전기일", "예산과목", "처지사", "전표 텍스트",
              "금액(천원)", "확신도", "매칭 근거", "자동 매칭 사업명", "최종 확정 사업명",
              "검수(O/X)", "메모"]


def _band(conf):
    c = -0.5 if conf is None or pd.isna(conf) else float(conf)
    return next(label for lo, hi, label in BANDS if lo <= c < hi)


def audit_sample(conn, year, per_band, seed=2026, budgets=("손익", "자본")):
    """확신도 구간마다 per_band 건 — 손익·자본을 합친 귀속 전표에서 무작위(재현 가능한 seed)."""
    frames = []
    for b in budgets:
        if not dbm.latest_run(conn, year, b):
            continue
        df = final_assignment(conn, year, b).merge(run_matching(conn, year, b, {}, {}),
                                                  on="erp_row_id", how="left")
        df["예산"] = b
        frames.append(df)
    pool = pd.concat(frames, ignore_index=True)
    pool["확신도 구간"] = pool["conf"].map(_band)
    picked = pd.concat([g.sample(min(per_band, len(g)), random_state=seed)
                        for _, g in pool.groupby("확신도 구간", sort=False)], ignore_index=True)
    ids = ",".join(str(int(i)) for i in picked["erp_row_id"])
    erp = pd.DataFrame(conn.execute(
        f"SELECT id, 전표번호, 전기일, 예산과목원문, 지사원문, 사업명 FROM erp_row WHERE id IN ({ids})").fetchall(),
        columns=["erp_row_id", "전표번호", "전기일", "예산과목", "처지사", "전표 텍스트"])
    out = picked.merge(erp, on="erp_row_id", how="left").sample(frac=1, random_state=seed)  # 구간 순서를 감춘다
    out = out.rename(columns={"amt": "금액(천원)", "conf": "확신도", "basis": "매칭 근거",
                              "pred": "자동 매칭 사업명", "gt": "최종 확정 사업명"})
    out["번호"] = range(1, len(out) + 1)
    out["검수(O/X)"] = ""
    out["메모"] = ""
    population = pool["확신도 구간"].value_counts().to_dict()
    return out[AUDIT_COLS], population


def write_audit_xlsx(path, sample, population, year):
    guide = pd.DataFrame({"안내": [
        f"{year}년 귀속 전표에서 확신도 구간마다 무작위로 뽑은 표본입니다.",
        "«자동 매칭 사업명»이 이 전표의 올바른 사업이면 O, 아니면 X 를 «검수(O/X)» 칸에 적어 주세요.",
        "«최종 확정 사업명»은 참고용입니다 — 최종이 틀렸다고 보이면 메모에 적어 주세요.",
        "다 채우면: python scripts/measure_match_precision.py --audit-score <이 파일>",
    ]})
    pop = pd.DataFrame([{"확신도 구간": k, "모집단 전표": v} for k, v in population.items()])
    with pd.ExcelWriter(path) as w:
        sample.to_excel(w, sheet_name="검수", index=False)
        pop.to_excel(w, sheet_name="모집단", index=False)
        guide.to_excel(w, sheet_name="안내", index=False)


def _wilson(k, n, z=1.96):
    if not n:
        return None, None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / d
    return round(100 * (c - h), 1), round(100 * (c + h), 1)


def audit_score(sample, population):
    """채운 검수표 → 구간별 정밀도(95% Wilson 구간) + 모집단 비중으로 가중한 전체 추정."""
    s = sample.copy()
    s["판정"] = s["검수(O/X)"].astype(str).str.strip().str.upper().map({"O": True, "X": False})
    done = s[s["판정"].notna()]
    rows, est = [], 0.0
    total = sum(population.values())
    for _, _, label in BANDS:
        g = done[done["확신도 구간"] == label]
        n, k = len(g), int(g["판정"].sum())
        lo, hi = _wilson(k, n)
        rows.append({"구간": label, "검수": n, "정답": k, "정밀도%": _rate(k, n),
                     "95% 구간": None if lo is None else f"{lo}~{hi}",
                     "모집단 전표": population.get(label, 0)})
        if n:
            est += (k / n) * population.get(label, 0) / total
    return {"검수 완료": len(done), "미기입": int(s["판정"].isna().sum()),
            "구간별": rows, "전체 추정 정밀도%": round(100 * est, 1)}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", help="SQLite 사본 경로(운영 PG 에 직접 쓰지 말 것)")
    ap.add_argument("--years", nargs="*", default=None)
    ap.add_argument("--budgets", nargs="*", default=["손익", "자본"])
    ap.add_argument("--json", default=None)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--audit-sample", metavar="XLSX",
                    help="표본 검수표 만들기(--years 첫 연도). 실데이터 — 저장소 밖에 둘 것")
    ap.add_argument("--per-band", type=int, default=67, help="확신도 구간마다 뽑을 전표 수(기본 67 → 약 200건)")
    ap.add_argument("--audit-score", metavar="XLSX", help="채운 검수표로 정밀도 계산(DB 불필요)")
    a = ap.parse_args()
    if a.audit_score:
        sample = pd.read_excel(a.audit_score, sheet_name="검수", dtype={"검수(O/X)": str})
        pop = pd.read_excel(a.audit_score, sheet_name="모집단")
        r = audit_score(sample, dict(zip(pop["확신도 구간"], pop["모집단 전표"])))
        print(f"검수 {r['검수 완료']}건 (미기입 {r['미기입']}) · 전체 추정 정밀도 {r['전체 추정 정밀도%']}%")
        for row in r["구간별"]:
            print(f"  {row['구간']}: {row['정답']}/{row['검수']} = {row['정밀도%']}% (95% {row['95% 구간']})")
        return
    if not a.db:
        ap.error("--db 가 필요합니다")
    os.environ.pop("DATABASE_URL", None)
    conn = dbm.connect(a.db)
    if a.audit_sample:
        year = (a.years or [r[0] for r in conn.execute("SELECT MAX(year) FROM year_lock")])[0]
        sample, pop = audit_sample(conn, year, a.per_band, budgets=a.budgets)
        write_audit_xlsx(a.audit_sample, sample, pop, year)
        print(f"{year}년 표본 {len(sample)}건 → {a.audit_sample} · 모집단 {pop}")
        return
    years = a.years or [r[0] for r in conn.execute("SELECT year FROM year_lock ORDER BY year")]
    results = []
    for y in years:
        for b in a.budgets:
            if not dbm.latest_run(conn, y, b):
                continue
            if a.check:
                diff, n = check_reproduces(conn, y, b)
                print(f"[재현] {y} {b}: 최신 실행과 다른 전표 {diff} / {n}")
            r = measure(conn, y, b)
            results.append(r)
            for label in ("학습 없음", "과년도 학습"):
                w, s = r[label]["넓게"], r[label]["엄격"]
                print(f"{y} {b} [{label}] 넓게 {w['일치율%']}% ({w['전표수']}건, 금액 {w['금액가중 일치율%']}%)"
                      f" · 자동확정 정밀도 {w['구간'][0]['정밀도%']}% · 엄격 {s['일치율%']}% ({s['전표수']}건)")
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
