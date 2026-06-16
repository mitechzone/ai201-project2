"""
agent.py

The FitFindr planning loop. Orchestrates the three tools in response to a
natural language user query, passing state between them via a session dict.

Complete tools.py and test each tool in isolation before implementing this file.

Usage (once implemented):
    from agent import run_agent
    from utils.data_loader import get_example_wardrobe

    result = run_agent(
        query="vintage graphic tee under $30, size M",
        wardrobe=get_example_wardrobe(),
    )
    print(result["fit_card"])
    print(result["error"])   # None on success
"""

import json

from tools import search_listings, suggest_outfit, create_fit_card, compare_price, _chat


# ── style profile memory (stretch) ──────────────────────────────────────────────
# In-memory store that outlives a single run_agent() call, so style preferences
# stated in one query carry into later queries within the same app run.
# Intentionally not persisted to disk — it resets when the app restarts.

_STYLE_PROFILE = {"styles": []}


def get_style_profile() -> dict:
    """Return the current in-memory style profile."""
    return _STYLE_PROFILE


def reset_style_profile() -> None:
    """Clear the style profile (used by tests and to start a new user session)."""
    _STYLE_PROFILE["styles"] = []


def _update_style_profile(new_prefs: list) -> list:
    """Merge new style keywords into the profile (case-insensitive dedup).

    Returns the updated list of remembered styles.
    """
    for pref in new_prefs or []:
        cleaned = pref.strip().lower()
        if cleaned and cleaned not in _STYLE_PROFILE["styles"]:
            _STYLE_PROFILE["styles"].append(cleaned)
    return _STYLE_PROFILE["styles"]


# ── query parsing ─────────────────────────────────────────────────────────────

def parse_query(query: str) -> dict | None:
    """
    Use the LLM to extract search parameters from a natural-language query.

    Returns a dict with keys:
        description (str): item keywords to search for
        size (str | None): requested size, or None if not specified
        max_price (float | None): price ceiling, or None if not specified
        style_prefs (list[str]): style keywords the user mentions (e.g. grunge,
            baggy, y2k), or an empty list if none — used by style memory.

    Returns None if the query can't be parsed (bad JSON, no description, or an
    API error) so the planning loop can report the failure to the user.
    """
    prompt = (
        "Extract thrift-search parameters from the user's request. "
        "Return ONLY a JSON object with exactly these keys:\n"
        '  "description": a string of item keywords (e.g. "vintage graphic tee"),\n'
        '  "size": the requested size as a string, or null if none is mentioned,\n'
        '  "max_price": the price ceiling as a number, or null if none is mentioned,\n'
        '  "style_prefs": a list of style descriptors the user mentions '
        '(e.g. ["grunge", "baggy"]), or [] if none.\n\n'
        f"User request: {query}"
    )

    try:
        raw = _chat(
            [
                {"role": "system", "content": "You extract structured search filters from text."},
                {"role": "user", "content": prompt},
            ],
            temperature=0,
        )
        # Tolerate ```json ... ``` fences around the JSON.
        text = raw.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[len("json"):]
        parsed = json.loads(text.strip())

        description = (parsed.get("description") or "").strip()
        if not description:
            return None

        size = parsed.get("size")
        size = size.strip() if isinstance(size, str) and size.strip() else None

        max_price = parsed.get("max_price")
        max_price = float(max_price) if max_price is not None else None

        style_prefs = parsed.get("style_prefs") or []
        if not isinstance(style_prefs, list):
            style_prefs = []
        style_prefs = [str(p).strip() for p in style_prefs if str(p).strip()]

        return {
            "description": description,
            "size": size,
            "max_price": max_price,
            "style_prefs": style_prefs,
        }
    except Exception:
        return None


# ── session state ─────────────────────────────────────────────────────────────

def _new_session(query: str, wardrobe: dict) -> dict:
    """
    Initialize and return a fresh session dict for one user interaction.

    The session dict is the single source of truth for everything that happens
    during a run — it stores the original query, parsed parameters, tool results,
    and any error that caused early termination.

    You may add fields to this dict as needed for your implementation.
    """
    return {
        "query": query,              # original user query
        "parsed": {},                # extracted description / size / max_price
        "search_results": [],        # list of matching listing dicts
        "selected_item": None,       # top result, passed into suggest_outfit
        "wardrobe": wardrobe,        # user's wardrobe dict
        "outfit_suggestion": None,   # string returned by suggest_outfit
        "fit_card": None,            # string returned by create_fit_card
        "error": None,               # set if the interaction ended early
        "notice": None,              # stretch: retry-fallback explanation
        "price_assessment": None,    # stretch: compare_price result string
        "style_profile": [],         # stretch: remembered style prefs snapshot
    }


# ── planning loop ─────────────────────────────────────────────────────────────

def run_agent(query: str, wardrobe: dict) -> dict:
    """
    Main agent entry point. Runs the FitFindr planning loop for a single
    user interaction and returns the completed session dict.

    Args:
        query:    Natural language user request
                  (e.g., "vintage graphic tee under $30, size M")
        wardrobe: User's wardrobe dict — use get_example_wardrobe() or
                  get_empty_wardrobe() from utils/data_loader.py

    Returns:
        The session dict after the interaction completes. Check session["error"]
        first — if it is not None, the interaction ended early and the other
        output fields (outfit_suggestion, fit_card) will be None.

    TODO — implement this function using the planning loop you designed in planning.md:

        Step 1: Initialize the session with _new_session().

        Step 2: Parse the user's query to extract a description, size, and
                max_price. You can use regex, string splitting, or ask the LLM
                to parse it — document your choice in planning.md.
                Store the result in session["parsed"].

        Step 3: Call search_listings() with the parsed parameters.
                Store results in session["search_results"].
                If no results: set session["error"] to a helpful message and
                return the session early. Do NOT proceed to suggest_outfit
                with empty input.

        Step 4: Select the item to use (e.g., the top result).
                Store it in session["selected_item"].

        Step 5: Call suggest_outfit() with the selected item and wardrobe.
                Store the result in session["outfit_suggestion"].

        Step 6: Call create_fit_card() with the outfit suggestion and selected item.
                Store the result in session["fit_card"].

        Step 7: Return the session.

    Before writing code, complete the Planning Loop and State Management sections
    of planning.md — your implementation should match what you described there.
    """
    # Step 1: fresh session.
    session = _new_session(query, wardrobe)

    # Step 2: parse the query into search parameters.
    parsed = parse_query(query) if query and query.strip() else None
    if not parsed:
        session["error"] = (
            "Sorry, I didn't quite catch what you're looking for — try describing "
            "the item, and add a size or budget if you have one."
        )
        return session
    session["parsed"] = parsed

    # Stretch (style memory): remember style prefs from this query and carry
    # forward anything remembered from earlier queries this app run.
    _update_style_profile(parsed["style_prefs"])
    session["style_profile"] = list(get_style_profile()["styles"])

    # Step 3: search listings. No matches → retry with loosened filters before
    # giving up, and don't call the later tools if nothing turns up at all.
    results = search_listings(parsed["description"], parsed["size"], parsed["max_price"])
    session["search_results"] = results
    if not results:
        results = _search_with_fallback(session, parsed)
        if not results:
            session["error"] = (
                "I couldn't find any listings matching that. Try a higher budget, a "
                "different size, or simpler keywords."
            )
            return session
        session["search_results"] = results

    # Step 4: select the top result.
    session["selected_item"] = results[0]

    # Stretch (price comparison): assess whether the price is fair.
    session["price_assessment"] = compare_price(session["selected_item"])

    # Step 5: suggest an outfit using the selected item, wardrobe, and remembered style.
    outfit = suggest_outfit(
        session["selected_item"], wardrobe, style_profile=session["style_profile"]
    )
    if not outfit or not outfit.strip():
        session["error"] = (
            "I found the item but couldn't put an outfit together just now — "
            "please try again in a moment."
        )
        return session
    session["outfit_suggestion"] = outfit

    # Step 6: turn the outfit into a shareable fit card.
    session["fit_card"] = create_fit_card(outfit, session["selected_item"])

    # Step 7: done.
    return session


def _search_with_fallback(session: dict, parsed: dict) -> list:
    """Retry search with loosened constraints when the exact query found nothing.

    First drops the size filter, then drops the price cap. On success, records a
    user-facing explanation in session["notice"]. Returns the matches (or []).
    """
    # Retry 1: drop the size filter (if one was applied).
    if parsed["size"] is not None:
        results = search_listings(parsed["description"], None, parsed["max_price"])
        if results:
            session["notice"] = (
                f"No exact matches in size {parsed['size']}, so I dropped the size "
                "filter to show you these."
            )
            return results

    # Retry 2: drop the price cap (if one was applied).
    if parsed["max_price"] is not None:
        results = search_listings(parsed["description"], None, None)
        if results:
            session["notice"] = (
                f"No matches under ${parsed['max_price']:.2f}, so I relaxed the "
                "budget (and size) to show you these."
            )
            return results

    return []


# ── CLI test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from utils.data_loader import get_example_wardrobe, get_empty_wardrobe

    print("=== Happy path: graphic tee ===\n")
    session = run_agent(
        query="looking for a vintage graphic tee under $30",
        wardrobe=get_example_wardrobe(),
    )
    if session["error"]:
        print(f"Error: {session['error']}")
    else:
        if session["notice"]:
            print(f"Notice: {session['notice']}\n")
        print(f"Found: {session['selected_item']['title']}")
        print(f"Price check: {session['price_assessment']}")
        print(f"\nOutfit: {session['outfit_suggestion']}")
        print(f"\nFit card: {session['fit_card']}")
        print(f"\nStyle memory: {session['style_profile']}")

    print("\n\n=== Retry-fallback path: impossible size ===\n")
    reset_style_profile()
    session_r = run_agent(
        query="vintage graphic tee size XXS under $50",
        wardrobe=get_example_wardrobe(),
    )
    print(f"Notice: {session_r['notice']}")
    print(f"Found: {session_r['selected_item'] and session_r['selected_item']['title']}")

    print("\n\n=== No-results path ===\n")
    session2 = run_agent(
        query="designer ballgown size XXS under $5",
        wardrobe=get_example_wardrobe(),
    )
    print(f"Error message: {session2['error']}")
