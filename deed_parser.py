import re

import fitz


PAN_RE = re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b", re.I)


def _clean(value):
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip(" /|\n\t")


def _first(patterns, text, flags=re.I):
    for pattern in patterns:
        match = re.search(pattern, text, flags)
        if match:
            return _clean(match.group(1))
    return ""


def _number(value):
    value = _clean(value).replace(",", "")
    try:
        number = float(value)
        return int(number) if number.is_integer() else number
    except (TypeError, ValueError):
        return None


def _relation(value):
    value = _clean(value)
    value = re.sub(r"\([^)]*[\u0900-\u097F][^)]*\)", "", value).strip()
    return value or "NA"


def _party_name(value):
    value = _clean(value)
    value = re.sub(r"\(\s*(?:Male|Female|Other|NA)?\s*\)\s*/?", "", value, flags=re.I)
    value = re.sub(r"/\s*\*{2,}\d{2,}\b", "", value)
    value = re.sub(r"\*{2,}\d{2,}\b", "", value)
    value = re.sub(r"\bTH\s+AUTH\b", "THROUGH AUTHORIZED REPRESENTATIVE", value, flags=re.I)
    entity_words = r"\b(?:LIMITED|LTD|PVT|LLP|COMPANY|CORPORATION|TRUST|SOCIETY|BANK|FIRM|AUTHORITY)\b"
    if not re.search(entity_words, value, re.I):
        value = re.split(
            r"\s+(?:Son|Daughter|Wife|Widow|Father|Mother|पुत्री?|पत्नी|विधवा|माता|पिता)(?=\s|$)",
            value,
            maxsplit=1,
            flags=re.I,
        )[0]
    return _clean(value) or "NA"


def _party_from_row(row, header):
    # Some page-break tables contain a wide leading cell before the true columns.
    offset = 0
    for index, cell in enumerate(header):
        if "name" in _clean(cell).lower() and index + 1 < len(header):
            if "relation" in _clean(header[index + 1]).lower():
                offset = index
                break
    cells = list(row)[offset:]
    cells += [""] * max(0, 6 - len(cells))
    name = _party_name(cells[0])
    relation = _relation(cells[1])
    relative = _clean(cells[2]) or "NA"
    grandfather = _clean(cells[3]) or "NA"
    proof = _clean(cells[4]).upper()
    pan_match = PAN_RE.search(proof)
    pan = pan_match.group(0).upper() if pan_match else "NA"
    if re.fullmatch(r"X{5}[0-9]{4}X", pan):
        pan = "NA"
    id_tail_match = re.search(r"\*{2,}([0-9]{4})", proof)
    address = _clean(cells[5]) or "NA"
    return {
        "name": name,
        "relation": relation,
        "relative": relative,
        "grandfather": grandfather,
        "pan": pan,
        "address": address,
        "_id_tail": id_tail_match.group(1) if id_tail_match else "",
    }


def _classify_party_table(header):
    joined = " ".join(_clean(x).lower() for x in header)
    if "pan number" not in joined or "relation" not in joined:
        return None
    if "owner share" in joined or "total area" in joined:
        return "first"
    if "transfer" in joined or "hissa" in joined:
        return "second"
    return None


def _locate_party_header(data):
    for row_index, row in enumerate(data[:4]):
        cells = [_clean(x).lower() for x in row]
        joined = " ".join(cells)
        if "pan number" not in joined:
            continue
        for offset, cell in enumerate(cells):
            if "name" in cell and offset + 1 < len(cells) and "relation" in cells[offset + 1]:
                return row_index, row
    return None, None


def _extract_parties(doc):
    parties = {"first": [], "second": []}
    seen = {"first": set(), "second": set()}

    current_role = None
    for page in doc:
        try:
            tables = page.find_tables().tables
        except Exception:
            tables = []
        headings = []
        for needle, role in [("First Party", "first"), ("Second Party", "second")]:
            for rect in page.search_for(needle):
                headings.append((rect.y0, role))
        headings.sort()

        for table in sorted(tables, key=lambda item: item.bbox[1]):
            data = table.extract()
            if len(data) < 2:
                continue
            header_index, header = _locate_party_header(data)
            if header is None:
                continue
            role = _classify_party_table(header)
            preceding = [item for item in headings if item[0] < table.bbox[1] + 2]
            if preceding:
                nearest_role = preceding[-1][1]
                # A nearby official heading is more reliable than a broken page table.
                if table.bbox[1] - preceding[-1][0] < 180:
                    role = nearest_role
                    current_role = role
            if not role:
                role = current_role
            if not role:
                continue
            for row in data[header_index + 1:]:
                party = _party_from_row(row, header)
                if party["name"] == "NA":
                    continue
                identity = party.get("_id_tail")
                existing = None
                if identity:
                    existing = next((p for p in parties[role] if p.get("_id_tail") == identity), None)
                if existing:
                    if existing["pan"] == "NA" and party["pan"] != "NA":
                        existing["pan"] = party["pan"]
                    for key in ("name", "relation", "relative", "grandfather", "address"):
                        if existing[key] == "NA" and party[key] != "NA":
                            existing[key] = party[key]
                    continue
                signature = tuple(party[k] for k in ("name", "relation", "relative", "grandfather", "pan", "address"))
                if signature not in seen[role]:
                    parties[role].append(party)
                    seen[role].add(signature)
            if role:
                current_role = role
    return parties


def _join(parties, key):
    return " & ".join(p.get(key, "NA") or "NA" for p in parties) or "NA"


def parse_deed_pdf(source, source_name=""):
    doc = fitz.open(stream=source, filetype="pdf") if isinstance(source, (bytes, bytearray)) else fitz.open(source)
    try:
        text = "\n".join(page.get_text("text") for page in doc)
        first_page = doc[0].get_text("text") if len(doc) else ""
        parties = _extract_parties(doc)

        deed_no = _first([
            r"प्रलेख\s*क्र\.?\s*:\s*([0-9]+)",
            r"Registration\s*No\.?\s*:\s*([0-9]+)",
        ], first_page)
        date = _first([
            r"पंजीकरण\s*दिनांक\s*:\s*([0-9]{1,2}/[0-9]{1,2}/[0-9]{4})",
            r"Registration\s*No\.?\s*:\s*[0-9]+\s*Date\s*:\s*([0-9]{1,2}/[0-9]{1,2}/[0-9]{4})",
        ], first_page)
        token = _first([
            r"Token\s*:\s*([A-Z0-9_-]+)",
            r"Token\s*No\.?\s*:\s*([A-Z0-9_-]+)",
        ], first_page)
        deed_line = _first([
            r"वसीका\s*का\s*नाम\s+(.+?)(?=\nजिला\s*-)",
            r"वसीका\s*का\s*नाम\s+([^\n]+)",
        ], first_page, flags=re.I | re.S)
        deed_type = ""
        deed_name = deed_line
        type_match = re.search(r"\(([^()]*)\)\s*$", deed_line)
        if type_match:
            deed_type = _clean(type_match.group(1)).upper()
            deed_name = _clean(deed_line[:type_match.start()])
        if not deed_type:
            deed_type = _first([r"Purpose\s*:\s*([^\n]+)"], first_page).upper()
        if not deed_name:
            deed_name = deed_type

        deed_amount = _number(_first([r"लेन-देन\s*राशि\s*-\s*([0-9,.]+)"], text))
        land_value = _number(_first([r"कलेक्टर\s*दर\s*-\s*([0-9,.]+)"], text))
        stamp_duty = _number(_first([
            r"कु\s*ल\s*स्टा+म्प\s*शुल्क\s*-\s*([0-9,.]+)",
            r"Stamp\s*Duty\s*Paid\s*:\s*₹?\s*([0-9,.]+)",
        ], text, flags=re.I | re.S))
        registration_fees = _number(_first([
            r"पंजीकरण\s*फीस\s*-\s*([0-9,.]+)",
            r"Registration\s*Fees\s*:\s*₹?\s*([0-9,.]+)",
        ], text, flags=re.I | re.S))

        first = parties["first"]
        second = parties["second"]
        missing = []
        if not text.strip():
            missing.append("IMAGE-ONLY PDF: original Paperless PDF दोबारा डाउनलोड करें")
        elif not (
            "Government of Haryana" in text
            and ("Joint/ Sub Registrar Office" in text or "Registration No." in text)
            and ("First Party" in text or "प्रथम पक्ष" in text)
        ):
            missing.append("NOT A PAPERLESS REGISTRY DEED")
        for label, value in [
            ("Deed Type", deed_type), ("Deed Name", deed_name),
            ("Deed Number", deed_no), ("Date", date), ("Token Number", token),
        ]:
            if not value:
                missing.append(label)
        if not first:
            missing.append("First Party")
        if "WILL" not in (deed_type + " " + deed_name).upper() and not second:
            missing.append("Second Party")
        for label, value in [
            ("Deed Amount", deed_amount), ("Land Value", land_value),
            ("Stamp Duty", stamp_duty), ("Registration Fees", registration_fees),
        ]:
            if value is None:
                missing.append(label)
        for role_label, role_parties in (("First Party", first), ("Second Party", second)):
            for index, party in enumerate(role_parties, start=1):
                if party["pan"] == "NA":
                    missing.append(f"{role_label} {index} PAN")
        if token and not re.fullmatch(r"[A-Z]{3}_[A-Z]{3}_[A-Z]{3}_[0-9]{15}", token):
            missing.append("Invalid Token Number")

        return {
            "Deed Type": deed_type or "NA",
            "Deed Name": deed_name or "NA",
            "Deed Number": deed_no or "NA",
            "Date": date or "NA",
            "Token Number": token or "NA",
            "Deed Amount": deed_amount,
            "Land Value": land_value,
            "Stamp Duty": stamp_duty,
            "Registration Fees": registration_fees,
            "First Party Name": _join(first, "name"),
            "First Party Relation": _join(first, "relation"),
            "First Party Father/Relative Name": _join(first, "relative"),
            "First Party Grandfather Name": _join(first, "grandfather"),
            "First Party PAN": _join(first, "pan"),
            "First Party Address": _join(first, "address"),
            "Second Party Name": _join(second, "name"),
            "Second Party Relation": _join(second, "relation"),
            "Second Party Father/Relative Name": _join(second, "relative"),
            "Second Party Grandfather Name": _join(second, "grandfather"),
            "Second Party PAN": _join(second, "pan"),
            "Second Party Address": _join(second, "address"),
            "Source PDF": source_name or "NA",
            "Review": "; ".join(missing),
        }
    finally:
        doc.close()
