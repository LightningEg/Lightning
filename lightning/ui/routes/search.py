"""The Search page and the Ctrl-K command bar: both ask the one matcher (lightning.ui.search_index)."""
from __future__ import annotations

import json

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from lightning.core.matching import rank_choices

from ..i18n import translate
from ..search_index import ACTIONS, GROUPS, PAGES, _fold_search_text, _score, entry, fmt_amount, matches  # noqa: F401  (tests and callers read them here)
from ..web import container, privacy_on, render

router = APIRouter()


@router.get("/search")
async def search(request: Request):
    c = container(request)
    query = " ".join(str(request.query_params.get("q", "")).split())
    results = matches(c, query, privacy=privacy_on(request))
    if request.query_params.get("format") == "json":
        if c.settings.get("locale") == "ar":
            # Page, action and account-type words are the app's own; a name someone typed has no entry and stays.
            results = [{**row, "label": translate(row["label"], "ar") if row["kind"] in ("Page", "Action", "Search", "Category") else row["label"],
                        "context": translate(row.get("context", ""), "ar")} for row in results]
        return JSONResponse({"query": query, "results": results})
    return render(request, "search.html", query=query, results=results if query else [])


@router.post("/search/picker")
async def scoped_picker(request: Request):
    """Rank the current enabled options of a picker; submitted values remain explicit choices."""
    form = await request.form(max_fields=5)
    raw, query = str(form.get("choices", "")), str(form.get("q", ""))
    if len(raw) > 512_000 or len(query) > 256:
        return JSONResponse({"error": "Too many choices."}, status_code=400)
    try:
        choices = json.loads(raw)
        if (not isinstance(choices, list) or len(choices) > 4000
                or any(not isinstance(row, dict) or not isinstance(row.get("id"), str)
                       or any(not isinstance(row.get(key, ""), str) or len(row.get(key, "")) > 512
                              for key in ("label", "context", "code")) for row in choices)):
            raise ValueError
    except (ValueError, TypeError):
        return JSONResponse({"error": "Invalid choices."}, status_code=400)
    return JSONResponse({"ids": rank_choices(query, choices, str(form.get("kind", "Text")))})
