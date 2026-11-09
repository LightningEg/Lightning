# Audit 16: the investment workflow beyond stocks - certificates, gold, property and the rest

Date: 2026-11-09 · Author/reviewer: Claude
Repository: app · Reviewed commit: 90f01900587841fa8fdea859fbf9f2cc8314140a
Code: r30 · App version: 2.1.2

## Assessment

The owner's read is right. Buying, selling and following a stock or fund works end to end. Everything else is stored
as if it were a stock (one "unit" at a "price") and reached through a different door for each kind, so the person has
to know Lightning's data model before they can record what they own. The backend is stricter than the screens: it
refuses the wrong combinations, but the forms offer them first.

Three things matter most, in this order:

1. **A certificate you already own cannot be recorded** (C1). This is the first thing a salaried Egyptian user will try.
2. **There is no single place to add an investment** (E1), and each kind's own door is hard to find.
3. **A flat's gain never reaches Investments** (P1), and a second gold bar of the same karat is refused (G1).

## Scope and method

Question: walking each investment kind as a user, what is awkward on screen and what is wrong or missing behind it?
Kinds walked: stock or fund (baseline), certificate of deposit, gold by the gram, gold jewellery, property as an "Other"
account, property as an *Other Investments* holding. Demo household (`python -m lightning --demo`, dummy data, date
2026-11-09), PC layout at 1280 px, driven by Playwright through the real forms; then the service code behind each
refusal or figure was read. Scripts: [flows/](evidence/flows/) (start the demo, then `node j1.js`, `j3.js` ... `j7.js`
in order from that folder; they change the demo data, which is rebuilt on every start).

## Findings

Severity: high = wrong money or a job that cannot be done; medium = a wrong or misleading screen; low = polish.

### Entry: finding the door

| ID | Severity | Observation and expected behavior | Follow-up |
| --- | --- | --- | --- |
| E1 | high | Investments has no Add button. A stock is added on the broker's account page, a certificate on a CD portfolio's page (after creating that account under Transactions › Accounts), jewellery inside a physical-asset account, a flat as an "Other" account. Expected: one *Add investment* that asks what it is. | IV-12K |
| E2 | medium | `/investments/new` lists things it then refuses: the certificate ("Certificates must be held in a bank-specific CD portfolio."), the gold price references ("only supplies a price"), jewellery items. | IV-12K |
| E3 | medium | *Cash account* (where the money came from) offers CD portfolios, the gam'eya, the broker and the gold account. | IV-12K |
| E4 | low | New investment's types are Silver, Stocks, five Funds, Gold, Other Investments: no certificate, no property, and nothing says where those live. | IV-12K |

### Certificates

| ID | Severity | Observation and expected behavior | Follow-up |
| --- | --- | --- | --- |
| C1 | high | A certificate bought before tracking began is refused: "CIB Payroll had 0.00 EGP of your cash on 2024-01-15; this purchase needs 50,000.00 EGP." Dated today instead, it takes the money from the bank now. There is no "I already own it". | NF-12I |
| C2 | medium | The certificate's holding page is the stock page: "Price 100,000", "1 certificate", "Unrealized gain 0.0%", "Average cost", a flat price chart, *Buy more* (opens the stock form that refuses it). No rate, next payout, unlock date or maturity. [Screenshot](evidence/certificate-holding-page.png). | IV-12J1 |
| C3 | medium | Monthly interest is forecast by day count (1,808.22, then 1,868.49) while the bank pays a fixed 1,833.33; matching copes with a 15% tolerance. | IV-12J2 |
| C4 | medium | A certificate paid at maturity (or compound) stays at its principal for its whole life; all its interest then appears as *Gain from sales* on one day. | IV-12J3 |
| C5 | medium | Nothing tells you a certificate matured or unlocked: no Needs you row, no reminder (only "interest expected tomorrow"). | IV-12J4 |
| C6 | low | Investments warns "These prices are old ... NBE 3-year certificate (2026-09-01)": the purchase date read as a stale price. | IV-12J4 |
| C7 | low | The certificates page opens with a wide table and a 12-field buy form always open; [at phone width](evidence/certificates-page.png) the PC template cuts the table after four columns (the phone app's own page was not checked, see limits). | IV-12J1 |
| C8 | low | Redemption is the whole certificate only; a variable rate is one number for the whole life. Banks allow part redemption and change variable rates. | IV-12J4 |

### Gold

| ID | Severity | Observation and expected behavior | Follow-up |
| --- | --- | --- | --- |
| G1 | high | A second gold investment of the same karat is refused: "GLD:24K already exists." on a Ticker field that says "For gold leave empty." | BT-12H |
| G2 | medium | Adding jewellery is two steps: an empty item ("0 pieces · No pieces held"), then a folded form for what you paid. [Screenshot](evidence/gold-account.png). | IV-12L |
| G3 | medium | A bar bought by the gram sits outside the table as one line ("Other tracked holdings") and is valued at what was paid (6,200 a gram) beside a 24K reference of 5,314; jewellery follows the reference. Same metal, two values. | IV-12L |
| G4 | low | "Gold price reference" is asked for though the karat decides it; 22K has none. | IV-12L |
| G5 | low | Labels: "piece · MANUAL reference", "Coin ·", "0.000 g", piastres on large figures; the page sits under Transactions. | IV-12L |
| G6 | low | Gold prices online are a world-price estimate; the shop price (with the local premium) must be typed. Already planned. | IT-6D |

### Property and other things you own

| ID | Severity | Observation and expected behavior | Follow-up |
| --- | --- | --- | --- |
| P1 | high | A flat worth 2,500,000, bought for 1,800,000, shows +700,000 on its own page but Cost 2,500,000 and gain "—" on Investments: the gain is in no total or return. [Flat](evidence/flat-account.png), [Investments](evidence/investments-after.png). | NF-12M1 |
| P2 | medium | A flat can also be an *Other Investments* holding, accepted only inside the stock broker (THNDR's balance became 3,021,108). | NF-12M1 |
| P3 | medium | No real-estate class: both flats fall under "Other Investments" (95.8%); they count in *Holdings after sale* as if sold today. | NF-12M1 |
| P4 | medium | The flat's page is a bank register: "Record your first Money out, Money in, or Transfer", bulk category edit, statement import. | NF-12M2 |
| P5 | high | No way to record a flat bought by instalments (down payment, years of payments, the part still owed). | NF-12M3 |
| P6 | medium | Rent received and maintenance cannot be tied to the property, so it has no yield or net return. | NF-12M4 |
| P7 | low | Kinds with no home at all: treasury bills, bonds, a share in a business, an insurance or pension plan. Owner decision (see below). | none yet |

### Figures

| ID | Severity | Observation and expected behavior | Follow-up |
| --- | --- | --- | --- |
| N1 | medium | *Money and value by class* counts a purchase as "Change in value": buying a 62,000 bar moved Gold from +5,535 to +67,535, while *What changed* above it kept +6,063. | IV-12N |
| N2 | low | A yearly rate is shown on 69 days ("+273.3 per year" for a gold pound); the certificate shows +3.7% with no yearly figure beside its 22%. | IV-12N |
| N3 | low | The donut folds a class into "Other" beside "Other Investments". | IV-12N |
| N4 | low | *Against the risk-free rate* on a certificate asks for "a T-bill or certificate rate". | IV-12J1 |

## What works

- Stocks and funds: search, buy, sell, dividend, split, return of capital, broker cash rule, holding page.
- The services refuse every wrong combination tried (certificate in a broker, price reference as a holding, purchase
  larger than the cash on that date, broker purchase without broker cash).
- Certificate interest matching to bank receipts, with *Match all suggested*.
- Jewellery valuation by weight and karat, with a manual override; an 18K price derived from 21K.
- The flat's own page: value now, "since you bought it", a link to the loan.

## Validation and limits

Browser evidence on the demo household only; the full test suite was not run because no code changed. Not checked:
the phone app's own pages (only `phone/investments/index.html` and `phone/deposits/` exist; the PC template at phone
width is not what the phone shows), Arabic, redeeming a certificate (the demo's is locked until 2027), selling
jewellery, foreign-currency certificates, shared ownership, zakat on these kinds, live price fetching.

## Owner decisions

- **Order to build** and **kinds with no home (P7)**: asked in the session's question dialog on 2026-11-09; the answer
  is recorded in the dated follow-ups below.

## Dated follow-ups

