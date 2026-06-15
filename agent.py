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

import re
from typing import Any

from tools import search_listings, suggest_outfit, create_fit_card


# ── query parsing ─────────────────────────────────────────────────────────────

def _parse_query(query: str) -> dict:
    """
    Extract a search description plus an optional size and max_price from a
    natural-language query. Size and max_price are only set when the user
    actually mentions them — otherwise they stay None.
    """
    text = query or ""

    # max_price: "under $30", "below 25", "max $40", "up to 50", or a bare "$30".
    price_match = re.search(
        r"(?:under|below|less than|max(?:imum)?|up to|cheaper than|<=?)\s*\$?\s*(\d+(?:\.\d+)?)",
        text,
        re.IGNORECASE,
    )
    if not price_match:
        price_match = re.search(r"\$\s*(\d+(?:\.\d+)?)", text)
    max_price = float(price_match.group(1)) if price_match else None

    # size: "size M", "size XXS", "size W30".
    size_match = re.search(r"\bsize[:\s]+([A-Za-z0-9/]+)", text, re.IGNORECASE)
    size = size_match.group(1).upper() if size_match else None

    # description: the query with the size/price phrases stripped out.
    description = text
    if price_match:
        description = description.replace(price_match.group(0), " ")
    if size_match:
        description = description.replace(size_match.group(0), " ")
    description = re.sub(r"\s+", " ", description).strip()

    return {"description": description, "size": size, "max_price": max_price}


# ── session state ─────────────────────────────────────────────────────────────

def _new_session(query: str, wardrobe: dict) -> dict[str, Any]:
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
    }


# ── planning loop ─────────────────────────────────────────────────────────────

def run_agent(query: str, wardrobe: dict) -> dict[str, Any]:
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
    # Step 1: initialize the session — the single source of truth for this run.
    session = _new_session(query, wardrobe)

    # Step 2: parse the query into search parameters.
    parsed = _parse_query(query)
    session["parsed"] = parsed

    # Step 3: search listings. If nothing matches, stop here — do not proceed
    # to suggest_outfit with empty input.
    results = search_listings(
        description=parsed["description"],
        size=parsed["size"],
        max_price=parsed["max_price"],
    )
    session["search_results"] = results
    if not results:
        session["error"] = (
            "No listings matched your search. Try broadening the style, size, or price."
        )
        return session

    # Step 4: select the top-ranked listing to style.
    session["selected_item"] = results[0]

    # (Planning step 6) Empty wardrobe — found an item but nothing to style it
    # with. Stop before suggest_outfit / create_fit_card.
    if not (wardrobe or {}).get("items"):
        session["error"] = (
            "I found an item, but I need wardrobe pieces to style it. "
            "Add items to your closet or use the example wardrobe for testing."
        )
        return session

    # Step 5: suggest an outfit from the wardrobe. suggest_outfit returns None
    # when it can't build one — treat that as an early exit, not a crash.
    outfit = suggest_outfit(session["selected_item"], wardrobe)
    if not outfit:
        session["error"] = (
            "I found the item, but couldn't build a compatible outfit from the wardrobe."
        )
        return session
    session["outfit_suggestion"] = outfit

    # Step 6: turn the outfit into a shareable fit-card caption. create_fit_card
    # returns an "Error: ..." string rather than raising on bad input.
    fit_card = create_fit_card(outfit, session["selected_item"])
    if not fit_card or fit_card.lower().startswith("error"):
        session["error"] = (
            "I found the item and built an outfit, but couldn't generate a caption."
        )
        return session
    session["fit_card"] = fit_card

    # Step 7: success — every field is populated and error stays None.
    return session


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
        outfit = session["outfit_suggestion"]
        recommendation = outfit["recommendation"] if isinstance(outfit, dict) else outfit
        print(f"Found: {session['selected_item']['title']}")
        print(f"\nOutfit: {recommendation}")
        print(f"\nFit card: {session['fit_card']}")

    print("\n\n=== No-results path ===\n")
    session2 = run_agent(
        query="designer ballgown size XXS under $5",
        wardrobe=get_example_wardrobe(),
    )
    print(f"Error message: {session2['error']}")
