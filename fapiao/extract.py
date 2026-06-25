#!/usr/bin/env python3
"""Extract fapiao data from PDF files using embedded text (offline, no AI)."""

import contextlib
import csv
import json
import re
import sys
from pathlib import Path

import fitz  # pymupdf

# Chinese number characters used in 大写 (written-out) amounts
_DAXIE = (
    r"[壹贰叁肆伍陆柒捌玖拾零百千万亿佰仟]"
    r"[壹贰叁肆伍陆柒捌玖拾零百千万亿佰仟圆元角分整]{2,}"
    r"[整]?"
)

NUM = r"[\d,]+\.?\d*"

# Full-width character mappings for normalization
_FULLWIDTH_DIGITS = "０１２３４５６７８９"
_FULLWIDTH_UPPER = "ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺ"
_FULLWIDTH_LOWER = "ａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ"
_FULLWIDTH_PUNCT = "．，：；（）￥"
_FULLWIDTH_CHARS = _FULLWIDTH_DIGITS + _FULLWIDTH_UPPER + _FULLWIDTH_LOWER + _FULLWIDTH_PUNCT
_ASCII_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz.,:;()¥"
_FULLWIDTH_TRANS = str.maketrans(_FULLWIDTH_CHARS, _ASCII_CHARS)


def _normalize_fullwidth(text: str) -> str:
    """Convert full-width characters to ASCII equivalents."""
    return text.translate(_FULLWIDTH_TRANS)


def _clean(s: str) -> str:
    return s.replace(",", "").strip()


def _approx_eq(a: float, b: float, tol: float = 0.02) -> bool:
    return abs(a - b) <= tol


_BUYER_NAMES = {"美国驻武汉总领事馆", "MonicaOrillo", "MONICA ORILLO"}


def _extract_seller(text: str) -> str | None:
    # Pattern 1: explicit 名称：<seller> on the same line (DiDi-style fapiaos).
    # Use [ \t]* (not \s*) so we don't cross newlines and grab the next field label.
    for name in re.findall(r"名称[：:][ \t]*([^\n]+)", text):
        name = name.strip()
        if len(name) > 255:
            continue
        if name and name not in _BUYER_NAMES and "名称" not in name:
            return name

    # Pattern 2: Railway e-tickets ── look for 中国铁路 with company suffix
    if "铁路电子客票" in text or ("中国铁路" in text and "买票请到" in text):
        # Look for full company name: 中国铁路 + entity type
        m = re.search(r"中国铁路(?:[\w（）]+)?(?:股份|集团)?有限公司", text)
        if m:
            return m.group(0)
        # Fallback to just 中国铁路
        return "中国铁路"

    # Pattern 3: bare line containing a company keyword (Walmart, Metro, restaurant, e-commerce)
    for line in text.split("\n"):
        line = line.strip()
        if len(line) > 255:
            continue
        if any(kw in line for kw in ("有限公司", "股份公司", "集团公司")) and line not in _BUYER_NAMES:
            return line
    return None


def _extract_products(text: str) -> list[tuple[str, str]]:
    """Extract product category and name from fapiao text.

    Returns list of (tax_category, product_name) tuples.
    Example: [('餐饮服务', '餐饮服务'), ('医疗仪器器械', '血压计YE660E')]
    """
    products = []
    # Pattern: *category*description
    # Category is typically short (2-20 chars), description can be long
    # Match lines that start with * and have format *category*description
    for match in re.finditer(r"\*([^*\n]{2,20})\*([^*\n]{1,200})", text):
        category = match.group(1).strip()
        description = match.group(2).strip()
        if category and description:
            products.append((category, description))
    return products


def parse_fapiao(raw_text: str) -> dict:
    # Normalize full-width characters to ASCII
    text = _normalize_fullwidth(raw_text)

    result = {
        "fapiao_number": None,
        "date": None,
        "amount": None,
        "vat_amount": None,
        "seller": None,
        "products": [],
        "skip": False,
        "skip_reason": "",
    }

    # ── GARBLED DETECTION ─────────────────────────────────────────────────────
    # All valid fapiaos have a date with 年; garbled airline ticket PDFs don't.
    if "年" not in text:
        result["skip"] = True
        result["skip_reason"] = "garbled text"
        return result

    # Detect railway e-tickets for special VAT handling
    is_railway_ticket = "铁路电子客票" in text or ("中国铁路" in text and "买票请到" in text)

    # ── SKIP CONTINUATION PAGES of multi-page fapiaos ────────────────────────
    m = re.search(r"共\s*(\d+)\s*页\s*第\s*(\d+)\s*页", text)
    if m and int(m.group(2)) < int(m.group(1)):
        result["skip"] = True
        result["skip_reason"] = f"page {m.group(2)} of {m.group(1)}"
        return result

    # ── FAPIAO NUMBER ──────────────────────────────────────────────────────────
    m = re.search(r"发票号码[：:]\s*(\d{15,})", text)
    if m:
        result["fapiao_number"] = m.group(1)
    else:
        m = re.search(r"(?<!\d)(\d{20})(?!\d)", text)
        if m:
            result["fapiao_number"] = m.group(1)

    # ── DATE ───────────────────────────────────────────────────────────────────
    m = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日", text)
    if m:
        result["date"] = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"

    # ── AMOUNT (小写) ──────────────────────────────────────────────────────────
    amount = None

    # S1: Labeled  （小写）¥xxx  ── Walmart, hotels
    m = re.search(r"[（(]小写[）)]\s*[¥￥]\s*(" + NUM + r")", text)
    if m:
        amount = _clean(m.group(1))

    # S2: DiDi/transport  （小写）\nxxx\n¥
    if not amount:
        m = re.search(r"[（(]小写[）)]\s*\n\s*(" + NUM + r")\s*\n\s*[¥￥]", text)
        if m:
            amount = _clean(m.group(1))

    # S4: Amount follows 大写  ── e-commerce, travel: 大写\n¥xxx
    if not amount:
        m = re.search(_DAXIE + r"\n[¥￥](" + NUM + r")", text)
        if m:
            amount = _clean(m.group(1))

    # S4b: Amount follows 大写 without ¥  ── restaurant format: 大写\nT\nP\nV
    if not amount:
        m = re.search(
            _DAXIE + r"\n(?![¥￥])(" + NUM + r")\n(?![¥￥])(" + NUM + r")\n(?![¥￥])(" + NUM + r")",
            text,
        )
        if m:
            t, p, v = float(_clean(m.group(1))), float(_clean(m.group(2))), float(_clean(m.group(3)))
            if _approx_eq(t, p + v):
                amount = _clean(m.group(1))

    # S3: Amount precedes 大写  ── Meituan multi-page last page: ¥xxx\n大写
    if not amount:
        m = re.search(r"[¥￥](" + NUM + r")\n" + _DAXIE, text)
        if m:
            amount = _clean(m.group(1))

    # S5: Metro/Makro format  ── three bare numbers before buyer name: P\nV\nT\n美国
    if not amount:
        m = re.search(
            r"(" + NUM + r")\n(" + NUM + r")\n(" + NUM + r")\n(?:美国|美利坚)",
            text,
        )
        if m:
            p, v, t = float(_clean(m.group(1))), float(_clean(m.group(2))), float(_clean(m.group(3)))
            if _approx_eq(t, p + v):
                amount = _clean(m.group(3))

    # S6: Bare-¥ triplet  ── Domino's format: T\n¥  P\n¥  V\n¥ (scattered)
    if not amount:
        bare_vals = [float(_clean(x)) for x in re.findall(r"(" + NUM + r")\n[¥￥]", text)]
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

    # S7: Railway e-tickets ── 票价 followed by ¥xxx (may be on next line)
    if not amount and is_railway_ticket:
        # Pattern 1: Same line - 票价:¥xxx or 票价：¥xxx
        m = re.search(r"票价[：:]\s*[¥￥]\s*(" + NUM + r")", text)
        if m:
            amount = _clean(m.group(1))
        # Pattern 2: Multiline - 票价: ... ¥xxx within 10 lines
        if not amount:
            m = re.search(r"票价[：:].{0,500}?[¥￥]\s*(" + NUM + r")", text, re.DOTALL)
            if m:
                amount = _clean(m.group(1))

    if amount is not None:
        with contextlib.suppress(ValueError):
            if not (0 < float(amount) <= 1_000_000):
                amount = None
    result["amount"] = amount

    # ── VAT AMOUNT ─────────────────────────────────────────────────────────────
    vat = None
    amt_float = None
    with contextlib.suppress(ValueError):
        amt_float = float(amount) if amount else None

    # V1: Inline 合计 row  ── Walmart: 合     计  ¥P  ¥V
    m = re.search(r"合\s+计\s+[¥￥]" + NUM + r"\s+[¥￥](" + NUM + r")", text)
    if m:
        vat = _clean(m.group(1))

    # V2: DiDi format  ── 合\n计\nP\n¥\nV\n¥
    if not vat:
        m = re.search(r"合\n计\n" + NUM + r"\n[¥￥]\n(" + NUM + r")\n[¥￥]", text)
        if m:
            vat = _clean(m.group(1))

    # V3: E-commerce  ── ¥P\n¥V\n大写  (skip if captured value == total)
    if not vat:
        m = re.search(r"[¥￥]" + NUM + r"\n[¥￥](" + NUM + r")\n" + _DAXIE, text)
        if m:
            candidate = _clean(m.group(1))
            if amt_float is None or not _approx_eq(float(candidate), amt_float):
                vat = candidate

    # V4: Restaurant format  ── 大写\nT\nP\nV (third number = VAT)
    if not vat:
        m = re.search(
            _DAXIE + r"\n(?![¥￥])(" + NUM + r")\n(?![¥￥])(" + NUM + r")\n(?![¥￥])(" + NUM + r")",
            text,
        )
        if m:
            t, p, v = float(_clean(m.group(1))), float(_clean(m.group(2))), float(_clean(m.group(3)))
            if _approx_eq(t, p + v):
                vat = _clean(m.group(3))

    # V5: Metro/Makro format  ── P\nV\nT\n美国 (second number = VAT)
    if not vat:
        m = re.search(
            r"(" + NUM + r")\n(" + NUM + r")\n(" + NUM + r")\n(?:美国|美利坚)",
            text,
        )
        if m:
            p, v, t = float(_clean(m.group(1))), float(_clean(m.group(2))), float(_clean(m.group(3)))
            if _approx_eq(t, p + v):
                vat = _clean(m.group(2))

    # V6: Fallback  ── find ¥ or bare-¥ value that pairs with another to equal total
    if not vat and amt_float is not None:
        all_vals = [float(_clean(x)) for x in re.findall(r"[¥￥](" + NUM + r")", text)] + [
            float(_clean(x)) for x in re.findall(r"(" + NUM + r")\n[¥￥]", text)
        ]
        val_set = {round(v, 2) for v in all_vals}
        for a in all_vals:
            if _approx_eq(a, amt_float):
                continue
            b = round(amt_float - a, 2)
            if b > 0 and b in val_set and not _approx_eq(b, amt_float):
                vat = f"{min(a, b):.2f}"
                break

    # V7: Railway e-tickets ── calculate 3% VAT if not found in text
    # Railway tickets don't list VAT separately; calculate from total amount
    if not vat and is_railway_ticket and amt_float is not None:
        # VAT = amount * 3 / 103 (3% of pre-tax amount)
        vat = f"{round(amt_float * 3 / 103, 2):.2f}"

    if vat is not None:
        with contextlib.suppress(ValueError):
            if not (0 < float(vat) <= 1_000_000):
                vat = None
    result["vat_amount"] = vat
    result["seller"] = _extract_seller(text)
    result["products"] = _extract_products(text)
    return result


def combine_pdfs(data_dir: str = "data", output: str = "combined_fapiaos.pdf") -> str | None:
    """Merge all PDFs in data_dir into a single file. Returns the output path, or None if no PDFs found."""
    pdf_files = sorted(Path(data_dir).glob("*.pdf"))
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
    """Process PDF and return list of successfully extracted fapiaos."""
    results, _ = process_pdf_with_skipped(pdf_path)
    return results


def process_pdf_with_skipped(pdf_path: str) -> tuple[list[dict], list[int]]:
    """Process PDF and return (successful results, skipped page numbers).

    Page numbers are 1-indexed.
    """
    results = []
    skipped_pages = []
    pages = 0
    doc = fitz.open(pdf_path)
    name = Path(pdf_path).name
    print(f"\nProcessing: {name}  ({len(doc)} pages)")

    for page_num in range(len(doc)):
        text = doc[page_num].get_text()
        data = parse_fapiao(text)

        if data["skip"]:
            print(f"  Page {page_num + 1:2d}: SKIP ({data['skip_reason']})")
            if data["skip_reason"] == "garbled text":
                skipped_pages.append(page_num + 1)  # 1-indexed
            else:
                pages += 1
            continue

        row = {
            "source_file": name,
            "page": page_num + 1,
            "fapiao_number": data["fapiao_number"],
            "date": data["date"],
            "amount": data["amount"],
            "vat_amount": data["vat_amount"],
            "seller": data["seller"],
            "products": data["products"],
            "pages_amount": pages + 1,
        }
        results.append(row)

        ok = all(v is not None for v in [row["fapiao_number"], row["date"], row["amount"], row["vat_amount"]])
        status = "✓" if ok else "!"
        print(
            f"  Page {page_num + 1:2d}: {status}  "
            f"{row['fapiao_number'] or 'NO_NUMBER':22}  "
            f"{row['date'] or 'NO_DATE':10}  "
            f"¥{row['amount'] or '?':8}  "
            f"VAT ¥{row['vat_amount'] or '?'}"
        )
        pages = 0

    doc.close()
    return results, skipped_pages


def main():
    if len(sys.argv) > 1:
        pdf_files = sys.argv[1:]
    else:
        # Combine any PDFs sitting in data/ first, then scan root for PDFs to process
        combine_pdfs()
        pdf_files = sorted(str(p) for p in Path(".").glob("*.pdf"))

    if not pdf_files:
        print("No PDF files found.", file=sys.stderr)
        sys.exit(1)

    all_results = []
    for pdf_path in pdf_files:
        all_results.extend(process_pdf(pdf_path))

    # Sort by date (oldest first), then by amount (largest first) as secondary sort
    all_results.sort(key=lambda r: (r.get("date") or "", -float(r.get("amount") or 0)))

    output_path = "fapiaos.csv"
    fieldnames = [
        "source_file",
        "page",
        "pages_amount",
        "seller",
        "fapiao_number",
        "date",
        "amount",
        "vat_amount",
        "products",
    ]
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        # Serialize products as JSON for CSV
        for row in all_results:
            if row.get("products"):
                row["products"] = json.dumps(row["products"], ensure_ascii=False)
            else:
                row["products"] = ""
        writer.writerows(all_results)

    total = len(all_results)
    complete = sum(
        1 for r in all_results if all(r[k] is not None for k in ["fapiao_number", "date", "amount", "vat_amount"])
    )
    print(f"\nDone. {total} fapiaos written to {output_path}  ({complete}/{total} fully extracted)")


if __name__ == "__main__":
    main()
