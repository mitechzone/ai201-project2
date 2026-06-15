# tests/test_tools.py
"""Isolation tests for the three FitFindr tools — at least one per failure mode.

Run from the project root with:  pytest tests/

Note: test_suggest_outfit_empty_wardrobe calls the live Groq API, so it needs
GROQ_API_KEY in .env and network access. The search tests and the empty-outfit
guard test are deterministic and run offline.
"""

from tools import search_listings, suggest_outfit, create_fit_card
from utils.data_loader import load_listings, get_empty_wardrobe


# ── search_listings ────────────────────────────────────────────────────────────

def test_search_returns_results():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert isinstance(results, list)
    assert len(results) > 0


def test_search_empty_results():
    # Failure mode: no listing matches → empty list, no exception.
    results = search_listings("designer ballgown", size="XXS", max_price=5)
    assert results == []


def test_search_price_filter():
    results = search_listings("jacket", size=None, max_price=10)
    assert all(item["price"] <= 10 for item in results)


# ── suggest_outfit ──────────────────────────────────────────────────────────────

def test_suggest_outfit_empty_wardrobe():
    # Failure mode: empty wardrobe → general advice string, not a crash. (Calls the API.)
    item = load_listings()[0]
    result = suggest_outfit(item, get_empty_wardrobe())
    assert isinstance(result, str)
    assert result.strip() != ""


# ── create_fit_card ─────────────────────────────────────────────────────────────

def test_create_fit_card_empty_outfit():
    # Failure mode: incomplete outfit input → descriptive error string, not a crash.
    item = load_listings()[0]
    result = create_fit_card("", item)
    assert isinstance(result, str)
    assert result.strip() != ""
