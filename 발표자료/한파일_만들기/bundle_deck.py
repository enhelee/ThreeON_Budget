"""Pack the deck folder into ONE html that opens offline by double-click:
assets -> data: URIs, gsap + HyperFrames runtime inlined into the composition (so the player never
injects the CDN runtime), composition handed to the player as srcdoc, player/slideshow js inlined."""
import base64, html, mimetypes, os, re, sys
SRC, OUT, VENDOR = sys.argv[1], sys.argv[2], sys.argv[3]
MIME = {".mp4": "video/mp4", ".png": "image/png", ".woff": "font/woff", ".woff2": "font/woff2"}
def data(rel):
    p = os.path.join(SRC, "composition", rel)
    if p.endswith(".png"):                      # characters show at most 520px but are 1254px and repeat on many slides
        import io; from PIL import Image
        im = Image.open(p); im.thumbnail((640, 640)); b = io.BytesIO(); im.save(b, "PNG", optimize=True)
        return "data:image/png;base64," + base64.b64encode(b.getvalue()).decode()
    return f"data:{MIME[os.path.splitext(p)[1]]};base64," + base64.b64encode(open(p, "rb").read()).decode()
def inline_js(path): return open(path).read().replace("</script", "<\\/script")
comp = open(os.path.join(SRC, "composition", "index.html")).read()
comp = re.sub(r'(src="|url\(")(assets/[^"]+)"', lambda m: m.group(1) + data(m.group(2)) + '"', comp)
comp = comp.replace('<script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>',
                    "<script>" + inline_js(os.path.join(VENDOR, "gsap.min.js")) + "</script>"
                    + "<script>" + inline_js(os.path.join(VENDOR, "runtime.js")) + "</script>")
LINK = '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Montserrat:wght@900&amp;display=swap" />'
assert LINK in comp                             # the one Google font (latin, 900) goes in too, so nothing loads from the net
mont = base64.b64encode(open(os.path.join(VENDOR, "montserrat900.woff2"), "rb").read()).decode()
comp = comp.replace(LINK, "<style>@font-face{font-family:'Montserrat';font-style:normal;font-weight:900;font-display:swap;"
                          f"src:url(data:font/woff2;base64,{mont}) format('woff2')}}</style>")
assert "cdn.jsdelivr" not in comp and "googleapis" not in comp and 'src="assets/' not in comp
page = open(os.path.join(SRC, "index.html")).read()
for js in ("player.js", "slideshow.js"):
    tag = f'<script src="{js}"></script>'; assert tag in page
    page = page.replace(tag, "<script>" + inline_js(os.path.join(SRC, js)) + "</script>")
old = '<hyperframes-player interactive src="composition/index.html">'
assert old in page
page = page.replace(old, '<hyperframes-player interactive srcdoc="' + html.escape(comp, quote=True) + '">')
open(OUT, "w").write(page)
print(OUT, round(os.path.getsize(OUT) / 1e6, 1), "MB")
