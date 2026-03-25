"""
nanvix-pptx-showcase-v2.py — Create a styled presentation using the REAL
python-pptx library running inside NanVix.

Dark theme, geometric accents, 5 slides. No raw XML hacks.
"""
import sys, io, base64

# Ensure site-packages is on sys.path (wxc-exec uses -S which skips it)
sp = "/sysroot/lib/python3.12/site-packages"
if sp not in sys.path:
    sys.path.append(sp)

from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN

# ── Colors ──────────────────────────────────────────────────────────────────
BG       = RGBColor(0x1a, 0x1a, 0x2e)
ACCENT1  = RGBColor(0xe9, 0x45, 0x60)  # coral
ACCENT2  = RGBColor(0x0f, 0x34, 0x60)  # dark blue
ACCENT3  = RGBColor(0x16, 0x21, 0x3e)  # darker navy
WHITE    = RGBColor(0xea, 0xea, 0xea)
DIM      = RGBColor(0xa0, 0xa0, 0xb0)
GOLD     = RGBColor(0xf0, 0xc0, 0x40)
GREEN    = RGBColor(0x2e, 0xb8, 0x72)

# ── Helpers ─────────────────────────────────────────────────────────────────
def set_slide_bg(slide, color):
    bg = slide.background
    fill = bg.fill
    fill.solid()
    fill.fore_color.rgb = color

def add_text(slide, left, top, width, height, text, size=18, bold=False,
             color=WHITE, align=PP_ALIGN.LEFT, font_name="Segoe UI"):
    txBox = slide.shapes.add_textbox(Inches(left), Inches(top),
                                      Inches(width), Inches(height))
    tf = txBox.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = text
    p.font.size = Pt(size)
    p.font.bold = bold
    p.font.color.rgb = color
    p.font.name = font_name
    p.alignment = align
    return tf

def add_para(tf, text, size=14, color=DIM, bold=False):
    p = tf.add_paragraph()
    p.text = text
    p.font.size = Pt(size)
    p.font.color.rgb = color
    p.font.bold = bold
    p.font.name = "Segoe UI"
    return p

def add_rect(slide, left, top, width, height, color):
    shape = slide.shapes.add_shape(
        1,  # MSO_SHAPE.RECTANGLE
        Inches(left), Inches(top), Inches(width), Inches(height)
    )
    shape.fill.solid()
    shape.fill.fore_color.rgb = color
    shape.line.fill.background()
    return shape

def add_rounded_rect(slide, left, top, width, height, color):
    shape = slide.shapes.add_shape(
        5,  # MSO_SHAPE.ROUNDED_RECTANGLE
        Inches(left), Inches(top), Inches(width), Inches(height)
    )
    shape.fill.solid()
    shape.fill.fore_color.rgb = color
    shape.line.fill.background()
    return shape

# ── Create presentation ─────────────────────────────────────────────────────
prs = Presentation()
prs.slide_width = Inches(13.333)
prs.slide_height = Inches(7.5)
blank_layout = prs.slide_layouts[6]  # blank

# ════════════════════════════════════════════════════════════════════════════
# SLIDE 1: Title
# ════════════════════════════════════════════════════════════════════════════
s1 = prs.slides.add_slide(blank_layout)
set_slide_bg(s1, BG)

# Accent stripe at top
add_rect(s1, 0, 0, 13.333, 0.08, ACCENT1)
# Large gradient-ish block on right
add_rect(s1, 8.5, 1.5, 4.5, 5.0, ACCENT2)
add_rect(s1, 9.0, 2.0, 4.0, 4.0, ACCENT3)

# Title
add_text(s1, 0.8, 1.5, 7.0, 1.2, "python-pptx", size=52, bold=True, color=WHITE)
tf = add_text(s1, 0.8, 2.8, 7.0, 1.0, "on NanVix", size=48, bold=True, color=GOLD)

# Accent bar
add_rect(s1, 0.8, 4.1, 2.5, 0.06, ACCENT1)

# Subtitle
add_text(s1, 0.8, 4.4, 7.0, 0.8,
         "Running a real Python library inside a microkernel VM",
         size=20, color=DIM)

# Stats on the right block
add_text(s1, 9.3, 2.3, 3.5, 0.6, "75", size=48, bold=True, color=GOLD, align=PP_ALIGN.CENTER)
add_text(s1, 9.3, 3.1, 3.5, 0.4, "built-in C modules", size=14, color=DIM, align=PP_ALIGN.CENTER)
add_text(s1, 9.3, 3.7, 3.5, 0.6, "16 MB", size=36, bold=True, color=ACCENT1, align=PP_ALIGN.CENTER)
add_text(s1, 9.3, 4.4, 3.5, 0.4, "static ELF binary", size=14, color=DIM, align=PP_ALIGN.CENTER)

# Footer
add_text(s1, 0.8, 6.5, 10.0, 0.5,
         f"CPython 3.12  \u2022  NanVix Microkernel  \u2022  {sys.platform}  \u2022  March 2026",
         size=11, color=DIM)

# ════════════════════════════════════════════════════════════════════════════
# SLIDE 2: The Challenge
# ════════════════════════════════════════════════════════════════════════════
s2 = prs.slides.add_slide(blank_layout)
set_slide_bg(s2, BG)
add_rect(s2, 0, 0, 13.333, 0.08, ACCENT1)

add_text(s2, 0.8, 0.4, 8.0, 0.7, "The Challenge", size=36, bold=True, color=ACCENT1)
add_rect(s2, 0.8, 1.05, 1.5, 0.04, GOLD)

# Problem statement
tf = add_text(s2, 0.8, 1.4, 6.0, 2.5,
    "python-pptx needs lxml and Pillow \u2014 both C extensions. "
    "NanVix has no dlopen(). Everything must be statically linked "
    "into a single ELF binary at build time.",
    size=17, color=WHITE)
add_para(tf, "", size=8)
add_para(tf, "This means cross-compiling every C dependency as a static archive, "
    "registering each module in CPython\u2019s internal init table, and creating "
    "shim layers to bridge Python\u2019s import system to the flat built-in namespace.",
    size=14, color=DIM)

# Dependency boxes
y = 1.4
add_rounded_rect(s2, 7.5, y, 5.0, 0.7, ACCENT2)
add_text(s2, 7.7, y+0.1, 4.8, 0.5, "python-pptx  (101 .py files)", size=14, color=WHITE, align=PP_ALIGN.CENTER)

y += 0.9
add_rounded_rect(s2, 7.5, y, 2.3, 0.7, ACCENT1)
add_text(s2, 7.5, y+0.1, 2.3, 0.5, "lxml.etree", size=14, color=WHITE, align=PP_ALIGN.CENTER)
add_rounded_rect(s2, 10.2, y, 2.3, 0.7, ACCENT1)
add_text(s2, 10.2, y+0.1, 2.3, 0.5, "PIL.Image", size=14, color=WHITE, align=PP_ALIGN.CENTER)

y += 0.9
add_rounded_rect(s2, 7.5, y, 5.0, 0.7, ACCENT3)
add_text(s2, 7.5, y+0.1, 5.0, 0.5, "libxml2.a + libxslt.a + libImaging.a", size=12, color=DIM, align=PP_ALIGN.CENTER)

y += 0.9
add_rounded_rect(s2, 7.5, y, 5.0, 0.7, RGBColor(0x10, 0x15, 0x30))
add_text(s2, 7.5, y+0.1, 5.0, 0.5, "CPython 3.12 static binary (75 modules)", size=12, color=GOLD, align=PP_ALIGN.CENTER)

# Arrow indicators (simple vertical bars as connectors)
for ay in [2.1, 3.0, 3.9]:
    add_rect(s2, 9.9, ay, 0.04, 0.2, GOLD)

# Bottom stats
add_text(s2, 0.8, 5.2, 3.0, 0.5, "6", size=48, bold=True, color=GOLD)
add_text(s2, 2.0, 5.5, 3.0, 0.4, "static libraries", size=14, color=DIM)
add_text(s2, 4.0, 5.2, 3.0, 0.5, "74", size=48, bold=True, color=ACCENT1)
add_text(s2, 5.4, 5.5, 3.0, 0.4, "object files in\nlibImaging", size=14, color=DIM)
add_text(s2, 7.5, 5.2, 3.0, 0.5, "3", size=48, bold=True, color=GREEN)
add_text(s2, 8.5, 5.5, 3.0, 0.4, "shim layers", size=14, color=DIM)

# ════════════════════════════════════════════════════════════════════════════
# SLIDE 3: Architecture (3 Shim Layers)
# ════════════════════════════════════════════════════════════════════════════
s3 = prs.slides.add_slide(blank_layout)
set_slide_bg(s3, BG)
add_rect(s3, 0, 0, 13.333, 0.08, GOLD)

add_text(s3, 0.8, 0.4, 10.0, 0.7, "Architecture: 3 Shim Layers", size=36, bold=True, color=GOLD)
add_rect(s3, 0.8, 1.05, 1.5, 0.04, ACCENT1)

layers = [
    ("Layer 1: C Shims", ACCENT1,
     "lxml_etree_builtin.c",
     "Maps PyInit__lxml_etree \u2192 PyInit_etree()\n_imaging_builtin.c bridges PIL to built-in _imaging"),
    ("Layer 2: Python Shims", GOLD,
     "lxml/etree.py  +  PIL/_imaging.py",
     "Re-exports private symbols (_Element, ElementBase)\nBridges package imports to flat built-in names"),
    ("Layer 3: CRT Stubs", GREEN,
     "nanvix-port/stubs.c",
     "__register_frame_info \u2192 no-op\nfork/sigaction/popen \u2192 ENOSYS"),
]

for i, (title, color, file, desc) in enumerate(layers):
    y = 1.5 + i * 1.8
    # Accent bar
    add_rect(s3, 0.8, y, 0.08, 1.5, color)
    # Title
    add_text(s3, 1.1, y, 5.0, 0.4, title, size=20, bold=True, color=color)
    # File
    add_text(s3, 1.1, y+0.45, 5.0, 0.3, file, size=12, color=GOLD)
    # Description
    add_text(s3, 1.1, y+0.8, 5.0, 0.7, desc, size=13, color=DIM)

# Right side: code snippet visual
add_rounded_rect(s3, 7.0, 1.3, 5.5, 5.2, ACCENT3)
add_text(s3, 7.3, 1.5, 5.0, 0.4, "Setup.local", size=14, bold=True, color=GOLD)
code_lines = [
    ("_lxml_etree", "lxml_etree_builtin.c -llxml_etree"),
    ("_lxml_elementpath", "lxml_elementpath_builtin.c"),
    ("_imaging", "_imaging_builtin.c -l_imaging -lz"),
]
for j, (mod, args) in enumerate(code_lines):
    y = 2.1 + j * 0.5
    add_text(s3, 7.3, y, 2.0, 0.4, mod, size=12, bold=True, color=ACCENT1)
    add_text(s3, 9.5, y, 3.0, 0.4, args, size=11, color=DIM)

add_rect(s3, 7.3, 3.8, 4.8, 0.04, GOLD)
add_text(s3, 7.3, 4.0, 5.0, 0.4, "Makefile.nanvix LIBS", size=14, bold=True, color=GOLD)
libs = ["-lxml_etree -lxslt -lexslt -lxml2", "-l_imaging -lz", "-lnanvix_stubs"]
for j, lib in enumerate(libs):
    add_text(s3, 7.3, 4.5 + j*0.4, 5.0, 0.3, lib, size=11, color=DIM)

add_text(s3, 7.3, 5.8, 5.0, 0.5, "= 75 built-in modules in one static binary",
         size=14, bold=True, color=GREEN)

# ════════════════════════════════════════════════════════════════════════════
# SLIDE 4: Lessons Learned
# ════════════════════════════════════════════════════════════════════════════
s4 = prs.slides.add_slide(blank_layout)
set_slide_bg(s4, BG)
add_rect(s4, 0, 0, 13.333, 0.08, ACCENT1)

add_text(s4, 0.8, 0.4, 10.0, 0.7, "Lessons Learned", size=36, bold=True, color=ACCENT1)
add_rect(s4, 0.8, 1.05, 1.5, 0.04, GOLD)

lessons = [
    ("\u26a0  timeout 15s killed CPython mid-boot",
     "Looked like 'no output' bug for 2 hours. NanVix needs 60s+ to init CPython."),
    ("\u26a0  LLM Council given incomplete evidence",
     "3 models proposed TLS corruption. Real cause: the timeout wrapper, not the binary."),
    ("\u26a0  import * skips _private names",
     "python-pptx needs lxml._Element. Had to explicitly re-export from C built-in."),
    ("\u26a0  Don't discard CRT sections",
     "Stub the callee (__register_frame_info), not the caller (.init section)."),
    ("\u26a0  mkramfs path matters",
     "Pass staging/ parent so FAT32 has sysroot/lib/... matching PYTHONHOME=/sysroot."),
    ("\u26a0  Don't over-trim stdlib",
     "zipfile \u2192 pathlib \u2192 urllib.parse. Import chains run deep."),
]

for i, (title, desc) in enumerate(lessons):
    y = 1.4 + i * 0.9
    col = i % 2
    x = 0.8 + col * 6.2
    if i >= 4:
        y = 1.4 + (i-2) * 0.9
    elif i >= 2:
        y = 1.4 + i * 0.9

    add_text(s4, 0.8, y, 5.5, 0.4, title, size=15, bold=True, color=GOLD)
    add_text(s4, 1.2, y+0.38, 5.2, 0.4, desc, size=12, color=DIM)

# Stats column
add_rect(s4, 8.5, 1.2, 4.2, 5.5, ACCENT3)
stats = [
    ("12", "issues found", ACCENT1),
    ("7", "mistakes documented", GOLD),
    ("3", "shim layers", WHITE),
    ("1", "working python-pptx", GREEN),
]
for j, (num, label, col) in enumerate(stats):
    y = 1.6 + j * 1.25
    add_text(s4, 8.8, y, 3.5, 0.7, num, size=52, bold=True, color=col, align=PP_ALIGN.CENTER)
    add_text(s4, 8.8, y+0.7, 3.5, 0.3, label, size=13, color=DIM, align=PP_ALIGN.CENTER)

# ════════════════════════════════════════════════════════════════════════════
# SLIDE 5: It Works
# ════════════════════════════════════════════════════════════════════════════
s5 = prs.slides.add_slide(blank_layout)
set_slide_bg(s5, BG)

# Large accent block
add_rect(s5, 0, 0, 13.333, 3.5, ACCENT2)
add_rect(s5, 0, 3.3, 13.333, 0.08, GOLD)

add_text(s5, 0.8, 0.8, 11.0, 1.5, "It Works. \U0001f389", size=56, bold=True, color=GOLD, align=PP_ALIGN.CENTER)

add_text(s5, 2.0, 2.5, 9.0, 0.7,
         "from pptx import Presentation",
         size=28, color=WHITE, align=PP_ALIGN.CENTER, font_name="Consolas")

# Details below
tf = add_text(s5, 1.5, 4.0, 10.0, 2.5,
    "This presentation was generated by python-pptx 1.0.2 running inside "
    "a NanVix microkernel VM. No raw XML templates. No hacks.",
    size=18, color=WHITE, align=PP_ALIGN.CENTER)
add_para(tf, "", size=8)
add_para(tf, "28KB PPTX  \u2022  38 Open XML entries  \u2022  Real slide masters & themes",
         size=14, color=DIM)
p = add_para(tf, "", size=8)
add_para(tf, f"CPython 3.12  \u2022  75 modules  \u2022  {sys.platform}  \u2022  March 2026",
         size=12, color=GOLD)

# ── Save and output ─────────────────────────────────────────────────────────
buf = io.BytesIO()
prs.save(buf)
data = buf.getvalue()

print(f"PPTX: {len(data)} bytes, {len(prs.slides)} slides")
sys.stdout.flush()
print("---PPTX_BASE64_START---")
sys.stdout.flush()
encoded = base64.b64encode(data).decode("ascii")
for i in range(0, len(encoded), 76):
    print(encoded[i:i+76])
    if i % (76 * 50) == 0:
        sys.stdout.flush()
sys.stdout.flush()
print("---PPTX_BASE64_END---")
sys.stdout.flush()
