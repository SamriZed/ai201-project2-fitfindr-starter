# tests/test_tools.py
"""
Tests for the three FitFindr tools in tools.py.

Each tool has at least one test per documented failure mode:
  - search_listings: no matches, over-budget items, no size match
  - suggest_outfit:  empty wardrobe, missing 'items', None wardrobe
  - create_fit_card: None outfit, empty recommendation, wrong type

The two LLM-backed tools (suggest_outfit, create_fit_card) are tested against a
mocked Groq client so the suite is fast, deterministic, and needs no API key.
The failure-mode guards all return before the LLM is ever called, so those
tests need no mock at all.
"""

import pytest

import tools
from tools import search_listings, suggest_outfit, create_fit_card
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe


# ── Fake Groq client ────────────────────────────────────────────────────────
# Mirrors the shape tools.py uses: client.chat.completions.create(...).choices[0].message.content

class _FakeGroqClient:
    def __init__(self, content):
        self._content = content
        self.calls = []  # records kwargs of each create() call for assertions

        class _Chat:
            def __init__(self, outer):
                self.completions = outer

        self.chat = _Chat(self)

    def create(self, **kwargs):
        self.calls.append(kwargs)

        class _Msg:
            content = self._content

        class _Choice:
            message = _Msg()

        class _Resp:
            choices = [_Choice()]

        return _Resp()


@pytest.fixture
def fake_groq(monkeypatch):
    """Patch tools._get_groq_client so LLM-backed tools return canned content."""
    client = _FakeGroqClient(
        "Just scored this thrifted gem and styled it up — obsessed! #OOTD"
    )
    monkeypatch.setattr(tools, "_get_groq_client", lambda: client)
    return client


@pytest.fixture
def sample_item():
    """A single listing used as the 'new item' across tests."""
    return search_listings("graphic tee")[0]


# ── Tool 1: search_listings ───────────────────────────────────────────────────

class TestSearchListings:
    def test_returns_results_for_matching_query(self):
        results = search_listings("vintage graphic tee", size=None, max_price=50)
        assert isinstance(results, list)
        assert len(results) > 0

    def test_results_include_required_fields(self):
        required = {"id", "title", "category", "price", "colors", "style_tags", "platform"}
        for item in search_listings("vintage"):
            assert required.issubset(item.keys())

    # Failure mode: nothing matches → empty list, NOT an exception.
    def test_no_matches_returns_empty_list(self):
        results = search_listings("designer ballgown", size="XXS", max_price=5)
        assert results == []

    def test_unmatchable_keyword_returns_empty_list(self):
        assert search_listings("zzzznotarealkeyword9000") == []

    # Failure mode: max_price must never let an over-budget item through.
    def test_price_filter_excludes_over_budget(self):
        results = search_listings("jacket", size=None, max_price=10)
        assert all(item["price"] <= 10 for item in results)

    # Failure mode: a size with no matches → empty list, not a crash.
    def test_size_filter_with_no_match_returns_empty(self):
        assert search_listings("tee", size="QXL-impossible") == []

    def test_optional_params_can_be_omitted(self):
        # size and max_price default to None — call with description only.
        results = search_listings("vintage")
        assert isinstance(results, list) and len(results) > 0


# ── Tool 2: suggest_outfit ──────────────────────────────────────────────────

class TestSuggestOutfit:
    # Failure mode: empty wardrobe → general styling advice as a non-empty
    # string (not None, not "", no crash).
    def test_empty_wardrobe_returns_advice_string(self, sample_item, fake_groq):
        result = suggest_outfit(sample_item, get_empty_wardrobe())
        assert isinstance(result, str) and result.strip()

    # Failure mode: wardrobe dict missing the 'items' key → treated as empty,
    # returns advice string, no KeyError.
    def test_wardrobe_without_items_key_returns_advice_string(self, sample_item, fake_groq):
        result = suggest_outfit(sample_item, {})
        assert isinstance(result, str) and result.strip()

    # Failure mode: wardrobe is None entirely → advice string, no AttributeError.
    def test_none_wardrobe_returns_advice_string(self, sample_item, fake_groq):
        result = suggest_outfit(sample_item, None)
        assert isinstance(result, str) and result.strip()

    def test_valid_wardrobe_returns_outfit_dict(self, sample_item, fake_groq):
        outfit = suggest_outfit(sample_item, get_example_wardrobe())
        assert isinstance(outfit, dict)
        assert isinstance(outfit["recommendation"], str) and outfit["recommendation"]
        assert isinstance(outfit["pieces"], list) and len(outfit["pieces"]) > 0

    def test_pieces_are_drawn_from_the_wardrobe(self, sample_item, fake_groq):
        wardrobe = get_example_wardrobe()
        valid_ids = {p["id"] for p in wardrobe["items"]}
        outfit = suggest_outfit(sample_item, wardrobe)
        assert all(piece["id"] in valid_ids for piece in outfit["pieces"])

    def test_empty_wardrobe_calls_the_llm_for_general_advice(self, sample_item, fake_groq):
        suggest_outfit(sample_item, get_empty_wardrobe())
        assert len(fake_groq.calls) == 1  # one LLM call to generate general advice


# ── Tool 3: create_fit_card ─────────────────────────────────────────────────

class TestCreateFitCard:
    # Failure mode: outfit is None → error string, no crash.
    def test_none_outfit_returns_error_string(self, sample_item):
        result = create_fit_card(None, sample_item)
        assert isinstance(result, str) and result.lower().startswith("error")

    # Failure mode: outfit dict with an empty/whitespace recommendation.
    def test_empty_recommendation_returns_error_string(self, sample_item):
        result = create_fit_card({"recommendation": "   "}, sample_item)
        assert result.lower().startswith("error")

    # Failure mode: outfit dict missing the recommendation key entirely.
    def test_missing_recommendation_key_returns_error_string(self, sample_item):
        result = create_fit_card({"pieces": []}, sample_item)
        assert result.lower().startswith("error")

    # Failure mode: outfit of an unexpected type (not dict/str) → error string.
    def test_wrong_type_outfit_returns_error_string(self, sample_item):
        assert create_fit_card(42, sample_item).lower().startswith("error")

    def test_invalid_outfit_never_calls_the_llm(self, sample_item, fake_groq):
        create_fit_card(None, sample_item)
        assert fake_groq.calls == []  # guard returns before any LLM call

    def test_valid_outfit_returns_caption_string(self, sample_item, fake_groq):
        outfit = {"recommendation": "Pair it with baggy jeans and combat boots.", "pieces": []}
        caption = create_fit_card(outfit, sample_item)
        assert isinstance(caption, str) and caption.strip()

    def test_accepts_plain_string_outfit(self, sample_item, fake_groq):
        # create_fit_card tolerates a plain recommendation string, not just a dict.
        caption = create_fit_card("Wear it with dark denim.", sample_item)
        assert isinstance(caption, str) and caption.strip()

    def test_prompt_includes_item_title_price_and_platform(self, sample_item, fake_groq):
        outfit = {"recommendation": "Layer it under a jacket.", "pieces": []}
        create_fit_card(outfit, sample_item)
        # The function passes through the LLM, but we can assert the *prompt* it
        # built carries the item facts the caption is required to mention.
        sent_prompt = fake_groq.calls[0]["messages"][-1]["content"]
        assert sample_item["title"] in sent_prompt
        assert str(sample_item["price"]) in sent_prompt
        assert sample_item["platform"] in sent_prompt
