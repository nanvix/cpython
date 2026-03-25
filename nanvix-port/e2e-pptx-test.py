"""
e2e-pptx-test.py - Create a polished PPTX with image, theming, and colors.

Pure stdlib: zipfile + struct + string templates.
Generates a professional 1-slide presentation with:
  - Dark navy gradient-style background
  - NanVix "N" logo (generated PNG, no Pillow)
  - Accent-colored title, subtitle, and detail text
  - Clean typography with Segoe UI / Calibri
  - Proper Open XML theme with coordinated colors

Base64-encodes the PPTX to stdout between delimiters for host extraction.
"""

import sys
import io
import base64
import zipfile
import struct

# ── PNG generator (no zlib needed — uncompressed deflate) ──

def _make_png(width, height, pixel_func):
    def chunk(ctype, data):
        c = ctype + data
        crc = 0xFFFFFFFF
        for byte in c:
            crc ^= byte
            for _ in range(8):
                crc = (crc >> 1) ^ (0xEDB88320 if crc & 1 else 0)
        crc ^= 0xFFFFFFFF
        return struct.pack(">I", len(data)) + c + struct.pack(">I", crc & 0xFFFFFFFF)

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    raw = b""
    for y in range(height):
        raw += b"\x00"
        for x in range(width):
            r, g, b = pixel_func(x, y, width, height)
            raw += bytes([r, g, b])
    deflate = b""
    off = 0
    while off < len(raw):
        blk = raw[off:off + 65535]
        final = 1 if off + 65535 >= len(raw) else 0
        deflate += struct.pack("<B", final)
        deflate += struct.pack("<HH", len(blk), len(blk) ^ 0xFFFF)
        deflate += blk
        off += 65535
    s1, s2 = 1, 0
    for byte in raw:
        s1 = (s1 + byte) % 65521
        s2 = (s2 + s1) % 65521
    zlib_data = b"\x78\x01" + deflate + struct.pack(">I", (s2 << 16) | s1)
    return sig + ihdr + chunk(b"IDAT", zlib_data) + chunk(b"IEND", b"")


def _lerp(a, b, t):
    return int(a + (b - a) * t)


def nanvix_logo(x, y, w, h):
    margin = w // 5
    thick = max(2, w // 9)
    inner_h = h - 2 * margin
    inner_w = w - 2 * margin
    t = y / h
    bg = (_lerp(20, 35, t), _lerp(40, 70, t), _lerp(100, 160, t))
    # Circular mask
    cx, cy = w / 2, h / 2
    r = w * 0.45
    if (x - cx) ** 2 + (y - cy) ** 2 > r * r:
        return (11, 17, 32)  # match slide background
    # N letter
    in_left = margin <= x < margin + thick and margin <= y < h - margin
    in_right = w - margin - thick <= x < w - margin and margin <= y < h - margin
    slope = inner_h / max(inner_w, 1)
    exp_x = margin + (y - margin) / slope if slope > 0 else margin
    in_diag = margin <= y < h - margin and abs(x - exp_x) < thick * 1.1
    if in_left or in_right or in_diag:
        return (255, 255, 255)
    return bg


LOGO_PNG = _make_png(80, 80, nanvix_logo)


# ── Units ──
def emu(inches):
    return str(int(inches * 914400))


# ── Color palette ──
# Dark professional theme inspired by modern tech presentations
BG_DARK    = "0B1120"   # Deep navy background
BG_CARD    = "131D36"   # Slightly lighter card background
ACCENT1    = "3B82F6"   # Bright blue (primary accent)
ACCENT2    = "10B981"   # Emerald green (secondary)
ACCENT3    = "F59E0B"   # Amber (tertiary)
TEXT_WHITE  = "F8FAFC"  # Near-white text
TEXT_MUTED  = "94A3B8"  # Muted slate text
TEXT_SUBTLE = "64748B"  # Subtle grey

# ── Open XML Parts ──

CONTENT_TYPES = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Default Extension="png" ContentType="image/png"/>
  <Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>
  <Override PartName="/ppt/slideMasters/slideMaster1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"/>
  <Override PartName="/ppt/slideLayouts/slideLayout1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml"/>
  <Override PartName="/ppt/slides/slide1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>
  <Override PartName="/ppt/theme/theme1.xml" ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.ms-office.activeX+xml"/>
</Types>'''

ROOT_RELS = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="ppt/presentation.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>'''

PRES_RELS = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="slideMasters/slideMaster1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide1.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" Target="theme/theme1.xml"/>
</Relationships>'''

PRESENTATION = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:presentation xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
                xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
                xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rId1"/></p:sldMasterIdLst>
  <p:sldIdLst><p:sldId id="256" r:id="rId2"/></p:sldIdLst>
  <p:sldSz cx="12192000" cy="6858000" type="screen16x9"/>
  <p:notesSz cx="6858000" cy="9144000"/>
</p:presentation>'''

SLIDE_MASTER_RELS = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" Target="../theme/theme1.xml"/>
</Relationships>'''

SLIDE_MASTER = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sldMaster xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
             xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
             xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:cSld>
    <p:bg><p:bgPr><a:solidFill><a:srgbClr val="{bg}"/></a:solidFill><a:effectLst/></p:bgPr></p:bg>
    <p:spTree>
      <p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>
      <p:grpSpPr/>
    </p:spTree>
  </p:cSld>
  <p:clrMap bg1="dk1" tx1="lt1" bg2="dk2" tx2="lt2" accent1="accent1" accent2="accent2" accent3="accent3" accent4="accent4" accent5="accent5" accent6="accent6" hlink="hlink" folHlink="folHlink"/>
  <p:sldLayoutIdLst><p:sldLayoutId id="2147483649" r:id="rId1"/></p:sldLayoutIdLst>
</p:sldMaster>'''.format(bg=BG_DARK)

SLIDE_LAYOUT_RELS = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="../slideMasters/slideMaster1.xml"/>
</Relationships>'''

SLIDE_LAYOUT = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sldLayout xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
             xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
             xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
             type="blank">
  <p:cSld name="Blank"><p:spTree>
    <p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>
    <p:grpSpPr/>
  </p:spTree></p:cSld>
</p:sldLayout>'''

SLIDE_RELS = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="../media/image1.png"/>
</Relationships>'''

THEME = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" name="NanVix Dark">
  <a:themeElements>
    <a:clrScheme name="NanVix Dark">
      <a:dk1><a:srgbClr val="{bg}"/></a:dk1>
      <a:lt1><a:srgbClr val="{white}"/></a:lt1>
      <a:dk2><a:srgbClr val="{card}"/></a:dk2>
      <a:lt2><a:srgbClr val="{muted}"/></a:lt2>
      <a:accent1><a:srgbClr val="{a1}"/></a:accent1>
      <a:accent2><a:srgbClr val="{a2}"/></a:accent2>
      <a:accent3><a:srgbClr val="{a3}"/></a:accent3>
      <a:accent4><a:srgbClr val="8B5CF6"/></a:accent4>
      <a:accent5><a:srgbClr val="EC4899"/></a:accent5>
      <a:accent6><a:srgbClr val="06B6D4"/></a:accent6>
      <a:hlink><a:srgbClr val="{a1}"/></a:hlink>
      <a:folHlink><a:srgbClr val="8B5CF6"/></a:folHlink>
    </a:clrScheme>
    <a:fontScheme name="NanVix">
      <a:majorFont><a:latin typeface="Segoe UI Semibold"/><a:ea typeface=""/><a:cs typeface=""/></a:majorFont>
      <a:minorFont><a:latin typeface="Segoe UI"/><a:ea typeface=""/><a:cs typeface=""/></a:minorFont>
    </a:fontScheme>
    <a:fmtScheme name="NanVix">
      <a:fillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:fillStyleLst>
      <a:lnStyleLst><a:ln w="6350"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln><a:ln w="6350"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln><a:ln w="6350"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln></a:lnStyleLst>
      <a:effectStyleLst><a:effectStyle><a:effectLst/></a:effectStyle><a:effectStyle><a:effectLst/></a:effectStyle><a:effectStyle><a:effectLst/></a:effectStyle></a:effectStyleLst>
      <a:bgFillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:bgFillStyleLst>
    </a:fmtScheme>
  </a:themeElements>
</a:theme>'''.format(bg=BG_DARK, white=TEXT_WHITE, card=BG_CARD, muted=TEXT_MUTED,
                     a1=ACCENT1, a2=ACCENT2, a3=ACCENT3)

CORE_PROPS = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
                   xmlns:dc="http://purl.org/dc/elements/1.1/"
                   xmlns:dcterms="http://purl.org/dc/terms/"
                   xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:title>NanVix Microkernel - CPython Demo</dc:title>
  <dc:creator>CPython 3.12 on NanVix</dc:creator>
  <dcterms:created xsi:type="dcterms:W3CDTF">2026-03-24T00:00:00Z</dcterms:created>
  <dcterms:modified xsi:type="dcterms:W3CDTF">2026-03-24T00:00:00Z</dcterms:modified>
</cp:coreProperties>'''

APP_PROPS = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties">
  <Application>NanVix CPython 3.12</Application>
  <Slides>1</Slides>
</Properties>'''


# ── Shape builders ──

def textbox(sid, x, y, cx, cy, runs, anchor="t"):
    """Textbox with multiple styled runs per paragraph."""
    paras = ""
    for para in runs:
        parts = ""
        algn = para.get("align", "l")
        spc_before = para.get("spcBef", 0)
        for run in para.get("runs", []):
            txt = run["t"]
            sz = run.get("sz", 1200)
            color = run.get("color", TEXT_WHITE)
            bold = ' b="1"' if run.get("bold") else ""
            italic = ' i="1"' if run.get("italic") else ""
            font = run.get("font", "")
            font_attr = ""
            if font:
                font_attr = '<a:latin typeface="{f}"/><a:cs typeface="{f}"/>'.format(f=font)
            parts += (
                "<a:r>"
                '<a:rPr lang="en-US" sz="{sz}" dirty="0"{b}{i}>'
                '<a:solidFill><a:srgbClr val="{c}"/></a:solidFill>'
                "{font}"
                "</a:rPr>"
                "<a:t>{t}</a:t>"
                "</a:r>"
            ).format(sz=sz, c=color, b=bold, i=italic, t=txt, font=font_attr)
        spc = ""
        if spc_before:
            spc = '<a:spcBef><a:spcPts val="{v}"/></a:spcBef>'.format(v=spc_before)
        paras += '<a:p><a:pPr algn="{a}">{spc}</a:pPr>{parts}</a:p>'.format(
            a=algn, spc=spc, parts=parts)

    return (
        "<p:sp>"
        "<p:nvSpPr>"
        '<p:cNvPr id="{id}" name="TextBox {id}"/>'
        '<p:cNvSpPr txBox="1"/><p:nvPr/>'
        "</p:nvSpPr>"
        "<p:spPr>"
        '<a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>'
        '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom>'
        "<a:noFill/>"
        "</p:spPr>"
        '<p:txBody><a:bodyPr wrap="square" rtlCol="0" anchor="{anchor}"/>'
        "{paras}"
        "</p:txBody>"
        "</p:sp>"
    ).format(id=sid, x=x, y=y, cx=cx, cy=cy, anchor=anchor, paras=paras)


def picture(sid, rid, x, y, cx, cy):
    return (
        "<p:pic>"
        "<p:nvPicPr>"
        '<p:cNvPr id="{id}" name="Logo"/>'
        '<p:cNvPicPr><a:picLocks noChangeAspect="1"/></p:cNvPicPr>'
        "<p:nvPr/>"
        "</p:nvPicPr>"
        "<p:blipFill>"
        '<a:blip r:embed="{rid}"/>'
        "<a:stretch><a:fillRect/></a:stretch>"
        "</p:blipFill>"
        "<p:spPr>"
        '<a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>'
        '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom>'
        "</p:spPr>"
        "</p:pic>"
    ).format(id=sid, rid=rid, x=x, y=y, cx=cx, cy=cy)


def rounded_rect(sid, x, y, cx, cy, fill_color, radius="16667"):
    """A rounded rectangle shape with solid fill (no text)."""
    return (
        "<p:sp>"
        "<p:nvSpPr>"
        '<p:cNvPr id="{id}" name="Rect {id}"/>'
        "<p:cNvSpPr/><p:nvPr/>"
        "</p:nvSpPr>"
        "<p:spPr>"
        '<a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>'
        '<a:prstGeom prst="roundRect"><a:avLst>'
        '<a:gd name="adj" fmla="val {r}"/>'
        "</a:avLst></a:prstGeom>"
        '<a:solidFill><a:srgbClr val="{fill}"/></a:solidFill>'
        "<a:ln><a:noFill/></a:ln>"
        "</p:spPr>"
        "<p:txBody><a:bodyPr/><a:p><a:endParaRPr/></a:p></p:txBody>"
        "</p:sp>"
    ).format(id=sid, x=x, y=y, cx=cx, cy=cy, fill=fill_color, r=radius)


def line_shape(sid, x, y, cx, cy, color, width=12700):
    """A simple line/connector shape. cx/cy are the extent (not endpoint)."""
    return (
        '<p:cxnSp>'
        '<p:nvCxnSpPr>'
        '<p:cNvPr id="{id}" name="Line {id}"/>'
        '<p:cNvCxnSpPr/><p:nvPr/>'
        '</p:nvCxnSpPr>'
        '<p:spPr>'
        '<a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>'
        '<a:prstGeom prst="line"><a:avLst/></a:prstGeom>'
        '<a:ln w="{w}"><a:solidFill><a:srgbClr val="{c}"/></a:solidFill></a:ln>'
        '</p:spPr>'
        '</p:cxnSp>'
    ).format(id=sid, x=x, y=y, cx=cx, cy=cy, c=color, w=width)


# ── Build slide ──
# Slide is 16:9 widescreen (13.333" x 7.5")
W = 12192000  # 13.333 inches
H = 6858000   # 7.5 inches

shapes = ""

# Background card panel (rounded rect behind content)
shapes += rounded_rect(10, emu(0.6), emu(0.5), emu(12.1), emu(6.5), BG_CARD)

# Accent stripe at top
shapes += line_shape(11, emu(0.6), emu(0.5), emu(12.1), "0", ACCENT1, 38100)

# Logo in top-left
shapes += picture(2, "rId2", emu(1.0), emu(0.8), emu(0.85), emu(0.85))

# Title: "NanVix Microkernel"
shapes += textbox(3, emu(2.1), emu(0.75), emu(8), emu(0.7), [
    {"align": "l", "runs": [
        {"t": "NanVix", "sz": 3200, "bold": True, "color": ACCENT1, "font": "Segoe UI Semibold"},
        {"t": " Microkernel", "sz": 3200, "bold": True, "color": TEXT_WHITE, "font": "Segoe UI Semibold"},
    ]}
])

# Subtitle
shapes += textbox(4, emu(2.1), emu(1.5), emu(9), emu(0.5), [
    {"align": "l", "runs": [
        {"t": "CPython 3.12 PowerPoint Generation Demo", "sz": 1400, "color": TEXT_MUTED, "font": "Segoe UI"},
    ]}
])

# Divider line
shapes += line_shape(12, emu(1.0), emu(2.3), emu(11.3), "0", "1E3A5F", 12700)

# Left column: "What is this?"
shapes += textbox(5, emu(1.0), emu(2.6), emu(5.5), emu(4), [
    {"align": "l", "runs": [
        {"t": "What is this?", "sz": 1800, "bold": True, "color": ACCENT2, "font": "Segoe UI Semibold"},
    ]},
    {"align": "l", "spcBef": 800, "runs": [
        {"t": "This PowerPoint presentation was ", "sz": 1200, "color": TEXT_MUTED},
        {"t": "generated entirely inside a microkernel VM", "sz": 1200, "color": TEXT_WHITE, "bold": True},
        {"t": ". No desktop OS, no Office suite, no internet.", "sz": 1200, "color": TEXT_MUTED},
    ]},
    {"align": "l", "spcBef": 600, "runs": [
        {"t": "The Python runtime, XML engine, and PNG image", "sz": 1200, "color": TEXT_MUTED},
    ]},
    {"align": "l", "runs": [
        {"t": "generator are all compiled into a single ", "sz": 1200, "color": TEXT_MUTED},
        {"t": "9 MB", "sz": 1200, "color": ACCENT3, "bold": True},
    ]},
    {"align": "l", "runs": [
        {"t": "static binary running on NanVix.", "sz": 1200, "color": TEXT_MUTED},
    ]},
])

# Right column: specs
shapes += textbox(6, emu(7.0), emu(2.6), emu(5.3), emu(4), [
    {"align": "l", "runs": [
        {"t": "Technical Details", "sz": 1800, "bold": True, "color": ACCENT1, "font": "Segoe UI Semibold"},
    ]},
    {"align": "l", "spcBef": 800, "runs": [
        {"t": "\u25cf  ", "sz": 1100, "color": ACCENT1},
        {"t": "Platform", "sz": 1100, "color": TEXT_MUTED},
        {"t": "   NanVix i686 microkernel", "sz": 1100, "color": TEXT_WHITE},
    ]},
    {"align": "l", "spcBef": 400, "runs": [
        {"t": "\u25cf  ", "sz": 1100, "color": ACCENT2},
        {"t": "Runtime", "sz": 1100, "color": TEXT_MUTED},
        {"t": "   CPython 3.12.3 (static)", "sz": 1100, "color": TEXT_WHITE},
    ]},
    {"align": "l", "spcBef": 400, "runs": [
        {"t": "\u25cf  ", "sz": 1100, "color": ACCENT3},
        {"t": "XML", "sz": 1100, "color": TEXT_MUTED},
        {"t": "   stdlib ElementTree", "sz": 1100, "color": TEXT_WHITE},
    ]},
    {"align": "l", "spcBef": 400, "runs": [
        {"t": "\u25cf  ", "sz": 1100, "color": "EC4899"},
        {"t": "Image", "sz": 1100, "color": TEXT_MUTED},
        {"t": "   Generated PNG (no Pillow)", "sz": 1100, "color": TEXT_WHITE},
    ]},
    {"align": "l", "spcBef": 400, "runs": [
        {"t": "\u25cf  ", "sz": 1100, "color": "8B5CF6"},
        {"t": "Output", "sz": 1100, "color": TEXT_MUTED},
        {"t": "   Base64 via stdout", "sz": 1100, "color": TEXT_WHITE},
    ]},
    {"align": "l", "spcBef": 400, "runs": [
        {"t": "\u25cf  ", "sz": 1100, "color": "06B6D4"},
        {"t": "Binary", "sz": 1100, "color": TEXT_MUTED},
        {"t": "   9.1 MB (67 modules)", "sz": 1100, "color": TEXT_WHITE},
    ]},
])

# Footer
shapes += textbox(7, emu(1.0), emu(6.6), emu(11.3), emu(0.4), [
    {"align": "r", "runs": [
        {"t": "Generated by CPython 3.12 on NanVix  \u00b7  github.com/nanvix", "sz": 900, "color": TEXT_SUBTLE, "italic": True},
    ]}
])


SLIDE1 = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"'
    ' xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
    ' xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
    "<p:cSld>"
    '<p:bg><p:bgPr><a:solidFill><a:srgbClr val="{bg}"/></a:solidFill><a:effectLst/></p:bgPr></p:bg>'
    "<p:spTree>"
    '<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
    "<p:grpSpPr/>"
    "{shapes}"
    "</p:spTree></p:cSld></p:sld>"
).format(bg=BG_DARK, shapes=shapes)


# ── Build PPTX ZIP ──
buf = io.BytesIO()
with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as zf:
    zf.writestr("[Content_Types].xml", CONTENT_TYPES)
    zf.writestr("_rels/.rels", ROOT_RELS)
    zf.writestr("ppt/presentation.xml", PRESENTATION)
    zf.writestr("ppt/_rels/presentation.xml.rels", PRES_RELS)
    zf.writestr("ppt/slideMasters/slideMaster1.xml", SLIDE_MASTER)
    zf.writestr("ppt/slideMasters/_rels/slideMaster1.xml.rels", SLIDE_MASTER_RELS)
    zf.writestr("ppt/slideLayouts/slideLayout1.xml", SLIDE_LAYOUT)
    zf.writestr("ppt/slideLayouts/_rels/slideLayout1.xml.rels", SLIDE_LAYOUT_RELS)
    zf.writestr("ppt/slides/slide1.xml", SLIDE1)
    zf.writestr("ppt/slides/_rels/slide1.xml.rels", SLIDE_RELS)
    zf.writestr("ppt/theme/theme1.xml", THEME)
    zf.writestr("ppt/media/image1.png", LOGO_PNG)
    zf.writestr("docProps/core.xml", CORE_PROPS)
    zf.writestr("docProps/app.xml", APP_PROPS)

pptx_bytes = buf.getvalue()

encoded = base64.b64encode(pptx_bytes).decode("ascii")
print("---PPTX_BASE64_START---")
for i in range(0, len(encoded), 76):
    print(encoded[i:i + 76])
print("---PPTX_BASE64_END---")
print("PPTX: %d bytes, image: %d bytes" % (len(pptx_bytes), len(LOGO_PNG)), file=sys.stderr)
