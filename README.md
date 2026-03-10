# Fapiao Extractor

Extracts key fields from Chinese electronic fapiao (发票) PDF files and fills them into the VAT Reimbursement Claim Form Excel template. Works entirely offline — no AI API required.

## What it extracts

From each fapiao page in a PDF:

| Field | Chinese | Example |
|---|---|---|
| Fapiao number | 发票号码 | 25427000000451759623 |
| Issue date | 开票日期 | 2025-10-18 |
| Total amount | 小写 | 293.70 |
| VAT amount | 税额合计 | 32.15 |

## Setup

One-time setup — only needed the first time:

```bash
python3 -m venv .venv
.venv/bin/pip install pymupdf openpyxl
```

## Typical workflow

### Step 1 — Add PDFs to the data folder

Drop each fapiao PDF you receive into the `data/` subfolder. You can add files at any time; there is no need to rename or sort them.

```
data/
  2025-11-02 Fapiaos Nov 2025.pdf
  2025-12-31 Fapiaos Nov Dec 2025.pdf
  ...
```

### Step 2 — Extract from PDFs

```bash
.venv/bin/python extract_fapiaos.py
```

The script first merges every PDF in `data/` into a single file called `combined_fapiaos.pdf`, then extracts fapiao data from all PDFs in the current folder (including the freshly combined one) and writes the results to `fapiaos.csv`.

The terminal output shows each fapiao with a `✓` (all fields found) or `!` (something missing). Pages that are skipped are noted with a reason (garbled airline ticket, continuation page of a multi-page fapiao, etc.).

You can also skip the `data/` folder entirely and pass specific files directly:

```bash
.venv/bin/python extract_fapiaos.py "November fapiaos.pdf" "December fapiaos.pdf"
```

### Step 2 — Review the CSV

Open `fapiaos.csv` and check the extracted values before writing to Excel. Fix any `!` rows manually if needed — the CSV is plain text and easy to edit.

### Step 3 — Fill the Excel form (run 1)

```bash
.venv/bin/python fill_excel.py 1
```

This copies the original template and writes the **date, fapiao number, and quantity (always 1)** into the form. Output is saved to:

```
VAT Reimbursement Claim Form - January 2026 (filled).xlsx
```

Open the file in Excel and verify the entries look correct before continuing.

### Step 4 — Fill the Excel form (run 2)

```bash
.venv/bin/python fill_excel.py 2
```

This opens the file saved in step 3 and adds the **fapiao amount and VAT amount**. The file is saved again in place.

The formula columns (auto-translated description, VAT rate) are computed automatically by Excel and are never overwritten.

## Web app

A Flask web interface is available for users who prefer not to use the command line.

### Start the server

```bash
.venv/bin/python app.py
```

Then open **http://127.0.0.1:5000** in a browser. Upload one or more fapiao PDFs and the Excel template, click **Process and download**, and the filled form is downloaded automatically.

The web app runs the full pipeline in one shot (no two-run split needed). It does not store any files — everything is processed in a temporary directory that is deleted immediately after the response is sent.

---

## Output files

| File | Description |
|---|---|
| `combined_fapiaos.pdf` | All PDFs from `data/` merged into one file |
| `fapiaos.csv` | Extracted data — review this before filling Excel |
| `VAT Reimbursement Claim Form - January 2026 (filled).xlsx` | Completed form — original template is never modified |

## PDF formats supported

The extractor handles the variety of fapiao layouts encountered in practice:

- Standard electronic fapiao (e.g. Walmart/Sam's Club)
- E-commerce platforms (Taobao, JD, etc.)
- Restaurants and food delivery
- Transport (DiDi ride receipts)
- Hotels and accommodation
- Metro/Makro wholesale receipts
- Multi-page fapiaos (only the final page with the grand total is counted)

Pages that cannot be parsed are skipped with a note: garbled airline/train ticket PDFs use a non-standard font encoding that makes text extraction unreliable.

## Limitations

- The form holds a maximum of 40 entries (rows 12–51). If the CSV has more, the extras are truncated with a warning.
- Airline and train ticket PDFs (e.g. from 12306 or travel agencies) are often garbled and skipped. Enter these manually in the Excel form.
- About 90% extraction accuracy is expected across varied fapiao formats. Always review `fapiaos.csv` before the Excel fill step.
