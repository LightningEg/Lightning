"""Chart geometry for server-rendered pages (App guideline 2.2 · 09 Charts).

Hand-drawn SVG and CSS, no chart library. This module only turns figures that services already
computed into positions and percentages; it never computes a financial figure. The markup lives
in templates/partials/charts.html. Rules from the guideline and the data-visualization checks:

- colours follow meaning: money in green, money out soft rose, over plan strong rose, money you
  hold azure; asset classes by family (cash azure, income teal, gold gold, growth green, other
  grey), a lighter shade for the fund version, families kept together around a donut;
- bars start at zero, values sit on the marks, one axis only;
- a trend with fewer than two points says so instead of drawing;
- every chart has a table view with the same numbers.
"""
from __future__ import annotations

from decimal import Decimal

from lightning.core.money import quantize

ZERO = Decimal(0)


def _gap(more: Decimal, less: Decimal) -> Decimal:
    """What is left or over, in whole EGP, as the two rounded figures beside it read: 80 of 67.50 is 12 over."""
    return quantize(more, 0) - quantize(less, 0)

# Asset class code (root or child) -> chart tone. One hue family per kind of asset, a lighter shade
# for the fund version (App guideline · Asset class colours). Order is the donut order.
CLASS_TONES = [("CASH", "cash"),
               ("DEPOSIT", "deposits"), ("GAMEYA", "deposits"), ("FUND.MONEY_MARKET", "money-market"), ("FUND.FIXED_INCOME", "fixed-income"),
               ("GOLD", "gold"), ("FUND.GOLD", "gold-fund"),
               ("STOCK", "equity"), ("FUND", "equity-fund"), ("FUND.EQUITY", "equity-fund"),
               ("OTHER", "other"), ("FUND.OTHER", "other-fund")]
TONE_ORDER = ["cash", "deposits", "money-market", "fixed-income", "gold", "gold-fund",
              "equity", "equity-fund", "other", "other-fund"]  # checked with the palette validator


def class_tone(code: str) -> str:
    """The chart colour for an asset class code: the most specific match wins."""
    best = ("", "other")
    for prefix, tone in CLASS_TONES:
        if (code == prefix or code.startswith(prefix + ".")) and len(prefix) > len(best[0]):
            best = (prefix, tone)
    return best[1]


def _nice_ceiling(value: Decimal) -> Decimal:
    """Round a maximum up to a clean axis number (1, 2, 2.5 or 5 × a power of ten)."""
    if value <= 0:
        return Decimal(1)
    magnitude = Decimal(10) ** (len(str(int(value))) - 1)
    for step in (1, 2, Decimal("2.5"), 5, 10):
        if value <= magnitude * step:
            return magnitude * step
    return magnitude * 10


def trend(labels: list[str], series: list[dict], plan: Decimal | None = None,
          min_points: int = 2) -> dict:
    """Lines over time on one axis.

    ``series``: [{"name", "tone", "values": [Decimal | None, ...]}], values aligned with ``labels``.
    Returns positions in percent of the plot box (x left→right, y top→bottom), ticks, and a
    ``too_short`` flag when no series has ``min_points`` known values.
    """
    known = [v for s in series for v in s["values"] if v is not None]
    points_per_series = [sum(1 for v in s["values"] if v is not None) for s in series]
    if not labels or max(points_per_series, default=0) < min_points:
        return {"too_short": True, "labels": labels, "series": series}
    low = min([ZERO, *known] + ([plan] if plan is not None else []))
    high = max([*known] + ([plan] if plan is not None else []) + [ZERO])
    top = _nice_ceiling(high) if high > 0 else ZERO
    bottom = -_nice_ceiling(-low) if low < 0 else ZERO
    span = (top - bottom) or Decimal(1)

    def y(value: Decimal) -> float:
        return float((top - value) / span * 100)

    def x(index: int) -> float:
        return 50.0 if len(labels) == 1 else 4 + 92 * index / (len(labels) - 1)

    drawn = []
    for s in series:
        pts = [(x(i), y(v), v, labels[i]) for i, v in enumerate(s["values"]) if v is not None]
        line = " ".join(f"{px:.2f},{py:.2f}" for px, py, _, _ in pts)
        zero_y = y(max(bottom, ZERO)) if bottom < 0 <= top else y(bottom)
        area = (f"M{pts[0][0]:.2f},{zero_y:.2f} " + " ".join(f"L{px:.2f},{py:.2f}" for px, py, _, _ in pts)
                + f" L{pts[-1][0]:.2f},{zero_y:.2f} Z") if pts else ""
        over = s.get("over")  # per month, when each month has its own plan
        dots = [{"x": px, "y": py, "value": v, "label": lab,
                 "over": bool(over[labels.index(lab)]) if over is not None
                 else plan is not None and s.get("plan_applies", True) and v > plan,
                 "change": None if n == 0 else v - pts[n - 1][2],  # since the previous point of this line
                 "pct": None if n == 0 or pts[n - 1][2] == 0 else float((v - pts[n - 1][2]) / abs(pts[n - 1][2]) * 100)}
                for n, (px, py, v, lab) in enumerate(pts)]
        drawn.append({**s, "line": line, "area": area if s.get("area") else "", "dots": dots,
                      "last": dots[-1] if dots else None})
    ticks = [{"value": v, "y": y(v)} for v in sorted({top, (top + bottom) / 2, bottom, ZERO}, reverse=True)
             if bottom <= v <= top]
    return {"too_short": False, "labels": [{"text": lab, "x": x(i)} for i, lab in enumerate(labels)],
            "series": drawn, "ticks": ticks, "plan": None if plan is None else {"value": plan, "y": y(plan)},
            "zero_y": y(ZERO) if bottom < 0 else None}


LABEL_HEIGHT = 16  # px: one end label (12px type), also the least space between two labels at one end
LABEL_NEAR_X = 30  # % of the plot width: end labels closer than this sideways compete for the same space


def end_labels(t: dict, height: float = 180) -> list[dict]:
    """Where each series writes its last value, so two labels never sit on each other (A12: labels never touch).

    A label stands above its point, right-aligned to it. Points are taken top down; when a label would touch one
    already placed it goes under its point instead, and when that is taken too it is left out (the dots still
    tell the value on hover). ``height`` is the plot's height in px. -> [{"x", "y", "value", "side"}], side
    "above" or "below"; positions are in percent of the plot like the dots."""
    ends = sorted((s["last"] for s in t.get("series", []) if s.get("last")), key=lambda d: d["y"])
    placed: list[tuple[float, float, float]] = []  # x, top, bottom (px)
    out = []
    for end in ends:
        at = end["y"] / 100 * height
        for side, top in (("above", at - 1.5 * LABEL_HEIGHT), ("below", at + LABEL_HEIGHT / 2)):
            box = (end["x"], top, top + LABEL_HEIGHT)
            if all(abs(x - box[0]) >= LABEL_NEAR_X or bottom <= box[1] or box[2] <= start for x, start, bottom in placed):
                placed.append(box)
                out.append({"x": end["x"], "y": end["y"], "value": end["value"], "side": side})
                break
    return out


def spread_labels(ys: list[float | None], height: float, gap: float = LABEL_HEIGHT) -> list[float | None]:
    """Move labels that stand at one end of a chart apart until each has ``gap`` px of its own, keeping their
    order and splitting the move between them. ``ys`` and the result are percent of ``height`` px (None stays)."""
    slots = sorted((i for i, y in enumerate(ys) if y is not None), key=lambda i: ys[i])
    px = [ys[i] / 100 * height for i in slots]
    low, high = gap / 2, height - gap / 2
    for _ in range(len(px) * 4):
        moved = False
        for k in range(len(px) - 1):
            short = gap - (px[k + 1] - px[k])
            if short > 0.01:
                px[k] -= short / 2
                px[k + 1] += short / 2
                moved = True
        px = [min(max(v, low), high) for v in px]
        if not moved:
            break
    out = list(ys)
    for i, v in zip(slots, px):
        out[i] = v / height * 100
    return out


def bars(rows: list[dict], limit: int = 4) -> dict:
    """Horizontal bars, largest first, from zero. rows: [{"label", "value", "href"?}]."""
    ordered = sorted((r for r in rows if r["value"]), key=lambda r: -abs(r["value"]))
    shown, rest = ordered[:limit], ordered[limit:]
    scale = max((abs(r["value"]) for r in shown), default=ZERO) or Decimal(1)
    return {"rows": [{**r, "width": float(abs(r["value"]) / scale * 100)} for r in shown],
            "more": len(rest), "more_total": sum((r["value"] for r in rest), ZERO)}


def grouped_bars(rows: list[dict], limit: int = 8) -> dict:
    """Bars under their parent category: an L1 header row with its total, then its L2 rows.

    rows: [{"group", "label", "value", "href"?}]. Groups are largest first, rows largest first
    inside each group; bar lengths share one scale so groups compare. At most ``limit`` bars show.
    """
    shown_rows = [r for r in rows if r["value"]]
    totals: dict[str, Decimal] = {}
    for r in shown_rows:
        totals[r["group"]] = totals.get(r["group"], ZERO) + r["value"]
    ordered = sorted(shown_rows, key=lambda r: (-totals[r["group"]], r["group"], -abs(r["value"])))
    shown, rest = ordered[:limit], ordered[limit:]
    scale = max((abs(r["value"]) for r in shown), default=ZERO) or Decimal(1)
    out, current = [], None
    for r in shown:
        if r["group"] != current:
            current = r["group"]
            out.append({"header": True, "label": current, "value": totals[current]})
        out.append({**r, "width": float(abs(r["value"]) / scale * 100)})
    return {"rows": out, "more": len(rest), "more_total": sum((r["value"] for r in rest), ZERO)}


def waterfall(start: tuple[str, Decimal], steps: list[tuple[str, Decimal]], end: tuple[str, Decimal]) -> dict:
    """A start value, the steps taken off (or added), and where it ends, as horizontal bars.

    Each step bar sits where the running total was, so the bars read as one path from start to end.
    Positions are percentages of the largest running total."""
    running, points = start[1], [start[1]]
    for _, value in steps:
        running += value
        points.append(running)
    scale = max([abs(v) for v in points] + [abs(end[1]), Decimal(1)])
    rows = [{"label": start[0], "value": start[1], "kind": "total", "left": 0.0, "width": float(abs(start[1]) / scale * 100)}]
    running = start[1]
    for label, value in steps:
        after = running + value
        low, high = min(running, after), max(running, after)
        rows.append({"label": label, "value": value, "kind": "up" if value > 0 else "down",
                     "left": float(max(low, ZERO) / scale * 100), "width": float((high - max(low, ZERO)) / scale * 100)})
        running = after
    rows.append({"label": end[0], "value": end[1], "kind": "end", "left": 0.0, "width": float(max(end[1], ZERO) / scale * 100)})
    return {"rows": rows}


def column_waterfall(start: tuple[str, Decimal], steps: list[tuple[str, Decimal]],
                     end: tuple[str, Decimal]) -> dict:
    """The same path as ``waterfall`` drawn as columns: a start column from zero, each step floating
    where the running total was, and the end column from zero. One zero line, values on the marks.

    Positions are percentages of the plot height, measured from the bottom: ``base`` and ``height``
    place a column, ``level`` is the running total after it (the thin link to the next column)."""
    running, levels = start[1], [start[1]]
    for _, value in steps:
        running += value
        levels.append(running)
    top = max([*levels, end[1], ZERO])
    bottom = min([*levels, end[1], ZERO])
    span = (top - bottom) or Decimal(1)

    def at(value: Decimal) -> float:
        return float((value - bottom) / span * 100)

    spans = [(start[0], start[1], "total", min(start[1], ZERO), max(start[1], ZERO))]
    running = start[1]
    for label, value in steps:
        after = running + value
        spans.append((label, value, "up" if value > 0 else "down", min(running, after), max(running, after)))
        running = after
    spans.append((end[0], end[1], "end" if end[1] >= 0 else "short", min(end[1], ZERO), max(end[1], ZERO)))
    columns = []
    for i, (label, value, kind, low, high) in enumerate(spans):
        level = levels[i] if i < len(levels) else None
        columns.append({"label": label, "value": value, "kind": kind, "base": at(low), "height": at(high) - at(low),
                        "level": at(level) if level is not None else None})
    return {"columns": columns, "zero": at(ZERO)}


def sankey(sources: list[dict], targets: list[dict], hub_label: str, min_gap: float = 11.0,
           xs: tuple[float, float, float] = (22.0, 49.0, 76.0)) -> dict:
    """Where money in went, in three columns: each source flows into one hub (money in), and the hub
    flows out to each target. Nothing is attributed from a source to a target, because the ledger
    does not say which income paid which bill.

    sources / targets: [{"label", "value", "tone", "href"?}], positive values, both summing to the
    same total. Positions are percentages of the plot box (y top→bottom). Label positions are
    pushed apart by at least ``min_gap`` so small nodes stay readable. ``xs`` places the source, hub and
    target columns; a half-width chart moves the targets left so their names have room."""
    sources = [s for s in sources if s["value"] > 0]
    targets = [t for t in targets if t["value"] > 0]
    total = sum((s["value"] for s in sources), ZERO)
    if not sources or not targets or total <= 0:
        return {"nodes": [], "links": []}
    gap, pad = 3.0, 4.0
    most = max(len(sources), len(targets))
    scale = (100 - 2 * pad - gap * (most - 1)) / float(total)

    def column(items, x):
        height = sum(float(i["value"]) * scale for i in items) + gap * (len(items) - 1)
        y, out = pad + (100 - 2 * pad - height) / 2, []
        for item in items:
            h = float(item["value"]) * scale
            out.append({**item, "x": x, "y": y, "h": h, "mid": y + h / 2})
            y += h + gap
        return out

    def spread(nodes):  # keep labels at least min_gap apart, inside the box
        mids = [n["mid"] for n in nodes]
        for i in range(1, len(mids)):
            mids[i] = max(mids[i], mids[i - 1] + min_gap)
        overflow = mids[-1] - (100 - min_gap / 2) if mids else 0
        if overflow > 0:
            mids = [m - overflow for m in mids]
            for i in range(len(mids) - 2, -1, -1):
                mids[i] = min(mids[i], mids[i + 1] - min_gap)
        for n, m in zip(nodes, mids):
            n["label_y"] = max(m, min_gap / 2)

    left, right = column(sources, xs[0]), column(targets, xs[2])
    hub_h = float(total) * scale
    hub = {"label": hub_label, "value": total, "tone": "in", "x": xs[1], "y": (100 - hub_h) / 2, "h": hub_h}
    spread(left)
    spread(right)
    width, links = 2.0, []

    def ribbon(x1, y1, x2, y2, h):
        mx = (x1 + x2) / 2
        return (f"M{x1:.2f},{y1:.2f} C{mx:.2f},{y1:.2f} {mx:.2f},{y2:.2f} {x2:.2f},{y2:.2f} "
                f"L{x2:.2f},{y2 + h:.2f} C{mx:.2f},{y2 + h:.2f} {mx:.2f},{y1 + h:.2f} {x1:.2f},{y1 + h:.2f} Z")

    y_in = hub["y"]
    for n in left:
        links.append({"d": ribbon(n["x"] + width, n["y"], hub["x"], y_in, n["h"]), "tone": n["tone"], "label": n["label"]})
        y_in += n["h"]
    y_out = hub["y"]
    for n in right:
        links.append({"d": ribbon(hub["x"] + width, y_out, n["x"], n["y"], n["h"]), "tone": n["tone"], "label": n["label"]})
        y_out += n["h"]
    return {"sources": left, "targets": right, "hub": hub, "links": links, "total": total, "width": width,
            "nodes": left + [hub] + right}


def meter(used: Decimal, total: Decimal | None) -> dict:
    """Spent of plan (or saved of target). Over plan fills the track in strong rose."""
    if not total or total <= 0:
        return {"width": 0.0, "over": used > 0, "left": None}
    return {"width": float(min(used / total, Decimal(1)) * 100), "over": used > total,
            "left": _gap(total, used), "over_by": _gap(used, total), "share": float(used / total * 100)}


def bullet(used: Decimal, plan: Decimal | None) -> dict:
    """Actual against plan on one scale: the plan as a soft band ending in a tick, what was spent
    inside it, and anything over the plan carried past the tick in strong rose.

    Widths are percentages of the row's scale (the larger of plan and spent)."""
    plan = plan or ZERO
    used = max(used, ZERO)
    scale = max(plan, used) or Decimal(1)
    return {"plan": float(plan / scale * 100), "spent": float(min(used, plan) / scale * 100),
            "over": float((used - plan) / scale * 100) if used > plan else 0.0,
            "is_over": used > plan, "left": _gap(plan, used), "over_by": _gap(used, plan),
            "share": float(used / plan * 100) if plan else None}


def plan_bar(planned: Decimal, spent: Decimal) -> dict:
    """One line for the whole plan: spent in azure, what is left in green, or over plan in rose
    past the planned length. Percentages of the larger of planned and spent."""
    b = bullet(spent, planned)
    return {"spent": b["spent"], "left": max(b["plan"] - b["spent"], 0.0), "over": b["over"],
            "is_over": b["is_over"], "share": b["share"]}


def waffle(rate: Decimal | None) -> dict:
    """100 squares; the share in its meaning colour. A negative rate fills none and says so."""
    if rate is None:
        return {"filled": 0, "cells": 100, "rate": None}
    return {"filled": int(max(min(rate, Decimal(100)), ZERO).to_integral_value()), "cells": 100, "rate": rate}


def diverging(rows: list[dict]) -> dict:
    """Differences both ways from one centre line: rows [{"label", "value", "group"?, "tone"?}].
    Bars are a share of the largest size; the sign picks the side."""
    scale = max((abs(r["value"]) for r in rows), default=ZERO) or Decimal(1)
    return {"rows": [{**r, "width": float(abs(r["value"]) / scale * 50)} for r in rows]}


def treemap(items: list[dict], width: float = 100.0, height: float = 100.0) -> list[dict]:
    """Squarified treemap: each item {"label", "value", ...} gets x, y, w, h in percent of the box,
    largest first, rectangles kept as square as the values allow."""
    items = sorted((i for i in items if i["value"] > 0), key=lambda i: -i["value"])
    total = float(sum((i["value"] for i in items), ZERO))
    if not total:
        return []
    area = width * height
    sizes = [float(i["value"]) / total * area for i in items]
    out, x, y, w, h, start = [], 0.0, 0.0, width, height, 0

    def worst(row, side):
        s = sum(row)
        return max(max(side * side * r / (s * s), (s * s) / (side * side * r)) for r in row)

    while start < len(sizes):
        side = min(w, h)
        row = [sizes[start]]
        end = start + 1
        while end < len(sizes) and worst(row + [sizes[end]], side) <= worst(row, side):
            row.append(sizes[end]); end += 1
        s = sum(row)
        if w >= h:  # lay the row down the left edge
            col_w = s / h
            yy = y
            for k, r in enumerate(row):
                out.append({**items[start + k], "x": x, "y": yy, "w": col_w, "h": r / col_w})
                yy += r / col_w
            x += col_w; w -= col_w
        else:  # along the top edge
            row_h = s / w
            xx = x
            for k, r in enumerate(row):
                out.append({**items[start + k], "x": xx, "y": y, "w": r / row_h, "h": row_h})
                xx += r / row_h
            y += row_h; h -= row_h
        start = end
    return out


def shared_lines(series: list[list[Decimal | None]]) -> list[str]:
    """Polylines for small multiples: every panel on the same scale (0 to the largest value)."""
    top = max((v for vals in series for v in vals if v is not None), default=ZERO) or Decimal(1)
    out = []
    for vals in series:
        n = len(vals)
        pts = [(4 + 92 * i / (n - 1) if n > 1 else 50, 92 - float(v / top) * 84) for i, v in enumerate(vals) if v is not None]
        out.append(" ".join(f"{px:.2f},{py:.2f}" for px, py in pts))
    return out


def donut(slices: list[dict], limit: int = 5) -> dict:
    """Parts of one whole: four by name, then "Other" (``limit`` counts Other).

    slices: [{"label", "value", "tone"}]; ordered by tone (cash, deposits, gold, equity, other) so
    that neighbouring hues stay distinct. Returns stroke-dash segments on a circle of
    circumference 100, with a small gap between slices.
    """
    parts = sorted((s for s in slices if s["value"] and s["value"] > 0), key=lambda s: -s["value"])
    folded = None
    if len(parts) > limit:  # keep the largest, fold the smallest
        parts, rest = parts[:limit - 1], parts[limit - 1:]
        folded = {"label": "Other", "value": sum((s["value"] for s in rest), ZERO), "tone": "other"}
    parts.sort(key=lambda s: (TONE_ORDER.index(s["tone"]) if s["tone"] in TONE_ORDER else 99, -s["value"]))
    if folded:
        parts.append(folded)
    total = sum((s["value"] for s in parts), ZERO)
    if not total:
        return {"segments": [], "total": ZERO}
    gap = 0.6 if len(parts) > 1 else 0.0
    offset, segments = 25.0, []  # start at 12 o'clock
    for s in parts:
        share = float(s["value"] / total * 100)
        segments.append({**s, "share": share, "dash": max(share - gap, 0.1), "offset": offset})
        offset -= share
    return {"segments": segments, "total": total}


def share(parts: list[dict]) -> dict:
    """Two to four parts of one whole in a single line."""
    shown = [p for p in parts if p["value"] and p["value"] > 0]
    total = sum((p["value"] for p in shown), ZERO)
    return {"parts": [{**p, "share": float(p["value"] / total * 100)} for p in shown] if total else [],
            "total": total}


def sparkline(values: list[Decimal | None], mark: str = "last") -> dict:
    """A small trend with no axes; only with two known points or more. ``dot`` is the point the card's label
    names (A12.1.15): the last one, or the lowest with ``mark="low"``."""
    known = [v for v in values if v is not None]
    if len(known) < 2:
        return {"points": ""}
    low, high = min(known), max(known)
    span = (high - low) or Decimal(1)
    pts = [(4 + 92 * i / (len(values) - 1), 90 - float((v - low) / span) * 80)
           for i, v in enumerate(values) if v is not None]
    dot = pts[known.index(low)] if mark == "low" else pts[-1]
    return {"points": " ".join(f"{x:.2f},{y:.2f}" for x, y in pts), "last": pts[-1], "dot": dot,
            "area": f"M{pts[0][0]:.2f},100 " + " ".join(f"L{x:.2f},{y:.2f}" for x, y in pts) + f" L{pts[-1][0]:.2f},100 Z"}


PACE_PLOT_PX = 220  # the pace chart's plot height in style.css (.pace-plot)
PACE_LABEL_GAP = 18  # px between the centres of its two end labels: 12px type, 15 tall, and air


def pace(by_day: list[Decimal], plan: Decimal, days: int, last_month: list[Decimal] | None = None) -> dict:
    """Pace (burn-up, A12.1.9): spending added up day by day against a straight line from zero to the plan,
    with the month before by the same day of the month. Positions in percent of the plot (0,0 top left)."""
    last_month = last_month or []
    top = max([plan, *by_day, *last_month, Decimal(1)]) * Decimal("1.08")

    def x(day: int) -> float:
        return min(day, days) / days * 100 if days else 0.0

    def y(value: Decimal) -> float:
        return 100 - float(value / top * 100)

    def line(values: list[Decimal]) -> str:
        return " ".join([f"0,100"] + [f"{x(i + 1):.2f},{y(v):.2f}" for i, v in enumerate(values[:days])])

    now = len(by_day)
    allowed = plan * now / days if days else ZERO
    # The plan's and last month's end labels stand at the right edge: when the two totals are close, they part.
    plan_label, before_label = spread_labels([y(plan), y(last_month[-1]) if last_month else None], PACE_PLOT_PX,
                                             gap=PACE_LABEL_GAP)
    pace_y = y(allowed)
    pace_label_y = pace_y - PACE_LABEL_GAP / PACE_PLOT_PX * 100
    if by_day and abs(pace_label_y - y(by_day[-1])) < PACE_LABEL_GAP / PACE_PLOT_PX * 100:
        pace_label_y = y(by_day[-1]) - PACE_LABEL_GAP / PACE_PLOT_PX * 100
    return {"actual": line(by_day) if by_day else "", "before": line(last_month) if last_month else "",
            "plan": {"x": 100.0, "y": y(plan), "value": plan, "label_y": plan_label},
            "today": {"x": x(now), "value": by_day[-1] if by_day else ZERO, "y": y(by_day[-1]) if by_day else 100.0,
                      "day": now, "pace": allowed, "pace_y": pace_y,
                      "pace_label_offset": (pace_label_y - pace_y) / 100 * PACE_PLOT_PX,
                      "before": last_month[min(now, len(last_month)) - 1] if last_month and now else None,
                      "before_y": y(last_month[min(now, len(last_month)) - 1]) if last_month and now else None} if now else None,
            "before_total": last_month[-1] if last_month else None,
            "before_end_y": y(last_month[-1]) if last_month else None, "before_label_y": before_label,
            "grid": [{"y": y(v), "value": v} for v in (top / Decimal("1.08") / 2, top / Decimal("1.08"))],
            "days": days}


def line_chart(values: list[Decimal | None]) -> dict[str, list]:
    """Older helper kept for the investments page: connect adjacent known observations."""
    known = [value for value in values if value is not None]
    if len(known) < 2 or len(values) < 2:
        return {"segments": [], "dots": []}
    low, high = min(known), max(known)
    span = high - low
    dots, segments, current = [], [], []
    for index, value in enumerate(values):
        if value is None:
            if len(current) > 1:
                segments.append(" ".join(current))
            current = []
            continue
        x = Decimal(5) + Decimal(90 * index) / Decimal(len(values) - 1)
        y = Decimal(50) if span == 0 else Decimal(85) - Decimal(70) * (value - low) / span
        point = f"{x:.2f},{y:.2f}"
        current.append(point)
        dots.append((f"{x:.2f}", f"{y:.2f}"))
    if len(current) > 1:
        segments.append(" ".join(current))
    return {"segments": segments, "dots": dots}
