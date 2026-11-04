"""Standalone native-module smoke test used in the focused packaged dependency check."""
from rapidfuzz.fuzz import ratio

assert ratio('Talabt', 'Talabat') > 90
assert ratio('أحمد', 'احمد') == 75
assert ratio('Groceres', 'Groceries') > 90
print('Frozen matcher passed')


# Reader locks are present on the statement branch. The matcher-only branch does not install them.
from importlib.util import find_spec
if find_spec('openpyxl') is not None:
    from io import BytesIO
    from openpyxl import Workbook
    from pypdf import PdfWriter
    from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
    from lightning.statement_files import read_statement
    workbook = Workbook()
    workbook.active.append(['Date', 'Amount', 'Counterparty'])
    workbook.active.append(['2026-09-01', -10, 'Fictional shop'])
    stream = BytesIO()
    workbook.save(stream)
    assert b'Fictional shop' in read_statement('fictional.xlsx', stream.getvalue(), 'EGP')
    writer = PdfWriter()
    page = writer.add_blank_page(width=1000, height=600)
    font = DictionaryObject({NameObject('/Type'): NameObject('/Font'), NameObject('/Subtype'): NameObject('/Type1'), NameObject('/BaseFont'): NameObject('/Courier')})
    page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): writer._add_object(font)})})
    content = DecodedStreamObject()
    lines = ['ACCOUNT TRANSACTIONS Currency EGP',
             'Posting Date Value Date Description               Debit         Credit        Balance',
             '01/09/2026 01/09/2026   FICTIONAL FT123456          10.00                          90.00']
    def escape(text):
        return text.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')
    content.set_data(('BT /F1 10 Tf 12 TL 20 550 Td ' + ' '.join(f'({escape(line)}) Tj T*' for line in lines) + ' ET').encode())
    page[NameObject('/Contents')] = writer._add_object(content)
    stream = BytesIO()
    writer.write(stream)
    assert b'FT123456' in read_statement('fictional.pdf', stream.getvalue(), 'EGP')
    print('Frozen statement readers passed')
