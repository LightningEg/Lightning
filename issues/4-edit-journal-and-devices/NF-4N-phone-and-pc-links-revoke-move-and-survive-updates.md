---
title: Phone and PC links: revoke from the PC, move a profile from phone to PC, survive updates, and work across versions
type: feature
pillar: everywhere
size: L
model: opus
status: new
created: 2026-11-12
by: owner
---

## Report
Owner, 2026-11-12, four asks about devices (see `NF-4B-multiple-devices.md`):
1. The PC needs a way to revoke a phone's access.
2. A profile can go from PC to phone today; it also needs to go from phone to PC (the road is one-way).
3. Connections between PCs and phones must survive any app update.
4. Different app versions must be able to connect; do not require the same version.

Not solved in the session that heard this: it touches the sync protocol and keys.

## Fix
Split it (skill `split-large-item`): revoke (a PC-side device list action and a key retirement the phone sees), reverse move (a phone-side export the PC imports and verifies), connection storage that no migration drops, and a protocol version range with a capability check instead of equality. Each step has a test that upgrades a real older pairing.
