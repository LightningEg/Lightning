"""Bounded, read-only statement readers. Their output uses the existing CSV mapping and review.

No workbook formula, macro, embedded PDF action or external link is executed. Only CIB's
text-based account-transactions layout is recognized; image/outlined PDFs need a CSV export.
"""
from __future__ import annotations

import csv
from datetime import date, datetime
from decimal import Decimal
from io import BytesIO, StringIO
from pathlib import PurePath
import re
from zipfile import BadZipFile, ZipFile

from lightning.bank_import_rows import _date, _decimal_amount, header_row_index
from lightning.core.errors import ValidationError
from lightning.core.limits import MAX_CSV_IMPORT_BYTES, MAX_STATEMENT_DOCUMENT_BYTES

MAX_FILE_BYTES = MAX_STATEMENT_DOCUMENT_BYTES
MAX_XML_BYTES = 32 * 1024 * 1024
MAX_ROWS, MAX_COLUMNS, MAX_PAGES = 10000, 80, 20
NO_PDF_TEXT = "This PDF has no readable text. Export CSV or Excel, or use the PDF-to-CSV AI prompt below."
PDF_LAYOUT = "This PDF layout is not supported. Use a CIB text-based account-transactions statement, or convert it to CSV for review."
DATE = r"\d{2}/\d{2}/\d{4}"
ROW_DATE = re.compile(rf"^\s*({DATE})\s+({DATE})(?:\s|$)")
MONEY = re.compile(r"^-?\d[\d,]*(?:\.\d{1,2})?$")


def _csv(rows) -> bytes:
    out = StringIO(newline="")
    csv.writer(out, lineterminator='\n').writerows(rows)
    data = out.getvalue().encode('utf-8-sig')
    if len(data) > MAX_CSV_IMPORT_BYTES:
        raise ValidationError("The extracted statement is too large. Export a shorter period.", "file")
    return data


def read_statement(filename: str, data: bytes, currency: str) -> bytes:
    """Preserve CSV bytes; normalize supported documents before the ordinary mapping/review."""
    suffix = PurePath(filename).suffix.lower()
    if suffix == '.csv':
        return data
    if len(data) > MAX_FILE_BYTES:
        raise ValidationError("Excel and PDF statements must be 8 MB or smaller.", "file")
    if suffix == '.xlsx':
        return read_excel(data, currency)
    if suffix == '.pdf':
        return read_cib_pdf(data, currency)
    raise ValidationError("Choose a CSV, .xlsx Excel workbook or text-based PDF statement.", "file")


def read_excel(data: bytes, currency: str | None = None) -> bytes:
    """One nonempty worksheet, literal cells only; all limits apply before iterating cells."""
    # openpyxl automatically uses defusedxml when available. Require it for imported XML.
    from defusedxml import ElementTree  # noqa: F401
    from defusedxml.common import DefusedXmlException
    from xml.etree.ElementTree import ParseError
    from openpyxl import load_workbook
    try:
        with ZipFile(BytesIO(data)) as archive:
            entries = archive.infolist()
            if (len(entries) > 2000 or sum(e.file_size for e in entries) > MAX_XML_BYTES
                    or any(e.file_size > 8 * 1024 * 1024 or '..' in PurePath(e.filename).parts
                           or e.filename.startswith('/') for e in entries)):
                raise ValidationError("This workbook is too large to read safely. Export one worksheet as CSV.", "file")
            if any('vbaproject' in e.filename.lower() for e in entries):
                raise ValidationError("Macro-enabled workbooks are not supported. Export the statement as CSV.", "file")
        workbook = load_workbook(BytesIO(data), read_only=True, data_only=False, keep_links=False)
        try:
            sheets = []
            for sheet in workbook.worksheets:
                if sheet.max_row > MAX_ROWS + 1 or sheet.max_column > MAX_COLUMNS:
                    raise ValidationError("This worksheet exceeds 10,000 rows or 80 columns. Export a shorter statement.", "file")
                rows = []
                for row in sheet.iter_rows():
                    values = []
                    for cell in row:
                        if cell.data_type == 'f':
                            raise ValidationError("This workbook contains formulas. Export its displayed values as CSV.", "file")
                        value = cell.value
                        if isinstance(value, (date, datetime)):
                            value = value.strftime('%Y-%m-%d')
                        elif value is None:
                            value = ''
                        elif isinstance(value, bool):
                            value = str(value)
                        else:
                            value = str(value)
                        if len(value) > 10000:
                            raise ValidationError("A workbook cell is too long. Export the statement as CSV.", "file")
                        values.append(value)
                    if any(values):
                        rows.append(values)
                if rows:
                    # Trim trailing empty columns, retaining the order and the bank's original header names.
                    width = max(next((i+1 for i in range(len(row)-1,-1,-1) if row[i]),0) for row in rows)
                    sheets.append([row[:width] for row in rows])
            if len(sheets) != 1:
                raise ValidationError("Choose a workbook with one nonempty worksheet, or export the wanted worksheet as CSV.", "file")
            rows = sheets[0]
            rows = rows[header_row_index(rows):]  # the bank's title lines stay out, as in a CSV (7AA)
            headers = [value.strip().casefold() for value in rows[0]]
            if currency and 'currency' in headers:
                index = headers.index('currency')
                currencies = {row[index].strip().upper() for row in rows[1:] if len(row) > index and row[index].strip()}
                if currencies and currencies != {currency}:
                    raise ValidationError("The workbook currency does not match this account. Export one currency at a time.", "file")
            if 'account' in headers:
                index = headers.index('account')
                accounts = {row[index].strip() for row in rows[1:] if len(row) > index and row[index].strip()}
                if len(accounts) > 1:
                    raise ValidationError("This workbook contains more than one account. Export one account at a time.", "file")
            return _csv(rows)
        finally:
            workbook.close()
    except ValidationError:
        raise
    except (BadZipFile, ValueError, KeyError, OSError, TypeError, ArithmeticError, ParseError, DefusedXmlException) as exc:
        raise ValidationError("This Excel workbook could not be read. Export it as CSV.", "file") from exc


def _cib_text_rows(text: str) -> list[dict]:
    """Read only aligned posting/value-date, description, debit, credit and balance columns."""
    lines = text.splitlines()
    header_index = next((i for i, line in enumerate(lines)
                         if all(word in line for word in ('Description', 'Debit', 'Credit', 'Balance'))), None)
    header = lines[header_index] if header_index is not None else None
    if header is None:
        raise ValidationError(PDF_LAYOUT, 'file')
    debit, credit, balance = (header.index(word) + len(word)/2 for word in ('Debit', 'Credit', 'Balance'))
    debit_left = (header.index('Description') + len('Description')/2 + debit) / 2
    credit_left, balance_left = (debit+credit)/2, (credit+balance)/2
    rows = []
    for line in lines[header_index + 1:]:
        match = ROW_DATE.match(line)
        if match:
            cells = [(m.group().strip(), (m.start()+m.end())/2, m.start()) for m in re.finditer(r'\S(?:.*?\S)?(?=\s{2,}|$)', line)]
            numeric = [(value, center, start) for value, center, start in cells if center >= debit_left and MONEY.fullmatch(value)]
            amounts = [(v, x) for v, x, _ in numeric if x < balance_left]
            balances = [(v, x) for v, x, _ in numeric if x >= balance_left]
            if len(amounts) != 1 or len(balances) != 1:
                raise ValidationError("A PDF transaction has ambiguous amount columns. Convert it to CSV and review the uncertain cells.", 'file')
            amount, start = amounts[0]
            value = _decimal_amount(amount)
            is_debit = start < credit_left
            if not is_debit and value < 0:
                raise ValidationError(PDF_LAYOUT, 'file')
            amount_value = -abs(value) if is_debit else value
            description = line[match.end():min(start for _, _, start in numeric)].strip()
            rows.append({'date':_date(match.group(1)), 'value_date':_date(match.group(2)),
                         'amount':amount_value,'balance':_decimal_amount(balances[0][0]), 'description':description})
        elif re.match(r'^\s*\d{1,4}[/-]\d{1,2}[/-]',line):
            raise ValidationError(PDF_LAYOUT,'file')
        elif rows and line.strip():
            # A wrapped description is confined to the description column; headers/footers are ignored.
            start = len(line)-len(line.lstrip())
            if header.index('Description')-3 <= start < debit_left and not any(word in line for word in ('Description','Posting','Credit','Debit','Balance')):
                rows[-1]['description'] += ' ' + line.strip()
    return rows


def read_cib_pdf(data: bytes, currency: str) -> bytes:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError
    try:
        reader = PdfReader(BytesIO(data), strict=True)
        if reader.is_encrypted:
            raise ValidationError("Password-protected PDFs are not supported. Export CSV or Excel instead.", 'file')
        if len(reader.pages) > MAX_PAGES:
            raise ValidationError("PDF statements must have 20 pages or fewer. Export a shorter period.", 'file')
        pages = []
        for page in reader.pages:
            contents = page.get_contents()
            if contents is not None and len(contents.get_data()) > MAX_STATEMENT_DOCUMENT_BYTES:
                raise ValidationError("This PDF contains too much text. Export a shorter period.", 'file')
            text = (page.extract_text(extraction_mode='layout') or '') if contents is not None else ''
            if len(text) > 200000 or sum(map(len,pages))+len(text) > 1000000:
                raise ValidationError("This PDF contains too much text. Export a shorter period.", 'file')
            pages.append(text)
        if not pages or any(not text.strip() for text in pages):
            raise ValidationError(NO_PDF_TEXT,'file')
        text='\n'.join(pages)
        if not re.search(r'ACCOUNT\s+TRANSACTIONS',text,re.I):
            raise ValidationError(PDF_LAYOUT,'file')
        currencies = {code.upper() for code in re.findall(r'Currency\s*:?\s*([A-Z]{3})\b',text,re.I)}
        if not currencies:
            raise ValidationError(PDF_LAYOUT, 'file')
        if currencies != {currency}:
            raise ValidationError("The PDF currency does not match this account. Choose the matching account.", 'file')
        rows = []
        for text in pages:
            rows.extend(_cib_text_rows(text))
        if not rows or len(rows)>MAX_ROWS:
            raise ValidationError(PDF_LAYOUT,'file')
        # Bank exports can be oldest or newest first. Require the printed running balances to reconcile.
        def reconciles(items):
            return all(abs(b['balance']-a['balance']-b['amount']) <= Decimal('0.01') for a,b in zip(items,items[1:]))
        if len(rows)>1 and not (reconciles(rows) or reconciles(list(reversed(rows)))):
            raise ValidationError("The PDF balances do not reconcile with its extracted rows. Convert it to CSV and review every amount.", 'file')
        output = [['Date','Amount','Counterparty','Notes','Reference']]
        for row in rows:
            description=row['description']
            reference=re.search(r'\b(?:FT|TT)[A-Z0-9]{5,}\b',description)
            notes=f"{description} · Value date: {row['value_date']} · Statement balance: {row['balance']:f}"
            output.append([row['date'],f"{row['amount']:f}",'',notes,reference.group() if reference else ''])
        return _csv(output)
    except ValidationError:
        raise
    except (PdfReadError, ValueError, TypeError, KeyError, OSError, IndexError, RecursionError, NotImplementedError) as exc:
        raise ValidationError("This PDF could not be read. Export CSV or Excel instead.",'file') from exc
