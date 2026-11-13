"""Bounded, lossless onboarding of comprehensive Lightning workbooks into unused profiles."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from io import BytesIO
import posixpath
import re
from zipfile import ZipFile, BadZipFile
from xml.etree import ElementTree as ET

from .data_export import TABLES, readable_relations
from lightning.core.dates import today
from lightning.core.errors import ValidationError
from lightning.core.ledger import Effect, PostingLine, validate_posting
from lightning.core.money import from_e6

MAX_UPLOAD = 16 * 1024 * 1024
MAX_EXPANDED = 96 * 1024 * 1024
MAX_CELLS = 750_000
NS = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
RNS = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'


def _xml(data):
    if b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper():
        raise ValueError('XML entities are not supported.')
    return ET.fromstring(data)


def read_workbook(data):
    if len(data) > MAX_UPLOAD:
        raise ValueError('Choose a workbook smaller than 16 MB.')
    try:
        with ZipFile(BytesIO(data)) as archive:
            entries = archive.infolist()
            if any('vbaproject' in entry.filename.casefold() for entry in entries):
                raise ValueError('Macros are not supported; save a plain .xlsx workbook.')
            if len(entries) > 1500 or sum(x.file_size for x in entries) > MAX_EXPANDED:
                raise ValueError('The expanded workbook is too large.')
            if len({x.filename for x in entries}) != len(entries):
                raise ValueError('Duplicate workbook files are not supported.')
            for entry in entries:
                if entry.filename.endswith('.rels'):
                    rels = _xml(archive.read(entry))
                    if any(r.get('TargetMode') == 'External' for r in rels):
                        raise ValueError('External workbook links are not supported.')
            workbook = _xml(archive.read('xl/workbook.xml'))
            rels = _xml(archive.read('xl/_rels/workbook.xml.rels'))
            paths = {r.get('Id'): posixpath.normpath(posixpath.join('xl', r.get('Target', '').lstrip('/')))
                     if not r.get('Target', '').startswith('/') else r.get('Target').lstrip('/') for r in rels}
            strings = []
            if 'xl/sharedStrings.xml' in archive.namelist():
                strings = [''.join(si.itertext()) for si in _xml(archive.read('xl/sharedStrings.xml'))]
            sheets, cells = {}, 0
            for sheet in workbook.find(NS + 'sheets'):
                name = sheet.get('name')
                if not name or name.casefold() in {n.casefold() for n in sheets}:
                    raise ValueError('Duplicate or unnamed sheets are not supported.')
                root = _xml(archive.read(paths[sheet.get(RNS + 'id')]))
                if root.findall('.//' + NS + 'f'):
                    raise ValueError(f'{name}: replace formulas with their values before importing.')
                rows = []
                for row in root.findall('.//' + NS + 'sheetData/' + NS + 'row'):
                    values, seen = [], set()
                    for cell in row:
                        cells += 1
                        if cells > MAX_CELLS:
                            raise ValueError('The workbook has too many cells.')
                        ref = cell.get('r', '')
                        match = re.fullmatch(r'([A-Z]+)[1-9][0-9]*', ref)
                        if not match or ref in seen:
                            raise ValueError(f'{name}: invalid or duplicate cell reference.')
                        seen.add(ref)
                        col = 0
                        for char in match[1]:
                            col = col * 26 + ord(char) - 64
                        if col > 256:
                            raise ValueError('The workbook has too many columns.')
                        while len(values) < col:
                            values.append(None)
                        value = cell.findtext(NS + 'v')
                        kind = cell.get('t')
                        if kind == 'inlineStr':
                            inline = cell.find(NS + 'is')  # an emptied cell may keep the tag with no text
                            value = ''.join(inline.itertext()) if inline is not None else None
                        elif kind == 's':
                            try:
                                value = strings[int(value)]
                            except (ValueError, IndexError):
                                raise ValueError('Invalid shared-string reference.') from None
                        elif kind == 'str':
                            pass  # plain text written without the shared table (Open XML SDK); formulas were refused above
                        elif kind == 'e':
                            raise ValueError(f'{name}: unsupported cell type; use plain values.')
                        if value is not None and len(str(value)) > 32767:
                            raise ValueError('A workbook cell contains too much text.')
                        values[col - 1] = value
                    if any(v is not None for v in values):
                        rows.append(values)
                sheets[name] = rows
            return sheets
    except (BadZipFile, KeyError, ET.ParseError, IndexError, TypeError, AttributeError, OverflowError) as exc:
        raise ValueError('Choose a valid Excel .xlsx workbook with plain values.') from exc


def _schema(c):
    return {name: [dict(row) for row in c.db.all(f'PRAGMA table_info("{name}")')]
            for name in (*TABLES, 'settings')}



def _has_custom_setup(c):
    # Compare every portable financial table with a fresh seed. Keep runtime identity
    # and audit metadata separate; user setup (even without a posting) must not be discarded.
    from lightning.database.connection import Database
    from lightning.database.migrator import migrate
    from lightning.database.seed import seed
    from lightning.database.settings import SettingsStore
    baseline = Database(':memory:')
    try:
        migrate(baseline)
        SettingsStore(baseline).set('base_currency', c.base_currency)
        seed(baseline)
        for name in (table for table in TABLES if table not in ('profile_identity', 'audit_log')):
            fields = [r['name'] for r in c.db.all(f'PRAGMA table_info("{name}")')
                      if r['name'] not in ('created_at', 'updated_at', 'registered_at')]
            columns = ','.join(f'"{col}"' for col in fields)
            existing = [tuple(row) for row in c.db.all(f'SELECT {columns} FROM "{name}" ORDER BY rowid')]
            initial = [tuple(row) for row in baseline.all(f'SELECT {columns} FROM "{name}" ORDER BY rowid')]
            if existing != initial:
                return True
        return False
    finally:
        baseline.close()

def _unused(c):
    if c.db.read_only:
        raise ValueError('Open a writable new profile before importing.')
    if _has_custom_setup(c):
        raise ValueError('Import into a new, empty profile. Your existing setup would otherwise be overwritten.')
    if c.db.one('SELECT id FROM accounts WHERE is_system=0 LIMIT 1') or c.db.one('SELECT id FROM transactions LIMIT 1'):
        raise ValueError('Import into a new, empty profile. Your existing records will not be overwritten.')
    for name in ('planned_items', 'cash_reserves', 'counterparties', 'rules', 'physical_items', 'budgets', 'price_history', 'fx_rates', 'bank_import_batches'):
        if c.db.one(f'SELECT 1 FROM "{name}" LIMIT 1'):
            raise ValueError('Import into a new, empty profile. Your existing records will not be overwritten.')


def _setting_allowed(key):
    return key in ('base_currency', 'locale', 'privacy_mode') or key.startswith(
        ('budget_', 'investment_', 'emergency_', 'health_', 'financial_health_'))


class WorkbookProblems(ValueError):
    """Everything wrong with a workbook, found in one pass: each line names the sheet, row and column in plain words,
    so a person (or the AI that filled the file) fixes them all before uploading again."""
    SHOWN = 25

    def __init__(self, problems):
        self.problems = list(problems)
        count = len(self.problems)
        super().__init__('Nothing was imported. ' + (self.problems[0] if count == 1 else f'{count} things need fixing in the workbook:'))

    @property
    def shown(self):
        extra = len(self.problems) - self.SHOWN
        return self.problems[:self.SHOWN] + ([f'… and {extra} more.'] if extra > 0 else [])


def _sheet_of(table):
    return table[:31]


def _plain_database_error(text):
    """A database refusal in the words of the sheet it came from (the checks before it catch most; this is the net)."""
    found = re.search(r'(NOT NULL|UNIQUE|CHECK|FOREIGN KEY) constraint failed:? ?([\w.]*)', text)
    kind, where = (found.group(1), found.group(2)) if found else ('', '')
    table, _, column = where.partition('.')
    place = f'Sheet "{_sheet_of(table)}"' + (f', column "{column}"' if column else '') if table else 'The workbook'
    if kind == 'NOT NULL':
        return f'{place} cannot be empty: fill in every row.'
    if kind == 'UNIQUE':
        return f'{place} repeats a value that must be different in every row (an id or a reference).'
    if kind == 'FOREIGN KEY':
        return f'{place} points to a record that is not in the workbook.'
    if kind == 'CHECK':
        return f'{place} holds a value that is not allowed (check the template for the choices).'
    return 'The workbook does not fit Lightning\'s records. ' + text


def _from_excel_serial(value, dated):
    """Excel (or an AI tool) turns a typed date or time into a date cell, saved as days since 1899-12-30: put back
    the text Lightning keeps, a yyyy-mm-dd date or a local timestamp. Anything else is left for the checks below."""
    text = str(value)
    if not re.fullmatch(r'[1-9][0-9]{4}(\.[0-9]+)?', text) or not 20_000 <= Decimal(text) < 80_000:  # 1954 to 2119
        return value
    moment = datetime(1899, 12, 30) + timedelta(seconds=int((Decimal(text) * 86_400).to_integral_value()))  # not money: seconds
    if dated:
        return moment.date().isoformat()
    return moment.astimezone().isoformat(timespec='seconds')


def _convert(value, field, table):
    name = field['name']
    if value is None:
        # Excel cannot keep an empty text: a blank cell in a required column with a default takes that default
        # (notes '' and the like), so a workbook an AI or a person left blank is not refused.
        default = field['dflt_value'] if field['notnull'] else None
        if isinstance(default, str) and len(default) >= 2 and default[0] == default[-1] == "'":
            return default[1:-1].replace("''", "'")
        if isinstance(default, str) and re.fullmatch(r'-?[0-9]+', default):
            return int(default)
        if field['notnull'] and default is None and field['type'].upper() == 'TEXT':
            return ''
        return None
    if name.endswith('_e6') or field['type'].upper() == 'INTEGER':
        try:
            number = Decimal(value)
            if name.endswith('_e6'):
                number *= 1_000_000
            if not number.is_finite() or number != number.to_integral_value() or abs(number) > 2**63 - 1:
                raise ValueError()
            return int(number)
        except (InvalidOperation, ValueError):
            raise ValueError('use a number with at most six decimal places.') from None
    dated = name == 'date' or name.endswith('_date') or name in ('date_from', 'date_to', 'first_date')
    if (dated or name.endswith('_at')) and field['type'].upper() == 'TEXT':
        value = _from_excel_serial(value, dated)
    if value and dated:
        try:
            if date.fromisoformat(str(value)).isoformat() != value:
                raise ValueError()
        except ValueError:
            raise ValueError('use a real date written yyyy-mm-dd, for example 2026-03-31.') from None
    return value


def _load(conn, tables, schema):
    required_categories = {row[0] for row in conn.execute('SELECT code FROM categories WHERE is_system=1')}
    conn.execute('PRAGMA defer_foreign_keys=ON')
    # Only identifiers supplied by this module/schema are used as SQL. Uploaded cells are parameters.
    for name in reversed((*TABLES, 'settings')):
        if name == 'profile_identity':
            continue  # A new profile retains its own device-pairing identity.
        if name == 'settings':
            for row in conn.execute('SELECT key FROM settings').fetchall():
                if _setting_allowed(row[0]):
                    conn.execute('DELETE FROM settings WHERE key=?', (row[0],))
        else:
            conn.execute(f'DELETE FROM "{name}"')
    for name in (*TABLES, 'settings'):
        if name == 'profile_identity':
            continue
        columns, rows = tables[name]
        if rows:
            sql = f'INSERT INTO "{name}" (' + ','.join(f'"{col}"' for col in columns) + ') VALUES (' + ','.join('?' for _ in columns) + ')'
            conn.executemany(sql, rows)
    base_row = conn.execute("SELECT value FROM settings WHERE key='base_currency'").fetchone()
    base = base_row[0] if base_row else None
    if not base or not conn.execute('SELECT 1 FROM registered_currencies WHERE code=?', (base,)).fetchone() or not conn.execute(
            'SELECT 1 FROM financial_assets WHERE is_cash=1 AND currency=?', (base,)).fetchone():
        raise ValueError('The default currency must be registered and have a cash asset. Keep the template currency records.')
    present_categories = {row[0] for row in conn.execute('SELECT code FROM categories')}
    if required_categories - present_categories:
        raise ValueError('Required system categories are missing. Keep the template system category records.')
    broken = conn.execute('PRAGMA foreign_key_check').fetchall()
    if broken:
        raise WorkbookProblems([f'Sheet "{_sheet_of(row[0])}", the row with id {row[1]}: it points to a record that is not on sheet "{_sheet_of(row[2])}". '
                                'Keep every account, asset, category and transaction that a row refers to.' for row in broken])
    for table in ('categories', 'asset_classes', 'accounts'):
        links = {r[0]: r[1] for r in conn.execute(f'SELECT id,parent_id FROM {table}')}
        for key in links:
            seen, node = set(), key
            while node is not None:
                if node in seen:
                    raise ValueError(f'{table}: parent references form a cycle.')
                seen.add(node)
                node = links.get(node)
    if conn.execute('SELECT 1 FROM ledger_entries l JOIN transactions t ON t.id=l.transaction_id JOIN accounts a ON a.id=l.account_id WHERE l.date<>t.date OR l.date<a.opening_date OR l.line_no<1 OR l.fx_rate_e6<=0 OR l.unit_price_e6<0 LIMIT 1').fetchone():
        raise ValueError('Ledger dates, line numbers, prices or FX rates are inconsistent.')
    if conn.execute('SELECT 1 FROM ledger_entries l JOIN accounts a ON a.id=l.account_id '
                    'JOIN financial_assets f ON f.id=l.asset_id WHERE f.is_cash=1 AND f.currency<>a.currency LIMIT 1').fetchone():
        raise ValueError('A cash asset currency must match its account currency.')
    if conn.execute("SELECT 1 FROM transactions t WHERE status='POSTED' AND NOT EXISTS (SELECT 1 FROM ledger_entries l WHERE l.transaction_id=t.id) LIMIT 1").fetchone():
        raise ValueError('A posted transaction has no ledger lines.')
    columns = [item[1] for item in conn.execute('PRAGMA table_info(ledger_entries)')]
    postings = {}
    cash_assets = {row[0]: bool(row[1]) for row in conn.execute('SELECT id,is_cash FROM financial_assets')}
    for raw in conn.execute('SELECT * FROM ledger_entries ORDER BY transaction_id,line_no'):
        row = dict(zip(columns, raw))
        postings.setdefault(row['transaction_id'], []).append(PostingLine(
            account_id=row['account_id'], asset_id=row['asset_id'],
            quantity=from_e6(row['quantity_e6']), unit_price=from_e6(row['unit_price_e6']),
            fx_rate=from_e6(row['fx_rate_e6']), amount=from_e6(row['amount_e6']),
            amount_base=from_e6(row['amount_base_e6']), effect=Effect(row['effect']),
            category_id=row['category_id'], owner_id=row['owner_id'], is_cash=cash_assets[row['asset_id']]))
    for transaction_id, lines in postings.items():
        try:
            validate_posting(lines)
        except ValidationError as exc:
            raise ValueError(f'Transaction {transaction_id}: {exc.message}') from None
    # The rules manual entry keeps (audit 2026-10-26): nothing dated after today, no holding below zero units.
    if conn.execute("SELECT 1 FROM transactions WHERE date > ? LIMIT 1", (today().isoformat(),)).fetchone():
        raise ValueError('A transaction is dated in the future. Record transactions on or after the day they happen.')
    if conn.execute(
            "SELECT 1 FROM (SELECT le.asset_id, SUM(le.quantity_e6) OVER (PARTITION BY le.account_id, le.asset_id "
            "ORDER BY le.date, t.id, le.line_no) AS q FROM ledger_entries le JOIN transactions t "
            "ON t.id=le.transaction_id WHERE t.status='POSTED') x JOIN financial_assets f ON f.id=x.asset_id "
            "WHERE f.is_cash=0 AND x.q < 0 LIMIT 1").fetchone():
        raise ValueError('An account would hold less than zero units of an investment. Check its buys and sells.')
    if conn.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
        raise ValueError('The workbook does not form a valid financial database.')



def _validate_context(c, sheets, tables):
    records = {name: [dict(zip(columns, row)) for row in rows] for name, (columns, rows) in tables.items()}
    lookup = {name: {row.get('id'): row for row in rows} for name, rows in records.items()}

    def levels(category_id):
        path, seen = [], set()
        while category_id in lookup['categories'] and category_id not in seen:
            seen.add(category_id)
            cat = lookup['categories'][category_id]
            if cat.get('parent_id') is not None:
                path.insert(0, cat['name'])
            category_id = cat.get('parent_id')
        return (path + ['', '', ''])[:3]

    for sheet, rows in sheets.items():
        if sheet == 'Read me':
            continue
        name = next(name for name in tables if name[:31] == sheet)
        headings = rows[0]
        relations = readable_relations(c, name)
        for raw, record in zip(rows[1:], records[name]):
            expected = {key.removesuffix('_id').replace('_', ' ').title():
                        lookup.get(target, {}).get(record.get(key), {}).get(label, '')
                        for key, (target, label) in relations.items()}
            if name == 'categories':
                expected.update(zip(('Category L1', 'Category L2', 'Category L3'), levels(record['id'])))
            if name == 'ledger_entries':
                txn = lookup['transactions'].get(record.get('transaction_id'), {})
                account = lookup['accounts'].get(record.get('account_id'), {})
                asset = lookup['financial_assets'].get(record.get('asset_id'), {})
                expected.update(dict(zip(('Transaction ID', 'Transaction reference', 'Account', 'Date', 'Counterparty',
                    'Currency', 'Total in currency', 'FX rate', 'Total in default currency', 'Category L1', 'Category L2'),
                    (record.get('transaction_id'), txn.get('ref', ''), account.get('name', ''), record.get('date'),
                     txn.get('counterparty', ''), asset.get('currency', ''), from_e6(record['amount_e6']),
                     from_e6(record['fx_rate_e6']), from_e6(record['amount_base_e6']), *levels(record.get('category_id'))[:2]))))
            for heading, value in expected.items():
                if heading not in headings:
                    continue
                index = headings.index(heading)
                actual = raw[index] if index < len(raw) else None
                if isinstance(value, (int, Decimal)):
                    try:
                        matches = Decimal(actual) == value
                    except (InvalidOperation, TypeError):
                        matches = False
                else:
                    matches = str(actual or '') == str(value or '')
                if not matches:
                    raise ValueError(f'{sheet}: {heading} differs from its mapping column. Update the readable and mapping columns together.')

def prepare_import(c, data):
    """Validate in an isolated in-memory copy; the live profile is never changed by preview."""
    _unused(c)
    sheets, schema = read_workbook(data), _schema(c)
    mapping = {name[:31]: name for name in schema}
    tables, problems = {}, []
    for sheet, rows in sheets.items():
        if sheet == 'Read me':
            continue
        if sheet not in mapping:
            problems.append(f'Sheet "{sheet}" is not one of Lightning\'s sheets. Use the complete template and keep its sheet names.')
            continue
        name = mapping[sheet]
        if not rows:
            problems.append(f'Sheet "{sheet}" has no heading row. Keep the column headings, even when the sheet is empty.')
            continue
        headers = rows[0]
        if any(h is None or not isinstance(h, str) for h in headers) or len(set(headers)) != len(headers):
            problems.append(f'Sheet "{sheet}": every column heading must be filled in and different from the others.')
            continue
        fields = {f['name'].removesuffix('_e6'): f for f in schema[name]}
        display = {key.removesuffix('_id').replace('_', ' ').title() for key in fields if key in readable_relations(c, name)}
        if name == 'ledger_entries':
            display |= {'Transaction ID', 'Transaction reference', 'Account', 'Date', 'Counterparty', 'Currency',
                        'Total in currency', 'FX rate', 'Total in default currency', 'Category L1', 'Category L2'}
        if name == 'categories':
            display |= {'Category L1', 'Category L2', 'Category L3'}
        unknown = [h for h in headers if h not in fields and h not in display]
        if unknown:
            problems.append(f'Sheet "{sheet}": column "{unknown[0]}" is not one of the template\'s columns'
                            + (f' (and {len(unknown) - 1} more)' if len(unknown) > 1 else '') + '. Use the template headings unchanged.')
            continue
        chosen = [h for h in headers if h in fields]
        missing = [f['name'] for f in schema[name] if (f['pk'] or (f['notnull'] and f['dflt_value'] is None)) and f['name'].removesuffix('_e6') not in chosen]
        if missing:
            problems.append(f'Sheet "{sheet}" is missing the column{"s" if len(missing) > 1 else ""} {", ".join(chr(34) + m + chr(34) for m in missing)}. Add back from the template.')
            continue
        records = []
        key_columns = [h for h in chosen if fields[h]['pk'] and sum(f['pk'] > 0 for f in schema[name]) == 1]
        seen_keys = {}
        for number, row in enumerate(rows[1:], 2):
            if len(row) > len(headers):
                problems.append(f'Sheet "{sheet}", row {number}: there are more values than column headings.')
                continue
            row = row + [None] * (len(headers) - len(row))
            record, bad = [], False
            for h in chosen:
                field = fields[h]
                try:
                    value = _convert(row[headers.index(h)], field, name)
                except ValueError as exc:
                    problems.append(f'Sheet "{sheet}", row {number}, column "{h}": {exc}')
                    bad = True
                    value = None
                else:
                    if value is None and field['notnull'] and not field['pk']:
                        problems.append(f'Sheet "{sheet}", row {number}, column "{h}": this cannot be empty. Fill it in.')
                        bad = True
                record.append(value)
            if bad:
                continue
            record = tuple(record)
            for h in key_columns:
                value = record[chosen.index(h)]
                if value is not None and (h, value) in seen_keys:
                    problems.append(f'Sheet "{sheet}", row {number}, column "{h}": {value} is already used in row {seen_keys[(h, value)]}. Each row needs its own.')
                    bad = True
                elif value is not None:
                    seen_keys[(h, value)] = number
            if name == 'settings' and not _setting_allowed(str(record[chosen.index('key')])):
                problems.append(f'Sheet "{sheet}", row {number}: the setting "{record[chosen.index("key")]}" is not one Lightning can import.')
                bad = True
            if not bad:
                records.append(record)
        tables[name] = ([fields[h]['name'] for h in chosen], records)
    if problems:
        raise WorkbookProblems(problems)
    missing = set(schema) - set(tables)
    if missing:
        raise WorkbookProblems([f'Sheet "{_sheet_of(name)}" is missing. Keep every sheet of the template, even the empty ones.' for name in sorted(missing)])
    _validate_context(c, sheets, tables)
    clone = c.db.driver.connect(':memory:', isolation_level=None)
    try:
        if c.db.encrypted:
            # SQLCipher backups require an encrypted destination as well; this key is ephemeral.
            import secrets
            clone.execute("PRAGMA key = \"x'" + secrets.token_hex(32) + "'\"")
        c.db.conn.backup(clone)
        clone.execute('PRAGMA foreign_keys=ON')
        clone.execute('BEGIN')
        _load(clone, tables, schema)
        clone.execute('ROLLBACK')
    except c.db.driver.DatabaseError as exc:
        raise ValueError(_plain_database_error(str(exc))) from None
    finally:
        clone.close()
    return tables


def confirm_import(c, data):
    tables = prepare_import(c, data)
    with c.db.transaction():
        _unused(c)
        _load(c.db.conn, tables, _schema(c))
    c.refresh_profile_currency()
    return sum(len(rows) for _, rows in tables.values())


SETUP_PROMPT = '''Prepare a comprehensive Lightning onboarding workbook from my financial records. Start with the downloaded complete Lightning template and retain every sheet and lower-case mapping heading, including empty sheets. Use accounts, asset_classes, financial_assets, categories, counterparties, transactions and ledger_entries for their corresponding records; preserve plans, holdings, ownership and review tables when present. Readable columns are context; lower-case schema columns at the tail are authoritative for import, so update both consistently. Each id must be unique within its sheet; every *_id must reference the matching record. Preserve seeded system records and category codes from the template. Category L1 and L2 are separate names; categories.parent_id stores the tree. Transaction references must be unique. A transaction may have multiple ledger lines and each needs a unique line_no; transfers must retain both sides. Amounts, quantity, unit_price and fx_rate are decimal values with at most six places, never stored millionths. Keep amount signs and currencies; amount_base is the amount in the default currency using fx_rate. Dates must be real yyyy-mm-dd dates. Keep all required timestamps, enum values and fields from the template. Do not invent opening balances, FX rates, category mappings or holdings. Ask me about ambiguous or missing information. Return an .xlsx workbook with plain values, no formulas or external links, then list every record you could not place so nothing is dropped silently. I will review the preview and import it into a new empty Lightning profile; this does not merge into an existing profile.'''
