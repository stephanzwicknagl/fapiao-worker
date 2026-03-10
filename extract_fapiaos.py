#!/usr/bin/env python3
"""Extract fapiao data from PDF files using embedded text (offline, no AI)."""

import csv
import re
import sys
from pathlib import Path

import fitz  # pymupdf


# Chinese number characters used in 大写 (written-out) amounts
_DAXIE = (
    r'[壹贰叁肆伍陆柒捌玖拾零百千万亿佰仟]'
    r'[壹贰叁肆伍陆柒捌玖拾零百千万亿佰仟圆元角分整]{2,}'
    r'[整]?'
)

NUM = r'[\d,]+\.?\d*'


def _clean(s: str) -> str:
    return s.replace(',', '').strip()


def _approx_eq(a: float, b: float, tol: float = 0.02) -> bool:
    return abs(a - b) <= tol


def parse_fapiao(text: str) -> dict:
    result = {
        'fapiao_number': None,
        'date': None,
        'amount': None,
        'vat_amount': None,
        'skip': False,
        'skip_reason': '',
    }

    # ── GARBLED DETECTION ─────────────────────────────────────────────────────
    # All valid fapiaos have a date with 年; garbled airline ticket PDFs don't.
    if '年' not in text:
        result['skip'] = True
        result['skip_reason'] = 'garbled text'
        return result

    # ── SKIP CONTINUATION PAGES of multi-page fapiaos ────────────────────────
    m = re.search(r'共\s*(\d+)\s*页\s*第\s*(\d+)\s*页', text)
    if m and int(m.group(2)) < int(m.group(1)):
        result['skip'] = True
        result['skip_reason'] = f"page {m.group(2)} of {m.group(1)}"
        return result

    # ── FAPIAO NUMBER ──────────────────────────────────────────────────────────
    m = re.search(r'发票号码[：:]\s*(\d{15,})', text)
    if m:
        result['fapiao_number'] = m.group(1)
    else:
        m = re.search(r'(?<!\d)(\d{20})(?!\d)', text)
        if m:
            result['fapiao_number'] = m.group(1)

    # ── DATE ───────────────────────────────────────────────────────────────────
    m = re.search(r'(\d{4})年(\d{1,2})月(\d{1,2})日', text)
    if m:
        result['date'] = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"

    # ── AMOUNT (小写) ──────────────────────────────────────────────────────────
    amount = None

    # S1: Labeled  （小写）¥xxx  ── Walmart, hotels
    m = re.search(r'[（(]小写[）)]\s*[¥￥]\s*(' + NUM + r')', text)
    if m:
        amount = _clean(m.group(1))

    # S2: DiDi/transport  （小写）\nxxx\n¥
    if not amount:
        m = re.search(r'[（(]小写[）)]\s*\n\s*(' + NUM + r')\s*\n\s*[¥￥]', text)
        if m:
            amount = _clean(m.group(1))

    # S4: Amount follows 大写  ── e-commerce, travel: 大写\n¥xxx
    if not amount:
        m = re.search(_DAXIE + r'\n[¥￥](' + NUM + r')', text)
        if m:
            amount = _clean(m.group(1))

    # S4b: Amount follows 大写 without ¥  ── restaurant format: 大写\nT\nP\nV
    if not amount:
        m = re.search(
            _DAXIE + r'\n(?![¥￥])(' + NUM + r')\n(?![¥￥])(' + NUM + r')\n(?![¥￥])(' + NUM + r')',
            text,
        )
        if m:
            t, p, v = float(_clean(m.group(1))), float(_clean(m.group(2))), float(_clean(m.group(3)))
            if _approx_eq(t, p + v):
                amount = _clean(m.group(1))

    # S3: Amount precedes 大写  ── Meituan multi-page last page: ¥xxx\n大写
    if not amount:
        m = re.search(r'[¥￥](' + NUM + r')\n' + _DAXIE, text)
        if m:
            amount = _clean(m.group(1))

    # S5: Metro/Makro format  ── three bare numbers before buyer name: P\nV\nT\n美国
    if not amount:
        m = re.search(
            r'(' + NUM + r')\n(' + NUM + r')\n(' + NUM + r')\n(?:美国|美利坚)',
            text,
        )
        if m:
            p, v, t = float(_clean(m.group(1))), float(_clean(m.group(2))), float(_clean(m.group(3)))
            if _approx_eq(t, p + v):
                amount = _clean(m.group(3))

    # S6: Bare-¥ triplet  ── Domino's format: T\n¥  P\n¥  V\n¥ (scattered)
    if not amount:
        bare_vals = [float(_clean(x)) for x in re.findall(r'(' + NUM + r')\n[¥￥]', text)]
        if len(bare_vals) >= 3:
            bare_set = {round(v, 2) for v in bare_vals}
            for c in sorted(bare_vals, reverse=True):
                found = False
                for a in bare_vals:
                    if a == c:
                        continue
                    b = round(c - a, 2)
                    if b > 0 and b in bare_set and not _approx_eq(b, c):
                        amount = f"{c:.2f}"
                        found = True
                        break
                if found:
                    break

    result['amount'] = amount

    # ── VAT AMOUNT ─────────────────────────────────────────────────────────────
    vat = None
    amt_float = None
    try:
        amt_float = float(amount) if amount else None
    except ValueError:
        pass

    # V1: Inline 合计 row  ── Walmart: 合     计  ¥P  ¥V
    m = re.search(r'合\s+计\s+[¥￥]' + NUM + r'\s+[¥￥](' + NUM + r')', text)
    if m:
        vat = _clean(m.group(1))

    # V2: DiDi format  ── 合\n计\nP\n¥\nV\n¥
    if not vat:
        m = re.search(r'合\n计\n' + NUM + r'\n[¥￥]\n(' + NUM + r')\n[¥￥]', text)
        if m:
            vat = _clean(m.group(1))

    # V3: E-commerce  ── ¥P\n¥V\n大写  (skip if captured value == total)
    if not vat:
        m = re.search(r'[¥￥]' + NUM + r'\n[¥￥](' + NUM + r')\n' + _DAXIE, text)
        if m:
            candidate = _clean(m.group(1))
            if amt_float is None or not _approx_eq(float(candidate), amt_float):
                vat = candidate

    # V4: Restaurant format  ── 大写\nT\nP\nV (third number = VAT)
    if not vat:
        m = re.search(
            _DAXIE + r'\n(?![¥￥])(' + NUM + r')\n(?![¥￥])(' + NUM + r')\n(?![¥￥])(' + NUM + r')',
            text,
        )
        if m:
            t, p, v = float(_clean(m.group(1))), float(_clean(m.group(2))), float(_clean(m.group(3)))
            if _approx_eq(t, p + v):
                vat = _clean(m.group(3))

    # V5: Metro/Makro format  ── P\nV\nT\n美国 (second number = VAT)
    if not vat:
        m = re.search(
            r'(' + NUM + r')\n(' + NUM + r')\n(' + NUM + r')\n(?:美国|美利坚)',
            text,
        )
        if m:
            p, v, t = float(_clean(m.group(1))), float(_clean(m.group(2))), float(_clean(m.group(3)))
            if _approx_eq(t, p + v):
                vat = _clean(m.group(2))

    # V6: Fallback  ── find ¥ or bare-¥ value that pairs with another to equal total
    if not vat and amt_float is not None:
        all_vals = (
            [float(_clean(x)) for x in re.findall(r'[¥￥](' + NUM + r')', text)]
            + [float(_clean(x)) for x in re.findall(r'(' + NUM + r')\n[¥￥]', text)]
        )
        val_set = {round(v, 2) for v in all_vals}
        for a in all_vals:
            if _approx_eq(a, amt_float):
                continue
            b = round(amt_float - a, 2)
            if b > 0 and b in val_set and not _approx_eq(b, amt_float):
                vat = f"{min(a, b):.2f}"
                break

    result['vat_amount'] = vat
    return result


def combine_pdfs(data_dir: str = 'data', output: str = 'combined_fapiaos.pdf') -> str | None:
    """Merge all PDFs in data_dir into a single file. Returns the output path, or None if no PDFs found."""
    pdf_files = sorted(Path(data_dir).glob('*.pdf'))
    if not pdf_files:
        return None

    print(f"Combining {len(pdf_files)} PDF(s) from '{data_dir}/':")
    combined = fitz.open()
    for pdf_path in pdf_files:
        print(f"  + {pdf_path.name}")
        with fitz.open(str(pdf_path)) as doc:
            combined.insert_pdf(doc)

    page_count = len(combined)
    combined.save(output)
    combined.close()
    print(f"  → saved as {output}  ({page_count} pages)\n")
    return output


def process_pdf(pdf_path: str) -> list[dict]:
    results = []
    doc = fitz.open(pdf_path)
    name = Path(pdf_path).name
    print(f"\nProcessing: {name}  ({len(doc)} pages)")

    for page_num in range(len(doc)):
        text = doc[page_num].get_text()
        data = parse_fapiao(text)

        if data['skip']:
            print(f"  Page {page_num + 1:2d}: SKIP ({data['skip_reason']})")
            continue

        row = {
            'source_file': name,
            'page': page_num + 1,
            'fapiao_number': data['fapiao_number'],
            'date': data['date'],
            'amount': data['amount'],
            'vat_amount': data['vat_amount'],
        }
        results.append(row)

        ok = all(v is not None for v in [row['fapiao_number'], row['date'], row['amount'], row['vat_amount']])
        status = '✓' if ok else '!'
        print(
            f"  Page {page_num + 1:2d}: {status}  "
            f"{row['fapiao_number'] or 'NO_NUMBER':22}  "
            f"{row['date'] or 'NO_DATE':10}  "
            f"¥{row['amount'] or '?':8}  "
            f"VAT ¥{row['vat_amount'] or '?'}"
        )

    doc.close()
    return results


def main():
    if len(sys.argv) > 1:
        pdf_files = sys.argv[1:]
    else:
        # Combine any PDFs sitting in data/ first, then scan root for PDFs to process
        combined = combine_pdfs()
        pdf_files = sorted(str(p) for p in Path('.').glob('*.pdf'))

    if not pdf_files:
        print('No PDF files found.', file=sys.stderr)
        sys.exit(1)

    all_results = []
    for pdf_path in pdf_files:
        all_results.extend(process_pdf(pdf_path))

    output_path = 'fapiaos.csv'
    fieldnames = ['source_file', 'page', 'fapiao_number', 'date', 'amount', 'vat_amount']
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_results)

    total = len(all_results)
    complete = sum(
        1 for r in all_results
        if all(r[k] is not None for k in ['fapiao_number', 'date', 'amount', 'vat_amount'])
    )
    print(f"\nDone. {total} fapiaos written to {output_path}  ({complete}/{total} fully extracted)")


if __name__ == '__main__':
    main()
