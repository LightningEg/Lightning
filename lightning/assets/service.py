"""Public API of the assets module: asset classes, financial assets (cash and investments) and their prices."""

from __future__ import annotations

import re
from dataclasses import replace
from decimal import Decimal

from lightning.core.codes import slug, validate_asset_code
from lightning.core.dates import fmt_date, parse_date, today
from lightning.core.errors import ConflictError, NotFoundError, ValidationError
from lightning.core.memo import in_request, request_cached
from lightning.core.money import ZERO, check_places, to_decimal
from lightning.database.connection import Database

from .domain import INVESTMENT_KINDS, AssetClass, Exposure, FinancialAsset, Liquidity, Price, PriceSource
from .repository import AssetRepository

_US_VENUES = {"XNAS", "XNYS", "ARCX", "XASE", "BATS"}


def _venue(class_code: str, mic: str, isin: str) -> tuple[str | None, str | None, str | None]:
    """(mic, country, isin) for an investment, checked against ISO 10383, 3166 and 6166.

    A stock with no exchange given is an EGX listing (XCAI); a fund is Egyptian unless its ISIN says not."""
    from lightning.market.iso import VENUES, is_isin, is_mic
    mic = (mic or "").strip().upper()
    isin = (isin or "").strip().upper().replace(" ", "")
    if isin and not is_isin(isin):
        raise ValidationError("That ISIN does not pass its check digit. It has 12 characters, like EGS60121C018.", "isin")
    if mic and not is_mic(mic):
        raise ValidationError("An exchange code (MIC) has four letters or digits, like XCAI for EGX.", "mic")
    if class_code == "STOCK" and not mic:
        mic = "XCAI"
    country = VENUES.get(mic, ("", ""))[1] or (isin[:2] if isin else "") or ("EG" if class_code.startswith("FUND") else "")
    return mic or None, country or None, isin or None


def _market_key(ticker: str, mic: str | None, country: str | None) -> str | None:
    """The asset's instrument in the market file, when it is a listed security: EG:COMI, US:AAPL."""
    if mic == "XCAI":
        return f"EG:{ticker}"
    if mic in _US_VENUES:
        return f"US:{ticker}"
    return None


class AssetService:
    def __init__(self, db: Database, base_currency: str = "EGP"):
        self.db = db
        self.repo = AssetRepository(db)
        self.base_currency = base_currency

    # -- asset classes -----------------------------------------------------
    @request_cached
    def list_classes(self) -> list[AssetClass]:
        """Tree order: each parent followed by its children."""
        classes = self.repo.list_classes()
        by_parent: dict[int | None, list[AssetClass]] = {}
        for c in classes:
            by_parent.setdefault(c.parent_id, []).append(c)
        ordered: list[AssetClass] = []

        def walk(parent_id: int | None) -> None:
            for child in by_parent.get(parent_id, []):
                ordered.append(child)
                walk(child.id)

        walk(None)
        return ordered

    def get_class(self, class_id: int) -> AssetClass:
        found = (self._classes_by_id().get(class_id) if in_request() else self.repo.get_class(class_id))
        if not found:
            raise NotFoundError("Asset class not found.")
        return found

    def get_class_by_code(self, code: str) -> AssetClass:
        found = self.repo.get_class_by_code(code)
        if not found:
            raise NotFoundError(f"Asset class {code} not found.")
        return found

    def display_name(self, class_id: int) -> str:
        """Names only, for screens: 'Liquid Cash › Bank Balance'."""
        names, current = [], self.get_class(class_id)
        while True:
            names.append(current.name)
            if current.parent_id is None:
                break
            current = self.get_class(current.parent_id)
        return " › ".join(reversed(names))

    # -- financial assets --------------------------------------------------
    @request_cached
    def _classes_by_id(self) -> dict[int, AssetClass]:
        return {item.id: item for item in self.repo.list_classes()}

    @request_cached
    def list_assets(self) -> list[FinancialAsset]:
        return self.repo.list_assets()

    @request_cached
    def _assets_by_id(self) -> dict[int, FinancialAsset]:
        return {item.id: item for item in self.repo.list_assets()}

    def get_asset(self, asset_id: int) -> FinancialAsset:
        found = (self._assets_by_id().get(asset_id) if in_request() else self.repo.get_asset(asset_id))
        if not found:
            raise NotFoundError("Financial asset not found.")
        return found

    def get_asset_by_code(self, code: str) -> FinancialAsset:
        found = self.repo.get_asset_by_code(code)
        if not found:
            raise NotFoundError(f"Financial asset {code} not found.")
        return found

    def investment_preferences(self, asset_id: int) -> tuple[str | None, str | None]:
        """User-facing allocation bucket and horizon for an investment."""
        row = self.db.one(
            "SELECT allocation_bucket,investment_horizon FROM financial_assets WHERE id=?",
            (asset_id,),
        )
        if row is None:
            raise NotFoundError("Financial asset not found.")
        return row["allocation_bucket"], row["investment_horizon"]

    def all_investment_preferences(self) -> dict[int, dict[str, str | None]]:
        """Saved allocation and horizon labels for investment views."""
        return {row["id"]: {"allocation_bucket": row["allocation_bucket"],
                            "investment_horizon": row["investment_horizon"]}
                for row in self.db.all(
                    "SELECT id,allocation_bucket,investment_horizon FROM financial_assets"
                )}

    def set_investment_preferences(self, asset_id: int, bucket: str, horizon: str | None) -> None:
        self.get_asset(asset_id)
        self.db.execute(
            "UPDATE financial_assets SET allocation_bucket=?,investment_horizon=? WHERE id=?",
            (bucket, horizon, asset_id),
        )

    def cash_asset(self, currency: str) -> FinancialAsset:
        found = self.repo.get_cash_asset(currency)
        if not found:
            raise ValidationError(f"Currency {currency} is not set up.", "currency")
        return found

    def investments(self, active_only: bool = False) -> list[FinancialAsset]:
        return [a for a in self.repo.list_assets() if not a.is_cash and (a.active or not active_only)]

    def investment_classes(self) -> list[AssetClass]:
        """Asset classes you can create an investment in (Stocks, Funds…, Gold, Other)."""
        return [c for c in self.list_classes() if c.code in INVESTMENT_KINDS]

    # -- creating investments (M3) ----------------------------------------
    def create_investment(self, name: str, class_code: str, symbol: str = "", karat: object = None,
                          isin: str = "", notes: str = "", mic: str = "", currency: str = "") -> FinancialAsset:
        """A stock, fund, gold or other investment you can hold in an account.

        Code = <prefix>:<symbol>, e.g. STK:COMI, FND:AZ-GOLD, GLD:21K. Units and decimals follow the class.
        """
        name = (name or "").strip()
        if not name:
            raise ValidationError("Enter a name, e.g. Commercial International Bank.", "name")
        kind = INVESTMENT_KINDS.get((class_code or "").strip())
        if kind is None:
            raise ValidationError("Choose what kind of investment this is.", "class_code")
        purity = None
        if class_code == "GOLD":
            carat = to_decimal(karat or "24", "karat")
            if carat not in (Decimal(24), Decimal(22), Decimal(21), Decimal(18)):
                raise ValidationError("Gold karat must be 24, 22, 21 or 18.", "karat")
            purity = (carat / Decimal(24)).quantize(Decimal("0.000001"))
            symbol = symbol or f"{int(carat)}K"
        symbol = slug(symbol or name, 20) or ""
        if not symbol:
            raise ValidationError("Enter a short symbol in Latin letters, e.g. COMI.", "symbol")
        code = validate_asset_code(f"{kind.prefix}:{symbol}")
        venue, country, isin = _venue(class_code, mic, isin) if class_code != "GOLD" else (None, None, None)
        existing = self.repo.get_asset_by_code(code)
        if existing and venue and existing.mic and existing.mic != venue:
            # The same ticker on another exchange is another holding: its code carries the exchange (U9).
            code = validate_asset_code(f"{kind.prefix}:{symbol}-{venue}")
            existing = self.repo.get_asset_by_code(code)
        if existing:
            raise ConflictError(f"{code} already exists.", "symbol")
        # A listing is priced in its own trading currency (audit 2026-10-15): given by the catalogue or the person
        # (a USD line in London or on EGX, a dollar fund), else its exchange's (US shares in USD), else the profile's.
        from lightning.market.iso import RATED_CURRENCIES, is_currency, venue_currency
        currency = (currency or "").strip().upper()
        if currency == "GBX":
            raise ValidationError("Enter pence prices in pounds sterling: choose GBP.", "currency")
        if currency and (not is_currency(currency) or currency not in RATED_CURRENCIES | {self.base_currency}):
            raise ValidationError(f"{currency} has no exchange rate source; choose another currency.", "currency")
        currency = currency or venue_currency(venue) or self.base_currency
        if currency != self.base_currency:
            from lightning.database.currencies import CurrencyRegistry
            CurrencyRegistry(self.db).register(currency)
        asset = FinancialAsset(
            id=0, code=code, name=name, asset_class_id=self.get_class_by_code(class_code).id,
            currency=currency, unit=kind.unit, quantity_decimals=kind.quantity_decimals, is_cash=False,
            exposure=kind.exposure, liquidity=kind.liquidity, purity=purity, isin=isin,
            price_source=PriceSource.MANUAL, external_symbol=None, active=True, notes=(notes or "").strip(),
            mic=venue, country=country, market_key=_market_key(code.split(":", 1)[1], venue, country),
        )
        with self.db.transaction():
            new_id = self.repo.insert_asset(asset)
        return self.get_asset(new_id)

    def create_physical_item_asset(self, name: str) -> FinancialAsset:
        """Create the non-tickered, piece-count ledger asset behind one named physical item."""
        from lightning.assets.domain import Exposure, Liquidity, PriceSource

        base = slug(name, 14) or "ITEM"
        suffix = 1
        code = f"OTH:ITEM-{base}-{suffix}"
        while self.repo.get_asset_by_code(code):
            suffix += 1
            code = f"OTH:ITEM-{base}-{suffix}"
        asset = FinancialAsset(
            id=0, code=code, name=name.strip(), asset_class_id=self.get_class_by_code("GOLD").id,
            currency=self.base_currency, unit="piece", quantity_decimals=0, is_cash=False,
            exposure=Exposure.GOLD, liquidity=Liquidity.DAYS, purity=None, isin=None,
            price_source=PriceSource.MANUAL, external_symbol=None, active=True,
            notes="Physical item ledger asset",
        )
        with self.db.transaction():
            new_id = self.repo.insert_asset(asset)
        return self.get_asset(new_id)

    def create_certificate_asset(self, name: str) -> FinancialAsset:
        """Create a separate non-cash ledger asset for one bank certificate."""
        from lightning.assets.domain import Exposure, Liquidity, PriceSource

        name = (name or "").strip()
        if not name:
            raise ValidationError("Enter a certificate name.", "name")
        base = slug(name, 22) or "CERTIFICATE"
        serial = 1
        code = f"CD:{base}-{serial}"
        while self.repo.get_asset_by_code(code):
            serial += 1
            code = f"CD:{base}-{serial}"
        asset = FinancialAsset(
            id=0, code=code, name=name, asset_class_id=self.get_class_by_code("DEPOSIT.CD").id,
            currency=self.base_currency, unit="certificate", quantity_decimals=0, is_cash=False,
            exposure=Exposure.FIXED_INCOME, liquidity=Liquidity.LOCKED, purity=None, isin=None,
            price_source=PriceSource.NONE, external_symbol=None, active=True,
            notes="Certificate of deposit; interest is forecast only.",
        )
        with self.db.transaction():
            new_id = self.repo.insert_asset(asset)
        return self.get_asset(new_id)

    def update_investment(self, asset_id: int, name: str, class_code: str | None = None, isin: str = "",
                          notes: str = "", active: bool = True, ticker: str | None = None,
                          mic: str | None = None) -> FinancialAsset:
        """Edit an investment: name, class, ISIN, exchange, ticker, notes and whether it is still active.
        A new ticker renames its code (STK:OLD -> STK:NEW); history stays with the asset, which keeps its id."""
        asset = self.get_asset(asset_id)
        if asset.is_cash:
            raise ValidationError("Currencies cannot be edited here.")
        name = (name or "").strip()
        if not name:
            raise ValidationError("Enter a name.", "name")
        class_id = asset.asset_class_id
        exposure = asset.exposure
        if class_code:
            kind = INVESTMENT_KINDS.get(class_code)
            if kind is None:
                raise ValidationError("Choose what kind of investment this is.", "class_code")
            class_id, exposure = self.get_class_by_code(class_code).id, kind.exposure
        code_class = class_code or self.get_class(class_id).code
        if code_class == "GOLD":
            venue, country, clean_isin = asset.mic, asset.country, (isin or "").strip() or None
        else:
            venue, country, clean_isin = _venue(code_class, asset.mic or "" if mic is None else mic, isin)
        code = asset.code
        if ticker is not None and ticker.strip() and ticker.strip().upper() != asset.ticker:
            symbol = slug(ticker, 20) or ""
            if not symbol:
                raise ValidationError("Enter a short ticker in Latin letters, e.g. COMI.", "ticker")
            code = validate_asset_code(f"{asset.code.split(':', 1)[0]}:{symbol}")
            if self.repo.get_asset_by_code(code):
                raise ConflictError(f"{code} already exists.", "ticker")
        # A match to the market file stays unless the ticker or exchange changed under it.
        unchanged = code == asset.code and venue == asset.mic
        market_key = asset.market_key if unchanged and asset.market_key else _market_key(code.split(":", 1)[1], venue, country)
        updated = replace(asset, code=code, name=name, asset_class_id=class_id, exposure=exposure, isin=clean_isin,
                          notes=(notes or "").strip(), active=active, mic=venue, country=country, market_key=market_key)
        with self.db.transaction():
            self.repo.update_asset(updated)
        return self.get_asset(asset_id)

    def link_market(self, asset_id: int, key: str | None) -> None:
        """Remember which market-file instrument an asset is (EG:COMI, EG:FUND:4104)."""
        asset = self.get_asset(asset_id)
        if asset.market_key != key:
            with self.db.transaction():
                self.repo.update_asset(replace(asset, market_key=key))

    def link_fund(self, asset_id: int, page: str) -> None:
        """A fund's Mubasher page (or its number) says where its prices come from online; blank forgets it,
        so the next fetch matches the fund by name again."""
        page = (page or "").strip()
        found = re.search(r"/funds/(\d+)", page) or re.fullmatch(r"(\d+)", page)
        if page and not found:
            raise ValidationError("Paste the fund's page on Mubasher, e.g. english.mubasher.info/countries/eg/funds/4104, "
                                  "or its number.", "fund_page")
        self.link_market(asset_id, f"EG:FUND:{int(found.group(1))}" if found else None)

    # -- prices -------------------------------------------------------------
    def set_price(self, asset_id: int, date: str, price: object, source: str = "MANUAL") -> Price:
        """Record the price of one unit on a date (a manual price wins over automatic ones)."""
        asset = self.get_asset(asset_id)
        if asset.is_cash:
            raise ValidationError("Currencies do not need a price.")
        day = parse_date(date)
        if day > today():
            raise ValidationError("Prices cannot be dated in the future.", "date")
        value = check_places(to_decimal(price, "price"), 6, "price")
        if value <= ZERO:
            raise ValidationError(f"The price of {asset.name} must be greater than zero.", "price")
        with self.db.transaction():
            self.repo.upsert_price(asset.id, fmt_date(day), value, asset.currency, source)
        return Price(asset.id, fmt_date(day), value, asset.currency, source)

    def set_prices(self, date: str, prices: dict[int, object]) -> int:
        """Several prices for one date (the 'Update prices' page). Empty values are skipped."""
        count = 0
        with self.db.transaction():
            for asset_id, raw in prices.items():
                if str(raw or "").strip():
                    self.set_price(asset_id, date, raw)
                    count += 1
        return count

    def priced_on(self, asset_id: int, date: str) -> bool:
        """Whether any price, typed or filled, is saved for the asset on that exact day."""
        return self.repo.has_price(asset_id, fmt_date(parse_date(date)))

    def remove_price(self, asset_id: int, date: str, source: str = "MANUAL") -> None:
        with self.db.transaction():
            self.repo.delete_price(asset_id, fmt_date(parse_date(date)), source)

    def price_history(self, asset_id: int, limit: int = 50) -> list[Price]:
        return self.repo.prices(asset_id, limit)
