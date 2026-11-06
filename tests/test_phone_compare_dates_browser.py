"""r24: on the phone the Compare periods dates show whole, not cut off beside their picker button."""
from test_bulk_action_safety import ui  # noqa: F401  (the shared browser fixture)


def test_compare_period_dates_are_not_truncated_at_320_and_360(c, ui):
    page, origin = ui(phone=True)
    for width in (320, 360):
        page.set_viewport_size({'width': width, 'height': 800})
        page.goto(f'{origin}/spending/compare')
        fields = page.locator('.compare-picker [data-smart-date]')
        assert fields.count() == 4
        for i in range(4):
            assert fields.nth(i).evaluate('(e) => e.scrollWidth <= e.clientWidth'), (width, i)
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
