# tests/test_tools.py
"""Isolation tests for the three FitFindr tools — at least one per failure mode.

Run from the project root with:  pytest tests/

Note: test_suggest_outfit_empty_wardrobe calls the live Groq API, so it needs
GROQ_API_KEY in .env and network access. The search tests and the empty-outfit
guard test are deterministic and run offline.
"""

from tools import search_listings, suggest_outfit, create_fit_card, compare_price
from utils.data_loader import load_listings, get_empty_wardrobe
from agent import _update_style_profile, reset_style_profile


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


# ── compare_price (stretch) ─────────────────────────────────────────────────────

def test_compare_price_returns_reasoning():
    item = load_listings()[0]
    result = compare_price(item)
    assert isinstance(result, str)
    # The reasoning string names a verdict and cites the comparison.
    assert any(v in result for v in ("Great deal", "Fair", "Pricey"))
    assert "median" in result


def test_compare_price_low_price_is_great_deal():
    item = dict(load_listings()[0], id="fake", category="tops", price=1.0)
    assert compare_price(item).startswith("Great deal")


def test_compare_price_high_price_is_pricey():
    item = dict(load_listings()[0], id="fake", category="tops", price=999.0)
    assert compare_price(item).startswith("Pricey")


# ── style profile memory (stretch) ──────────────────────────────────────────────

def test_update_style_profile_accumulates():
    # Merges across calls, dedups case-insensitively, lowercases.
    reset_style_profile()
    _update_style_profile(["Grunge", "baggy"])
    result = _update_style_profile(["grunge", "y2k"])
    assert result == ["grunge", "baggy", "y2k"]
    reset_style_profile()
