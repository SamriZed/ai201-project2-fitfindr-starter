# FitFindr — Starter Kit

This starter kit contains everything you need to begin Project 2.

## What's Included

```
ai201-project2-fitfindr-starter/
├── data/
│   ├── listings.json          # 40 mock secondhand listings
│   └── wardrobe_schema.json   # Wardrobe format + example wardrobe
├── utils/
│   └── data_loader.py         # Helper functions for loading the data
├── planning.md                # Your planning template — fill this out first
└── requirements.txt           # Python dependencies
```

## Setup

```bash
pip install -r requirements.txt
```

Set your Groq API key in a `.env` file (get a free key at [console.groq.com](https://console.groq.com)):
```
GROQ_API_KEY=your_key_here
```

## The Mock Listings Dataset

`data/listings.json` contains 40 mock secondhand listings across categories (tops, bottoms, outerwear, shoes, accessories) and styles (vintage, y2k, grunge, cottagecore, streetwear, and more).

Each listing has: `id`, `title`, `description`, `category`, `style_tags`, `size`, `condition`, `price`, `colors`, `brand`, and `platform`.

Load it with:
```python
from utils.data_loader import load_listings
listings = load_listings()
```

## The Wardrobe Schema

`data/wardrobe_schema.json` defines the format your agent uses to represent a user's existing wardrobe. It includes:

- `schema`: field definitions for a wardrobe item
- `example_wardrobe`: a sample wardrobe with 10 items you can use for testing
- `empty_wardrobe`: a starting template for a new user

Load an example wardrobe with:
```python
from utils.data_loader import get_example_wardrobe
wardrobe = get_example_wardrobe()
```

## Where to Start

1. **Read `planning.md` and fill it out before writing any code.**
2. Verify the data loads correctly by running `python utils/data_loader.py`.
3. Build and test each tool individually before connecting them through your planning loop.

Your implementation files go in this same directory. There's no required file structure for your agent code — organize it however makes sense for your design.

---

## Running the Agent

```bash
python app.py          # launch the Gradio web UI (open the localhost URL it prints)
python agent.py        # run the CLI demo (happy path + no-results path)
pytest                 # run the test suite
```

In the web UI, type a **natural-language** query — e.g. `vintage graphic tee under $30, size M`. The agent parses the size and price out of the sentence; it does not expect Python keyword syntax like `size='M'`.

## Tool Inventory

### 1. `search_listings`
- **Inputs:**
  - `description: str` — keywords describing the item (e.g. `"vintage graphic tee"`)
  - `size: str | None = None` — optional size filter; case-insensitive substring match (`"M"` matches `"S/M"`)
  - `max_price: float | None = None` — optional inclusive price cap
- **Output:** `list[dict]` — matching listing dicts sorted by relevance (best first); empty list if nothing matches.
- **Purpose:** Filter the mock dataset by optional size/price, score the rest by keyword overlap with the title, style tags, and description, drop zero-score listings, and return the ranked results.

### 2. `suggest_outfit`
- **Inputs:**
  - `new_item: dict` — a listing dict (the item being considered)
  - `wardrobe: dict` — a wardrobe dict with an `"items"` list (may be empty)
- **Output:** `dict | str`
  - Wardrobe **has** items → an outfit `dict`: `{"recommendation": str, "pieces": list[dict]}`
  - Wardrobe **empty** → a non-empty `str` of general styling advice
- **Purpose:** Score wardrobe pieces by shared `style_tags` and matching `colors`, pick one piece per complementary category (head-to-toe), and ask the LLM (Groq `llama-3.3-70b-versatile`) to write a styling recommendation. With no wardrobe, it falls back to general advice instead of failing.

### 3. `create_fit_card`
- **Inputs:**
  - `outfit: dict` — the outfit returned by `suggest_outfit` (a plain string is also accepted)
  - `new_item: dict` — the listing dict for the item
- **Output:** `str` — a 2–4 sentence casual caption naming the item, price, and platform; or an `"Error: ..."` string if the outfit is missing/empty.
- **Purpose:** Turn an outfit into a social-media-ready OOTD caption at high temperature (so repeat runs vary).

## Planning Loop

`run_agent(query: str, wardrobe: dict) -> dict` orchestrates the tools in one linear pass — no re-entry, no hardcoded values. Each step reads from `session` and writes its result back before the next step runs:

1. **Initialize** a fresh `session` dict.
2. **Parse** the query (`_parse_query`) into `description` / `size` / `max_price` using regex. Size and price are only set if the user actually mentions them.
3. **Search** with those parameters. If the result list is empty → set `error`, return early (no further tools run).
4. **Select** the top-ranked listing as `selected_item`.
5. **Guard the wardrobe:** if it has no items → set `error`, return early (before styling).
6. **Suggest an outfit** from `selected_item` + `wardrobe`. If it can't produce one → set `error`, return early.
7. **Create the fit card** from the outfit + item. If it returns an error string → set `error`, return a partial result.
8. **Return** the populated `session` (`error` stays `None` on success).

The key property: tools are **gated** by the previous step's result, so a query that finds nothing never reaches `suggest_outfit` or `create_fit_card`.

## State Management

There is a single source of truth — the `session` dict from `_new_session()`:

| Field | Written by | Holds |
|---|---|---|
| `query` | init | original user query |
| `parsed` | step 2 | `{description, size, max_price}` |
| `search_results` | step 3 | list returned by `search_listings` |
| `selected_item` | step 4 | top result (passed to both later tools) |
| `wardrobe` | init | the wardrobe dict |
| `outfit_suggestion` | step 6 | outfit dict from `suggest_outfit` |
| `fit_card` | step 7 | caption from `create_fit_card` |
| `error` | any early exit | user-facing message, else `None` |

State passes **by reference**: `session["selected_item"]` is the exact same dict object handed to `suggest_outfit` and `create_fit_card`, and `session["outfit_suggestion"]` is exactly what goes into `create_fit_card` — no copies, no re-fetching. `app.py`'s `handle_query` reads these fields off the returned session and maps them to the three UI panels.

## Error Handling

| Tool | Failure mode | Agent / tool response | Concrete example from testing |
|---|---|---|---|
| `search_listings` | No listings match the query | Returns `[]` (no exception). The agent sets `error` and returns before any other tool. | Query `"designer ballgown size XXS under $5"` → `search_listings` returns `[]` → agent `error` = `"No listings matched your search. Try broadening the style, size, or price."`, with `outfit_suggestion` and `fit_card` left `None`. |
| `suggest_outfit` | Wardrobe is empty | The **agent** guards this first and returns the "need wardrobe pieces" message. The **tool** itself, if called standalone, returns a general-advice string. | Standalone: `suggest_outfit(graphic_tee, get_empty_wardrobe())` returned `"I'm obsessed with this graphic tee... Pair it with distressed denim jeans and combat boots..."` (a non-empty string, no crash). |
| `create_fit_card` | Outfit is `None` / empty / missing `recommendation` | Returns a descriptive `"Error: ..."` string instead of raising or guessing. | `create_fit_card(None, item)` returned `"Error: no outfit to caption — provide an outfit with a recommendation."` |

All failure modes are covered by `tests/test_tools.py` (21 tests, at least one per failure mode), which mock the Groq client so the suite is fast and needs no API key.

## Spec Reflection

What matched the plan, and what changed once code met reality:

- **Search relevance vs. exact filters.** The plan described size as an "exact match," but real listing sizes are messy (`"S/M"`, `"XL (oversized)"`, `"W30 L30"`). I implemented size as a case-insensitive *substring* match so `"M"` sensibly matches `"S/M"`. Description matching became a weighted keyword score (style-tag hits > title > description) rather than a strict filter, which made ranking feel natural.
- **`suggest_outfit` return shape.** The original stub typed the return as `str`, but my plan called for an "outfit object." I settled on a `dict` (`{recommendation, pieces}`) so the agent and `create_fit_card` could use structured data, and made `create_fit_card` tolerant of a plain string too.
- **Empty-wardrobe behavior — a spec conflict I had to resolve.** My planning verification said the empty case should "return None or an error structure," but the tool spec said it should "offer general styling advice." Testing surfaced the contradiction. I chose **general advice as a plain string**, updated the tests, and updated `planning.md` to match — so docs, code, and tests now agree.
- **Two interfaces, two input formats.** A confusing moment in testing: calling `search_listings('ballgown', size='XXS', max_price=5)` (structured args) behaves differently from typing that literal text into the app box (one natural-language string the agent must parse). This clarified that query parsing belongs in the agent layer, and the UI expects natural language.

If I extended this: make the query parser more forgiving (e.g. accept `size=M`), add machine-readable `error` *codes* alongside the human messages, and add an opt-in integration test that hits the real LLM.

## AI Usage

I used **Claude (Claude Code)** to implement each component from the specs in `planning.md`. Below are specific instances showing what I provided, what it produced, and what I changed or overrode. (My up-front AI tool *plan* lives in `planning.md`; this section reports how closely the actual work followed it.)

### Instance 1 — `search_listings`
- **Input I gave:** The Tool 1 spec block from `planning.md` (inputs, return value, failure modes) and the instruction to use `load_listings()` from `utils/data_loader.py` rather than re-reading the file.
- **What it produced:** A function that loads listings, applies the optional size/price filters, scores each remaining listing by keyword overlap (style tags weighted highest, then title, then description), drops zero-score results, and returns them sorted by score.
- **What I changed/overrode:** My plan said size should be an *exact* match; I kept the AI's case-insensitive substring approach instead because the dataset's size strings are inconsistent. I verified the result against three queries (a match-all `"vintage"`, a price-capped query, and a no-match query) before trusting it.

### Instance 2 — `suggest_outfit` (and overriding my own spec)
- **Input I gave:** The Tool 2 spec block plus `data/wardrobe_schema.json` so the AI knew the wardrobe item fields (`name`, `category`, `colors`, `style_tags`).
- **What it produced:** A first version with several helper functions (a neutral-colors set, a `_compatibility_score`, a `_select_pieces`) plus the main function returning `{recommendation, pieces}`.
- **What I changed/overrode:** (a) I asked it to **consolidate** the helpers into one self-contained function because the extra functions were hard to follow. (b) More significantly, my planning verification said an empty wardrobe should return `None`, but the tool spec said it should give general advice — I **overrode the `None` behavior** and had it return a general-advice string instead, then updated the tests and `planning.md` to match.

### Instance 3 — `agent.py` planning loop
- **Input I gave:** The numbered TODO steps already in `agent.py` plus the "Planning Loop" and Architecture diagram sections of `planning.md`.
- **What it produced:** `run_agent()` wired to parse the query, call the three tools in order, store each result in the session dict, and branch early on no-results / empty-wardrobe / no-outfit.
- **What I changed/overrode:** I had it add the empty-wardrobe guard *before* `suggest_outfit` (matching my Architecture diagram's error branch) rather than relying on the tool's return value, and I confirmed via testing that a no-results query never calls the downstream tools.
