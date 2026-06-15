"""
tools.py

The three required FitFindr tools. Each tool is a standalone function that
can be called and tested independently before being wired into the agent loop.

Complete and test each tool before moving to agent.py.

Tools:
    search_listings(description, size, max_price)  → list[dict]
    suggest_outfit(new_item, wardrobe)              → str
    create_fit_card(outfit, new_item)               → str
"""

import os
import re

from dotenv import load_dotenv
from groq import Groq

from utils.data_loader import load_listings

load_dotenv()


# ── Groq client ───────────────────────────────────────────────────────────────

def _get_groq_client():
    """Initialize and return a Groq client using GROQ_API_KEY from .env."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not set. Add it to a .env file in the project root."
        )
    return Groq(api_key=api_key)


# ── Tool 1: search_listings ───────────────────────────────────────────────────

def search_listings(
    description: str,
    size: str | None = None,
    max_price: float | None = None,
) -> list[dict]:
    """
    Search the mock listings dataset for items matching the description,
    optional size, and optional price ceiling.

    Args:
        description: Keywords describing what the user is looking for
                     (e.g., "vintage graphic tee").
        size:        Size string to filter by, or None to skip size filtering.
                     Matching is case-insensitive (e.g., "M" matches "S/M").
        max_price:   Maximum price (inclusive), or None to skip price filtering.

    Returns:
        A list of matching listing dicts, sorted by relevance (best match first).
        Returns an empty list if nothing matches — does NOT raise an exception.

    Each listing dict has the following fields:
        id, title, description, category, style_tags (list), size,
        condition, price (float), colors (list), brand, platform

    TODO:
        1. Load all listings with load_listings().
        2. Filter by max_price and size (if provided).
        3. Score each remaining listing by keyword overlap with `description`.
        4. Drop any listings with a score of 0 (no relevant matches).
        5. Sort by score, highest first, and return the listing dicts.

    Before writing code, fill in the Tool 1 section of planning.md.
    """
    listings = load_listings()

    # Tokenize the search description into lowercase keywords.
    keywords = [tok for tok in re.split(r"[^a-z0-9]+", (description or "").lower()) if tok]

    results = []
    for listing in listings:
        # --- Price filter (optional, inclusive cap) ---
        if max_price is not None and listing.get("price", 0) > max_price:
            continue

        # --- Size filter (optional, case-insensitive substring match) ---
        if size is not None:
            listing_size = str(listing.get("size", "")).lower()
            if size.lower() not in listing_size:
                continue

        # --- Relevance scoring by keyword overlap ---
        title = str(listing.get("title", "")).lower()
        desc = str(listing.get("description", "")).lower()
        tags = [str(t).lower() for t in listing.get("style_tags", [])]
        tag_blob = " ".join(tags)

        score = 0
        for kw in keywords:
            if kw in tags:
                score += 3          # exact style-tag hit is the strongest signal
            elif kw in tag_blob:
                score += 2          # partial tag hit (e.g. "graphic" in "graphic tee")
            if kw in title:
                score += 2          # title mention
            if kw in desc:
                score += 1          # description mention

        # An empty/whitespace description means "match all" remaining listings.
        if keywords and score == 0:
            continue

        results.append((score, listing))

    # Highest score first; stable sort preserves dataset order on ties.
    results.sort(key=lambda pair: pair[0], reverse=True)
    return [listing for _, listing in results]


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

def suggest_outfit(new_item: dict, wardrobe: dict) -> dict | str:
    """
    Given a thrifted item and the user's wardrobe, suggest a complete outfit.

    Args:
        new_item: A listing dict (the item the user is considering buying).
        wardrobe: A wardrobe dict with an 'items' key containing a list of
                  wardrobe item dicts. May be empty — handled gracefully.

    Returns:
        When the wardrobe HAS items: an outfit dict with
            - "recommendation": a styling string that names the new item and
              explains how to wear it with the chosen wardrobe pieces.
            - "pieces": the list of wardrobe item dicts used in the outfit.
        When the wardrobe is EMPTY: a plain non-empty string of general styling
        advice for the item (what to pair it with, what vibe it suits) — never
        raises an exception and never returns an empty string.
    """
    # 1. Empty-wardrobe guard: there are no pieces to build a specific outfit
    #    from, so offer general styling advice for the item instead of failing.
    items = (wardrobe or {}).get("items") or []
    if not items:
        item_name = new_item.get("title", "this piece")
        prompt = (
            f"A shopper is considering this thrifted item: {item_name} "
            f"(category: {new_item.get('category', 'n/a')}; "
            f"colors: {', '.join(new_item.get('colors', [])) or 'n/a'}; "
            f"style: {', '.join(new_item.get('style_tags', [])) or 'n/a'}).\n\n"
            "They have no wardrobe saved yet, so give general styling advice: what "
            f"kinds of pieces pair well with the {item_name}, what vibe it suits, and "
            "how to build an outfit around it. Keep it to 3-4 friendly sentences."
        )
        client = _get_groq_client()
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "You are a concise, enthusiastic personal stylist."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
        )
        return response.choices[0].message.content.strip()

    # 2. Score each wardrobe piece by how well it pairs with the new item:
    #    shared style_tags and matching colors both raise the score.
    new_tags = {str(t).lower() for t in new_item.get("style_tags", [])}
    new_colors = {str(c).lower() for c in new_item.get("colors", [])}

    def score(piece: dict) -> float:
        piece_tags = {str(t).lower() for t in piece.get("style_tags", [])}
        piece_colors = {str(c).lower() for c in piece.get("colors", [])}
        return 2.0 * len(new_tags & piece_tags) + 1.5 * len(new_colors & piece_colors)

    # 3. Pick compatible pieces: one per complementary category (so the outfit is
    #    head-to-toe, not two tops), taking the best-scoring piece in each slot.
    new_category = str(new_item.get("category", "")).lower()
    pieces: list[dict] = []
    for category in ["tops", "bottoms", "shoes", "outerwear", "accessories"]:
        if category == new_category:
            continue  # the new item already fills this slot
        candidates = [p for p in items if str(p.get("category", "")).lower() == category]
        if candidates:
            pieces.append(max(candidates, key=score))

    # Fallback: if categories were sparse, use the top-scoring pieces overall.
    if not pieces:
        pieces = sorted(items, key=score, reverse=True)[:4]

    # 4. Ask the LLM to turn the chosen pieces into a styling recommendation.
    item_name = new_item.get("title", "this piece")
    piece_lines = "\n".join(
        f"- {p.get('name', 'item')} ({p.get('category', 'n/a')}, "
        f"colors: {', '.join(p.get('colors', [])) or 'n/a'})"
        for p in pieces
    )
    prompt = (
        f"The user is considering buying this thrifted item: {item_name} "
        f"(colors: {', '.join(new_item.get('colors', [])) or 'n/a'}; "
        f"style: {', '.join(new_item.get('style_tags', [])) or 'n/a'}).\n\n"
        f"From their wardrobe, these pieces pair well with it:\n{piece_lines}\n\n"
        f"Suggest one complete outfit built around the {item_name}. Name the "
        f"specific wardrobe pieces, explain how to wear them together, and keep "
        f"it to 3-4 sentences of friendly, concrete styling advice."
    )

    client = _get_groq_client()
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": "You are a concise, enthusiastic personal stylist."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.7,
    )
    recommendation = response.choices[0].message.content.strip()

    # 5. Return the outfit object: a recommendation string + the pieces used.
    return {"recommendation": recommendation, "pieces": pieces}


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

def create_fit_card(outfit: dict, new_item: dict) -> str:
    """
    Generate a short, shareable outfit caption for the thrifted find.

    Args:
        outfit:   The outfit returned by suggest_outfit() — a dict with a
                  "recommendation" string (a plain string is also accepted).
        new_item: The listing dict for the thrifted item.

    Returns:
        A 2–4 sentence string usable as an Instagram/TikTok caption.
        If outfit is None / empty / missing its recommendation, returns a
        descriptive error message string — does NOT raise an exception.

    The caption:
    - Feels casual and authentic (like a real OOTD post, not a product listing)
    - Mentions the item name, price, and platform naturally (once each)
    - Captures the outfit vibe in specific terms
    - Varies between calls on the same input (higher LLM temperature)
    """
    # 1. Guard: pull the recommendation text out of the outfit, whether it's a
    #    dict (from suggest_outfit) or a plain string. Bail out gracefully if
    #    there's nothing to caption — don't guess, don't crash.
    if isinstance(outfit, dict):
        recommendation = outfit.get("recommendation", "")
    elif isinstance(outfit, str):
        recommendation = outfit
    else:
        recommendation = ""

    if not recommendation or not recommendation.strip():
        return "Error: no outfit to caption — provide an outfit with a recommendation."

    # 2. Build the prompt with the item details and the outfit recommendation.
    title = new_item.get("title", "this find")
    price = new_item.get("price", "?")
    platform = new_item.get("platform", "online")
    prompt = (
        "Write a short, casual Instagram/TikTok OOTD caption for a thrifted find.\n\n"
        f"Item: {title}\n"
        f"Price: ${price}\n"
        f"Platform: {platform}\n"
        f"Outfit: {recommendation}\n\n"
        "Rules: 2-4 sentences, casual and authentic (not a product description). "
        f"Mention the item name, the ${price} price, and that it's from {platform} "
        "naturally — once each. Capture the vibe in specific terms. Add a couple of "
        "fitting hashtags at the end."
    )

    # 3. Call the LLM with a high temperature so captions vary on repeat runs.
    client = _get_groq_client()
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": "You write fun, authentic social media OOTD captions."},
            {"role": "user", "content": prompt},
        ],
        temperature=1.0,
    )
    return response.choices[0].message.content.strip()
