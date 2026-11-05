---
title: Turn bank descriptions into payees, transfers and categories
type: polish
look: technical
pillar: capture
size: L
status: ready
created: 2026-11-05
by: Claude Opus 5.5
---

## Report
With a real-looking CIB statement (Description column only), the review is mostly typing. From
[the report](../../reports/2026-11-05-import-scenarios/report.md) (F10-F13):
- Description is mapped to **Notes**, not Counterparty, so every row is "No counterparty" and the statement's 46 rows show
  as 46 groups named "No counterparty".
- When Description is mapped to Counterparty, `POS PURCHASE CARREFOUR MAADI` is not matched to the saved **Carrefour**;
  only `FAWRY WE INTERNET` got a suggestion. Rows of one shop in two branches fall into two groups.
- `ATM WITHDRAWAL 0012 NASR CITY` is not offered as a transfer to **Cash wallet**; `INSTAPAY TRF TO VODAFONE CASH` is not
  offered as a transfer to **Vodafone Cash**; `سحب نقدي ATM` neither.
- No category is suggested for a new name, even for an obvious shop.

## 7AC1 Clean the name · M
A list of bank prefixes and suffixes (POS PURCHASE, PURCHASE, INSTAPAY TRF TO/FROM, IPN, FAWRY, ATM WITHDRAWAL, card
masks, branch numbers, city names; Arabic: مشتريات نقاط البيع, تحويل وارد, تحويل صادر, سحب نقدي) is removed before
matching and grouping. The original text stays in Notes. With no Counterparty column, a Description column feeds both.

## 7AC2 Find saved names inside the text · M
A saved counterparty or alias whose name appears as whole words in the cleaned text is suggested (Carrefour inside
"CARREFOUR MAADI"). Grouping uses the matched name, so one shop is one group.

## 7AC3 Cash and wallet moves · M
ATM / cash withdrawal suggests a transfer to the person's only cash account; InstaPay, Vodafone Cash, Etisalat Cash,
Fawry wallet names suggest the matching own account. Still a suggestion the person confirms.

## 7AC4 A first category · S
A new name gets its counterparty's usual category, else a small keyword list (supermarkets, fuel, ride-hailing, telecom,
utilities, pharmacies) shown as a suggestion, never posted silently.
