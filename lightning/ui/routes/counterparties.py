from __future__ import annotations

from fastapi import APIRouter, Request

from lightning.core.errors import LightningError, ValidationError
from lightning.counterparties import MAX_ALIASES_PER_COUNTERPARTY

from ..web import container, redirect, render

router = APIRouter(prefix="/counterparties")


@router.get("")
async def list_counterparties(request: Request):
    c = container(request)
    query = " ".join(request.query_params.get("q", "").split())
    all_parties = c.counterparties.list_all()
    aliases = {party["id"]: c.counterparties.aliases_for(party["id"]) for party in all_parties}
    suggestions = c.counterparties.suggestions(query, limit=10) if query else []
    suggested_names = {name.casefold() for name, _ in suggestions}
    parties = [party for party in all_parties if not query or
               query.casefold() in party["name"].casefold() or
               any(query.casefold() in item["alias"].casefold() for item in aliases[party["id"]]) or
               party["name"].casefold() in suggested_names]
    categories = c.categories.pickable()
    return render(request, "counterparties.html", parties=parties, categories=categories, query=query,
                  total_parties=len(all_parties), search_suggestions=suggestions,
                  category_labels={item.id: c.categories.display_name(item.id) for item in categories},
                  aliases_by_id={party["id"]: aliases[party["id"]] for party in parties},
                  alias_limit=MAX_ALIASES_PER_COUNTERPARTY, usual=c.transactions.usual_categories())


@router.post("")
async def create_counterparty(request: Request):
    c = container(request)
    form = await request.form()
    name = str(form.get("name", "")).strip()
    raw_category_id = str(form.get("default_category_id", "")).strip()
    action = str(form.get("counterparty_action", ""))
    counterparty_id = str(form.get("counterparty_id", "")).strip()
    alias_id = str(form.get("alias_id", "")).strip()
    alias = str(form.get("alias", "")).strip()
    categories = c.categories.pickable()
    parties = c.counterparties.list_all()
    category_labels = {item.id: c.categories.display_name(item.id) for item in categories}
    try:
        category_id = int(raw_category_id) if raw_category_id else None
        if category_id is not None and category_id not in {item.id for item in categories}:
            raise ValidationError("Choose one of the suggested categories.")
        if action == "rename":
            selected = c.counterparties.get(int(counterparty_id))
            c.counterparties.rename(int(counterparty_id), name, category_id)
            return redirect("/counterparties", f"Updated {selected['name']}.")
        elif action.startswith("kind:"):
            selected = c.counterparties.get(int(counterparty_id))
            if not selected:
                raise ValidationError("Choose a saved counterparty.")
            kind = action.split(":", 1)[1]
            c.counterparties.set_kind(int(counterparty_id), kind)
            return redirect("/counterparties", f"{selected['name']} is now marked as a {'person' if kind == 'PERSON' else 'business'}.")
        elif action == "activate":
            c.counterparties.set_active(int(counterparty_id), True)
            return redirect("/counterparties", "Counterparty activated.")
        elif action == "delete":
            selected = c.counterparties.get(int(counterparty_id))
            archived = c.counterparties.delete_or_archive(int(counterparty_id))
            message = (f"{selected['name']} is in transaction history, so it was archived."
                       if archived else f"Deleted {selected['name']} and its aliases.")
            return redirect("/counterparties", message)
        elif action == "add_alias":
            selected = c.counterparties.get(int(counterparty_id))
            if not selected:
                raise ValidationError("Choose a saved counterparty.")
            c.counterparties.add_alias(int(counterparty_id), alias)
            return redirect("/counterparties", f"Added alias for {selected['name']}.")
        elif action == "rename_alias":
            selected = c.counterparties.get(int(counterparty_id))
            if not selected:
                raise ValidationError("Choose a saved counterparty.")
            c.counterparties.rename_alias(int(counterparty_id), int(alias_id), alias)
            return redirect("/counterparties", f"Updated alias for {selected['name']}.")
        elif action == "remove_alias":
            selected = c.counterparties.get(int(counterparty_id))
            if not selected:
                raise ValidationError("Choose a saved counterparty.")
            c.counterparties.remove_alias(int(counterparty_id), int(alias_id))
            return redirect("/counterparties", f"Removed alias from {selected['name']}.")
        elif action == "create":
            c.counterparties.create(name, category_id, kind=str(form.get("kind", "")).strip().upper() or None)
        elif action.startswith("existing:"):
            selected_id = int(action.split(":", 1)[1])
            selected = c.counterparties.get(selected_id)
            suggestions = {candidate for candidate, _ in c.counterparties.suggestions(name)}
            resolved = c.counterparties.resolve(name)
            if not selected or (selected["name"] not in suggestions and (not resolved or resolved["id"] != selected_id)):
                raise ValidationError("Choose one of the displayed matches, or create a new Counterparty.")
            c.counterparties.add_alias(selected_id, name)
            if category_id is not None:
                c.counterparties.set_default_category(selected_id, category_id)
        else:
            matches = []
            resolved = c.counterparties.resolve(name)
            if resolved:
                matches.append({"id": resolved["id"], "name": resolved["name"]})
            else:
                matches.extend({"id": int(row["id"]), "name": row["name"]}
                               for row in parties if row["name"] in
                               {candidate for candidate, _ in c.counterparties.suggestions(name)})
            return render(request, "counterparties.html", parties=parties, categories=categories,
                          category_labels=category_labels, entered_name=name,
                          entered_category_id=raw_category_id, similar_counterparties=matches,
                          aliases_by_id={party["id"]: c.counterparties.aliases_for(party["id"]) for party in parties},
                          alias_limit=MAX_ALIASES_PER_COUNTERPARTY,
                          exact_existing=bool(resolved), review_required=True)
    except (ValueError, LightningError) as exc:
        parties = c.counterparties.list_all()
        return render(request, "counterparties.html", status_code=400, parties=parties, categories=categories,
                      category_labels=category_labels,
                      aliases_by_id={party["id"]: c.counterparties.aliases_for(party["id"]) for party in parties},
                      alias_limit=MAX_ALIASES_PER_COUNTERPARTY,
                      error=str(exc) if isinstance(exc, ValueError) else exc.message,
                      entered_name=name, entered_category_id=raw_category_id)
    return redirect("/counterparties", f"Saved {name}.")


@router.get("/{counterparty_id:int}")
async def counterparty_page(request: Request, counterparty_id: int):
    """A page per counterparty (7T2): money with them by month, plans, reserves, claims, money held, aliases, rules."""
    c = container(request)
    try:
        page = c.linked.counterparty(counterparty_id)
    except LightningError as exc:
        return redirect("/counterparties", exc.message)
    return render(request, "counterparty.html", page=page, party=page["party"])
