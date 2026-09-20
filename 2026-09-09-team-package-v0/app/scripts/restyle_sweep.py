# -*- coding: utf-8 -*-
"""옛 팔레트 유틸리티 → 한난 토큰 일괄 치환 (Phase 8 Task 4, 1회성 — 기록용으로 남긴다).

  py scripts/restyle_sweep.py            # 실행(덮어씀)
  py scripts/restyle_sweep.py --dry-run  # 파일별 치환 건수만

치환표의 근거: docs/superpowers/specs/2026-09-21-한난-디자인시스템-design.md §7.
순서가 중요하다 — 긴 토큰(`bg-slate-950/30`)을 짧은 것(`bg-slate-950`)보다 먼저 바꾼다.
`hover:`·`sm:` 같은 변형 접두는 토큰 앞에 붙어 있으므로 본체만 바꾸면 그대로 따라온다.
"""
import os
import re
import sys

WEB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web")

RULES = [
    # 오버레이·검정 면
    ("bg-slate-950/30", "bg-overlay"), ("bg-slate-950", "bg-ink"),
    # 파랑(강조) → 검정/중성. 호버 글자만 브랜드 빨강
    ("hover:text-blue-900", "hover:text-brand"), ("hover:text-blue-700", "hover:text-brand"),
    ("hover:bg-blue-50/40", "hover:bg-subtle"), ("hover:bg-blue-100", "hover:bg-subtle"),
    ("hover:border-blue-400", "hover:border-ink"), ("hover:border-blue-300", "hover:border-ink"),
    ("text-blue-950", "text-ink"), ("text-blue-900", "text-ink"), ("text-blue-800", "text-ink"), ("text-blue-700", "text-ink"),
    ("bg-blue-700", "bg-ink"), ("bg-blue-600", "bg-ink"), ("bg-blue-500", "bg-ink"),
    ("bg-blue-100", "bg-subtle"), ("bg-blue-50", "bg-subtle"),
    ("border-blue-300", "border-line-strong"), ("border-blue-200", "border-line-strong"),
    ("accent-blue-600", "accent-brand"), ("ring-blue-500", "ring-brand"),
    # 중성 slate → 4단계
    ("text-slate-950", "text-ink"), ("text-slate-900", "text-ink"), ("text-slate-800", "text-ink"), ("text-slate-700", "text-ink"),
    ("text-slate-600", "text-sub"), ("text-slate-500", "text-sub"),
    ("text-slate-400", "text-tri"), ("text-slate-300", "text-tri"),
    ("hover:bg-slate-50", "hover:bg-subtle"),
    ("bg-slate-300", "bg-line-strong"), ("bg-slate-200", "bg-line"), ("bg-slate-100", "bg-subtle"), ("bg-slate-50", "bg-subtle"),
    ("border-slate-300", "border-line-strong"), ("border-slate-200", "border-line"),
    ("divide-slate-100", "divide-line-subtle"),
    # 상태색 — 의미 유지
    ("text-emerald-700", "text-ok"), ("bg-emerald-500", "bg-ok"), ("bg-emerald-100", "bg-ok-bg"), ("bg-emerald-50", "bg-ok-bg"), ("border-emerald-200", "border-ok"),
    ("text-amber-900", "text-warn"), ("text-amber-800", "text-warn"), ("text-amber-700", "text-warn"),
    ("bg-amber-500", "bg-warn"), ("bg-amber-50", "bg-warn-bg"), ("border-amber-300", "border-warn"), ("border-amber-200", "border-warn"),
    ("text-red-600", "text-err"), ("text-rose-900", "text-err"), ("text-rose-800", "text-err"), ("text-rose-700", "text-err"),
    ("bg-rose-50", "bg-err-bg"), ("border-rose-300", "border-err"),
    # 형태 — 카드 16 · 입력/컨테이너 12 · 그림자 제거(떠 있는 것은 index.html 이 shadow-float 로 직접 지정)
    ("rounded-2xl", "rounded-card"), ("rounded-xl", "rounded-control"),
    ("hover:shadow-md", ""), ("shadow-xl", "shadow-float"), ("shadow-lg", "shadow-float"), ("shadow-sm", ""),
]
_SHADOW_BARE = re.compile(r"(?<![\w-])shadow(?![\w-])")   # 낱말 `shadow` 만


def sweep(text):
    n = 0
    for old, new in RULES:
        c = text.count(old)
        if c:
            text = text.replace(old, new); n += c
    text, c = _SHADOW_BARE.subn("", text); n += c
    text = re.sub(r'class="([^"]*)"', lambda m: 'class="' + " ".join(m.group(1).split()) + '"', text)   # 빈칸 정리
    return text, n


def main():
    dry = "--dry-run" in sys.argv
    total = 0
    targets = [os.path.join(WEB, "index.html")]
    for root, _, files in os.walk(os.path.join(WEB, "src")):
        targets += [os.path.join(root, f) for f in files if f.endswith(".js")]
    for p in targets:
        with open(p, encoding="utf-8") as f:
            s = f.read()
        t, n = sweep(s)
        if n:
            print(f"{os.path.relpath(p, WEB):40s} {n:4d}")
            total += n
            if not dry:
                with open(p, "w", encoding="utf-8", newline="\n") as f:
                    f.write(t)
    print("합계", total, "(dry-run)" if dry else "")


if __name__ == "__main__":
    main()
