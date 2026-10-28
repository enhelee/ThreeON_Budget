# -*- coding: utf-8 -*-
"""원본 보고서 hwpx → 저장소용 양식(숫자·원인 문장·작성자를 비운 것).

    python scripts/make_report_template.py perf <원본.hwpx> templates/report_perf_template.hwpx
    python scripts/make_report_template.py plan <원본.hwpx> templates/report_plan_template.hwpx

원본에는 그 해 실데이터(금액·사업명이 든 원인 문장)가 있다 — 저장소에는 서식만 남긴다.
표의 숫자 칸은 비우고, □·◈ 문장은 빈 본문, ○ 원인 문장은 묶음마다 자리표시 한 줄씩만 둔다
(채우기가 그 한 줄을 본떠 원하는 수만큼 늘린다).
"""
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
from budget import report_hwpx as rh, report_plan as rp  # noqa: E402

def is_number_cell(text):
    """숫자·기호만 있는 칸 — «983», «160 (22%)», «+52 <+25.6%>», «△28», «-»."""
    s = text.strip()
    return bool(s) and not re.sub(r"[\d,.%△+\-<>()\s]", "", s)
PLACEHOLDER = [{"label": "과목", "body": "원인"}]


def _blank_numbers(tables):
    for tb in tables:
        for tc in rh._cells(tb).values():
            if is_number_cell(rh._text(tc)):
                rh.set_cell(tc, "")


def _blank_box(tbl):
    for p in tbl.iter(rh.Q("p")):
        if rh._text(p).strip():
            rh.set_body(p, "")


def sanitize_perf(sec):
    tops = rh._top_tables(sec)
    _blank_numbers(tops)
    _blank_box(tops[2])
    _, heads, groups = rh._paragraph_roles(sec)
    for head, protos in zip(heads, groups):
        rh.set_body(head, "")
        rh._fill_bullets(sec, protos, PLACEHOLDER if protos else [])


def sanitize_plan(sec):
    tops = rh._top_tables(sec)
    _blank_numbers(tops[5:12] + tops[14:18])         # 장 번호(1·2·3) 칸은 남긴다
    for ti in (5, 14):                                # 정비등급 칸
        for (r, c), tc in rh._cells(tops[ti]).items():
            if r >= 1:
                rh.set_cell(tc, "")
    _blank_box(tops[4])
    _blank_box(tops[13])
    heads, autos, groups, conts = rp.plan_roles(sec)
    for p in conts:
        sec.remove(p)
    for i, head in enumerate(heads):
        if f"h{i}" in rp.TEXT_KEYS:
            rh.set_body(head, "")
    for p in autos.values():
        rh.set_body(p, "", "실적분석")
    for protos in groups.values():
        rh._fill_bullets(sec, protos, PLACEHOLDER)


def sanitize(kind, src_bytes):
    zin, sec, root_tag = rh.load_section(src_bytes)
    {"perf": sanitize_perf, "plan": sanitize_plan}[kind](sec)
    hpf = zin.read("Contents/content.hpf").decode("utf-8")
    hpf = re.sub(r'(<opf:meta name="(creator|lastsaveby)" content="text">)[^<]*', r"\1", hpf)   # 작성자 사번·이름
    return rh.repack(zin, sec, root_tag, {"Contents/content.hpf": hpf.encode("utf-8")})


if __name__ == "__main__":
    kind, src, dst = sys.argv[1], sys.argv[2], sys.argv[3]
    with open(src, "rb") as f:
        out = sanitize(kind, f.read())
    with open(dst, "wb") as f:
        f.write(out)
    left = re.findall(r"\d[\d,.]*", rh.section_text(out))
    print(f"양식 저장: {dst} ({len(out):,} bytes) · 남은 숫자 토막 {len(left)}개: {sorted(set(left))}")
