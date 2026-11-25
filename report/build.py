import sys, re, json, subprocess, os
from rb import *
import content1, content2, content3, content4, content5

def make(toc, lof, out):
    b = B()
    content1.front(b)
    b.new_section(header=False, footer=True, fmt='lowerRoman', start=1)   # abstract, TOC, LoF: roman numerals
    content1.abstract(b)
    # TOC
    b.pagebreak(); b.p('TABLE OF CONTENTS', 15, True, align='c', after=10, before=6, ls=1.0)
    t = b.d.add_table(rows=0, cols=3); 
    def trow(num, title, page, lvl):
        r = t.add_row().cells
        for c, (txt, al) in zip(r, [(num, 0), (title, 0), (page, 1)]):
            c.text = ''; pp = c.paragraphs[0]; pp.paragraph_format.space_after = Pt(1.5 if lvl else 3); pp.paragraph_format.line_spacing = 1.0; pp.alignment = al
            b._runs(pp, txt, 10.5 if lvl else 11.5, bold=(lvl == 0))
    def short(text):
        m = re.match(r'(2\.\d+) Authors: (.*?)\((\d{4})\)', text)
        if m:
            first = m.group(2).split(',')[0].split(' and ')[0].split(' et al')[0].strip().split()[-1]
            return f'{m.group(1)} {first} et al. ({m.group(3)})' if (' and ' in m.group(2) or ',' in m.group(2) or 'et al' in m.group(2)) else f'{m.group(1)} {first} ({m.group(3)})'
        return text
    for kind, label, text, pg in toc: trow(label if kind == 'chap' else '', ('' if kind == 'chap' else '    ') + (text.title() if kind == 'chap' and label else short(text)), pg, 0 if kind == 'chap' else 1)
    fix_table(t, [1.4, 11.6, 2.0])
    # LoF
    b.pagebreak(); b.p('LIST OF FIGURES', 15, True, align='c', after=10, before=6, ls=1.0)
    t2 = b.d.add_table(rows=1, cols=3)
    for c, h in zip(t2.rows[0].cells, ['FIGURE No.', 'FIGURE NAME', 'PAGE No.']):
        c.text = ''; pp = c.paragraphs[0]; pp.alignment = 1; pp.paragraph_format.space_after = Pt(3); b._runs(pp, h, 11, True)
    fix_table(t, [1.8, 11.2, 2.0]) if False else None
    for n, cap, pg in lof:
        r = t2.add_row().cells
        for c, (txt, al) in zip(r, [(n, 0), (cap, 0), (pg, 1)]):
            c.text = ''; pp = c.paragraphs[0]; pp.paragraph_format.space_after = Pt(1.5); pp.paragraph_format.line_spacing = 1.0; pp.alignment = al; b._runs(pp, txt, 10)
        r[0].width = Cm(2.0); r[1].width = Cm(11.4); r[2].width = Cm(2.0)
    fix_table(t2, [2.0, 11.2, 2.0])
    b.new_section(header=True, footer=True, fmt='decimal', start=1)       # body: arabic numerals from Chapter 1
    b.registry = []
    content1.build_ch1(b); content1.build_ls(b); content2.build_ch3(b); content2.build_ch4(b); content3.build_ch5(b); content3.build_ch6(b); content4.build_ch7(b); content4.build_ch8(b); content5.build_ch9(b); content5.build_ch10(b); content5.build_refs(b)
    b.save(out); return b.registry

def pdf(docx):
    subprocess.run(['soffice', '--headless', '--convert-to', 'pdf', '--outdir', os.path.dirname(os.path.abspath(docx)), docx], check=True, capture_output=True, timeout=600)

def pages_of(pdfpath):
    txt = subprocess.run(['pdftotext', '-layout', pdfpath, '-'], capture_output=True, text=True).stdout.split('\f')
    return txt

def norm(s): return re.sub(r'\s+', ' ', s).strip().lower()

def locate(registry, pages, first_body):
    toc, lof = [], []; cursor = first_body
    for kind, label, text in registry:
        key = norm(text) if kind != 'fig' else norm(f'Figure {label}: {text}')
        if kind == 'chap': key = norm(text)
        found = None
        for i in range(cursor, len(pages)):
            pg = norm(pages[i])
            if kind == 'chap':
                if key in pg and (f'chapter {label}' in pg or label == '' ): found = i; break
            elif key[:60] in pg: found = i; break
        if found is None: found = cursor
        cursor = found
        pno = found - first_body + 1
        if kind == 'fig': lof.append((label, text, str(pno)))
        else: toc.append((kind if kind != 'h3' else 'h3', label, text, str(pno)))
    return toc, lof

if __name__ == '__main__':
    out = 'RescueNet_X_Project_Report.docx'
    toc0 = [('chap', '', 'x', '0')] * 3; 
    reg = make([('chap', '1', 'x', '0')] * 90, [('1.1', 'x', '0')] * 90, out)       # pass 0: sizes only
    pdf(out); pages = pages_of('RescueNet_X_Project_Report.pdf')
    first_body = next(i for i, p in enumerate(pages) if 'CHAPTER 1' in p and 'INTRODUCTION' in p and i > 5)
    toc, lof = locate(reg, pages, first_body)
    toc = [t for t in toc if t[0] in ('chap', 'h2')]
    reg2 = make(toc, lof, out); pdf(out); pages = pages_of('RescueNet_X_Project_Report.pdf')
    first_body2 = next(i for i, p in enumerate(pages) if 'CHAPTER 1' in p and 'INTRODUCTION' in p and i > 5)
    toc2, lof2 = locate(reg2, pages, first_body2); toc2 = [t for t in toc2 if t[0] in ('chap', 'h2')]
    if (toc2, lof2) != (toc, lof):
        reg3 = make(toc2, lof2, out); pdf(out); pages = pages_of('RescueNet_X_Project_Report.pdf')
    print('pdf pages:', len(pages) - 1, 'front pages before chapter 1:', first_body2)
