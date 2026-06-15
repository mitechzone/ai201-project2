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

from dotenv import load_dotenv
from groq import Groq

from utils.data_loader import load_listings

load_dotenv()

MODEL = "openai/gpt-oss-120b" # "llama-3.3-70b-versatile"


# ── Groq client ───────────────────────────────────────────────────────────────

def _get_groq_client():
    """Initialize and return a Groq client using GROQ_API_KEY from .env."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not set. Add it to a .env file in the project root."
        )
    return Groq(api_key=api_key)


def _chat(messages: list[dict], temperature: float) -> str:
    """Send a chat completion to Groq and return the response text.

    Shared call path for the LLM-backed tools.
    """
    client = _get_groq_client()
    response = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        temperature=temperature,
    )
    return response.choices[0].message.content


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

    # 1. Filter by price and size (when provided).
    if max_price is not None:
        listings = [l for l in listings if l["price"] <= max_price]
    if size is not None:
        listings = [l for l in listings if size.lower() in l["size"].lower()]

    # 2. Score by keyword overlap between the query and each listing's text.
    tokens = description.lower().split()
    scored = []
    for listing in listings:
        searchable = " ".join([
            listing["title"],
            listing["description"],
            " ".join(listing["style_tags"]),
            listing["category"],
        ]).lower()
        score = sum(1 for token in tokens if token in searchable)
        if score > 0:
            scored.append((score, listing))

    # 3. Sort by score (highest first) and return the listing dicts.
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [listing for _, listing in scored]


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

def suggest_outfit(new_item: dict, wardrobe: dict) -> str:
    """
    Given a thrifted item and the user's wardrobe, suggest 1–2 complete outfits.

    Args:
        new_item: A listing dict (the item the user is considering buying).
        wardrobe: A wardrobe dict with an 'items' key containing a list of
                  wardrobe item dicts. May be empty — handle this gracefully.

    Returns:
        A non-empty string with outfit suggestions.
        If the wardrobe is empty, offer general styling advice for the item
        rather than raising an exception or returning an empty string.

    TODO:
        1. Check whether wardrobe['items'] is empty.
        2. If empty: call the LLM with a prompt for general styling ideas
           (what kinds of items pair well, what vibe it suits, etc.).
        3. If not empty: format the wardrobe items into a prompt and ask
           the LLM to suggest specific outfit combinations using the new item
           and named pieces from the wardrobe.
        4. Return the LLM's response as a string.

    Before writing code, fill in the Tool 2 section of planning.md.
    """
    item_desc = (
        f"{new_item['title']} (category: {new_item['category']}, "
        f"colors: {', '.join(new_item['colors'])}, "
        f"style: {', '.join(new_item['style_tags'])})"
    )

    items = wardrobe.get("items", [])
    if not items:
        # Empty wardrobe → general styling advice rather than naming owned pieces.
        prompt = (
            f"A shopper is considering this secondhand item:\n{item_desc}\n\n"
            "They haven't told you what's in their wardrobe yet. Suggest how to "
            "style this piece in general terms: what kinds of items pair well "
            "with it, what vibe it suits, and one or two complete outfit ideas. "
            "Keep it to 2-4 sentences, friendly and concrete."
        )
    else:
        wardrobe_lines = "\n".join(
            f"- {it['name']} (category: {it['category']}, "
            f"colors: {', '.join(it['colors'])}, "
            f"style: {', '.join(it['style_tags'])})"
            for it in items
        )
        prompt = (
            f"A shopper is considering this secondhand item:\n{item_desc}\n\n"
            f"Here is their current wardrobe:\n{wardrobe_lines}\n\n"
            "Suggest 1-2 complete outfit combinations that pair the new item with "
            "specific named pieces from their wardrobe. Mention the wardrobe pieces "
            "by name. Keep it to 2-4 sentences, friendly and concrete."
        )

    try:
        suggestion = _chat(
            [
                {
                    "role": "system",
                    "content": "You are a thoughtful personal stylist for secondhand fashion.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
        )
    except Exception:
        # Graceful fallback — never raise, never return an empty string.
        return (
            f"Couldn't reach the styling advisor right now, but {new_item['title']} "
            "is versatile — try pairing it with simple basics in a neutral color "
            "and let the piece be the focal point of the look."
        )

    return suggestion.strip() if suggestion and suggestion.strip() else (
        f"{new_item['title']} pairs well with simple, neutral basics — let it be "
        "the statement piece of the outfit."
    )


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

def create_fit_card(outfit: str, new_item: dict) -> str:
    """
    Generate a short, shareable outfit caption for the thrifted find.

    Args:
        outfit:   The outfit suggestion string from suggest_outfit().
        new_item: The listing dict for the thrifted item.

    Returns:
        A 2–4 sentence string usable as an Instagram/TikTok caption.
        If outfit is empty or missing, return a descriptive error message
        string — do NOT raise an exception.

    The caption should:
    - Feel casual and authentic (like a real OOTD post, not a product description)
    - Mention the item name, price, and platform naturally (once each)
    - Capture the outfit vibe in specific terms
    - Sound different each time for different inputs (use higher LLM temperature)

    TODO:
        1. Guard against an empty or whitespace-only outfit string.
        2. Build a prompt that gives the LLM the item details and the outfit,
           and asks for a caption matching the style guidelines above.
        3. Call the LLM and return the response.

    Before writing code, fill in the Tool 3 section of planning.md.
    """
    # 1. Guard against an empty / whitespace-only outfit string.
    if not outfit or not outfit.strip():
        return (
            "I couldn't create a fit card yet — there's no outfit to caption. "
            "Pick an item and get a styling suggestion first, then try again."
        )

    # 2. Build the prompt from the item details and the outfit.
    prompt = (
        f"Write a short, casual social media caption (Instagram/TikTok OOTD style) "
        f"for a thrifted find.\n\n"
        f"Item: {new_item['title']}\n"
        f"Price: ${new_item['price']}\n"
        f"Platform: {new_item['platform']}\n"
        f"Outfit: {outfit}\n\n"
        "Guidelines: 2-4 sentences. Sound like a real person posting their outfit, "
        "not a product description. Mention the item, its price, and the platform "
        "naturally (once each). Capture the vibe in specific terms. Emojis welcome."
    )

    # 3. Call the LLM (higher temperature for variety) and return the caption.
    try:
        caption = _chat(
            [
                {
                    "role": "system",
                    "content": "You write fun, authentic outfit captions for thrifted fashion finds.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.8,
        )
    except Exception:
        return (
            f"snagged this {new_item['title'].lower()} off {new_item['platform']} "
            f"for ${new_item['price']} and i'm obsessed — full fit coming soon ✨"
        )

    return caption.strip() if caption and caption.strip() else (
        f"thrifted this {new_item['title'].lower()} off {new_item['platform']} "
        f"for ${new_item['price']} 🖤"
    )
