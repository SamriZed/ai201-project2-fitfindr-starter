# FitFindr — planning.md

> Complete this document before writing any implementation code.
> Your spec and agent diagram are what you'll use to direct AI tools (Claude, Copilot, etc.) to generate your implementation — the more specific they are, the more useful the generated code will be.
> Your planning.md will be reviewed as part of your submission.
> Update it before starting any stretch features.

---

## Tools

List every tool your agent will use. For each tool, fill in all four fields.
You must have at least 3 tools. The three required tools are listed — add any additional tools below them.

### Tool 1: search_listings

**What it does:**
<!-- Describe what this tool does in 1–2 sentences -->
Searches the mock marketplace data for listings that match the user's style request. It filters and ranks listings using the query text plus optional size and price constraints, then returns the best matches first.
**Input parameters:**
<!-- List each parameter, its type, and what it represents -->

- `description` (str): Required search phrase describing the item the user wants, such as "vintage graphic tee" or "wide-leg jeans".
- `size` (str): Optional size constraint to compare against each listing's `size` field, such as "M" or "W30 L30".
- `max_price` (float): Optional maximum price filter. Only listings at or below this price should be included.

**What it returns:**
<!-- Describe the return value — what fields does a result contain? -->
Returns a list of matching listing objects sorted by relevance. Each listing object includes `id`, `title`, `description`, `category`, `style_tags`, `size`, `condition`, `price`, `colors`, `brand`, and `platform`, and may also include a computed relevance score if the implementation uses one internally.
**What happens if it fails or returns nothing:**
<!-- What should the agent do if no listings match? -->
If no listings match the filters, return an empty list. The agent should stop the workflow immediately, tell the user that nothing matched, and suggest broadening the description, removing the size filter, or raising the price cap. It should not call `suggest_outfit` or `create_fit_card`.


---

### Tool 2: suggest_outfit

**What it does:**
<!-- Describe what this tool does in 1–2 sentences -->
Builds an outfit recommendation around the newly found listing by comparing it against the user's wardrobe. It should pick compatible wardrobe items, explain why they work together, and generate styling guidance in the user's preferred aesthetic.

**Input parameters:**
<!-- List each parameter, its type, and what it represents -->

- `new_item` (dict): The selected listing from `search_listings`, including at least `id`, `title`, `category`, `style_tags`, `colors`, `condition`, `price`, and `platform`.
- `wardrobe` (dict): The active wardrobe object in the schema from `data/wardrobe_schema.json`, with an `items` list of wardrobe items.

**What it returns:**
<!-- Describe the return value -->
Returns an outfit object with a short human-readable recommendation plus the wardrobe items used to build it. The output should include the recommended look, a list of matching wardrobe pieces, and optional styling notes such as tuck, layer, cuff, or accessory suggestions.

**What happens if it fails or returns nothing:**
<!-- What should the agent do if the wardrobe is empty or no outfit can be suggested? -->
If `wardrobe.items` is empty, or if no compatible outfit can be built, return `None` or an empty outfit structure with an error flag. The agent should tell the user that there is not enough wardrobe data to style the item, avoid calling `create_fit_card`, and either ask the user to add wardrobe items or fall back to a simple item-only summary.


---

### Tool 3: create_fit_card

**What it does:**
<!-- Describe what this tool does in 1–2 sentences -->
Creates a short, social-ready fit caption from the chosen listing and the suggested outfit. It should sound like a casual user post and mention the item, the vibe, and one or two styling details.

**Input parameters:**
<!-- List each parameter, its type, and what it represents -->
- `outfit` (dict): The outfit object returned by `suggest_outfit`, including the recommended look, supporting wardrobe pieces, and styling notes.
- `new_item` (dict): The selected listing from `search_listings`, including fields like `title`, `price`, `platform`, `category`, and `style_tags`.

**What it returns:**
<!-- Describe the return value -->
Returns a caption string or caption object for the fit card. The output should include the final post text and may optionally include metadata such as hashtags, tone, or a short title for display.

**What happens if it fails or returns nothing:**
<!-- What should the agent do if the outfit data is incomplete? -->
If `outfit` is missing, empty, or incomplete, return `None` or an error structure instead of guessing. The agent should stop before showing a fit card, keep the earlier search result if available, and tell the user that it needs more outfit information or a valid wardrobe match.

---

### Additional Tools (if any)

<!-- Copy the block above for any tools beyond the required three -->

---

## Planning Loop

**How does your agent decide which tool to call next?**
<!-- Describe the logic your planning loop uses. What does it look at? What conditions change its behavior? How does it know when it's done? -->
1. Read the user's message and extract a shopping query. Build `description` from the item and style terms, set `size` only if the user mentioned one, and set `max_price` only if the user gave a price cap.
2. Call `search_listings(description=..., size=..., max_price=...)`.
3. If `search_listings` returns an empty list, set `session.last_error = "no_search_results"`, set `session.message = "No listings matched your search. Try broadening the style, size, or price."`, and return immediately. Do not call any other tool.
4. If `search_listings` returns results, set `session.search_results = results` and `session.selected_item = results[0]`.
5. Check whether the session already has a wardrobe object. If it does not, load the default wardrobe for the current path: use `get_example_wardrobe()` for the sample/demo flow or `get_empty_wardrobe()` for a new user with no closet data.
6. If `session.wardrobe.items` is empty after that load, set `session.last_error = "empty_wardrobe"`, set `session.message = "I found an item, but I need wardrobe pieces to style it."`, and return immediately. Do not call `create_fit_card`.
7. Call `suggest_outfit(new_item=session.selected_item, wardrobe=session.wardrobe)`.
8. If `suggest_outfit` returns `None`, an empty outfit, or an error flag, set `session.last_error = "no_outfit"`, set `session.message = "I found the item, but couldn't build a compatible outfit from the current wardrobe."`, and return immediately. Do not call `create_fit_card`.
9. If an outfit is returned, set `session.outfit = outfit` and call `create_fit_card(outfit=session.outfit, new_item=session.selected_item)`.
10. If `create_fit_card` returns nothing or an error, set `session.last_error = "incomplete_fit_card"`, keep `session.outfit` and `session.selected_item` for debugging, and return a partial response instead of inventing a caption.
11. If `create_fit_card` succeeds, set `session.fit_card = caption` and return the final combined response to the user. This is the success branch and the loop ends here.


---

## State Management

**How does information from one tool get passed to the next?**
<!-- Describe how your agent stores and accesses state within a session. What data is tracked? How is it passed between tool calls? -->
The agent maintains a single `session` object with these fields: `query` (the user's original message), `search_results` (the list returned by `search_listings`), `selected_item` (the top result from `search_results`), `wardrobe` (the current wardrobe dict), `outfit` (the outfit suggestion returned by `suggest_outfit`), `fit_card` (the caption returned by `create_fit_card`), `last_error` (error code string or None), and `message` (user-facing message). The Planning Loop reads from session before each tool call and writes to session after each tool returns. For example, after `search_listings` returns, the loop writes `session.search_results = results` and `session.selected_item = results[0]`. Then `suggest_outfit` reads `session.selected_item` and `session.wardrobe` and writes `session.outfit`. Finally, `create_fit_card` reads `session.outfit` and `session.selected_item` and writes `session.fit_card`. If an error occurs, the agent sets `session.last_error` to an error code and `session.message` to a user-facing explanation, then returns early without modifying other fields.
---

## Error Handling

For each tool, describe the specific failure mode you're handling and what the agent does in response.

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| search_listings | No results match the query | Set `session.last_error = "no_search_results"`, set `session.message = "No listings matched your search. Try broadening the style, size, or price."`, and return immediately without calling `suggest_outfit` or `create_fit_card`. |
| suggest_outfit | Wardrobe is empty | Set `session.last_error = "empty_wardrobe"`, set `session.message = "I found an item, but I need wardrobe pieces to style it. Add items to your closet or use the example wardrobe for testing."`, and return early without calling `create_fit_card`. |
| create_fit_card | Outfit input is missing or incomplete | Set `session.last_error = "incomplete_fit_card"`, keep `session.outfit` and `session.selected_item` for debugging, and return a partial response with the listing and outfit but no caption. |

---

## Architecture

<!-- Draw a diagram of your agent showing how the components connect:
     User input → Planning Loop → Tools (search_listings, suggest_outfit, create_fit_card)
                                                                          ↕
                                                                   State / Session
     Show what triggers each tool, how state flows between them, and where error paths branch off.
     ASCII art, a Mermaid diagram (https://mermaid.js.org/syntax/flowchart.html), or an embedded
     sketch are all fine. You'll share this diagram with an AI tool when asking it to implement
     the planning loop and each individual tool. -->
```text
User query
     │
     ▼
Planning Loop ───────────────────────────────────────────┐
     │                                                    │
     ├─► search_listings(description, size, max_price)    │
     │       │                                            │
     │       ├──► results=[]                              │
     │       │     └──► [ERROR] "No listings found..." → return
     │       │                                            │
     │       └──► results=[item, ...]                     │
     │             ▼                                      │
     │        Session: selected_item = results[0]        │
     │             │                                      │
     ├─► suggest_outfit(selected_item, wardrobe)          │
     │       │                                            │
     │       ├──► wardrobe empty                          │
     │       │     └──► [ERROR] "Wardrobe is empty" → return
     │       │                                            │
     │       └──► outfit_suggestion = "..."              │
     │             ▼                                      │
     │        Session: outfit = outfit_suggestion         │
     │             │                                      │
     └─► create_fit_card(outfit_suggestion, selected_item)│
               │                                            │
               ├──► outfit missing / incomplete             │
               │     └──► [ERROR] "Outfit input missing" → return
               │                                            │
               └──► fit_card = "..."                       │
                     │                                        └─ error path returns here
                     ▼
                Return session
```

---

## AI Tool Plan

<!-- For each part of the implementation below, describe:
     - Which AI tool you plan to use (Claude, Copilot, ChatGPT, etc.)
     - What you'll give it as input (which sections of this planning.md, your agent diagram)
     - What you expect it to produce
     - How you'll verify the output matches your spec before moving on

     "I'll use AI to help me code" is not a plan.
     "I'll give Claude my Tool 1 spec (inputs, return value, failure mode) and ask it to implement
     search_listings() using load_listings() from the data loader — then test it against 3 queries
     before trusting it" is a plan. -->

**Milestone 3 — Individual tool implementations:**
I'll use Claude to implement each of the three tools independently.

For `search_listings`: I'll give Claude the Tool 1 spec block (inputs, return value, failure modes) and ask it to implement the function using `load_listings()` from `utils/data_loader.py`. I expect it to produce a function that filters listings by `description` (title and style_tags match), `size` (optional exact match), and `max_price` (optional cap), returning results sorted by relevance or as a list. Before using it, I'll verify:
  1. The function accepts all three parameters and treats size and max_price as optional.
  2. Empty filters (no matches) return an empty list, not an exception.
  3. Results include all required fields: id, title, category, price, colors, style_tags, platform.
  Then I'll test with 3 queries: (a) a match-all query like "vintage", (b) a query with a price cap that matches, (c) a query that matches nothing.

For `suggest_outfit`: I'll give Claude the Tool 2 spec block plus the wardrobe schema from `data/wardrobe_schema.json`. I expect it to produce a function that takes a new_item dict and a wardrobe dict, picks compatible wardrobe pieces based on style_tags and colors, and returns an outfit object with a recommendation string and a list of matching wardrobe items. Before using it, I'll verify:
  1. When wardrobe.items is empty, the function returns a non-empty string of general styling advice for the item (not None, not an empty string, no exception).
  2. When wardrobe items exist, the function returns an outfit with at least a `recommendation` string and a `pieces` list.
  3. The recommendation mentions the new item name and suggests how to wear it.
  Then I'll test with the example wardrobe and a graphic tee to confirm the output makes stylistic sense.

For `create_fit_card`: I'll give Claude the Tool 3 spec block. I expect it to produce a function that takes an outfit dict and a new_item dict and returns a caption string or caption object. The caption should be casual and mention the item, price, and one styling detail. Before using it, I'll verify:
  1. When outfit is None or missing critical fields, the function returns None or an error structure instead of guessing.
  2. When outfit is valid, the caption includes the item title, price, and platform.
  3. The tone is casual and social-media-ready.
  Then I'll test with a sample outfit and listing to confirm the caption reads naturally

**Milestone 4 — Planning loop and state management:**
I'll use Claude to wire the planning loop using the "Planning Loop" section and the Architecture diagram. I expect it to produce an `agent()` or `plan()` function that maintains a session state object and calls the three tools in the right order with the right error handling. Before using it, I'll verify:
  1. The function parses the user query and extracts `description`, `size`, and `max_price` correctly.
  2. After `search_listings` returns empty, the function sets `session.last_error = "no_search_results"` and returns early without calling `suggest_outfit` or `create_fit_card`.
  3. After `suggest_outfit` returns no outfit, the function sets `session.last_error = "no_outfit"` and returns early without calling `create_fit_card`.
  4. When all tools succeed, the function stores results in session and returns the final response with listing, outfit, and fit card.
  Then I'll test one full success path and one test for each early-exit branch (no search results, empty wardrobe, no outfit).


---

## A Complete Interaction (Step by Step)

Write out what a full user interaction looks like from start to finish — tool call by tool call. Use a specific example query.



**Example user query:** "I'm looking for a vintage graphic tee under $30. I mostly wear baggy jeans and chunky sneakers. What's out there and how would I style it?"

FitFindr first turns the user's request into a structured listing search, then ranks the results and picks the best matching item. If `search_listings` returns no matches, it stops and tells the user how to broaden the query; if it finds a match, it uses the saved wardrobe to suggest an outfit and then turns that outfit into a fit-card caption.

**Step 1:**
<!-- What does the agent do first? Which tool is called? With what input? -->

Call `search_listings` first with the parsed shopping request: `description="vintage graphic tee"`, `size="M"`, and `max_price=30.0`. The tool searches the mock listings data and returns the best matches sorted by relevance.

**Step 2:**
<!-- What happens next? What was returned from step 1? What tool is called now? -->

If `search_listings` returns one or more results, choose the top match as the `new_item` and call `suggest_outfit(new_item=top_match, wardrobe=user_wardrobe)`. This tool analyzes the new item in the context of the user's existing wardrobe (baggy jeans and chunky sneakers) and returns a suggested outfit that incorporates the new item.

**Step 3:**
<!-- Continue until the full interaction is complete -->

Use the outfit returned by `suggest_outfit` and the chosen listing as input to `create_fit_card(outfit=suggested_outfit, new_item=top_match)`. This produces the short, social-caption style fit card that summarizes the find and how to wear it.

**Final output to user:**
<!-- What does the user actually see at the end? -->

The user sees the best matching listing, a styling suggestion based on their wardrobe, and a polished fit-card caption. If no listings match, the user instead gets a short explanation of what to change in the search and no styling or fit-card tools are called.
