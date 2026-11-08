"""Shared, bounded resource limits used across application layers."""

MAX_CSV_IMPORT_BYTES = 5_000_000
MAX_STATEMENT_DOCUMENT_BYTES = 8 * 1024 * 1024
IMPORT_REQUEST_ENVELOPE_BYTES = 64 * 1024
MAX_STATEMENT_UPLOAD_REQUEST_BYTES = MAX_STATEMENT_DOCUMENT_BYTES + IMPORT_REQUEST_ENVELOPE_BYTES
MAX_CSV_UPLOAD_REQUEST_BYTES = MAX_CSV_IMPORT_BYTES + IMPORT_REQUEST_ENVELOPE_BYTES
MAX_CSV_MAPPING_REQUEST_BYTES = ((MAX_CSV_IMPORT_BYTES + 2) // 3) * 4 + IMPORT_REQUEST_ENVELOPE_BYTES
# Confirmation posts expand a CSV into editable form controls. Twelve fields
# per row and 600,000 fields cover the current review schema for about 50,000
# rows; 32 MiB allows those names/values and URL-encoding overhead while keeping
# Guard's in-memory body and the parser's in-memory form explicitly bounded.
# Larger reviews remain intentionally capped and should be split into files.
MAX_IMPORT_REVIEW_REQUEST_BYTES = 32 * 1024 * 1024
MAX_IMPORT_REVIEW_FIELDS = 600_000

# A raw workbook bundle is carried to worksheet choice as base64 multipart text.
MAX_WORKSHEET_REQUEST_BYTES = ((MAX_STATEMENT_DOCUMENT_BYTES + 2) // 3) * 4 + IMPORT_REQUEST_ENVELOPE_BYTES
MAX_STATEMENT_UPLOAD_FILES = 20
