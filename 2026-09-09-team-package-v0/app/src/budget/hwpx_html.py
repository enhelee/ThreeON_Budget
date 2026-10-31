# -*- coding: utf-8 -*-
"""hwpx 본문 → HTML — 웹에서 보고서를 «종이 모양 그대로» 보여 주고 그 자리에서 고치게.

한글 편집기를 흉내 내지 않는다. 보고서 양식에 실제로 쓰이는 것만 그린다:
문단(정렬·여백·들여쓰기·줄간격) · 글자(크기·굵기·기울임·밑줄·색·글꼴) · 표(셀 합치기·크기·테두리·
배경·세로 정렬) · 그림 · 쪽 나눔. 단위 HWPUNIT 은 1/7200 인치 → 96dpi 화면에서 ÷75 = px.

고칠 수 있는 칸은 marks({요소: 칸 정보})로 받는다 — report_hwpx 가 양식을 채우면서 «이 셀·이 run 은
어느 입력값에서 왔는지» 적어 둔 것이다. 그 요소에 data-path·contenteditable 을 붙여 낸다.
화면에서 고친 값은 입력값으로 돌아가고, 서버가 같은 채우기로 hwpx 와 이 HTML 을 다시 만든다
(그래서 보이는 내용과 내려받는 파일이 어긋나지 않는다).
"""
import base64
import re
import xml.etree.ElementTree as ET
from html import escape

HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"
HH = "http://www.hancom.co.kr/hwpml/2011/head"
HC = "http://www.hancom.co.kr/hwpml/2011/core"
P = lambda t: f"{{{HP}}}{t}"
H = lambda t: f"{{{HH}}}{t}"
C = lambda t: f"{{{HC}}}{t}"

PX = 75.0                   # HWPUNIT → px
FALLBACK = {"명조": "serif", "바탕": "serif", "고딕": "sans-serif", "돋움": "sans-serif", "굴림": "sans-serif",
            "헤드라인": "sans-serif", "견고딕": "sans-serif"}
BORDER = {"SOLID": "solid", "DASH": "dashed", "DOT": "dotted", "DASH_DOT": "dashed", "DOUBLE_SLIM": "double",
          "DOUBLE": "double", "THICK_SLIM": "double", "SLIM_THICK": "double"}
ALIGN = {"LEFT": "left", "RIGHT": "right", "CENTER": "center", "JUSTIFY": "justify", "DISTRIBUTE": "justify"}


def px(v):
    """HWPUNIT → px. 한글은 음수를 부호 없는 32비트로 적기도 한다(4294967295 = -1) — 부호를 되돌린다."""
    n = int(float(v or 0))
    if n >= 2 ** 31:
        n -= 2 ** 32
    return round(n / PX, 2)


def _family(face):
    fb = next((v for k, v in FALLBACK.items() if k in face), "sans-serif")
    return f"'{face}', {fb}"


class Styles:
    """header.xml 의 글꼴·글자 모양·문단 모양·테두리 → CSS 문자열(id 별)."""

    def __init__(self, header_xml):
        root = ET.fromstring(header_xml)
        faces = {}
        for ff in root.iter(H("fontface")):
            if ff.get("lang") == "HANGUL":
                faces = {f.get("id"): f.get("face") for f in ff.iter(H("font"))}
        self.char, self.char_pt, self.para, self.para_pad, self.border = {}, {}, {}, {}, {}
        self.para_dist = set()        # 배분 정렬 문단 — 글자를 칸 폭에 고르게(화면에서 report.js 가 자간으로)
        for cp in root.iter(H("charPr")):
            pt = int(cp.get("height", "1000")) / 100
            css = [f"font-size:calc({pt}pt * var(--fit, 1))"]   # --fit: 화면이 칸 맞춤으로 줄일 때
            fr = cp.find(H("fontRef"))
            if fr is not None and faces.get(fr.get("hangul")):
                css.append(f"font-family:{_family(faces[fr.get('hangul')])}")
            col = cp.get("textColor")
            if col and col.lower() not in ("#000000", "none"):
                css.append(f"color:{col}")
            if cp.find(H("bold")) is not None:
                css.append("font-weight:700")
            if cp.find(H("italic")) is not None:
                css.append("font-style:italic")
            ul = cp.find(H("underline"))
            if ul is not None and ul.get("type") not in (None, "NONE"):
                css.append("text-decoration:underline")
            ratio = cp.find(H("ratio"))
            if ratio is not None and ratio.get("hangul") not in (None, "100"):
                css.append(f"display:inline-block;transform:scaleX({int(ratio.get('hangul')) / 100});transform-origin:left")
            sp = cp.find(H("spacing"))
            if sp is not None and sp.get("hangul") not in (None, "0"):
                css.append(f"letter-spacing:{int(sp.get('hangul')) / 100}em")
            self.char[cp.get("id")] = ";".join(css)
            self.char_pt[cp.get("id")] = pt
        for pp in root.iter(H("paraPr")):
            al = pp.find(H("align"))
            align = ALIGN.get(al.get("horizontal") if al is not None else "", "justify")
            css = [f"text-align:{align}"]
            if al is not None and al.get("horizontal") == "DISTRIBUTE":
                self.para_dist.add(pp.get("id"))
            sw = pp.find(f"{P('switch')}/{P('default')}")
            box = sw if sw is not None else pp
            mg = box.find(H("margin"))
            if mg is not None:
                get = lambda k: float((mg.find(C(k)).get("value") if mg.find(C(k)) is not None else 0) or 0)
                left, indent = get("left"), get("intent")
                if left or indent < 0:
                    css.append(f"padding-left:{px(left + max(0, -indent))}px")
                    self.para_pad[pp.get("id")] = (px(left), px(left + max(0, -indent)))   # (왼쪽 여백, 그린 안쪽 여백)
                if indent:
                    css.append(f"text-indent:{px(indent)}px")
                if get("right"):
                    css.append(f"padding-right:{px(get('right'))}px")
                if get("prev"):
                    css.append(f"margin-top:{px(get('prev'))}px")
                if get("next"):
                    css.append(f"margin-bottom:{px(get('next'))}px")
            ls = box.find(H("lineSpacing"))
            if ls is not None and ls.get("type") == "PERCENT":
                css.append(f"line-height:{int(ls.get('value', '160')) / 100}")
            self.para[pp.get("id")] = ";".join(css)
        for bf in root.iter(H("borderFill")):
            css = []
            for side in ("left", "right", "top", "bottom"):
                b = bf.find(H(f"{side}Border"))
                kind = BORDER.get(b.get("type")) if b is not None else None
                if kind:
                    w = max(1, round(float(re.sub(r"[^\d.]", "", b.get("width", "0.1")) or 0.1) * 3.78))
                    if kind == "double":
                        w = max(3, w)
                    css.append(f"border-{side}:{w}px {kind} {b.get('color', '#000')}")
                else:
                    css.append(f"border-{side}:none")
            wb = bf.find(f".//{C('winBrush')}")
            if wb is not None and wb.get("faceColor") not in (None, "none"):
                css.append(f"background:{wb.get('faceColor')}")
            self.border[bf.get("id")] = ";".join(css)


def _run_text(t):
    out = [escape(t.text or "")]
    for ch in t:
        tag = ch.tag.split("}")[1]
        # fwSpace = 한글의 «고정폭 빈칸»(숫자 한 자 폭) — 양쪽 정렬에서도 늘어나지 않는다. 그냥 «　» 로 두면 브라우저가 늘려
        #   «◈ (전체금액)» 사이가 크게 벌어졌다(2026-10-29) → 폭 고정 상자(글자는 그대로 둬 고친 글에도 남는다).
        out.append({"fwSpace": '<span class="rp-fw">　</span>', "nbSpace": " ", "tab": "  ", "lineBreak": "<br>"}.get(tag, ""))
        out.append(escape(ch.tail or ""))
    return "".join(out)


def _colgroup(tbl):
    """열 폭 — 칸마다 (시작 열, 칸 수, 폭)으로 열 하나하나의 폭을 푼다.
    table-layout:fixed 는 첫 줄로 열 폭을 정하는데, 첫 줄에 합친 칸이 있으면 고르게 나눠 버려 과목 칸이
    195px 이 115px 로 그려졌다(2026-10-29) → <col> 로 정확한 폭을 준다."""
    n = int(tbl.get("colCnt") or 0)
    cells = []
    for tc in (tc for tr in tbl.findall(P("tr")) for tc in tr.findall(P("tc"))):   # 칸 안 표는 빼고
        addr, span, sz = tc.find(P("cellAddr")), tc.find(P("cellSpan")), tc.find(P("cellSz"))
        if addr is None or sz is None:
            continue
        cells.append((int(addr.get("colAddr")), int(span.get("colSpan") if span is not None else 1), int(sz.get("width"))))
    if not n or not cells:
        return ""
    col = [None] * n
    for _ in range(n + 1):                              # 한 칸에 모르는 열이 하나뿐이면 빼서 구한다 — 될 때까지
        for c0, k, wd in cells:
            unknown = [i for i in range(c0, min(c0 + k, n)) if col[i] is None]
            if len(unknown) == 1:
                col[unknown[0]] = wd - sum(col[i] for i in range(c0, min(c0 + k, n)) if col[i] is not None)
        if None not in col:
            break
    if None in col or min(col) <= 0:
        return ""                                       # 못 풀면 브라우저에 맡긴다(예전처럼)
    return "<colgroup>" + "".join(f'<col style="width:{px(v)}px">' for v in col) + "</colgroup>"


def _attrs(slot):
    """칸 정보 → HTML 속성. kind: num·text·count·date·label·body(고침) / calc(계산 — 못 고침)."""
    if not slot:
        return ""
    if slot.get("kind") == "calc":
        return ' class="rp-calc" title="자동 계산 — 다른 칸을 고치면 따라 바뀝니다"'
    a = f' class="rp-edit rp-{slot["kind"]}" contenteditable="plaintext-only" spellcheck="false" data-path="{escape(slot["path"])}" data-kind="{slot["kind"]}"'
    return a


class Renderer:
    def __init__(self, styles, images, marks=None):
        self.s, self.images, self.marks = styles, images, marks or {}

    def section(self, sec):
        out = []
        for p in sec.findall(P("p")):
            if p.get("pageBreak") == "1" and out:
                out.append('<div class="rp-pagebreak" aria-hidden="true"></div>')
            out.append(self.para(p))
        return "".join(out)

    def para(self, p):
        css = self.s.para.get(p.get("paraPrIDRef"), "")
        inner, first_pt = [], None
        for run in p.findall(P("run")):
            cid = run.get("charPrIDRef")
            first_pt = first_pt or self.s.char_pt.get(cid)
            for ch in run:
                tag = ch.tag.split("}")[1]
                if tag == "t":
                    inner.append(f'<span style="{self.s.char.get(cid, "")}">{_run_text(ch)}</span>')
                elif tag == "tbl":
                    inner.append(self.table(ch, self.s.para_pad.get(p.get("paraPrIDRef"), (0, 0))))
                elif tag == "pic":
                    inner.append(self.pic(ch))
            slot = self.marks.get(run)
            if slot and inner:
                # 이 run 의 글자 span 을 고칠 수 있는 칸으로 감싼다(라벨·본문)
                last = inner.pop()
                inner.append(f'<span{_attrs(slot)}>{last}</span>')
        slot = self.marks.get(p)
        extra = _attrs(slot) if slot else ""
        body = "".join(inner)
        if not re.sub(r"<[^>]+>|\s|　", "", body) and "<table" not in body and "<img" not in body:
            body = " "
        fs = f"font-size:calc({first_pt}pt * var(--fit, 1));" if first_pt else ""
        tools = self.tools(p)
        cls = "rp-p rp-dist" if p.get("paraPrIDRef") in self.s.para_dist else "rp-p"
        return f'<div class="{cls}" style="{fs}{css}"{extra}>{body}{tools}</div>'

    def tools(self, p):
        """○ 줄 늘이기·빼기 단추(편집 화면에서만 보인다 — hwpx 에는 없다)."""
        t = self.marks.get(("tools", p))
        if not t:
            return ""
        btn = []
        if t.get("add"):
            btn.append(f'<button class="rp-tool" contenteditable="false" data-rp-act="add-bullet" data-k="{t["add"]}" title="이 아래에 ○ 원인 줄 추가">+ ○</button>')
        if t.get("del") is not None:
            btn.append(f'<button class="rp-tool" contenteditable="false" data-rp-act="del-bullet" data-k="{t["del"][0]}" data-i="{t["del"][1]}" title="이 ○ 줄 빼기">−</button>')
        return f'<span class="rp-tools">{"".join(btn)}</span>'

    def table(self, tbl, pad=(0, 0)):
        sz = tbl.find(P("sz"))
        w = px(sz.get("width")) if sz is not None else None
        pos = tbl.find(P("pos"))
        if pos is None or pos.get("treatAsChar") == "1":
            # «글자처럼 취급» 표 — 한글에서는 문단 첫 줄의 글자 자리에 놓인다. 블록으로 그리면 내어쓰기 문단에서
            #   표가 내어쓴 만큼 오른쪽으로 밀렸다(2026-10-29) → 줄 안 표로 그려 문단 정렬·첫 줄 들여쓰기를 그대로 따른다.
            margin = "display:inline-table;vertical-align:top"
        else:
            # 떠 있는 표 — 단(COLUMN)·문단(PARA) 왼쪽에서 horzOffset 만큼. 문단 안쪽 여백(내어쓰기)은 빼 준다
            base = pad[0] if pos.get("horzRelTo") == "PARA" else 0
            margin = f"margin-left:{round(px(pos.get('horzOffset')) + base - pad[1], 2)}px"
        rows = []
        for tr in tbl.findall(P("tr")):
            cells = []
            for tc in tr.findall(P("tc")):
                span, csz = tc.find(P("cellSpan")), tc.find(P("cellSz"))
                cm, sub = tc.find(P("cellMargin")), tc.find(P("subList"))
                st = [self.s.border.get(tc.get("borderFillIDRef"), "")]
                if csz is not None:
                    st.append(f"width:{px(csz.get('width'))}px;height:{px(csz.get('height'))}px")
                # hasMargin="0" = 표 기본 여백(inMargin)을 따름 — 이때 cellMargin 은 4294967295 같은 «미지정» 값이다
                m = cm if tc.get("hasMargin") == "1" and cm is not None else tbl.find(P("inMargin"))
                if m is not None:
                    st.append("padding:{}px {}px {}px {}px".format(*(max(0, px(m.get(k))) for k in ("top", "right", "bottom", "left"))))
                va = (sub.get("vertAlign") if sub is not None else "CENTER") or "CENTER"
                st.append(f"vertical-align:{ {'TOP': 'top', 'BOTTOM': 'bottom'}.get(va, 'middle') }")
                body = "".join(self.para(p) for p in (sub.findall(P("p")) if sub is not None else []))
                attr = ""
                if span is not None and span.get("colSpan") != "1":
                    attr += f' colspan="{span.get("colSpan")}"'
                if span is not None and span.get("rowSpan") != "1":
                    attr += f' rowspan="{span.get("rowSpan")}"'
                slot = self.marks.get(tc)
                if slot:                                # 셀 전체가 한 칸 — 서식은 그대로 두고 감싼다
                    body = f'<div{_attrs(slot)}>{body}</div>'
                cells.append(f'<td{attr} style="{";".join(st)}">{body}</td>')
            rows.append(f"<tr>{''.join(cells)}</tr>")
        width = f"width:{w}px;" if w else ""
        return f'<table class="rp-tbl" style="{width}{margin}">{_colgroup(tbl)}{"".join(rows)}</table>'

    def pic(self, pic):
        img = pic.find(f".//{C('img')}")
        cur = pic.find(P("curSz"))
        src = self.images.get(img.get("binaryItemIDRef")) if img is not None else None
        if not src:
            return ""
        w = px(cur.get("width")) if cur is not None else ""
        h = px(cur.get("height")) if cur is not None else ""
        return f'<img class="rp-pic" src="{src}" style="width:{w}px;height:{h}px" alt="">'


def images_of(zin):
    """BinData 그림 → data URI(id 별). content.hpf 의 id 와 파일 이름을 잇는다."""
    out = {}
    try:
        hpf = zin.read("Contents/content.hpf").decode("utf-8")
    except KeyError:
        return out
    for iid, href, mt in re.findall(r'<opf:item id="([^"]+)" href="(BinData/[^"]+)" media-type="([^"]+)"', hpf):
        try:
            data = zin.read(href)
        except KeyError:
            continue
        mt = {"image/jpg": "image/jpeg"}.get(mt, mt)
        out[iid] = f"data:{mt};base64,{base64.b64encode(data).decode()}"
    return out


def page_css(sec):
    """용지 폭·여백(px) — 화면 쪽 크기."""
    pp = sec.find(f".//{P('pagePr')}")
    if pp is None:
        return 794, 76, 76
    m = pp.find(P("margin"))
    return px(pp.get("width")), px(m.get("left")), px(m.get("right"))


def render(zin, sec, marks=None):
    styles = Styles(zin.read("Contents/header.xml"))
    width, ml, mr = page_css(sec)
    body = Renderer(styles, images_of(zin), marks).section(sec)
    # 용지 폭에는 좌우 여백이 들어 있다 — 글자 영역 = 폭 − 여백(.rp-page 는 content-box). 여백을 두 번 더해
    #   글자 영역이 151px 넓었고, 그래서 표가 한쪽으로 쏠리고 양쪽 정렬 줄이 벌어져 보였다(2026-10-29).
    return (f'<div class="rp-page" style="width:{round(width - ml - mr, 2)}px;padding:56px {mr}px 72px {ml}px">'
            f"{body}</div>")
