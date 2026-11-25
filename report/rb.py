"""Report builder helpers (python-docx): formatting follows the reference report (A4, Times New Roman 12, justified, page border,
header/footer, roman front matter, arabic chapters)."""
import re, json
from docx import Document
from docx.shared import Pt, Cm, RGBColor, Emu
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK, WD_LINE_SPACING
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.section import WD_SECTION
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from PIL import Image

FONT = 'Times New Roman'
TITLE = 'Flood Digital Twin and RescueNet X 2.0'

def _rf(run, size=None, bold=None, italic=None, color=None, font=FONT):
    run.font.name = font; run._element.rPr.rFonts.set(qn('w:eastAsia'), font)
    if size: run.font.size = Pt(size)
    if bold is not None: run.bold = bold
    if italic is not None: run.italic = italic
    if color: run.font.color.rgb = RGBColor.from_string(color)

def _shade(cell, hexcolor):
    tcPr = cell._tc.get_or_add_tcPr(); sh = OxmlElement('w:shd'); sh.set(qn('w:val'), 'clear'); sh.set(qn('w:color'), 'auto'); sh.set(qn('w:fill'), hexcolor); tcPr.append(sh)

def _cell_margins(table, top=40, bottom=40, left=70, right=70):
    tblPr = table._tbl.tblPr; m = OxmlElement('w:tblCellMar')
    for k, v in (('top', top), ('left', left), ('bottom', bottom), ('right', right)):
        e = OxmlElement(f'w:{k}'); e.set(qn('w:w'), str(v)); e.set(qn('w:type'), 'dxa'); m.append(e)
    tblPr.append(m)

def _page_border(section):
    sectPr = section._sectPr
    for e in sectPr.findall(qn('w:pgBorders')): sectPr.remove(e)
    b = OxmlElement('w:pgBorders'); b.set(qn('w:offsetFrom'), 'page')
    for side in ('top', 'left', 'bottom', 'right'):
        e = OxmlElement(f'w:{side}'); e.set(qn('w:val'), 'double'); e.set(qn('w:sz'), '6'); e.set(qn('w:space'), '24'); e.set(qn('w:color'), '000000'); b.append(e)
    # pgBorders must come after pgMar in the schema order
    pgMar = sectPr.find(qn('w:pgMar')); pgMar.addnext(b)

def _field(paragraph, instr):
    r = paragraph.add_run(); f1 = OxmlElement('w:fldChar'); f1.set(qn('w:fldCharType'), 'begin'); r._r.append(f1)
    r2 = paragraph.add_run(); it = OxmlElement('w:instrText'); it.set(qn('xml:space'), 'preserve'); it.text = instr; r2._r.append(it)
    r3 = paragraph.add_run(); f2 = OxmlElement('w:fldChar'); f2.set(qn('w:fldCharType'), 'separate'); r3._r.append(f2)
    r4 = paragraph.add_run('1'); r5 = paragraph.add_run(); f3 = OxmlElement('w:fldChar'); f3.set(qn('w:fldCharType'), 'end'); r5._r.append(f3)
    for r_ in (r, r2, r3, r4, r5): _rf(r_, 11)

def _pg_num(section, fmt=None, start=None):
    sectPr = section._sectPr
    for e in sectPr.findall(qn('w:pgNumType')): sectPr.remove(e)
    e = OxmlElement('w:pgNumType')
    if fmt: e.set(qn('w:fmt'), fmt)
    if start is not None: e.set(qn('w:start'), str(start))
    sectPr.append(e)

def _para_border(p, side='bottom', sz=12, val='thick'):
    pPr = p._p.get_or_add_pPr(); b = OxmlElement('w:pBdr'); e = OxmlElement(f'w:{side}'); e.set(qn('w:val'), val); e.set(qn('w:sz'), str(sz)); e.set(qn('w:space'), '1'); e.set(qn('w:color'), '000000'); b.append(e); pPr.append(b)

def fix_table(t, ws_cm):
    t.autofit = False
    tblPr = t._tbl.tblPr
    for e in tblPr.findall(qn('w:tblW')): tblPr.remove(e)
    w = OxmlElement('w:tblW'); w.set(qn('w:w'), str(int(sum(ws_cm) / 2.54 * 1440))); w.set(qn('w:type'), 'dxa'); tblPr.append(w)
    for e in tblPr.findall(qn('w:tblLayout')): tblPr.remove(e)
    lay = OxmlElement('w:tblLayout'); lay.set(qn('w:type'), 'fixed'); tblPr.append(lay)
    grid = t._tbl.tblGrid
    for i, gc in enumerate(grid.findall(qn('w:gridCol'))):
        if i < len(ws_cm): gc.set(qn('w:w'), str(int(ws_cm[i] / 2.54 * 1440)))
    for row in t.rows:
        for i, c in enumerate(row.cells):
            if i < len(ws_cm): c.width = Cm(ws_cm[i])

class B:
    def __init__(self):
        self.d = Document(); self.registry = []   # (kind, label, text)
        self.chap = 0; self.sec_i = 0; self.fig_n = {}; self.tab_n = {}; self.cur_chap_label = ''
        st = self.d.styles['Normal']; st.font.name = FONT; st.font.size = Pt(12); st.element.rPr.rFonts.set(qn('w:eastAsia'), FONT)
        pf = st.paragraph_format; pf.space_after = Pt(6); pf.line_spacing = 1.35; pf.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        s = self.d.sections[0]; s.page_width, s.page_height = Cm(21.0), Cm(29.7); s.left_margin = Cm(3.2); s.right_margin = Cm(2.4); s.top_margin = Cm(2.6); s.bottom_margin = Cm(2.4)
        s.header_distance = Cm(1.2); s.footer_distance = Cm(1.1); _page_border(s)
        self.registry_page = {}
        self.pb_pending = False

    # ---------- basic text
    def p(self, text='', size=12, bold=False, italic=False, align=None, after=6, before=0, keep=False, indent=None, color=None, ls=None, first=None):
        para = self.d.add_paragraph(); self._runs(para, text, size, bold, italic, color)
        pf = para.paragraph_format; pf.space_after = Pt(after); pf.space_before = Pt(before)
        if align == 'c': para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        elif align == 'l': para.alignment = WD_ALIGN_PARAGRAPH.LEFT
        elif align == 'r': para.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        if keep: pf.keep_with_next = True
        if indent is not None: pf.left_indent = Cm(indent)
        if first is not None: pf.first_line_indent = Cm(first)
        if ls: pf.line_spacing = ls
        if self.pb_pending: pf.page_break_before = True; self.pb_pending = False
        return para

    def _runs(self, para, text, size=12, bold=False, italic=False, color=None):
        # inline **bold** and *italic* markers
        parts = re.split(r'(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`)', text)
        for part in parts:
            if not part: continue
            if part.startswith('**'): r = para.add_run(part[2:-2]); _rf(r, size, True, italic, color)
            elif part.startswith('`'): r = para.add_run(part[1:-1]); _rf(r, size - 1.5, bold, italic, color, font='Courier New')
            elif part.startswith('*'): r = para.add_run(part[1:-1]); _rf(r, size, bold, True, color)
            else: r = para.add_run(part); _rf(r, size, bold, italic, color)

    def pagebreak(self): self.pb_pending = True

    def chapter(self, num, title):
        self.chap = num; self.sec_i = 0; self.fig_n[num] = 0; self.tab_n[num] = 0
        self.pagebreak()
        self.p(f'CHAPTER {num}', 16, True, align='l', after=14, keep=True)
        self.p(title.upper(), 16, True, align='c', after=14, keep=True)
        self.registry.append(('chap', f'{num}', title.upper()))

    def unnumbered(self, title):
        self.pagebreak(); self.p(title.upper(), 16, True, align='c', after=14, keep=True); self.registry.append(('chap', '', title.upper()))

    def h2(self, text, label=True):
        self.p(text, 14, True, align='l', after=6, before=8, keep=True); self.registry.append(('h2', '', text))

    def h3(self, text):
        self.p(text, 12.5, True, align='l', after=4, before=4, keep=True); self.registry.append(('h3', '', text))

    def bul(self, items, size=12, style='•', indent=0.9):
        for it in items:
            para = self.d.add_paragraph(); pf = para.paragraph_format; pf.left_indent = Cm(indent); pf.first_line_indent = Cm(-0.5); pf.space_after = Pt(3)
            self._runs(para, f'{style}  ' + it, size)
    def num(self, items, size=12, indent=0.9):
        for i, it in enumerate(items, 1):
            para = self.d.add_paragraph(); pf = para.paragraph_format; pf.left_indent = Cm(indent); pf.first_line_indent = Cm(-0.6); pf.space_after = Pt(3)
            self._runs(para, f'{i}.  ' + it, size)

    # ---------- figures, tables, code, equations
    def fig(self, path, caption, width=14.6, maxh=19.0):
        self.fig_n[self.chap] = self.fig_n.get(self.chap, 0) + 1; n = f'{self.chap}.{self.fig_n[self.chap]}'
        im = Image.open(path); w, h = im.size; wcm = width; hcm = wcm * h / w
        if hcm > maxh: wcm = maxh * w / h; hcm = maxh
        para = self.d.add_paragraph(); para.alignment = WD_ALIGN_PARAGRAPH.CENTER; para.paragraph_format.keep_with_next = True; para.paragraph_format.space_after = Pt(2); para.paragraph_format.space_before = Pt(4)
        if self.pb_pending: para.paragraph_format.page_break_before = True; self.pb_pending = False
        para.add_run().add_picture(path, width=Cm(wcm))
        txt = f'Figure {n}: {caption}'; self.p(txt, 11, True, align='c', after=8, ls=1.0); self.registry.append(('fig', n, caption)); return n

    def tbl(self, caption, header, rows, widths=None, size=10, align=None, bold_first=False, hdr_fill='D9E2EC'):
        self.tab_n[self.chap] = self.tab_n.get(self.chap, 0) + 1; n = f'{self.chap}.{self.tab_n[self.chap]}'
        self.p(f'Table {n}: {caption}', 11, True, align='c', after=3, before=4, keep=True, ls=1.0)
        t = self.d.add_table(rows=1, cols=len(header)); t.style = 'Table Grid'; t.alignment = WD_TABLE_ALIGNMENT.CENTER; _cell_margins(t)
        total = 15.4
        if widths: ws = [total * w / sum(widths) for w in widths]
        else: ws = [total / len(header)] * len(header)
        def fill(cell, text, b=False, shade=None, al=None):
            cell.text = ''; para = cell.paragraphs[0]; para.paragraph_format.space_after = Pt(0); para.paragraph_format.line_spacing = 1.0; para.alignment = WD_ALIGN_PARAGRAPH.LEFT if al is None else al
            self._runs(para, text, size, b)
            if shade: _shade(cell, shade)
        for i, h in enumerate(header): fill(t.rows[0].cells[i], h, True, hdr_fill, WD_ALIGN_PARAGRAPH.CENTER)
        trPr = t.rows[0]._tr.get_or_add_trPr(); th = OxmlElement('w:tblHeader'); th.set(qn('w:val'), 'true'); trPr.append(th)
        for r in rows:
            cells = t.add_row().cells
            for i, v in enumerate(r): fill(cells[i], str(v), bold_first and i == 0)
        for row in t.rows:
            trPr = row._tr.get_or_add_trPr(); cs = OxmlElement('w:cantSplit'); cs.set(qn('w:val'), 'true'); trPr.append(cs)
        fix_table(t, ws)
        sp = self.d.add_paragraph(); sp.paragraph_format.space_after = Pt(4); sp.paragraph_format.line_spacing = 0.6
        return n

    def code(self, caption, text, size=7.6):
        numbered = not caption.startswith('Algorithm')
        if numbered: self.fig_n[self.chap] = self.fig_n.get(self.chap, 0) + 1; n = f'{self.chap}.{self.fig_n[self.chap]}'
        t = self.d.add_table(rows=1, cols=1); t.style = 'Table Grid'; t.alignment = WD_TABLE_ALIGNMENT.CENTER; _cell_margins(t, 60, 60, 110, 110)
        fix_table(t, [15.4]); c = t.rows[0].cells[0]; _shade(c, 'F4F6F8'); c.text = ''
        lines = text.rstrip('\n').split('\n')
        for i, ln in enumerate(lines):
            para = c.paragraphs[0] if i == 0 else c.add_paragraph(); para.paragraph_format.space_after = Pt(0); para.paragraph_format.line_spacing = 1.0; para.alignment = WD_ALIGN_PARAGRAPH.LEFT
            r = para.add_run(ln if ln else ' '); _rf(r, size, font='Courier New')
        t.rows[0]._tr.get_or_add_trPr()
        if numbered: self.p(f'Figure {n}: {caption}', 11, True, align='c', after=8, before=3, ls=1.0); self.registry.append(('fig', n, caption)); return n
        self.p(caption + ' (pseudocode)', 11, True, align='c', after=8, before=3, ls=1.0)

    def fig2(self, p1, c1, p2, c2, width=7.3):
        t = self.d.add_table(rows=2, cols=2); t.alignment = WD_TABLE_ALIGNMENT.CENTER
        nums = []
        for j, (pth, cap) in enumerate([(p1, c1), (p2, c2)]):
            self.fig_n[self.chap] = self.fig_n.get(self.chap, 0) + 1; n = f'{self.chap}.{self.fig_n[self.chap]}'; nums.append(n)
            c = t.rows[0].cells[j]; c.text = ''; pp = c.paragraphs[0]; pp.alignment = WD_ALIGN_PARAGRAPH.CENTER; pp.paragraph_format.space_after = Pt(1); pp.paragraph_format.keep_with_next = True
            pp.add_run().add_picture(pth, width=Cm(width)); c.width = Cm(7.7)
            c2 = t.rows[1].cells[j]; c2.text = ''; qq = c2.paragraphs[0]; qq.alignment = WD_ALIGN_PARAGRAPH.CENTER; qq.paragraph_format.space_after = Pt(4); qq.paragraph_format.line_spacing = 1.0
            self._runs(qq, f'Figure {n}: {cap}', 9.5, True); c2.width = Cm(7.7); self.registry.append(('fig', n, cap))
        for row in t.rows:
            trPr = row._tr.get_or_add_trPr(); cs = OxmlElement('w:cantSplit'); cs.set(qn('w:val'), 'true'); trPr.append(cs)
        fix_table(t, [7.7, 7.7])
        sp = self.d.add_paragraph(); sp.paragraph_format.space_after = Pt(2); sp.paragraph_format.line_spacing = 0.5
        return nums

    def eq(self, text, label):
        para = self.d.add_paragraph(); para.alignment = WD_ALIGN_PARAGRAPH.CENTER; para.paragraph_format.space_after = Pt(6); para.paragraph_format.space_before = Pt(3)
        r = para.add_run(text); _rf(r, 12, italic=True); r2 = para.add_run(f'        ({label})'); _rf(r2, 12)

    # ---------- sections, header, footer
    def new_section(self, header=False, footer=False, fmt=None, start=None, border=True):
        s = self.d.add_section(WD_SECTION.NEW_PAGE); s.header.is_linked_to_previous = False; s.footer.is_linked_to_previous = False
        s.page_width, s.page_height = Cm(21.0), Cm(29.7); s.left_margin = Cm(3.2); s.right_margin = Cm(2.4); s.top_margin = Cm(2.6); s.bottom_margin = Cm(2.4)
        if border: _page_border(s)
        _pg_num(s, fmt, start)
        for part in (s.header, s.footer):
            for pp in part.paragraphs: pp.text = ''
        if header:
            hp = s.header.paragraphs[0]; hp.alignment = WD_ALIGN_PARAGRAPH.CENTER; r = hp.add_run(f'{TITLE}: Flood Risk Intelligence and Response'); _rf(r, 10, True); _para_border(hp, 'bottom', 18, 'thinThickSmallGap')
        if footer:
            fp = s.footer.paragraphs[0]; _para_border(fp, 'top', 18, 'thickThinSmallGap')
            fp.paragraph_format.tab_stops.add_tab_stop(Cm(6.7), alignment=1); fp.paragraph_format.tab_stops.add_tab_stop(Cm(15.4), alignment=2)
            r = fp.add_run('DEPT OF CSE-DS, ACSCE.\t2025-26\tPage '); _rf(r, 11); _field(fp, 'PAGE')
        return s

    def save(self, path): self.d.save(path)
