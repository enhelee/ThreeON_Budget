# -*- coding: utf-8 -*-
"""참고 엑셀(예산표준화 V3 양식) 가져오기 — 표준화 방향 반영의 출발점(2026-10-26).

재무·플랜트관리부가 손으로 만든 «예산표준화(25년실적 반영)» 통합문서 한 권에서 아래를 읽는다.
**파싱만 한다** — 저장은 화면이 미리보기를 확인한 뒤 `/api/forecast/reference/apply` 로 한다.

  지사 시트(시트명 = 지사 이름에서 «지사»·«사업소»를 뗀 것)
    4~21행   계정별 연도 실적         → reference_actual (유형 = 기타 | 고온부품재생 | CRI | LTSA)
    28~31행  기계장치 분해(정기/CRI/투자비/기타)   → 기계장치 실적의 유형
    «… LTSA» 행(동탄)                 → 정기유지보수 실적 중 LTSA
    손익소계 아래 설비 행(#1 GT·ST·DH…)  → site_grade_eq, 대표 등급 → site_grade
    «… Standization» 표               → reference_standard(값·수식) + benchmark_rule(수식 해석)
  그룹 시트(중대형chp·소형CHP·DH)의 합산 수식 → 연도별 소속 = site_history
  표준화방향 시트의 «화성->파주» 같은 짝 + CRI 실적  → cri_rule 초안
  «… LTSA» 행의 최근 실적                          → regular_contract 초안(최근 실적 유지 가정)

수식 해석은 «엑셀이 실제로 쓰는 모양»만 안다(아래 _rule_from_formula). 모르는 모양은 엑셀 값을
그대로 쓰는 «직접 입력» 규칙이 된다 — 숫자는 엑셀과 같고, 사유에 원래 수식이 남는다.
"""
import io
import re

import pandas as pd
from openpyxl import load_workbook
from openpyxl.utils import column_index_from_string, get_column_letter

from .forecast_import import site_sheet_map

# 엑셀 계정 라벨 → 앱 예산과목
ACCOUNT_LABELS = {
    "저장품-열원(보수)": "저장품-열원(보수)",
    "건 물": "건물", "건물": "건물",
    "구축물": "구축물",
    "기계장치": "기계장치",
    "공구와기구-열원시설공기구": "공구와기구-열원시설공기구",
    "공구와기구": "공구와기구-열원시설공기구",
    "건가-외주비-열원정기점검": "외주비-열원정기점검",
    "건설중인자산-재생고온부품": "건설중인자산-재생고온부품",
    "건설중인자산-자산화예비품": "건설중인자산-자산화예비품",
    "수선유지비-건물/구축물": "수선유지비-건물/구축물",
    "수선유지비-열원정기점검": "수선유지비-열원정기점검",
    "수선유지비-열원경상정비": "수선유지비-열원경상정비",
    "수선유지비-열원정기유지보수": "수선유지비-열원정기유지보수",
    "수선유지비-열원정기유지보수(LTSA 제외)": "수선유지비-열원정기유지보수",
    "수선유지비-열원보완개선및기타": "수선유지비-열원보완및개선",
    "지급수수료-열원점검수수료": "지급수수료-열원점검수수료",
    "- (비정기, 표준화) 기타기계장치": "기계장치",
}
PL_ACCOUNTS = {"수선유지비-건물/구축물", "수선유지비-열원정기점검", "수선유지비-열원경상정비",
               "수선유지비-열원정기유지보수", "수선유지비-열원보완및개선", "지급수수료-열원점검수수료"}
GRADE_TOKENS = {"MI", "TI", "CI", "BSI", "HGPI", "간이", "A", "B", "C", "표준"}
GROUP_SHEETS = {"중대형chp": "중대형CHP", "소형chp": "소형CHP", "dh": "DH"}
SUBTOTALS = {"자본소계", "손익소계"}

_REF = r"(?:'?([^'!=+\-*/(),]+)'?!)?\$?([A-Z]{1,2})\$?(\d+)"
_RE_REF = re.compile(_REF)
_RE_RANGE = re.compile(r"(?:'?([^'!=+\-*/(),]+)'?!)?\$?([A-Z]{1,2})\$?(\d+):\$?([A-Z]{1,2})\$?(\d+)")


def _label(v):
    return re.sub(r"\s+", " ", str(v or "")).strip()


def _num(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def norm_grade(token):
    """엑셀 등급 표기를 앱 등급으로 — 'A급'→A, 'CI(광교만 시행)'→CI, '동남권 MI'→MI, 'C->A'→A, '준A'→A."""
    t = _label(token)
    if not t or t in ("-", "비고"):
        return ""
    if "->" in t:
        t = t.split("->")[-1].strip()
    t = re.sub(r"\(.*?\)", "", t).strip()
    t = t.replace("급", "").replace("준", "").strip()
    for g in ("MI", "TI", "CI", "BSI", "HGPI"):
        if g in t.upper().split() or t.upper().endswith(g):
            return g
    return t


class _Sheet:
    """지사 시트 한 장 — 값(v)·수식(f) 두 벌과 행 역할."""

    def __init__(self, site, wv, wf):
        self.site, self.v, self.f = site, wv, wf
        self.year_by_col = {}
        for r in range(1, 8):
            cols = {c: int(wv.cell(r, c).value) for c in range(2, wv.max_column + 1)
                    if isinstance(wv.cell(r, c).value, (int, float)) and 2000 < wv.cell(r, c).value < 2100}
            if len(cols) >= 3:
                self.year_by_col = cols
                break
        self.latest = max(self.year_by_col.values()) if self.year_by_col else None
        self.account_row, self.split_row, self.std_rows = {}, {}, {}
        self.std_headers = []          # [(header_row, kind, {col: grade})]
        sub = None
        for r in range(1, wv.max_row + 1):
            lab = _label(wv.cell(r, 1).value)
            if "Standization" in lab:
                kind = "손익" if "손익" in lab else "자본"
                grades = {}
                for c in range(2, wv.max_column + 1):
                    g = norm_grade(wv.cell(r, c).value)
                    if g in GRADE_TOKENS:
                        grades[c] = g
                self.std_headers.append((r, kind, grades))
                continue
            if self.std_headers:
                acct = ACCOUNT_LABELS.get(lab)
                if acct:
                    self.std_rows[r] = (acct, self.std_headers[-1][2])
                continue
            if lab == "손익소계":
                sub = r
            if lab in ACCOUNT_LABELS and lab != "- (비정기, 표준화) 기타기계장치" and sub is None:
                self.account_row.setdefault(ACCOUNT_LABELS[lab], r)
            low = lab.replace(" ", "")
            if "(정기)고온부품재생" in low:
                self.split_row[r] = ("기계장치", "고온부품재생")
            elif "(정기?)CRI" in low or "(정기)CRI" in low:
                self.split_row[r] = ("기계장치", "CRI")
            elif "기타기계장치" in low and "표준화" in low:
                self.split_row[r] = ("기계장치", "기타")
            elif "LTSA" in lab and lab.startswith("-") and "고온부품" not in lab:
                self.split_row[r] = ("수선유지비-열원정기유지보수", "LTSA")
            elif "(나머지)" in low and "유지보수" in low:
                self.split_row[r] = ("수선유지비-열원정기유지보수", "기타")
        self.subtotal_row = sub
        self.row_account = {r: a for a, r in self.account_row.items()}
        self.first_std = self.std_headers[0][0] if self.std_headers else 10 ** 6

    # ── 실적 ────────────────────────────────────────────────────────────────
    def actuals(self):
        out = {}
        for acct, r in self.account_row.items():
            for c, y in self.year_by_col.items():
                out[(y, acct, "기타")] = _num(self.v.cell(r, c).value) or 0.0
        split = {}
        for r, (acct, kind) in self.split_row.items():
            for c, y in self.year_by_col.items():
                val = _num(self.v.cell(r, c).value)
                if val is not None:
                    split.setdefault((y, acct), {}).setdefault(kind, 0.0)
                    split[(y, acct)][kind] += val
        for (y, acct), kinds in split.items():
            total = out.get((y, acct, "기타"), 0.0)
            regular = sum(v for k, v in kinds.items() if k != "기타")
            if not regular:
                continue
            for k, v in kinds.items():
                if k != "기타" and v:
                    out[(y, acct, k)] = v
            out[(y, acct, "기타")] = total - regular
        return [{"사업장": self.site, "연도": y, "예산과목": a, "유형": k, "금액": v}
                for (y, a, k), v in sorted(out.items())]

    # ── 설비별 등급 ─────────────────────────────────────────────────────────
    def equipment_grades(self):
        rows = []
        if self.subtotal_row is None:
            return rows
        r = self.subtotal_row + 1
        while r <= self.v.max_row and not _label(self.v.cell(r, 1).value):
            r += 1                                         # 손익소계 아래 보조 소계 줄
        while r <= self.v.max_row:
            eq = _label(self.v.cell(r, 1).value)
            vals = [_label(self.v.cell(r, c).value) for c in self.year_by_col]
            if not eq and not any(vals):
                break
            eq = eq or f"{r}행"
            for c, y in self.year_by_col.items():
                raw = _label(self.v.cell(r, c).value)
                if raw and raw != "-" and not raw.startswith("*"):
                    rows.append({"사업장": self.site, "연도": y, "설비": eq, "등급": raw})
            r += 1
        return rows

    def standard_grades(self):
        out = set()
        for _, _, grades in self.std_headers:
            out |= set(grades.values())
        return out

    def representative(self, eq_rows):
        """표준화 표의 등급 어휘와 가장 잘 맞는 설비 행을 대표로 고른다(동률이면 앞 행)."""
        vocab = self.standard_grades()
        by_eq = {}
        for row in eq_rows:
            by_eq.setdefault(row["설비"], []).append(row)
        best, score = None, -1
        for eq, rows in by_eq.items():
            s = sum(1 for x in rows if norm_grade(x["등급"]) in vocab)
            if s > score:
                best, score = eq, s
        if best is None:
            return []
        out = []
        gt_alias = {"A": "MI", "B": "TI", "C": "CI"}      # GT 행의 A급 = MI (동탄 2023 등)
        for x in by_eq[best]:
            g = norm_grade(x["등급"])
            if g and g not in vocab and gt_alias.get(g) in vocab:
                g = gt_alias[g]
            if g:
                out.append({"사업장": self.site, "연도": x["연도"], "등급": g})
        return out


def _year_of(sheet, col_letter):
    return sheet.year_by_col.get(column_index_from_string(col_letter))


def _cell_role(sheets, here, sheet_name, col, row):
    """참조 셀의 역할 — ('actual', 사업장, 예산과목, 연도) | ('std', 사업장, 예산과목, 등급) | None."""
    sh = here if not sheet_name else sheets.get(sheet_name.strip())
    if sh is None:
        return None
    row, c = int(row), column_index_from_string(col)
    if row >= sh.first_std:
        if row in sh.std_rows:
            acct, grades = sh.std_rows[row]
            if c in grades:
                return ("std", sh.site, acct, grades[c])
        return None
    year = sh.year_by_col.get(c)
    if year is None:
        return None
    if row in sh.row_account:
        return ("actual", sh.site, sh.row_account[row], year)
    if row in sh.split_row and sh.split_row[row][1] == "기타":
        return ("actual", sh.site, sh.split_row[row][0], year)
    return None


def _args(text):
    """AVERAGE/MAX 인자 → [(시트, 열, 행, 상수조정)]. 범위는 펼친다. 모르는 모양이면 None."""
    out = []
    for part in [p.strip() for p in text.split(",") if p.strip()]:
        m = _RE_RANGE.fullmatch(part)
        if m:
            sname, c1, r1, c2, r2 = m.groups()
            if r1 != r2:
                return None
            a, b = sorted((column_index_from_string(c1), column_index_from_string(c2)))
            out.extend((sname, get_column_letter(i), r1, 0.0) for i in range(a, b + 1))
            continue
        m = re.fullmatch(_REF + r"\s*([+-])\s*([\d.]+)", part)
        if m:
            sname, col, row, sign, k = m.groups()
            out.append((sname, col, row, (-1 if sign == "-" else 1) * float(k)))
            continue
        m = _RE_REF.fullmatch(part)
        if m:
            out.append((*m.groups(), 0.0))
            continue
        try:
            out.append((None, None, None, float(part)))     # 인자에 섞인 상수(예산 배정값 등)
        except ValueError:
            return None
    return out


def _rule_from_formula(sheets, here, acct, grade, formula, value):
    """표준화 표 셀 수식 하나 → 산정 규칙 dict. 모르면 직접 입력."""
    base = {"사업장": here.site, "예산과목": acct, "등급": grade, "연도목록": "", "보정률": None,
            "참조지사": "", "참조등급": "", "조정액": None}
    direct = dict(base, 방식="직접 입력", 조정액=float(value or 0.0),
                  사유=f"엑셀 값 그대로 (수식: {formula})" if isinstance(formula, str) else "엑셀 입력값")
    if not isinstance(formula, str) or not formula.startswith("="):
        return direct
    f = formula[1:].replace(" ", "")
    factor = None
    m = re.fullmatch(r"(.+)\*([\d.]+)", f)
    if m:
        f, factor = m.group(1), float(m.group(2))
    else:
        m = re.fullmatch(r"(.+)/([\d.]+)", f)
        if m:
            f, factor = m.group(1), 1.0 / float(m.group(2))
    reason = f"엑셀 수식 {formula}"

    m = re.fullmatch(r"(AVERAGE|MAX)\((.*)\)", f)
    if m:
        fn, args = m.groups()
        parsed = _args(args)
        if parsed is None:
            return direct
        years, adjust, ref_site = [], 0.0, None
        for sname, col, row, k in parsed:
            if col is None:
                return direct                    # 상수가 평균 인자로 섞이면 재현 불가 → 값 고정
            role = _cell_role(sheets, here, sname, col, row)
            if not role or role[0] != "actual" or role[2] != acct:
                return direct
            if ref_site not in (None, role[1]):
                return direct
            ref_site = role[1]
            years.append(role[3])
            adjust += k
        if fn == "MAX":
            if adjust:
                return direct
            return dict(base, 방식="최대값", 연도목록=",".join(map(str, years)), 보정률=factor,
                        참조지사="" if ref_site == here.site else ref_site, 사유=reason)
        n = len(years)
        latest = here.latest
        method, ylist = "지정연도 평균", ",".join(map(str, years))
        contiguous = sorted(years) == list(range(min(years), max(years) + 1))
        if ref_site == here.site and contiguous and max(years) == latest and n in (3, 5) and "$" in formula:
            method, ylist = f"{n}개년 평균", ""
        return dict(base, 방식=method, 연도목록=ylist, 보정률=factor,
                    참조지사="" if ref_site == here.site else ref_site,
                    조정액=(adjust / n) * (factor or 1.0) if adjust else None, 사유=reason)

    m = _RE_REF.fullmatch(f)
    if m:
        role = _cell_role(sheets, here, *m.groups())
        if role is None or role[2] != acct:
            return direct
        if role[0] == "std":
            if (role[1], role[3]) == (here.site, grade):
                return direct
            return dict(base, 방식="등급 차용", 참조지사="" if role[1] == here.site else role[1],
                        참조등급=role[3], 보정률=factor, 사유=reason)
        site, year = role[1], role[3]
        if site == here.site and "$" in formula and year == here.latest:
            return dict(base, 방식="최근실적", 보정률=factor, 사유=reason)
        if site == here.site and here.grade_by_year.get(year) == grade and \
                year == max(y for y, g in here.grade_by_year.items() if g == grade):
            return dict(base, 방식="등급별 최근실적", 보정률=factor, 사유=reason)
        return dict(base, 방식="지정연도 평균", 연도목록=str(year), 보정률=factor,
                    참조지사="" if site == here.site else site, 사유=reason)
    return direct


def _group_history(wb_f, sheets_by_name, latest):
    """그룹 시트의 합산 수식(4행)에서 연도별 소속을 읽어 연혁 구간으로 압축한다."""
    member = {}
    for name in wb_f.sheetnames:
        key = re.sub(r"\(.*?\)", "", name).strip().lower()
        group = GROUP_SHEETS.get(key)
        if not group:
            continue
        ws = wb_f[name]
        for c in range(2, ws.max_column + 1):
            head = str(ws.cell(3, c).value or "")
            m = re.match(r"(\d{4})", head)
            f = ws.cell(4, c).value
            if not m or not isinstance(f, str):
                continue
            year = int(m.group(1))
            for sname in re.findall(r"'?([^'!=+]+)'?!", f):
                sh = sheets_by_name.get(sname.strip())
                if sh:
                    member.setdefault(sh.site, {})[year] = group
    rows = []
    for site, by_year in sorted(member.items()):
        spans = []
        for y in sorted(by_year):
            if spans and spans[-1][2] == by_year[y] and spans[-1][1] == y - 1:
                spans[-1][1] = y
            else:
                spans.append([y, y, by_year[y]])
        for i, (a, b, g) in enumerate(spans):
            last = i == len(spans) - 1
            rows.append({"사업장": site, "시작연도": a,
                         "종료연도": None if last else b, "그룹": g, "설비": "", "비고": "참고 엑셀 그룹 합산 수식"})
    return rows


def parse_reference(data: bytes, site_names) -> dict:
    """참고 엑셀 → 미리보기용 표 묶음. 키: reference_actual · reference_standard · site_grade_eq ·
    site_grade · benchmark_rule · site_history · cri_rule · regular_contract · warnings"""
    wb_v = load_workbook(io.BytesIO(data), data_only=True)
    wb_f = load_workbook(io.BytesIO(data), data_only=False)
    short_to_full = site_sheet_map(site_names)
    sheets = {}
    for name in wb_v.sheetnames:
        site = short_to_full.get(name.strip())
        if site:
            sheets[name.strip()] = _Sheet(site, wb_v[name], wb_f[name])
    out = {k: [] for k in ("reference_actual", "reference_standard", "site_grade_eq", "site_grade",
                           "benchmark_rule", "site_history", "cri_rule", "regular_contract")}
    warnings = []
    unknown = [n for n in wb_v.sheetnames if n.strip() not in sheets
               and re.sub(r"\(.*?\)", "", n).strip().lower() not in GROUP_SHEETS
               and n.strip() not in ("표준화방향", "생산자물가지수", "합계") and not n.startswith("수정이력")]
    if unknown:
        warnings.append("지사로 알아보지 못한 시트: " + ", ".join(unknown))

    for sh in sheets.values():
        out["reference_actual"] += sh.actuals()
        eq = sh.equipment_grades()
        out["site_grade_eq"] += eq
        rep = sh.representative(eq)
        out["site_grade"] += rep
        sh.grade_by_year = {r["연도"]: r["등급"] for r in rep}

    uncalculated = []
    for sh in sheets.values():
        for r, (acct, grades) in sh.std_rows.items():
            for c, grade in grades.items():
                val = sh.v.cell(r, c).value
                formula = sh.f.cell(r, c).value
                is_formula = isinstance(formula, str) and formula.startswith("=")
                if _num(val) is None and not is_formula:
                    continue
                if _num(val) is not None:
                    out["reference_standard"].append({"사업장": sh.site, "예산과목": acct, "등급": grade,
                                                      "표준금액": float(val),
                                                      "엑셀수식": formula if is_formula else ""})
                elif not uncalculated:
                    uncalculated.append(sh.site)
                out["benchmark_rule"].append(_rule_from_formula(sheets, sh, acct, grade, formula, val))

    if uncalculated:
        warnings.append("수식 결과값이 저장되지 않은 파일입니다(엑셀에서 한 번 열어 저장하면 대조 기준값도 들어옵니다).")
    latest = max((sh.latest for sh in sheets.values() if sh.latest), default=None)
    out["site_history"] = _group_history(wb_f, sheets, latest)

    # CRI 짝 — 표준화방향 시트의 «화성->파주» 표기. 단가·시차는 그 짝의 CRI 실적에서.
    text = ""
    for name in wb_v.sheetnames:
        if name.strip() == "표준화방향":
            ws = wb_v[name]
            text = " ".join(str(c.value) for row in ws.iter_rows() for c in row if c.value)
    pairs = re.findall(r"([가-힣]{2,4})\s*->\s*([가-힣]{2,4})", text)
    full = {short: short_to_full[short] for short in short_to_full}
    cri_actual = [r for r in out["reference_actual"] if r["유형"] == "CRI" and r["금액"]]
    mi_years = {}
    for r in out["site_grade"]:
        if "MI" in r["등급"]:
            mi_years.setdefault(r["사업장"], []).append(r["연도"])
    seen = set()
    for a, b in pairs:
        if a not in full or b not in full or full[a] in seen:
            continue
        site, mate = full[a], full[b]
        ref = [x for x in cri_actual if x["사업장"] in (site, mate)]
        unit, unit_year, lag = (ref[0]["금액"], ref[0]["연도"], None) if ref else (0.0, latest or 2025, None)
        if ref:
            prior = [y for y in mi_years.get(ref[0]["사업장"], []) if y < unit_year]
            lag = unit_year - max(prior) if prior else None
        seen.add(site)
        out["cri_rule"].append({"사업장": site, "짝지사": mate, "지급시차": lag or 2, "기준단가": unit,
                                "단가기준연도": unit_year, "활성": bool(ref),
                                "비고": "참고 엑셀: 표준화방향 짝 표기" + (f" · {ref[0]['사업장']} {unit_year} CRI 실적 단가"
                                                                  if ref else " · CRI 실적 없음(단가 입력 필요)")})

    # LTSA 계약 초안 — 최근 실적을 기준연도부터 유지한다고 가정(계약서로 바꿀 것).
    for sh in sheets.values():
        for r, (acct, kind) in sh.split_row.items():
            if kind != "LTSA":
                continue
            item = _label(sh.v.cell(r, 1).value).lstrip("- ").replace("(정기)", "").strip()
            latest_val = None
            for c, y in sorted(sh.year_by_col.items(), key=lambda kv: -kv[1]):
                if _num(sh.v.cell(r, c).value):
                    latest_val = (y, float(sh.v.cell(r, c).value))
                    break
            if latest_val:
                out["regular_contract"].append({"사업장": sh.site, "항목": item or "GT LTSA", "예산과목": acct,
                                                "기준연도실적": latest_val[1], "실적연도": latest_val[0]})
    out["warnings"] = warnings
    return out


def contract_plan(drafts, base_year: int, years: int = 10) -> list:
    """LTSA 초안(최근 실적) → 기준연도부터 years 년 계획 행."""
    rows = []
    for d in drafts:
        for y in range(int(base_year), int(base_year) + years):
            rows.append({"사업장": d["사업장"], "연도": y, "항목": d["항목"], "예산과목": d["예산과목"],
                         "금액": d["기준연도실적"],
                         "비고": f"{d['실적연도']} 실적 유지 가정 — 계약서 금액으로 바꿀 것"})
    return rows


def preview_counts(parsed) -> dict:
    return {k: len(v) for k, v in parsed.items() if isinstance(v, list) and k != "warnings"}


def to_frames(parsed) -> dict:
    return {k: pd.DataFrame(v) for k, v in parsed.items() if isinstance(v, list) and k != "warnings"}
