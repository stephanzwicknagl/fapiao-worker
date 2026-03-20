# Fix SEC-L.7, L.8: Amount Bounds and Seller Name Length Limits

- [x] Fix 3.7: Add bounds checking on parsed invoice amounts in `fapiao/extract.py` — skip any parsed float that is ≤ 0 or > 1,000,000. Added before `result['amount']` and `result['vat_amount']` assignments in `parse_fapiao()`.
- [x] Fix 3.8: Add a 255-character length limit on extracted seller names in `fapiao/extract.py` — skip candidates that exceed this length. Added `continue` guard in both pattern 1 and pattern 2 of `_extract_seller()`, before `_BUYER_NAMES` check.
- [x] Mark tickets 3.7 and 3.8 as resolved in `docs/epics/epic-security-low.md`. Updated ticket headers to ✓ RESOLVED, replaced Required Changes with Resolution notes, and checked acceptance criteria boxes.
