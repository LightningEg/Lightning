# Non-Functional Requirements (as built)

**Verified** = evidence found in code/tests. **Target** = proposed, not a guarantee. No performance,
availability or scale number below is measured unless it says so.

| ID | Attribute | Requirement | Evidence (current) | Gap / risk | Recommendation | Pri |
|---|---|---|---|---|---|---|
| NFR-001 | Privacy | Data never leaves the device unless the user pairs devices or enables relay | Loopback bind (`runtime/app.py`, `Host`); profiles in Documents/Lightning (**Verified**) | Optional cloud relay and price fetch do use the network | Network table published in DECISIONS (D-006) | Must |
| NFR-002 | Security | Encrypted at rest | SQLCipher + Argon2id/AES-GCM wrapped key (**Verified**, `security/keys.py`) | Freed memory not wiped (owner decision); no malware protection | Keep documented in-app | Must |
| NFR-003 | Security | Brute-force slowing | 5 free tries then 1/5/15/60-min waits (**Verified**) | Offline guessing possible if `keys.json` copied; Argon2 slows it | None needed now | Must |
| NFR-004 | Security | Stale tab cannot write into another profile | Session-token check in `SessionGate` (**Verified**) | — | — | Must |
| NFR-005 | Reliability | No lost writes on failure | Atomic transactions, savepoints, FULL-synchronous journal store (**Verified**) | Power-loss during restore relies on OS flush semantics; native acceptance still held (2A, 4A) | Finish drills before claiming | Must |
| NFR-006 | Data integrity | Exact money | Scaled integers, overflow checks, two documented roundings (**Verified**) | Two rounding modes are easy to confuse | Keep tests on both | Must |
| NFR-007 | Backup/recovery | Verified encrypted backups | Daily backup, kept 30, reopened to verify; pre-upgrade backup (**Verified**) | Cross-PC sync folders unsupported | Warn in UI | Must |
| NFR-008 | Performance | Pages fast on phone | `perf-check` skill, per-request memo, static assets bypass the gate (**Verified** mechanism) | **No stated budget or benchmark in the repo** | Targets set in D-007; measure before quoting | Should |
| NFR-009 | Scalability | Single user, one ledger | By design | Behaviour at e.g. 100k+ ledger lines **Unknown** | Add a large-profile perf test | Could |
| NFR-010 | Availability | Works offline | Local-first (**Verified**) | Price/FX freshness needs network | Show staleness (already: 10-day stale rule) | Should |
| NFR-011 | Maintainability | Layer rules enforced | import-linter contract + test (**Verified**) | Large files in `ui/`, `sync/` | Split as touched | Should |
| NFR-012 | Testability | Broad automated tests | 271 test files, ≈2,170 functions; Mohab year test (**Verified**) | Windows/Android evidence is manual or by-hand CI | — | Must |
| NFR-013 | Usability | Answer first; few clicks; plain words | Guideline A16 checklist, tests (`test_brand_audit.py`) (**Verified**) | Owner acceptance checks held (Overview §9) | Run end-to-end checks | Must |
| NFR-014 | Accessibility | — | **Unknown**: no dedicated accessibility test found | Contrast mentioned for website only | Add an audit item | Should |
| NFR-015 | Compatibility | Windows (WebView2), Android, Linux browser | Builds and probes in workflows (**Verified**) | Windows unsigned (SmartScreen warnings) | Code-signing (owner) | Should |
| NFR-016 | I18n | English + Egyptian Arabic, RTL, digit handling | `test_arabic_*.py` (**Verified**) | Mixed strings can slip; `arabic-check` skill is manual | Run before releases | Must |
| NFR-017 | Observability | Diagnose problems | `audit_log`, UI status lines (**Verified**) | Only 3 `logging` uses in `lightning/` | Add structured local log (no data) | Should |
| NFR-018 | Portability | Move a profile | Backup/restore files | Restore only into same-named profile | — | Could |
| NFR-019 | Compliance | — | None claimed. Zakat is an estimate; CD interest is an estimate | Legal/regulatory status **Unknown** (see D-008) | Labelled as estimates (D-008) | Could |
| NFR-020 | Supply chain | Reproducible, vetted dependencies | Hash-pinned locks, CodeQL, fork-safe PR checks (**Verified**) | Dependency refresh PR #122 blocked on native wheels (1H) | Finish 1H | Should |
