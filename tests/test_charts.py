

def test_each_trend_dot_knows_its_change_from_the_previous_point():
    from decimal import Decimal as D
    from lightning.ui.charts import trend
    chart = trend(["a", "b", "c"], [{"name": "Net worth", "tone": "good", "values": [D(100), D(110), D(99)]}])
    first, second, third = chart["series"][0]["dots"]
    assert first["change"] is None and first["pct"] is None
    assert second["change"] == 10 and round(second["pct"]) == 10
    assert third["change"] == -11 and round(third["pct"]) == -10


def _boxes(chart, height):
    """Each end label as (left %, top px, bottom px), the way the stylesheet draws it: above is 24 px to 8 px over the
    point, below is 8 px to 24 px under it."""
    from lightning.ui.charts import end_labels
    boxes = []
    for e in end_labels(chart, height):
        at = e["y"] / 100 * height
        boxes.append((e["x"], at - 24 if e["side"] == "above" else at + 8))
    return [(x, top, top + 16) for x, top in boxes]


def test_two_end_labels_close_together_never_touch():
    """Value against cost ends 12,126 over 11,703 on a 200,000 axis: the labels share one spot (3C)."""
    from decimal import Decimal as D
    from lightning.ui.charts import end_labels, trend
    chart = trend(["a", "b", "c"], [{"name": "Value", "tone": "hold", "values": [D(1000), D(9000), D(12126)]},
                                    {"name": "Cost", "tone": "other", "values": [D(1000), D(9000), D(11703)]}])
    labels = end_labels(chart, 210)
    assert [e["value"] for e in labels] == [D(12126), D(11703)]  # both shown, the higher one first
    assert [e["side"] for e in labels] == ["above", "below"]
    (x1, top1, bottom1), (x2, top2, bottom2) = _boxes(chart, 210)
    assert bottom1 <= top2  # one clear line between them


def test_end_labels_that_are_far_apart_both_stand_above_their_points():
    from decimal import Decimal as D
    from lightning.ui.charts import end_labels, trend
    chart = trend(["a", "b"], [{"name": "Value", "tone": "hold", "values": [D(10), D(100)]},
                               {"name": "Cost", "tone": "other", "values": [D(10), D(20)]}])
    assert [e["side"] for e in end_labels(chart, 180)] == ["above", "above"]


def test_a_third_label_in_the_same_place_is_left_out_not_drawn_over_the_others():
    from decimal import Decimal as D
    from lightning.ui.charts import end_labels, trend
    chart = trend(["a", "b"], [{"name": n, "tone": "hold", "values": [D(1), D(100)]} for n in "xyz"])
    assert [e["side"] for e in end_labels(chart, 180)] == ["above", "below"]


def test_the_paces_end_labels_part_when_the_totals_are_close():
    """Budget pace: the plan 8,719 and last month 8,774 are 0.6% apart; the labels need 16 px each (3S2)."""
    from decimal import Decimal as D
    from lightning.ui.charts import PACE_LABEL_GAP, PACE_PLOT_PX, pace
    chart = pace([D(100)] * 5, D(8719), 31, [D(8774) * (i + 1) / 31 for i in range(31)])
    gap = (chart["before_label_y"] - chart["plan"]["label_y"]) / 100 * PACE_PLOT_PX
    assert abs(gap) >= PACE_LABEL_GAP - 0.01
    assert (chart["plan"]["label_y"] > chart["before_label_y"]) == (chart["plan"]["y"] > chart["before_end_y"])  # same order
    far = pace([D(100)] * 5, D(8719), 31, [D(4000) * (i + 1) / 31 for i in range(31)])
    assert abs(far["plan"]["label_y"] - far["plan"]["y"]) < 1e-6 and abs(far["before_label_y"] - far["before_end_y"]) < 1e-6  # untouched
    assert pace([D(100)], D(8719), 31)["before_label_y"] is None
