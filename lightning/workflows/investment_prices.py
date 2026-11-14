"""The same holding scope for displaying and saving an investment's total value."""
from lightning.core.errors import ValidationError
from lightning.core.money import ZERO, to_decimal
from lightning.investments.owned import unit_price


def holding_totals(portfolio) -> dict[int, dict]:
    """All held units across accounts, including custody: one price applies to every unit."""
    rows = {}
    for position in portfolio.open:
        row = rows.setdefault(position.asset_id, {"quantity": ZERO, "accounts": set()})
        row["quantity"] += position.quantity
        row["accounts"].add(position.account_id)
    return rows


def total_at_price(price, holding):
    """The native total shown beside an editable estimate, using the displayed quantity."""
    return None if price is None or holding is None else price * holding["quantity"]


def save_inputs(c, day: str, prices: dict, totals: dict) -> int:
    """Called inside the route's atomic save. Physical estimates use their own valuation source."""
    held = holding_totals(c.investments.portfolio(day))
    prices = dict(prices)
    item_values = {}
    for asset_id, raw in totals.items():
        position = held.get(asset_id)
        if not position or position["quantity"] <= ZERO:
            raise ValidationError("A total value needs a positive holding quantity.", "value")
        if asset_id in prices:
            raise ValidationError("Enter either a unit price or total value for each investment, not both.", "price")
        asset = c.assets.get_asset(asset_id)
        total = to_decimal(raw, "value")
        if asset.code.startswith("OTH:ITEM-"):
            item_values[asset_id] = total
        else:
            if total <= ZERO:
                raise ValidationError("A total value must be greater than zero.", "value")
            prices[asset_id] = unit_price(total, position["quantity"])
            if prices[asset_id] <= ZERO:
                raise ValidationError("The total value is too small for this holding quantity.", "value")
    count = c.assets.set_prices(day, prices)
    for asset_id, value in item_values.items():
        c.physical_items.record_valuation(asset_id, day, value)
        count += 1
    return count
