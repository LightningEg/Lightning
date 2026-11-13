---
title: Pair a PC with the phone in seconds: find it, then type two digits
type: feature
pillar: everywhere
size: L
model: opus
status: ready
created: 2026-11-12
by: Claude Opus 5.5
github: 615
---

# Pair a PC with the phone in seconds: find it, then type two digits

Pairing took the owner about five minutes (2026-11-12): the PC asks for the phone's address (`192.168.1.20:47513`) and a
12-character code. The Local pairing decision (2026-10-23, `ai/PROJECT_OVERVIEW.md`) already says "no typed address",
but "Connect with an address and code" (`profiles.html` mode `connect`, `phone/devices.html`) is still the path people take.

**Owner decision (2026-11-12):** the PC finds the phone on the same Wi-Fi by itself; the person types only **two
digits** shown on the phone. The address and code stay as a hidden fallback for networks that block discovery.

**Security note for the builder:** two digits are 1 in 100 per guess. They may only confirm a key exchange that is
already authenticated (the digits come from both sides' keys, as `check_digits` does now), with a small attempt budget
per offer, the short offer lifetime, the profile password proof and the home's confirmation of the named device all
kept. If that cannot hold, ask the owner before shipping.

## 4N1 Discovery is the first way · M
"Pair a PC" on the phone opens pairing and is found by "Find your phone or PC" on the PC with no other step; the PC
shows the phone by name. Say plainly when the network blocks discovery and offer the fallback.

## 4N2 Two typed digits · M
Replace the three six-digit choices and the 12-character code with two digits typed on the PC, derived from the
exchange; three wrong tries close the offer. Update `lightning/sync/journal/pairing.py` and its tests.

## 4N3 The fallback is short · S
The fallback address is pre-filled from the PC's own network (only the last part to type) and the code is the same
two digits plus nothing else where the protocol allows.

**Done when:** on a home Wi-Fi a PC pairs with the phone in under 30 seconds with two digits typed, tested on a real
phone and PC (launch checklist #579).
