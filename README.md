# FitFindr

A multi-tool agent that finds secondhand pieces, styles them against your wardrobe, and writes a shareable fit card.

## Tool Inventory

### `search_listings(description, size, max_price)`
- **Purpose:** Search the listings for items matching the specified description, size, and max price.
- **Inputs:**
  - `description` (str): keywords matching what outfit the user is looking for
  - `size` (str): size to filter by, or None to skip this filter
  - `max_price` (float): max price to filter by, or None to skip this filter
- **Returns:** A list of matching listing dicts, each with `id`, `title`, `description`, `category`, `style_tags` (list), `size`, `condition`, `price` (float), `colors` (list), `brand`, `platform`. Returns `[]` if no matches were found.

### `suggest_outfit(new_item, wardrobe, style_profile=None)`
- **Purpose:** Suggests complete outfit pairing based on a provided `new_item` with the user's wardrobe.
- **Inputs:**
  - `new_item` (dict): selected listing dict for the item the user is considering.
  - `wardrobe` (dict): a wardrobe dict
  - `style_profile` (list, optional): remembered style keywords (stretch: style memory). When provided, the suggestion leans into them.
- **Returns:** Non-empty `str` with outfit suggestions.

### `create_fit_card(outfit, new_item)`
- **Purpose:** Generate a 2-4 sentence social media caption for the `new_item`.
- **Inputs:**
  - `outfit` (str): outfit suggestions returned by `suggest_outfit`
  - `new_item` (dict): selected listing dict for the item the user is considering.
- **Returns:** A short caption `str` for sharing.

### `compare_price(new_item)` (stretch)
- **Purpose:** Estimates whether a listing's price is fair by comparing it against other listings in the same category in the dataset.
- **Inputs:**
  - `new_item` (dict): the selected listing dict to assess.
- **Returns:** An `str` that states the verdict **and the reasoning**: the verdict ("great deal", "fair", or "pricey") plus the item's price compared to the median price of same-category listings and how many comparables were used. The verdict is "great deal" when the price is 15%+ below the median, "pricey" when 15%+ above, and "fair" within that band.

## How the Planning Loop Works

The agent runs a deterministic planning loop in `run_agent(query, wardrobe)`. Each step's decision depends on what the previous step returned:

1. Initialize the session with `_new_session()`.

2. Parse the user query to extract `description`, `size`, and `max_price` using LLM. Store the parameters in `session["parsed"]`.

   If the parameter could not be parsed, set `session["error"]` to "Sorry, I don't understand your query. Please try again" and return early.

3. Call `search_listings` with the parsed parameters. Store the results in `session["search_results"]`.

   If `search_listings` returns no results, set `session["error"]` to "Sorry, no listings matched your description, size, and budget." and return early.

4. Set `session["selected_item"]` to `results[0]`, i.e., the first item. Call `suggest_outfit` with the selected item and wardrobe. Store the result in `session["outfit_suggestion"]`.

   If `suggest_outfit` results in an error or returns an empty string, set `session["error"]` to "Sorry, an error has occurred." and return early.

5. Call `create_fit_card` with the outfit suggestion and selected item. Store the result in `session["fit_card"]`.

   If `create_fit_card` results in an error or returns an empty string, set `session["error"]` to "Sorry, an error has occurred." and return early.

6. Return the session.

### Stretch additions to the loop

- **Style memory (Step 2):** the LLM parse also extracts `style_prefs` from the query. These are merged into a module-level style profile and snapshotted into `session["style_profile"]`, then passed to `suggest_outfit` so later queries reflect earlier-stated preferences without re-entry.
- **Retry with fallback (Step 3):** if `search_listings` returns `[]`, retry with loosened constraints before erroring, first drop the size filter, then drop the price cap. On success, set `session["notice"]` explaining what was loosened and continue. Only if every retry is still empty does the no-results error fire.
- **Price comparison (after Step 4):** once an item is selected, call `compare_price(selected_item)` and store the result in `session["price_assessment"]`.

Because each branch checks the prior result, the agent behaves differently on different inputs: an impossible query stops after `search_listings` (after retries) with only `session["error"]` set, while a normal query flows through all the tools.

## State Management

We use a `session` dict to share information among tools. The `session` dict tracks the following data:

- `query`
- `parsed`
- `search_results`
- `selected_item`
- `wardrobe`
- `outfit_suggestion`
- `fit_card`
- `error`
- `notice` (stretch: retry explanation)
- `price_assessment` (stretch: the `compare_price` result string)
- `style_profile` (stretch: a snapshot of the remembered preferences)

Each tool's output is written to the session before the next reads it. For example, the dict in `session["selected_item"]` is passed directly into `suggest_outfit`, and the string it returns is written to `session["outfit_suggestion"]` and then passed straight into `create_fit_card`. The user never re-enters anything between steps.

Style memory is held in a **module-level dict in `agent.py`** that outlives any single `run_agent()` call, so preferences persist across queries within one app run. It is intentionally in-memory (no file), so it resets when the app restarts.

## Error Handling

Each tool handles its own failure mode and the agent reports it clearly instead of crashing:

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| search_listings | No results match the query | After retrying with loosened filters, returns early with a graceful error message. |
| suggest_outfit | Wardrobe is empty | Provides generic styling advice based on the selected item only. |
| create_fit_card | Outfit input is missing or incomplete | Returns a graceful error message instead of raising. |
| compare_price (stretch) | Fewer than 2 comparable listings | Returns: "Unknown — there aren't enough comparable listings to judge whether this price is fair." |

**Concrete example from testing.** Running the impossible query `"designer ballgown size XXS under $5"` through the agent triggers the no-results path. `search_listings` returns `[]`, the retry fallback also finds nothing, and the agent returns:

> I couldn't find any listings matching that. Try a higher budget, a different size, or simpler keywords.

`session["selected_item"]` and `session["fit_card"]` both stay `None`. The agent never calls the later tools with empty input.


## Stretch Features

- **Retry with fallback**

  When `search_listings` returns no results, the agent retries with loosened constraints before giving up, first dropping the size filter, then dropping the price cap, and explains the adjustment in `session["notice"]`, e.g. *"No exact matches in size XXS, so I dropped the size filter to show you these."*

- **Price comparison (`compare_price`)**

  Comparisons are made against the **median price of other listings in the same category** (excluding the item itself). The price is rated a "great deal" when it is 15%+ below that median, "pricey" when 15%+ above, and "fair" in between. The returned string includes the median and the number of comparables used. Rendered in a dedicated "Price check" panel in the UI.

- **Style profile memory**

   Style keywords (e.g. "grunge", "baggy") are extracted from each query by the LLM parse step and merged into an in-memory module-level profile in `agent.py`. The profile is passed into `suggest_outfit`, so a later query reflects style preferences stated in an earlier one without the user re-entering them. It persists across queries within one app run and resets when the app restarts.

## Spec Reflection

- **One way the spec helped:**

   Writing the per-tool specs in `planning.md` before any code meant the AI-generated tool implementations matched my intent on the first pass, so review was just confirming the code against a checklist.

- **One way the implementation diverged**

   The error strings in `planning.md`'s tables and loop steps are placeholder drafts (e.g. *"Sorry, no listings matched your description, size, and budget."*), but the implemented agent uses friendlier, more actionable wording (e.g. *"I couldn't find any listings matching that. Try a higher budget, a different size, or simpler keywords."*). I changed this during implementation because the draft messages read as generic apologies, while good UX call for telling the user specifically what to try next.

## AI Usage

1. **Implementing `search_listings`**

   I gave Claude the Tool 1 spec block from `planning.md` plus the `load_listings()` signature, and directed it to implement the function in `tools.py`. I reviewed that it filtered on all three parameters and returned `[]` (not an exception) for an impossible query, then tested it against three queries (a normal search, a price-filtered search, and an impossible one) before trusting it.

2. **Implementing the planning loop (`run_agent`)**

   I gave Claude the Planning Loop and State Management sections plus the Mermaid architecture diagram, and directed it to implement `run_agent` so it branches on an empty `search_listings` result and stores every intermediate value in the `session` dict.
   
   I **overrode** the draft error messages from `planning.md` with friendlier user-facing strings, and verified the no-results branch leaves `selected_item`/`fit_card` as `None` so the later tools never run on empty input.

3. **Building the price-comparison stretch (`compare_price`)**

   I first directed Claude to return a one-word verdict, then **revised** the spec and the code so the tool returns a full reasoning string (verdict + price vs. median + comparable count), because the stretch goals require the assessment to come *with reasoning*. I updated `planning.md` first and then the implementation to keep them in sync.
