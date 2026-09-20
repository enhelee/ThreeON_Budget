# -*- coding: utf-8 -*-
"""한난체(HananCha) TTF → 제목용 서브셋 woff2.

  py scripts/make_hanan_font.py "<HANAN.TTF 경로>" [출력=web/public/assets/fonts/HananCha-v1.woff2]

왜 서브셋인가: 원본 866KB. 제목에만 쓰므로 완성형 한글 2,350자 + ASCII + 기본 기호면 충분하다.
원본 TTF 는 CI 자산이라 저장소에 넣지 않는다 — 결과 woff2 만 커밋한다(사내 도구 자산).
파일명의 -v1 은 /assets/* 가 immutable 캐시라 교체 시 이름을 바꿔야 하기 때문이다.
"""
import os
import sys

from fontTools import subset

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_OUT = os.path.join(os.path.dirname(HERE), "web", "public", "assets", "fonts", "HananCha-v1.woff2")


def unicodes():
    u = set(range(0x20, 0x7F))                 # ASCII
    u |= set(range(0xAC00, 0xD7A4))            # 한글 음절 전체(폰트에 있는 2,350자만 남는다)
    u |= set(range(0x3131, 0x318F))            # 호환 자모
    u |= set(range(0x2000, 0x2070))            # 문장부호(–—‘’“”•…)
    u |= {0x00B7, 0x00D7, 0x00F7, 0x00B0, 0x00A0, 0x2190, 0x2192, 0x2191, 0x2193, 0x2264, 0x2265, 0x2260, 0x25A0, 0x25CF, 0x25CB, 0x3001, 0x3002, 0x300C, 0x300D, 0x3010, 0x3011, 0x00AB, 0x00BB}
    return sorted(u)


def main():
    if len(sys.argv) < 2:
        print(__doc__); return 2
    src, out = sys.argv[1], (sys.argv[2] if len(sys.argv) > 2 else DEFAULT_OUT)
    opts = subset.Options()
    opts.flavor = "woff2"
    opts.layout_features = ["*"]
    opts.name_IDs = ["*"]
    opts.notdef_outline = True
    font = subset.load_font(src, opts)
    sub = subset.Subsetter(opts)
    sub.populate(unicodes=unicodes())
    sub.subset(font)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    subset.save_font(font, out, opts)
    print(f"{out}  {os.path.getsize(out)/1024:.0f} KB  glyphs={len(font.getGlyphOrder())}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
