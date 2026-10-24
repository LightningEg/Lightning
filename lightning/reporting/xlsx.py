"""Minimal, in-memory OOXML writer for local analysis exports (no temporary plaintext files)."""

from __future__ import annotations

from decimal import Decimal
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile
from xml.sax.saxutils import escape, quoteattr


MAX_ROWS = 1_048_576
MAX_CELL_TEXT = 32_767


def _column_name(index: int) -> str:
    name = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(65 + remainder) + name
    return name


def _clean_text(value: str) -> str:
    # XML 1.0 disallows these control characters. Keep tabs and line breaks as data.
    return "".join(char for char in value
                   if char in "\t\n\r" or 0x20 <= ord(char) <= 0xD7FF
                   or 0xE000 <= ord(char) <= 0xFFFD or 0x10000 <= ord(char) <= 0x10FFFF)


def _cell(value, ref: str, style: int = 0) -> str:
    style_attr = f' s="{style}"' if style else ""
    if value is None:
        return f'<c r="{ref}"{style_attr}/>'
    if isinstance(value, bool):
        return f'<c r="{ref}" t="b"{style_attr}><v>{1 if value else 0}</v></c>'
    if isinstance(value, (int, float, Decimal)):
        return f'<c r="{ref}"{style_attr}><v>{value}</v></c>'
    text = _clean_text(str(value))
    if len(text) > MAX_CELL_TEXT:
        raise ValueError("A cell contains more text than Excel can store (32,767 characters). Shorten that note and prepare the export again.")
    # inlineStr is always data, including strings beginning with =, +, - or @.
    return f'<c r="{ref}" t="inlineStr"{style_attr}><is><t xml:space="preserve">{escape(text)}</t></is></c>'


def _worksheet(headers: list[str], rows: list[tuple], widths: list[int]) -> bytes:
    if len(rows) + 1 > MAX_ROWS:
        raise ValueError("This period has more rows than one Excel sheet can hold. Narrow the period and prepare the export again; no records were truncated.")
    widths = [min(54, max(12, len(str(header)) + 3,
                  max((max((len(part) for part in str(row[i] or "").splitlines()), default=0)
                       for row in rows if i < len(row)), default=0) + 2))
              for i, header in enumerate(headers)]
    max_col = max(1, len(headers))
    max_row = max(1, len(rows) + 1)
    cols = "".join(f'<col min="{i}" max="{i}" width="{width}" customWidth="1"/>'
                   for i, width in enumerate(widths, 1))
    output = [('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
               '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
               'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">')]
    output.append('<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" '
                  'activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>')
    output.append(f'<cols>{cols}</cols>')
    output.append('<sheetData>')
    output.append('<row r="1">' + "".join(_cell(value, f"{_column_name(i)}1", 1)
                                           for i, value in enumerate(headers, 1)) + '</row>')
    for row_number, row in enumerate(rows, 2):
        output.append(f'<row r="{row_number}">')
        output.extend(_cell(value, f"{_column_name(i)}{row_number}",
                            2 if isinstance(value, Decimal) else 0)
                      for i, value in enumerate(row, 1))
        output.append('</row>')
    output.append('</sheetData>')
    if rows:
        output.append(f'<autoFilter ref="A1:{_column_name(max_col)}{max_row}"/>')
    output.append('</worksheet>')
    return "".join(output).encode("utf-8")


def workbook_bytes(sheets: list[tuple[str, list[str], list[tuple], list[int]]]) -> bytes:
    """Write (sheet name, headings, rows, widths) tables to one XLSX entirely in memory."""
    if len(sheets) != 4 or [sheet[0] for sheet in sheets] != ["Summary", "Transactions", "Investment ledger", "Categories"]:
        raise ValueError("AI analysis workbooks must contain the four required sheets in order.")
    return tabular_workbook_bytes(sheets)


def tabular_workbook_bytes(sheets: list[tuple[str, list[str], list[tuple], list[int]]]) -> bytes:
    """The same inline-text writer, for complete local data exports with any set of tables."""
    names = [sheet[0] for sheet in sheets]
    if not names or len(set(name.casefold() for name in names)) != len(names) or any(
            not name or len(name) > 31 or any(ch in name for ch in '[]:*?/\\') for name in names):
        raise ValueError("Workbook sheet names must be unique and at most 31 characters.")
    output = BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED, compresslevel=6) as archive:
        content_overrides = ''.join(
            f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            for i in range(1, len(sheets) + 1))
        archive.writestr("[Content_Types].xml", (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
            + content_overrides + '</Types>'))
        archive.writestr("_rels/.rels", (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            '</Relationships>'))
        entries = ''.join(f'<sheet name={quoteattr(name)} sheetId="{i}" r:id="rId{i}"/>'
                          for i, (name, _, _, _) in enumerate(sheets, 1))
        archive.writestr("xl/workbook.xml", (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            f'<sheets>{entries}</sheets></workbook>'))
        rel_entries = ''.join(
            f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>'
            for i in range(1, len(sheets) + 1))
        rel_entries += (f'<Relationship Id="rId{len(sheets)+1}" '
                        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>')
        archive.writestr("xl/_rels/workbook.xml.rels", (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            f'{rel_entries}</Relationships>'))
        archive.writestr("xl/styles.xml", (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<numFmts count="1"><numFmt numFmtId="164" formatCode="#,##0.00####"/></numFmts>'
            '<fonts count="1"><font><sz val="11"/><color rgb="FF000000"/><name val="Arial"/></font></fonts>'
            '<fills count="2"><fill><patternFill patternType="none"/></fill>'
            '<fill><patternFill patternType="gray125"/></fill></fills>'
            '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
            '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
            '<cellXfs count="3">'
            '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1"><alignment horizontal="left" vertical="top"/></xf>'
            '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1"><alignment horizontal="left" vertical="top"/></xf>'
            '<xf numFmtId="164" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1" applyAlignment="1"><alignment horizontal="left" vertical="top"/></xf>'
            '</cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>'))
        for i, (_, headers, rows, widths) in enumerate(sheets, 1):
            archive.writestr(f"xl/worksheets/sheet{i}.xml", _worksheet(headers, rows, widths))
    return output.getvalue()
