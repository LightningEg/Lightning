"""Names and scope of saved budget-estimate exclusions; no financial calculations."""


def exclusion_context(c) -> dict:
    categories = c.categories.tree()
    counts = {category.id: len([child for child in categories if child.code.startswith(category.code + ".")])
              for category in categories}
    explicit = c.budgets.one_off_ids(with_children=False)
    return {"estimate_exclusions": tuple({"id": category.id, "name": category.name,
                                          "subcategories": counts[category.id]}
                                         for category in categories if category.id in explicit),
            "subcategory_counts": counts}
