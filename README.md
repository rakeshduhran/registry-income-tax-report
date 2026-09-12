# Registry PDF → Excel — V6 Verified

## V7 - Income Tax Deed Report

- Keeps the existing V6 Registry Index parser unchanged.
- Adds multi-file Paperless Registry Deed PDF upload.
- Adds From Date and To Date filtering.
- Extracts Deed Type, Deed Name, Deed Number, Date, Token Number, Deed Amount,
  Land Value, Stamp Duty and Registration Fees.
- Extracts unlimited First/Second Parties with Relation, Relative/Father,
  Grandfather, PAN and Address.
- Keeps a company/firm/trust name together with its authorized representative.
- Ignores masked Aadhaar and validates PAN format.
- Joins multiple parties with ` & ` while preserving the same order across fields.
- Rejects a PDF when a required field or PAN is missing.
- Wrong, incomplete and image-only/scanned PDFs are shown on screen with the
  rejection reason and are never written to the downloaded Excel. Download the
  original Paperless PDF for reliable extraction.

Major fixes:
- Registry detection is independent of Village/Area columns.
- Registry starts come from the raw ASCII token `1234/2025-2026/1`.
- Separate embedded font decoders are used for `Mangal` and `Mangal,Bold`.
- Uses the tested Panipat Index Report geometry (scaled by page width).
- 20-page self-test runs before a large PDF is processed.
- Final export is blocked if any Registry/Area block is lost.
- Multiple Area rows merge into one Registry/Year/Book row.
- WILL and CANCELLATION OF WILL => Second Party blank.
- Full Excel + Full CSV; preview export is not the full data.
- Normal openpyxl export to avoid constant-memory cell loss.
