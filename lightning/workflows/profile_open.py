"""What every way of opening a profile does once it is open (9K): one list, so the desktop profiles and
`python -m lightning` cannot drift apart again."""

from __future__ import annotations

import logging

from lightning.core.dates import today

_log = logging.getLogger(__name__)


def open_profile_tasks(container, *, wait: bool) -> list:
    """Fill held investments' prices from the files the app has, fetch month-end closes still missing (on
    another thread unless ``wait``), then post month-end valuation checkpoints that are due. Opening a profile
    never fails because of these: each step that fails is logged and the profile opens with the prices it has.
    Returns the reports of the steps that ran, for a console to print."""
    from lightning.workflows.live_prices import fetch_if_due, start_if_due
    from lightning.workflows.market_prices import fill_if_due

    reports = []
    if container.db.read_only:
        return reports
    day = today()
    for step in (fill_if_due, fetch_if_due if wait else start_if_due):
        try:
            report = step(container, day)
        except Exception:  # noqa: BLE001 - prices stay as saved; Investment prices can fill them by hand
            _log.warning("Price step %s failed while opening the profile", step.__name__, exc_info=True)
            continue
        if report not in (None, False, True):
            reports.append(report)
    try:
        reports.append(f"Investment reevaluations: {container.reevaluations.process_due()} monthly checkpoint(s) posted.")
    except Exception:  # noqa: BLE001 - the next price update or investment write posts them
        _log.warning("Month-end valuation checkpoints failed while opening the profile", exc_info=True)
    return reports
