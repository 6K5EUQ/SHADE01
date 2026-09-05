#!/usr/bin/env python3
"""SHADE01 비상 절차 md -> 인쇄용 HTML. Chrome headless 로 PDF 를 뽑는다."""
import html
import re
import sys
from pathlib import Path

CSS = """
@page { size: A4; margin: 14mm 13mm 12mm 13mm; }
* { box-sizing: border-box; }
body { font-family: "NanumSquare_ac","Noto Sans CJK KR","Noto Sans KR",sans-serif;
       font-size: 9.6pt; line-height: 1.45; color: #14181d; margin: 0; }
h1 { font-size: 17pt; margin: 0 0 2mm; padding-bottom: 2mm;
     border-bottom: 2.5pt solid #14181d; letter-spacing: -0.3pt; }
h2 { font-size: 11.5pt; margin: 5mm 0 1.8mm; padding: 1.2mm 2mm;
     background: #14181d; color: #fff; border-radius: 1mm;
     break-after: avoid; page-break-after: avoid; }
h3 { font-size: 10pt; margin: 3.5mm 0 1.5mm; color: #14181d;
     border-left: 2.5pt solid #14181d; padding-left: 2mm;
     break-after: avoid; page-break-after: avoid; }
p { margin: 1.2mm 0; }
hr { border: none; border-top: 0.7pt solid #c3cad2; margin: 4mm 0; }
strong { font-weight: 700; }
code { font-family: "DejaVu Sans Mono",monospace; font-size: 8.5pt;
       background: #eef1f4; padding: 0.3mm 1mm; border-radius: 0.8mm;
       white-space: nowrap; }
blockquote { margin: 2mm 0; padding: 2mm 3mm; background: #f4f6f8;
             border-left: 2.5pt solid #8d99a6; font-size: 9pt; }
blockquote p { margin: 0.6mm 0; }
ul { margin: 1.2mm 0; padding-left: 5mm; }
ol { margin: 1.2mm 0; padding-left: 6mm; }
li { margin: 0.7mm 0; }
ol li { margin: 1.1mm 0; }
ul.checks { list-style: none; padding-left: 0; }
ul.checks li { position: relative; padding: 1.1mm 0 1.1mm 6.5mm;
               border-bottom: 0.4pt dotted #ccd3da;
               break-inside: avoid; page-break-inside: avoid; }
ul.checks li::before { content: ""; position: absolute; left: 0.6mm; top: 1.7mm;
                       width: 3.4mm; height: 3.4mm; border: 0.9pt solid #5a6672;
                       border-radius: 0.6mm; }
table { width: 100%; border-collapse: collapse; margin: 2mm 0; font-size: 8.8pt;
        break-inside: avoid; page-break-inside: avoid; }
th { background: #e6eaee; text-align: left; font-weight: 700;
     padding: 1.1mm 1.6mm; border: 0.4pt solid #b6bfc8; }
td { padding: 1.1mm 1.6mm; border: 0.4pt solid #ccd3da; vertical-align: top; }
tr:nth-child(even) td { background: #f7f9fa; }
.crit { color: #b3261e; font-weight: 700; }
h2 .crit, h2 code { color: #fff; background: none; }
"""


def inline(t):
    t = html.escape(t)
    t = re.sub(r'`([^`]+)`', r'<code>\1</code>', t)
    t = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', t)
    t = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', t)
    # 🔴 / ⚠️ / ⛔ 로 시작하는 강조는 붉게
    t = re.sub(r'(🔴|⛔)', r'<span class="crit">\1</span>', t)
    return t


def cells(line):
    return [c.strip() for c in line.strip().strip('|').split('|')]


def convert(md):
    out, i = [], 0
    lines = md.split('\n')
    n = len(lines)
    while i < n:
        ln = lines[i]
        s = ln.strip()

        if not s:
            i += 1
            continue

        if s.startswith('---') and set(s) == {'-'}:
            out.append('<hr>')
            i += 1
            continue

        m = re.match(r'^(#{1,3})\s+(.*)', s)
        if m:
            lvl = len(m.group(1))
            out.append(f'<h{lvl}>{inline(m.group(2))}</h{lvl}>')
            i += 1
            continue

        if s.startswith('>'):
            buf = []
            while i < n and lines[i].strip().startswith('>'):
                buf.append(lines[i].strip().lstrip('>').strip())
                i += 1
            out.append('<blockquote>' +
                       ''.join(f'<p>{inline(b)}</p>' for b in buf if b) +
                       '</blockquote>')
            continue

        # 테이블: 다음 줄이 구분선이어야 한다
        if s.startswith('|') and i + 1 < n and re.match(r'^\|[\s:|-]+\|$', lines[i + 1].strip()):
            head = cells(s)
            i += 2
            rows = []
            while i < n and lines[i].strip().startswith('|'):
                rows.append(cells(lines[i].strip()))
                i += 1
            t = ['<table><thead><tr>']
            t += [f'<th>{inline(c)}</th>' for c in head]
            t.append('</tr></thead><tbody>')
            for r in rows:
                t.append('<tr>' + ''.join(f'<td>{inline(c)}</td>' for c in r) + '</tr>')
            t.append('</tbody></table>')
            out.append(''.join(t))
            continue

        # 체크박스 목록
        if re.match(r'^- \[ \]', s):
            items = []
            while i < n:
                cur = lines[i].strip()
                m2 = re.match(r'^- \[ \]\s+(.*)', cur)
                if m2:
                    items.append(inline(m2.group(1)))
                    i += 1
                elif cur and lines[i].startswith('      ') and items:
                    items[-1] += ' ' + inline(cur)   # 이어지는 들여쓴 줄
                    i += 1
                else:
                    break
            out.append('<ul class="checks">' +
                       ''.join(f'<li>{x}</li>' for x in items) + '</ul>')
            continue

        # 번호 목록
        if re.match(r'^\d+\.\s', s):
            items = []
            while i < n and re.match(r'^\d+\.\s', lines[i].strip()):
                items.append(inline(re.sub(r'^\d+\.\s+', '', lines[i].strip())))
                i += 1
            out.append('<ol>' + ''.join(f'<li>{x}</li>' for x in items) + '</ol>')
            continue

        # 일반 목록
        if s.startswith('- '):
            items = []
            while i < n and lines[i].strip().startswith('- '):
                items.append(inline(lines[i].strip()[2:]))
                i += 1
            out.append('<ul>' + ''.join(f'<li>{x}</li>' for x in items) + '</ul>')
            continue

        out.append(f'<p>{inline(s)}</p>')
        i += 1

    return '\n'.join(out)


def main():
    src = Path(sys.argv[1])
    dst = Path(sys.argv[2])
    md = src.read_text(encoding='utf-8')
    title = md.split('\n', 1)[0].lstrip('# ').strip()
    dst.write_text(
        f'<!doctype html><html lang="ko"><head><meta charset="utf-8">'
        f'<title>{html.escape(title)}</title><style>{CSS}</style></head>'
        f'<body>{convert(md)}</body></html>',
        encoding='utf-8')


main()
