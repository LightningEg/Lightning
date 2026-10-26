"""Bounded, lossless onboarding of comprehensive Lightning workbooks into unused profiles."""
from __future__ import annotations

from datetime import date
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
                            value = ''.join(cell.find(NS + 'is').itertext())
                        elif kind == 's':

                            try:
                                value = strings[int(value)]
                            except (ValueError, IndexError):
                                raise ValueError('Invalid shared-string reference.') from None
                        elif kind in ('e', 'str'):
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


def _convert(value, field, table):
    name = field['name']
    if value is None:
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
            raise ValueError(f'{table}.{name}: use a finite number with at most six decimal places.') from None
    if value and (name == 'date' or name.endswith('_date') or name in ('date_from', 'date_to', 'first_date')):
        try:
            if date.fromisoformat(str(value)).isoformat() != value:
                raise ValueError()
        except ValueError:
            raise ValueError(f'{table}.{name}: use a real date in yyyy-mm-dd format.') from None
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
    if conn.execute('PRAGMA foreign_key_check').fetchone():
        raise ValueError('The workbook contains a missing reference. Keep every referenced account, asset, category and transaction.')
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
    tables = {}
    for sheet, rows in sheets.items():
        if sheet == 'Read me':
            continue
        if sheet not in mapping:
            raise ValueError(f'Unsupported sheet: {sheet}. Use the complete Lightning template; no records were imported.')
        name = mapping[sheet]
        if not rows:
            raise ValueError(f'{sheet}: keep the column headings, even when the sheet is empty.')
        headers = rows[0]
        if any(h is None or not isinstance(h, str) for h in headers) or len(set(headers)) != len(headers):
            raise ValueError(f'{sheet}: headings must be nonempty and unique.')
        fields = {f['name'].removesuffix('_e6'): f for f in schema[name]}
        display = {key.removesuffix('_id').replace('_', ' ').title() for key in fields if key in readable_relations(c, name)}
        if name == 'ledger_entries':
            display |= {'Transaction ID', 'Transaction reference', 'Account', 'Date', 'Counterparty', 'Currency',
                        'Total in currency', 'FX rate', 'Total in default currency', 'Category L1', 'Category L2'}
        if name == 'categories':
            display |= {'Category L1', 'Category L2', 'Category L3'}
        if any(h not in fields and h not in display for h in headers):
            raise ValueError(f'{sheet}: unsupported column. Use the template headings unchanged.')
        chosen = [h for h in headers if h in fields]
        missing = [f['name'] for f in schema[name] if (f['pk'] or (f['notnull'] and f['dflt_value'] is None)) and f['name'].removesuffix('_e6') not in chosen]
        if missing:
            raise ValueError(f'{sheet}: required mapping columns are missing: {", ".join(missing)}.')
        records = []
        for number, row in enumerate(rows[1:], 2):
            if len(row) > len(headers):
                raise ValueError(f'{sheet} row {number}: more values than headings.')
            row = row + [None] * (len(headers) - len(row))
            record = tuple(_convert(row[headers.index(h)], fields[h], name) for h in chosen)
            if name == 'settings' and not _setting_allowed(str(record[chosen.index('key')])):
                raise ValueError('The workbook contains an unsupported runtime setting.')
            records.append(record)
        tables[name] = ([fields[h]['name'] for h in chosen], records)
    missing = set(schema) - set(tables)
    if missing:
        raise ValueError('This is not a complete workbook. Missing sheets: ' + ', '.join(sorted(missing)) + '.')
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
        raise ValueError('Workbook data violates a required type, unique key or financial constraint: ' + str(exc)) from None
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


SETUP_PROMPT = '''Prepare a comprehensive Lightning onboarding workbook from my financial records. Start with the downloaded complete Lightning template and retain every sheet and lower-case mapping heading, including empty sheets. Use accounts, asset_classes, financial_assets, categories, counterparties, transactions and ledger_entries for their corresponding records; preserve plans, holdings, ownership and review tables when present. Readable columns are context; lower-case schema columns at the tail are authoritative for import, so update both consistently. Each id must be unique within its sheet; every *_id must reference the matching record. Preserve seeded system records and category codes from the template. Category L1 and L2 are separate names; categories.parent_id stores the tree. Transaction references must be unique. A transaction may have multiple ledger lines and each needs a unique line_no; transfers must retain both sides. Amounts, quantity, unit_price and fx_rate are decimal values with at most six places, never stored millionths. Keep amount signs and currencies; amount_base is the amount in the default currency using fx_rate. Dates must be real yyyy-mm-dd dates. Keep all required timestamps, enum values and fields from the template. Do not invent opening balances, FX rates, category mappings or holdings. Ask me about ambiguous or missing information. Return an .xlsx workbook with plain values, no formulas or external links. I will review the preview and import it into a new empty Lightning profile; this does not merge into an existing profile.'''
