"""Yahoo's chart feed, for history only: a whole series of daily closes per instrument in one request.

Yahoo's closes are adjusted for later splits (and EGX bonus shares), but a past holding must be valued
at the price it actually traded at, so each close is multiplied back by the splits that came after it."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from urllib.parse import quote
from zoneinfo import ZoneInfo

from ..model import Quote, SourceError

CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
# Yahoo's exchange suffixes for the Gulf and European boards the app fetches itself (owner 2026-11-04). The UAE and
# Bahrain are keyed AE: and BH:, and one country cannot tell Dubai from Abu Dhabi, so their suffix comes from the venue
# (VENUE_SUFFIX). A venue is listed only once Yahoo's answer names it (IT-6F2, 2026-11-10: EMAAR.AE is DFM in AED;
# ALDAR.AD, ALDAR.AE and BATELCO.BH were not found); the others' latest closes still come from the board.
SUFFIX = {"SA": ".SR", "QA": ".QA", "KW": ".KW", "GB": ".L", "DE": ".DE", "FR": ".PA", "NL": ".AS", "BE": ".BR",
          "PT": ".LS", "ES": ".MC", "IT": ".MI", "CH": ".SW", "SE": ".ST", "DK": ".CO", "FI": ".HE", "IS": ".IC"}
VENUE_SUFFIX = {"XDFM": ".AE"}
# A close is dated by its market's own day.
ZONES = {"US": "America/New_York", "XAU/USD": "America/New_York", "XAG/USD": "America/New_York",
         "SA": "Asia/Riyadh", "QA": "Asia/Qatar", "KW": "Asia/Kuwait", "GB": "Europe/London", "DE": "Europe/Berlin",
         "FR": "Europe/Paris", "NL": "Europe/Amsterdam", "BE": "Europe/Brussels", "PT": "Europe/Lisbon",
         "ES": "Europe/Madrid", "IT": "Europe/Rome", "CH": "Europe/Zurich", "SE": "Europe/Stockholm",
         "DK": "Europe/Copenhagen", "FI": "Europe/Helsinki", "IS": "Atlantic/Reykjavik",
         "AE": "Asia/Dubai", "BH": "Asia/Bahrain"}
# A series quoted in a currency's minor unit (pence, fils) is brought to the ISO unit, as the boards are.
MINOR = {"GBp": Decimal(100), "GBX": Decimal(100), "KWF": Decimal(1000), "ZAc": Decimal(100), "ILA": Decimal(100)}


def symbol_for(key: str, mic: str = "") -> str | None:
    """EG:COMI -> COMI.CA, US:BRK.B -> BRK-B, USD/EGP -> EGP=X, XAU/USD -> GC=F (gold, an ounce); others have none.
    A venue in VENUE_SUFFIX names its own: AE:EMAAR on XDFM -> EMAAR.AE (a second listing's -MIC ending is dropped)."""
    if mic in VENUE_SUFFIX and ":" in key:
        ticker = key.partition(":")[2].removesuffix(f"-{mic}")
        return ticker.replace("_", "-") + VENUE_SUFFIX[mic] if ticker else None
    if key.startswith("EG:") and ":FUND:" not in key:
        return key[3:] + ".CA"
    if key.startswith("US:"):
        return key[3:].replace(".", "-")
    country, _, ticker = key.partition(":")
    if country in SUFFIX and ticker and "-X" not in ticker:  # SA:2222 -> 2222.SR, SE:VOLV_B -> VOLV-B.ST
        return ticker.replace("_", "-").replace(".", "-") + SUFFIX[country]
    if key.endswith("/EGP") and key[:3].isalpha() and key[:3] != "EGP":
        return "EGP=X" if key[:3] == "USD" else f"{key[:3]}EGP=X"  # EUR/EGP -> EUREGP=X
    return {"XAU/USD": "GC=F", "XAG/USD": "SI=F"}.get(key)


def parse(data: dict, key: str, zone: str = "Africa/Cairo") -> list[Quote]:
    try:
        result = data["chart"]["result"][0]
        stamps = result.get("timestamp") or []
        per_unit = MINOR.get(str((result.get("meta") or {}).get("currency") or ""), Decimal(1))
        closes = result["indicators"]["quote"][0].get("close") or []
        splits = (result.get("events") or {}).get("splits") or {}
    except (KeyError, IndexError, TypeError):
        raise SourceError(f"Yahoo's chart answer for {key} has no price series") from None
    events = []
    for split in splits.values():
        try:
            events.append((int(split["date"]), Decimal(str(split["numerator"])) / Decimal(str(split["denominator"]))))
        except (KeyError, ValueError, InvalidOperation, ZeroDivisionError):
            continue
    tz = ZoneInfo(zone)
    quotes: dict[str, Quote] = {}
    for stamp, value in zip(stamps, closes):
        if value is None:
            continue
        try:
            close = Decimal(str(value))
        except InvalidOperation:
            continue
        for when, ratio in events:  # undo every split that happened after this day
            if when > stamp:
                close *= ratio
        close /= per_unit
        if close.is_finite() and close > 0:
            day = datetime.fromtimestamp(int(stamp), tz).date().isoformat()
            quotes[day] = Quote(key, day, close.quantize(Decimal("0.000001")), "yahoo-history")
    return [quotes[d] for d in sorted(quotes)]


def fetch_history(session, key: str, since: str = "max", mic: str = "") -> list[Quote]:
    symbol = symbol_for(key, mic)
    if not symbol:
        return []
    data = session.get_json(CHART.format(symbol=quote(symbol, safe="")),
                            {"range": since, "interval": "1d", "events": "split"})
    zone = ZONES.get(key.partition(":")[0], "Africa/Cairo")
    return parse(data, key, zone)
