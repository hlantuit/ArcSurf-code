#!/usr/bin/env python
"""ESSD submission manuscript (.docx) built from the manuscript parts artifacts/essd_parts/01-08 *.html (the same
text as the web draft), on the Copernicus Word template (manuscript/essd_template/Copernicus_Word_template.docx,
from the ESSD submission page, 22 Oct 2026): its body is emptied, its page (21 x 24 cm), margins, continuous line
numbers, page-number footer and styles are kept, and only its styles are used (MS title, Authors, Affiliation,
Correspondence, Normal, Heading 1-3, Caption). Section order as the ESSD composition list (data and code availability
before the conclusions, then the appendix and the end sections); a run-in "Abstract."; tables as Word tables with the
caption above; figures placed after the paragraph that first cites them, caption below; references with a hanging
indent. Open items of the draft (span.todo) are kept, highlighted in yellow, so that nothing unfinished goes
unnoticed; the editorial notes of the web draft are left out. Document properties: author H. Lantuit, AWI.
usage: build_docx.py [OUT.docx]"""
import os
import re
import sys

from lxml import html as LH
from PIL import Image
from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_COLOR_INDEX
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PARTS = f'{ROOT}/artifacts/essd_parts'
ART = f'{ROOT}/artifacts'
ORDER = ['01_front.html', '02_intro.html', '03_data.html', '04_methods.html', '05_dataset_qa.html',
         '06_addendum.html', '07_tail.html', '07b_appendix.html', '07c_backmatter.html', '08_figs.html']
TEMPLATE = f'{ROOT}/manuscript/essd_template/Copernicus_Word_template.docx'
TEXT_W, MAX_H = 17.0, 17.5                     # cm: 17.7 cm text width of the template; tallest figure with its caption
AUTHOR, ORG = 'Hugues Lantuit', 'Alfred Wegener Institute, Helmholtz Centre for Polar and Marine Research'
WS = re.compile(r'\s+')
FIGREF = re.compile(r'Figs?\.\s*((?:\d+[a-z]?(?:\s*(?:,|and|–|-|to)\s*)?)+)')


# ------------------------------------------------------------------ document setup
def from_template(title):
    """the Copernicus template with its example body removed (the final sectPr, which holds the page size, margins,
    line numbering and footer, stays); document properties set to the author instead of the template's"""
    doc = Document(TEMPLATE)
    body = doc.element.body
    for el in list(body):
        if el.tag != qn('w:sectPr'):
            body.remove(el)
    cp = doc.core_properties
    cp.author = cp.last_modified_by = AUTHOR
    cp.title, cp.subject, cp.keywords, cp.comments, cp.category = title, '', '', '', ''
    cp.revision = 1
    import datetime
    cp.created = cp.modified = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0, tzinfo=None)
    return doc


def set_company(path):
    """docProps/app.xml of the saved file: the template's company (Copernicus) replaced by the author's institute"""
    import shutil
    import zipfile
    tmp = path + '.tmp'
    with zipfile.ZipFile(path) as zi, zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as zo:
        for it in zi.infolist():
            data = zi.read(it.filename)
            if it.filename == 'docProps/app.xml':
                data = re.sub(rb'<Company>[^<]*</Company>', f'<Company>{ORG}</Company>'.encode(), data)
                data = re.sub(rb'<Template>[^<]*</Template>', b'<Template>Normal.dotm</Template>', data)
            zo.writestr(it, data)
    shutil.move(tmp, path)


LABEL = re.compile(r'\s*(Table|Figure)\s+([A-Z]?\d+)\.\s*')


def split_label(node):
    """('Figure 3:', a copy of the caption node without its leading 'Figure 3.' / 'Table A1.'): the label sits in the
    text of a table caption and in a leading <b> of a figure caption"""
    import copy
    node = copy.deepcopy(node)
    m = LABEL.match(node.text or '')
    if m:
        node.text = node.text[m.end():]
    elif len(node) and node[0].tag in ('b', 'strong') and LABEL.match(node[0].text or ''):
        m = LABEL.match(node[0].text)
        node.text = (node.text or '') + (node[0].tail or '')
        node.remove(node[0])
    return (f'{m.group(1)} {m.group(2)}:' if m else ''), node


def caption(doc, label, node, fmt=None):
    """caption in the template's Caption style: bold label ('Figure 3:', 'Table 2:'), the text in regular weight"""
    p = doc.add_paragraph(style='Caption')
    p.add_run(label + ' ').bold = True
    add_inline(p, node, dict(fmt or {}, b=False))
    for r in p.runs[1:]:
        if r.bold is None:
            r.bold = False
    return p


# ------------------------------------------------------------------ inline text
def _cls(el):
    return (el.get('class') or '').split()


def add_inline(par, node, fmt=None, first=None):
    """append the text of an lxml node and its children to paragraph par, carrying inline formatting"""
    fmt = dict(fmt or {})
    first = first if first is not None else [True]

    def emit(text, f):
        if not text:
            return
        text = WS.sub(' ', text)
        if first[0]:
            text = text.lstrip()
            if not text:
                return
            first[0] = False
        run = par.add_run(text)
        run.bold = f.get('b') or None
        run.italic = f.get('i') or None
        if f.get('sup'):
            run.font.superscript = True
        if f.get('sub'):
            run.font.subscript = True
        if f.get('code'):
            run.font.name = 'Consolas'
            run.font.size = Pt(11)
        if f.get('todo'):
            run.font.highlight_color = WD_COLOR_INDEX.YELLOW
        if f.get('size'):
            run.font.size = Pt(f['size'])

    emit(node.text, fmt)
    for ch in node:
        tag = ch.tag if isinstance(ch.tag, str) else ''
        f = dict(fmt)
        if tag in ('em', 'i'):
            f['i'] = True
        elif tag in ('strong', 'b'):
            f['b'] = True
        elif tag == 'sup':
            f['sup'] = True
        elif tag == 'sub':
            f['sub'] = True
        elif tag == 'code':
            f['code'] = True
        elif tag == 'br':
            par.add_run().add_break()
        if tag == 'span' and 'todo' in _cls(ch):
            f['todo'] = True
            emit(' [TODO: ', f)
            add_inline(par, ch, f, first)
            emit(']', f)
        elif tag != 'br':
            add_inline(par, ch, f, first)
        emit(ch.tail, fmt)
    return par


def text_of(node):
    return WS.sub(' ', node.text_content()).strip()


# ------------------------------------------------------------------ blocks
def heading(doc, el, level):
    num = el.find('.//span[@class="n"]')
    n = text_of(num) if num is not None else ''
    t = text_of(el)
    if n and t.startswith(n):
        t = t[len(n):].strip()
    return doc.add_heading(f'{n} {t}'.strip(), level=level)


def table(doc, el):
    cap = el.find('.//caption')
    if cap is not None:
        caption(doc, *split_label(cap)).paragraph_format.keep_with_next = True
    rows = el.findall('.//tr')
    ncol = max(sum(int(c.get('colspan', '1')) for c in r if c.tag in ('td', 'th')) for r in rows)
    t = doc.add_table(rows=len(rows), cols=ncol)
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    taken = set()
    for i, r in enumerate(rows):
        j = 0
        head = r.getparent().tag == 'thead'
        for c in [c for c in r if c.tag in ('td', 'th')]:
            while (i, j) in taken:
                j += 1
            cs, rs = int(c.get('colspan', '1')), int(c.get('rowspan', '1'))
            cell = t.cell(i, j)
            if cs > 1 or rs > 1:
                cell = cell.merge(t.cell(i + rs - 1, j + cs - 1))
            for a in range(i, i + rs):
                for b in range(j, j + cs):
                    taken.add((a, b))
            par = cell.paragraphs[0]
            par.paragraph_format.line_spacing = 1.0
            par.paragraph_format.space_after = Pt(1)
            add_inline(par, c, {'b': head or c.tag == 'th', 'size': 9})
            if 'num' in _cls(c):
                par.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            j += cs
    # column widths in proportion to the text they hold (square-root weighted, at least 1.3 cm), on the text width
    lens = [0.0] * ncol
    for r in rows:
        j = 0
        for c in [c for c in r if c.tag in ('td', 'th')]:
            cs = int(c.get('colspan', '1'))
            if cs == 1 and j < ncol:
                lens[j] = max(lens[j], len(text_of(c)))
            j += cs
    wts = [max(l, 4) ** 0.5 for l in lens]
    widths = [max(1.8, TEXT_W * w / sum(wts)) for w in wts]       # 1.8 cm keeps '10.5 %' on one line
    widths = [w * TEXT_W / sum(widths) for w in widths]
    t.autofit = False
    for row in t.rows:
        for j, cell in enumerate(row.cells):
            if j < ncol:
                cell.width = Cm(widths[j])
    # horizontal rules only (Copernicus table style): top and bottom of the table, below the header
    tblPr = t._tbl.tblPr
    borders = OxmlElement('w:tblBorders')
    for side, val in (('top', 'single'), ('bottom', 'single'), ('left', 'nil'), ('right', 'nil'),
                      ('insideH', 'nil'), ('insideV', 'nil')):
        b = OxmlElement(f'w:{side}')
        b.set(qn('w:val'), val)
        if val == 'single':
            b.set(qn('w:sz'), '8')
            b.set(qn('w:color'), '000000')
        borders.append(b)
    tblPr.append(borders)
    nhead = len(el.findall('.//thead/tr'))
    if nhead:
        for cell in t.rows[nhead - 1].cells:
            tcPr = cell._tc.get_or_add_tcPr()
            tb = OxmlElement('w:tcBorders')
            b = OxmlElement('w:bottom')
            b.set(qn('w:val'), 'single')
            b.set(qn('w:sz'), '6')
            b.set(qn('w:color'), '000000')
            tb.append(b)
            tcPr.append(tb)
    doc.add_paragraph()


def _small(img, tmpdir):
    """a copy at most 3000 px wide for embedding (enough for 16 cm at ~475 dpi), so the .docx stays light"""
    im = Image.open(img)
    if im.width <= 3000:
        return img
    os.makedirs(tmpdir, exist_ok=True)
    out = os.path.join(tmpdir, os.path.splitext(os.path.basename(img))[0] + '_3000.jpg')
    im.convert('RGB').resize((3000, round(im.height * 3000 / im.width)), Image.LANCZOS).save(out, quality=88)
    return out


def figure(doc, fig, tmpdir):
    n, img, cap = fig
    if img and os.path.exists(img):
        img = _small(img, tmpdir)
        w, h = Image.open(img).size
        width = min(TEXT_W, MAX_H * w / h)
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.keep_with_next = True
        p.add_run().add_picture(img, width=Cm(width))
    else:
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = p.add_run(f'[Figure {n} in preparation]')
        r.font.highlight_color = WD_COLOR_INDEX.YELLOW
    caption(doc, *split_label(cap))


def parse_figures(tree):
    figs = {}
    for f in tree.iter('figure'):
        cap = f.find('figcaption')
        if cap is None:
            continue
        m = re.match(r'Figure (\d+)\.', text_of(cap))
        if not m:
            continue
        img = f.find('.//img')
        src = os.path.normpath(os.path.join(ART, img.get('src'))) if img is not None else None
        figs[int(m.group(1))] = (int(m.group(1)), src, cap)
    return figs


def cited(text):
    out = []
    for m in FIGREF.finditer(text):
        nums = [int(x) for x in re.findall(r'\d+', m.group(1))]
        if re.search(r'\d\s*(?:–|-|to)\s*\d', m.group(1)) and len(nums) == 2:
            nums = list(range(nums[0], nums[1] + 1))
        out.extend(nums)
    return out


# ------------------------------------------------------------------ main
def main():
    out = sys.argv[1] if len(sys.argv) > 1 else f'{ROOT}/manuscript/ArcSurf_ESSD_manuscript.docx'
    os.makedirs(os.path.dirname(out), exist_ok=True)
    trees = {p: LH.fromstring(open(f'{PARTS}/{p}', encoding='utf-8').read()) for p in ORDER}
    figs = parse_figures(trees['08_figs.html'])
    placed = set()

    # title page, in the template's styles
    fr = trees['01_front.html']
    title = text_of(fr.find('.//h1'))
    doc = from_template(title)
    doc.add_paragraph(title, style='MS title')
    add_inline(doc.add_paragraph(style='Authors'), fr.find('.//div[@class="authors"]'))
    for af in fr.findall('.//div[@class="affil"]'):
        inner = (af.text or '') + ''.join(LH.tostring(c, encoding='unicode', with_tail=True) for c in af)
        for part in re.split(r'\s+·\s+', inner):          # one affiliation per line
            node = LH.fromstring(f'<div>{part}</div>')
            t = text_of(node)
            if t.startswith('Correspondence'):
                p = doc.add_paragraph(style='Correspondence')
                p.add_run('Correspondence to').italic = True
                p.add_run(': ' + t.split(':', 1)[1].strip())
            else:
                add_inline(doc.add_paragraph(style='Affiliation'), node)
    ab = fr.find('.//section[@id="abstract"]/p')
    p = doc.add_paragraph()
    p.add_run('Abstract.').bold = True
    p.add_run(' ')
    add_inline(p, ab)
    tmpdir = os.path.join(os.path.dirname(out), '_img')

    def place_after(text):
        for n in cited(text):
            for k in sorted(figs):
                if k <= n and k not in placed:
                    figure(doc, figs[k], tmpdir)
                    placed.add(k)

    for name in ORDER[1:]:
        tree = trees[name]
        for sec in tree.iter('section'):
            sid = sec.get('id') or ''
            if sid in ('figures', 'editorial') or 'status' in _cls(sec):
                continue
            for el in sec:
                tag = el.tag if isinstance(el.tag, str) else ''
                if tag == 'h2':
                    heading(doc, el, 1)
                elif tag == 'h3':
                    heading(doc, el, 2)
                elif tag == 'h4':
                    heading(doc, el, 3)
                elif tag == 'p':
                    par = add_inline(doc.add_paragraph(), el)
                    place_after(text_of(el))
                elif tag == 'div' and ('tbl' in _cls(el) or el.find('.//table') is not None):
                    table(doc, el.find('.//table'))
                elif tag == 'table':
                    table(doc, el)
                elif tag in ('ol', 'ul'):
                    refs = 'refs' in _cls(el)
                    for li in el.findall('li'):
                        par = doc.add_paragraph()
                        if refs:
                            par.paragraph_format.left_indent = Cm(0.6)
                            par.paragraph_format.first_line_indent = Cm(-0.6)
                            par.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.LEFT   # long URLs, no stretched gaps
                            add_inline(par, li)
                        else:                           # the template has no numbered list style
                            par.style = doc.styles['Bullets']
                            add_inline(par, li)
    for k in sorted(figs):                       # figures never cited in the text
        if k not in placed:
            figure(doc, figs[k], tmpdir)
    doc.save(out)
    set_company(out)
    print(f'wrote {out}: {len(figs)} figures ({len(placed)} placed at their first citation)')


if __name__ == '__main__':
    main()
