
import io, os, tempfile, shutil, gc
from datetime import date, datetime
import fitz
import pandas as pd
import streamlit as st

from parser_core import MangalDecoder, parse_page, merge_one, build_rows, self_test
from deed_parser import parse_deed_pdf

st.set_page_config(page_title="Registry PDF → Excel", layout="wide")
st.title("Registry PDF → Excel — V7")
mode = st.radio(
    "Report Type",
    ["Registry Index Excel", "Income Tax Report (Deed PDFs)"],
    horizontal=True,
)

def save_upload_to_temp(uploaded):
    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    uploaded.seek(0)
    shutil.copyfileobj(uploaded, tmp, length=1024 * 1024)
    tmp.flush()
    tmp.close()
    return tmp.name

def income_tax_excel(files, from_date, to_date):
    rows = []
    progress = st.progress(0)
    status = st.empty()
    for index, uploaded_file in enumerate(files, start=1):
        status.write(f"Reading {index}/{len(files)}: {uploaded_file.name}")
        rows.append(parse_deed_pdf(uploaded_file.getvalue(), uploaded_file.name))
        progress.progress(index / len(files))

    df = pd.DataFrame(rows)
    parsed_dates = pd.to_datetime(df["Date"], format="%d/%m/%Y", errors="coerce")
    in_range = parsed_dates.between(pd.Timestamp(from_date), pd.Timestamp(to_date))
    unknown_date = parsed_dates.isna()
    df = df[in_range | unknown_date].copy()
    if df.empty:
        raise ValueError("चुनी हुई तारीखों में कोई registry नहीं मिली।")
    rejected = df[df["Review"].fillna("").ne("")].copy()
    valid = df[df["Review"].fillna("").eq("")].copy()
    if valid.empty:
        return valid, rejected, None
    amount_columns = ["Deed Amount", "Land Value", "Stamp Duty", "Registration Fees"]
    for column in amount_columns:
        df[column] = pd.to_numeric(df[column], errors="coerce")

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        valid.to_excel(writer, sheet_name="Income Tax Report", index=False)

        for sheet in writer.book.worksheets:
            sheet.freeze_panes = "A2"
            sheet.auto_filter.ref = sheet.dimensions
            for cell in sheet[1]:
                cell.font = cell.font.copy(bold=True)
            for column_cells in sheet.columns:
                letter = column_cells[0].column_letter
                width = min(55, max(12, max(len(str(c.value or "")) for c in column_cells[:200]) + 2))
                sheet.column_dimensions[letter].width = width
            for column_name in amount_columns:
                if column_name in valid.columns:
                    col_number = valid.columns.get_loc(column_name) + 1
                    for row_number in range(2, sheet.max_row + 1):
                        sheet.cell(row_number, col_number).number_format = '#,##0.00'

    output.seek(0)
    return valid, rejected, output.getvalue()


if mode == "Income Tax Report (Deed PDFs)":
    st.caption("एक साथ कई Paperless Registry Deed PDFs चुनें। Masked Aadhaar छोड़कर सभी Sellers/Buyers के PAN निकाले जाएँगे।")
    today = date.today()
    financial_year_start = date(today.year if today.month >= 4 else today.year - 1, 4, 1)
    date_col1, date_col2 = st.columns(2)
    with date_col1:
        from_date = st.date_input("From Date", value=financial_year_start, format="DD/MM/YYYY")
    with date_col2:
        to_date = st.date_input("To Date", value=today, format="DD/MM/YYYY")
    deed_files = st.file_uploader("Registry Deed PDFs चुनें", type=["pdf"], accept_multiple_files=True)
    if deed_files:
        try:
            if from_date > to_date:
                raise ValueError("From Date, To Date से बाद की नहीं हो सकती।")
            deed_df, rejected_df, deed_excel = income_tax_excel(deed_files, from_date, to_date)
            if not deed_df.empty:
                st.success(f"{len(deed_df)} valid records तैयार हुए।")
                st.dataframe(deed_df, use_container_width=True, hide_index=True)
            if not rejected_df.empty:
                st.error(f"{len(rejected_df)} file reject हुईं। इनका data Excel में save नहीं किया गया।")
                st.dataframe(
                    rejected_df[["Source PDF", "Review"]],
                    use_container_width=True,
                    hide_index=True,
                )
            if deed_excel:
                st.download_button(
                    "Income Tax Excel डाउनलोड करें",
                    data=deed_excel,
                    file_name="Income_Tax_Registry_Report.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
        except Exception as error:
            st.error(f"Error: {error}")
            st.exception(error)
    st.stop()


st.caption("Independent registry detection + multi-Mangal Hindi decoding + self-test + big-file mode")
uploaded = st.file_uploader("Index PDF चुनें", type=["pdf"])

if uploaded:
    temp_pdf = None
    doc = None
    decoder = None

    try:
        temp_pdf = save_upload_to_temp(uploaded)
        doc = fitz.open(temp_pdf)
        decoder = MangalDecoder(doc)

        st.write(f"PDF Pages: **{len(doc)}**")

        # Fail early rather than producing a wrong/empty Excel.
        test = self_test(doc, decoder, pages=20)
        st.write(
            f"Self-test: {test['parsed_blocks']}/{test['expected_blocks']} registry blocks, "
            f"First Party {test['first_party_nonblank']}, Deed {test['deed_nonblank']}"
        )

        if not test["ok"]:
            st.error(
                "Self-test fail हुआ। पूरी PDF process नहीं की गई ताकि गलत Excel न बने। "
                "यह PDF layout review की जरूरत है।"
            )
            st.stop()

        progress = st.progress(0)
        status = st.empty()

        by = {}
        order = []
        raw_ascii_blocks = 0
        parsed_blocks = 0
        mismatched_pages = []
        total = len(doc)

        for i in range(total):
            page = doc.load_page(i)
            recs, raw_n = parse_page(page, i + 1, decoder)

            raw_ascii_blocks += raw_n
            parsed_blocks += len(recs)

            if len(recs) != raw_n:
                mismatched_pages.append(i + 1)

            for r in recs:
                merge_one(by, order, r)

            del recs, page

            if (i + 1) % 25 == 0:
                gc.collect()

            progress.progress((i + 1) / total)
            status.write(
                f"Page {i+1}/{total} — {parsed_blocks}/{raw_ascii_blocks} blocks — "
                f"{len(order)} unique registries"
            )

        # Hard validation: never silently export if registry blocks were lost.
        if raw_ascii_blocks == 0 or parsed_blocks != raw_ascii_blocks:
            st.error(
                f"Validation fail: PDF में {raw_ascii_blocks} registry blocks मिले लेकिन "
                f"{parsed_blocks} parse हुए। गलत Excel export नहीं की गई। "
                f"Problem pages: {mismatched_pages[:20]}"
            )
            st.stop()

        records = [by[k] for k in order]
        headers, rows, review_rows = build_rows(records)

        df = pd.DataFrame(rows, columns=headers)
        rv = pd.DataFrame(review_rows, columns=headers)

        output = io.BytesIO()
        # Normal openpyxl: previous constant_memory mode caused incomplete cells.
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df.to_excel(writer, sheet_name="Registry Data", index=False)

            if len(rv):
                rv.to_excel(writer, sheet_name="Needs Review", index=False)
            else:
                pd.DataFrame({
                    "Status": ["No structural extraction issues detected"]
                }).to_excel(writer, sheet_name="Needs Review", index=False)

            pd.DataFrame({
                "Check": [
                    "PDF Pages",
                    "ASCII Registry/Area Blocks",
                    "Parsed Registry/Area Blocks",
                    "Unique Registry/Year/Book Records",
                    "Merged Extra Area Blocks",
                    "Registry Block Loss",
                    "WILL/CANCELLATION OF WILL Rule",
                    "Hindi Decoder",
                    "Self-test",
                ],
                "Result": [
                    total,
                    raw_ascii_blocks,
                    parsed_blocks,
                    len(records),
                    parsed_blocks - len(records),
                    0,
                    "Second Party blank",
                    "Separate embedded Mangal + Mangal,Bold font programs",
                    "PASS",
                ],
            }).to_excel(writer, sheet_name="Verification", index=False)

        output.seek(0)
        full_csv = df.to_csv(index=False).encode("utf-8-sig")

        status.success(
            f"Done — {len(records)} unique registries; "
            f"{parsed_blocks}/{raw_ascii_blocks} registry blocks verified"
        )

        c1, c2, c3 = st.columns(3)
        c1.metric("PDF Pages", total)
        c2.metric("Registry Blocks", parsed_blocks)
        c3.metric("Unique Registries", len(records))

        preview_n = min(100, len(df))
        st.subheader(f"Preview — first {preview_n} of {len(df)} rows")
        st.dataframe(df.head(preview_n), use_container_width=True, hide_index=True)

        b1, b2 = st.columns(2)
        with b1:
            st.download_button(
                "⬇️ Full Excel Download करें",
                data=output,
                file_name=uploaded.name.rsplit(".", 1)[0] + "_registry.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
        with b2:
            st.download_button(
                "⬇️ Full CSV Download करें",
                data=full_csv,
                file_name=uploaded.name.rsplit(".", 1)[0] + "_registry.csv",
                mime="text/csv",
                use_container_width=True,
            )

    except Exception as e:
        st.error(f"Error: {e}")
        st.exception(e)

    finally:
        try:
            if decoder:
                decoder.close()
        except Exception:
            pass
        try:
            if doc:
                doc.close()
        except Exception:
            pass
        try:
            if temp_pdf and os.path.exists(temp_pdf):
                os.unlink(temp_pdf)
        except Exception:
            pass
