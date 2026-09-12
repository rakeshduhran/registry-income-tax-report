Registry PDF → Excel — V6 Verified
Major fixes:
Registry detection is independent of Village/Area columns.
Registry starts come from the raw ASCII token 1234/2025-2026/1.
Separate embedded font decoders are used for Mangal and Mangal,Bold.
Uses the tested Panipat Index Report geometry (scaled by page width).
20-page self-test runs before a large PDF is processed.
Final export is blocked if any Registry/Area block is lost.
Multiple Area rows merge into one Registry/Year/Book row.
WILL and CANCELLATION OF WILL => Second Party blank.
Full Excel + Full CSV; preview export is not the full data.
Normal openpyxl export to avoid constant-memory cell loss.

## V8 - Browser-only Income Tax Report

- Open `income-tax.html` from the green button on the existing portal.
- Select many separate Paperless Deed PDFs together, or upload one ZIP containing up to 600 PDFs.
- Extracts deed details, amounts, unlimited First/Second Parties, PAN and address.
- Keeps company/firm/trust and its authorized representative together in the party name.
- Masked Aadhaar is ignored. A deed with missing/invalid required data or PAN is rejected on screen and is never included in Excel.
- Processing happens inside the browser; Streamlit and a server are not required.
