"""Public API of the categories module."""

from __future__ import annotations

from dataclasses import replace
from difflib import SequenceMatcher
import re

from lightning.core.codes import path_segment, validate_path_code
from lightning.core.errors import ConflictError, NotFoundError, ValidationError
from lightning.core.memo import in_request, request_cached
from lightning.database.connection import Database

from .domain import MAX_DEPTH, SYSTEM_CODE, Category, CategoryFamily, Direction, IncomeClass, Movement, Scope
from .repository import CategoryRepository


class CategoryService:
    def __init__(self, db: Database):
        self.db = db
        self.repo = CategoryRepository(db)

    # -- reading -----------------------------------------------------------
    @request_cached
    def tree(self, movement: Movement | None = None, active_only: bool = False) -> list[Category]:
        """Activity categories in tree order. Movement is a legacy/reporting filter only."""
        cats = self.repo.list()
        by_parent: dict[int | None, list[Category]] = {}
        for c in cats:
            by_parent.setdefault(c.parent_id, []).append(c)
        ordered: list[Category] = []

        def walk(parent_id: int | None, parent_active: bool) -> None:
            for child in by_parent.get(parent_id, []):
                visible = parent_active and child.active
                if movement and child.movement != movement:
                    continue
                if active_only and not visible:
                    continue
                ordered.append(child)
                walk(child.id, visible)

        walk(None, True)
        return ordered

    def pickable(self, movement: Movement | None = None) -> list[Category]:
        """L2 and L3 categories users can choose (an L2 with L3 detail can still be chosen)."""
        return sorted(
            (c for c in self.tree(active_only=True) if not c.is_root and not c.is_system
             and 2 <= c.depth <= MAX_DEPTH and c.code.startswith("EXP.")
             and not (movement is not None and c.code == "EXP.SYSTEM.CUSTODY")
             and (movement is None or c.movement == movement)),
            key=lambda c: (self.display_name(c.id).casefold(), c.id),
        )

    @request_cached
    def _by_id(self) -> dict[int, Category]:
        return {item.id: item for item in self.repo.list()}

    def get(self, category_id: int) -> Category:
        found = self._by_id().get(category_id) if in_request() else self.repo.get(category_id)
        if not found:
            raise NotFoundError("Category not found.")
        return found

    def get_by_code(self, code: str) -> Category:
        found = self.repo.get_by_code(code)
        if not found:
            raise NotFoundError(f"Category {code} not found.")
        return found

    def display_name(self, category_id: int) -> str:
        """Names only, for screens: 'Personal › Food & Groceries' (the Expenses/Income root is implied)."""
        names, current = [], self.get(category_id)
        while current.parent_id is not None:
            names.append(current.name)
            current = self.get(current.parent_id)
        return " › ".join(reversed(names)) or current.name

    def find_by_text(self, text: str) -> Category:
        """What someone typed in the Category box -> the category. Accepts the full name
        ('Personal › Food & Groceries'), the plain name ('Food & Groceries') or the code; case does not matter."""
        wanted = " ".join((text or "").split()).casefold()
        if not wanted:
            raise ValidationError("Choose a category — or pick one of your accounts as the counterparty for a transfer.",
                                  "category")
        options = [c for c in self.pickable()]
        for key in (lambda c: self.display_name(c.id), lambda c: c.name, lambda c: c.code):
            matches = [c for c in options if key(c).casefold() == wanted]
            if len(matches) == 1:
                return matches[0]
            if len(matches) > 1:
                names = " or ".join(self.display_name(c.id) for c in matches)
                raise ValidationError(f"Which one — {names}?", "category")
        partial = [c for c in options if wanted in self.display_name(c.id).casefold()]
        if len(partial) == 1:
            return partial[0]
        if partial:
            names = ", ".join(self.display_name(c.id) for c in partial[:4])
            raise ValidationError(f"'{text}' matches several categories: {names}. Pick one from the list.",
                                  "category")
        raise ValidationError(f"There is no category called '{text}'. Pick one from the list, or add it under "
                              "Categories.", "category")

    def suggestions(self, text: str, parent_id: int | None = None, limit: int = 3) -> list[tuple[Category, float]]:
        """Suggest existing L2 categories so near-duplicates can be reviewed before creation."""
        wanted = re.sub(r"[^\w]+", " ", (text or "").casefold()).strip()
        if not wanted:
            return []
        matches = []
        for category in self.pickable():
            if parent_id is not None and category.parent_id != parent_id:
                continue
            names = (category.name, self.display_name(category.id), category.code)
            score = max((SequenceMatcher(None, wanted, re.sub(r"[^\w]+", " ", name.casefold()).strip()).ratio()
                         for name in names), default=0.0)
            if any(wanted in re.sub(r"[^\w]+", " ", name.casefold()).strip() for name in names):
                score = max(score, 0.8)
            if score >= 0.5:
                matches.append((category, score))
        return sorted(matches, key=lambda item: (-item[1], self.display_name(item[0].id).casefold()))[:limit]

    def groups(self, movement: Movement | None = None, include_inactive: bool = True) -> list[tuple[Category, list[Category]]]:
        """L1 activity families with their broad L2 categories, for the categories page."""
        items = [c for c in self.tree() if c.code.startswith("EXP.") and c.depth <= 2
                 and not c.is_root and not c.is_system]
        if not include_inactive:
            items = [c for c in items if c.active]
        result: list[tuple[Category, list[Category]]] = []
        for c in items:
            if c.depth == 1:
                result.append((c, []))
            elif result:
                result[-1][1].append(c)
        family_order = {"PERSONAL": 0, "WORK": 1, "INVESTMENT": 2}
        result.sort(key=lambda pair: family_order.get(pair[0].family.value if pair[0].family else "", 99))
        for _, children in result:
            children.sort(key=lambda c: (c.name.casefold(), c.id))
        return result

    L1_ORDER = {"EXP.PERSONAL": 0, "EXP.WORK": 1, "EXP.INVEST": 2, SYSTEM_CODE: 3}
    DIRECTION_ORDER = {Direction.IN: 0, Direction.OUT: 1, Direction.BOTH: 2}

    def table(self, include_inactive: bool = False) -> list[tuple[Category, list[dict]]]:
        """The categories page: each L1 with its rows in order. An L2 comes before its L3 detail.

        Inside an L1, categories are soft-grouped by direction (+ income, − expense, ± both) and then
        sorted by name, so income never mixes into a run of expenses. Each row: {"category", "level",
        "has_children", "parent"}."""
        items = [c for c in self.tree() if c.code.startswith("EXP.") and 1 <= c.depth <= MAX_DEPTH
                 and not c.is_system and (include_inactive or c.active)]
        kids: dict[int | None, list[Category]] = {}
        for c in items:
            kids.setdefault(c.parent_id, []).append(c)
        key = lambda c: (self.DIRECTION_ORDER[c.direction], c.name.casefold(), c.id)
        result = []
        for l1 in sorted((c for c in items if c.depth == 1), key=lambda c: (self.L1_ORDER.get(c.code, 9), c.name.casefold())):
            rows = []
            for l2 in sorted(kids.get(l1.id, []), key=key):
                children = sorted(kids.get(l2.id, []), key=key)
                rows.append({"category": l2, "level": 2, "has_children": bool(children), "parent": l1})
                rows += [{"category": l3, "level": 3, "has_children": False, "parent": l2} for l3 in children]
            if rows or l1.code in self.L1_ORDER:  # an empty group that is not one of the four is noise
                result.append((l1, rows))
        return result

    def select_groups(self, categories=None) -> list[dict]:
        """Category choices for a picker, never as breadcrumbs: one group per L1 (its header), each
        L2 by its own name, and an L2 that has L3 detail as a header with its details under it.

        ``categories``: the choosable categories (Category objects or ids); default: pickable().
        Returns [{"label": L1 name, "options": [{"id", "name", "level", "header"}]}]; a header option
        whose L2 is not choosable itself has ``id`` None."""
        chosen = [c if isinstance(c, Category) else self.get(int(c)) for c in
                  (self.pickable() if categories is None else categories)]
        allowed = {c.id for c in chosen}
        all_items = {c.id: c for c in self.repo.list()}
        by_l1: dict[int, dict[int, list[Category]]] = {}
        for c in chosen:
            path = [c]
            while path[-1].parent_id is not None and all_items.get(path[-1].parent_id) and all_items[path[-1].parent_id].depth >= 1:
                path.append(all_items[path[-1].parent_id])
            l1 = path[-1] if path[-1].depth == 1 else c
            l2 = next((p for p in path if p.depth == 2), c)
            by_l1.setdefault(l1.id, {}).setdefault(l2.id, [])
            if c.depth >= 3:
                by_l1[l1.id][l2.id].append(c)
        groups = []
        for l1_id in sorted(by_l1, key=lambda i: (self.L1_ORDER.get(all_items[i].code, 9), all_items[i].name.casefold())):
            options = []
            for l2_id in sorted(by_l1[l1_id], key=lambda i: all_items[i].name.casefold()):
                details = sorted(by_l1[l1_id][l2_id], key=lambda c: c.name.casefold())
                l2 = all_items[l2_id]
                options.append({"id": l2.id if l2.id in allowed else None, "name": l2.name, "level": 2,
                                "header": bool(details), "movement": l2.movement.value})
                options += [{"id": d.id, "name": d.name, "level": 3, "header": False, "movement": d.movement.value}
                            for d in details]
            groups.append({"label": all_items[l1_id].name if all_items[l1_id].depth == 1 else "Other", "options": options})
        return groups

    def archived(self) -> list[Category]:
        """Archived L2 and L3 categories, for the page's Archived list."""
        return sorted((c for c in self.tree() if c.code.startswith("EXP.") and c.depth >= 2 and not c.active
                       and not c.is_system), key=lambda c: self.display_name(c.id).casefold())

    def set_direction(self, category_id: int, direction: Direction | str) -> None:
        """Choose + income, − expense or ± both. Income and expense also set how reports read it
        (income kind, or personal / work spending); sub-categories without their own choice follow."""
        try:
            direction = Direction(direction)
        except ValueError:
            raise ValidationError("Choose +, − or ±.", "direction") from None
        cat = self.get(category_id)
        if cat.is_root or cat.depth < 2:
            raise ValidationError("Choose + or − on a category, not on a top-level group.", "direction")
        if cat.code == "EXP.SYSTEM.CUSTODY" and direction != Direction.IN:
            raise ValidationError("Money held for others is always money in.", "direction")

        def applied(c: Category) -> Category:
            if direction == Direction.BOTH:
                return replace(c, direction_set=Direction.BOTH)
            if direction == Direction.IN:
                income = IncomeClass.INVESTMENT if c.family == CategoryFamily.INVESTMENT else IncomeClass.HOUSEHOLD
                return replace(c, direction_set=None, movement=Movement.INFLOW, income_class=c.income_class or income,
                               scope=None)
            scope = Scope.WORK if c.family == CategoryFamily.WORK else Scope.PERSONAL
            return replace(c, direction_set=None, movement=Movement.OUTFLOW, income_class=None, scope=c.scope or scope)

        with self.db.transaction():
            self.repo.update(applied(cat))
            for child in self.descendants(cat.id):
                if child.direction_set is None or child.direction_set == cat.direction_set:
                    self.repo.update(applied(child))

    def descendants(self, category_id: int) -> list[Category]:
        root = self.get(category_id)
        return [c for c in self.repo.list() if c.code.startswith(root.code + ".")]

    def require(self, category_id: int | None, movement: Movement, allow_system: bool = False,
                allow_inactive: bool = False) -> Category:
        """Validate that a category can be used for this direction of money."""
        if category_id is None:
            raise ValidationError("Choose a category.", "category")
        cat = self.get(category_id)
        if not cat.active and not allow_inactive:
            raise ValidationError(f"{cat.label} is inactive.", "category")
        if cat.is_root or (cat.is_system and not allow_system):
            raise ValidationError("Choose a more specific category than the top level.", "category")
        return cat

    # -- writing -----------------------------------------------------------
    def create(
        self,
        parent_id: int,
        name: str,
        code: str | None = None,
        default_reimbursable: bool | None = None,
    ) -> Category:
        name = (name or "").strip()
        if not name:
            raise ValidationError("Enter a name.", "name")
        parent = self.get(parent_id)
        if not parent.code.startswith("EXP.") or parent.family is None:
            raise ValidationError("Add categories inside Personal, Work, Investment or System.", "parent")
        if parent.depth >= MAX_DEPTH:
            raise ValidationError("Categories stop at L3: activity family, category, then detail.", "parent")
        code = self._child_code(parent, code or path_segment(name))
        if self.repo.code_exists(code):
            raise ConflictError(f"The code {code} is already used.", "code")
        cat = Category(
            id=0,
            code=code,
            name=name,
            parent_id=parent.id,
            movement=parent.movement,
            scope=parent.scope,
            income_class=parent.income_class,
            family=parent.family,
            default_reimbursable=(
                parent.default_reimbursable if default_reimbursable is None else default_reimbursable
            ),
            is_system=False,
            active=True,
            sort_order=self.repo.next_sort_order(),
            direction_set=parent.direction_set if parent.depth >= 2 else None,
        )
        with self.db.transaction():
            new_id = self.repo.insert(cat)
        return self.get(new_id)

    def update(
        self,
        category_id: int,
        name: str,
        code: str | None = None,
        active: bool = True,
        default_reimbursable: bool | None = None,
    ) -> list[int]:
        """Update a category (a code change carries over to its sub-categories). Returns the ids changed."""
        cat = self.get(category_id)
        name = (name or "").strip()
        if not name:
            raise ValidationError("Enter a name.", "name")
        new_code = cat.code
        if code and validate_path_code(code) != cat.code:
            if cat.is_root or cat.is_system:
                raise ValidationError("This category's code is fixed.", "code")
            parent = self.get(cat.parent_id)  # type: ignore[arg-type]
            new_code = self._child_code(parent, validate_path_code(code).rsplit(".", 1)[-1])
            if self.repo.code_exists(new_code, exclude_id=cat.id):
                raise ConflictError(f"The code {new_code} is already used.", "code")
        if not active and (cat.is_root or cat.is_system):
            raise ValidationError("This category cannot be deactivated.", "active")
        changed = [cat.id]
        with self.db.transaction():
            if not active:
                for child in self.descendants(cat.id):
                    if child.active:
                        self.repo.update(replace(child, active=False))
            if new_code != cat.code:
                for child in self.descendants(cat.id):
                    self.repo.update(replace(child, code=new_code + child.code[len(cat.code):]))
                    changed.append(child.id)
            self.repo.update(
                replace(
                    cat,
                    name=name,
                    code=new_code,
                    active=active,
                    default_reimbursable=(
                        cat.default_reimbursable if default_reimbursable is None else default_reimbursable
                    ),
                )
            )
        return changed

    def delete_or_archive(self, category_id: int) -> bool:
        """Delete an unused category; archive it when history or another record refers to it.

        Returns True when archived and False when permanently deleted.
        """
        category = self.get(category_id)
        if category.is_root or category.is_system or category.depth < 2:
            raise ValidationError("Top-level activity categories cannot be deleted.")
        # Any record that refers to it (history, budgets, rules, plans, reserves, children...) keeps it archived.
        references = self.db.referenced("categories", category_id)
        with self.db.transaction():
            if references:
                for item in [category, *self.descendants(category_id)]:
                    if item.active:
                        self.repo.update(replace(item, active=False))
                return True
            self.db.execute("DELETE FROM categories WHERE id=?", (category_id,))
        return False

    @staticmethod
    def _child_code(parent: Category, segment: str) -> str:
        segment = validate_path_code(segment)
        if segment.startswith(parent.code + "."):
            segment = segment[len(parent.code) + 1 :]
        if "." in segment:
            raise ValidationError("A category code adds one part to its parent's code.", "code")
        return f"{parent.code}.{segment}"
