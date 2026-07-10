# Solution Documentation — Portfolio Insights Generator

---

## Overview

I built a three-file Python application:

- **`transaction_processor.py`** — handles all data loading, cleaning, and analytics through a `TransactionStore` class that accepts data from any source
- **`insights_generator.py`** — formats the analytics into a structured prompt and calls the Anthropic API (Claude) to generate a natural language compliance and performance report
- **`dashboard.py`** — a Streamlit dashboard that ties everything together, displaying the raw data, analytics charts, and AI-generated insights

The data flows in one direction: raw CSV (or API or database) → cleaned DataFrame → `TransactionStore` analytics methods → structured prompt → Claude API → displayed insights. Each layer only knows about the one below it, which made everything easy to test and extend independently.

---

## Data Structure Choices

**1. What data structures did you use?**

- A **pandas DataFrame** as the primary storage container for all transaction rows
- A **Python dict** (`ticker_index`) mapping each ticker symbol to the list of row positions where it appears — built once at initialization for fast lookups
- A **`collections.deque`** inside the FIFO matching algorithm to represent the queue of open buy lots per trader/ticker combination
- Plain **Python dicts** as return values from every analytics method, since they feed directly into both Streamlit's chart functions and the LLM prompt builder

**2. Why these structures?**

I thought a lot about this before writing any code. The assignment said to handle 1,000+ transactions efficiently, and I wanted a structure that could scale. I considered a plain list of dicts (simple but slow to filter), a database (overkill for what we're doing), and a DataFrame.

I chose the DataFrame because it gives me vectorized operations for free — things like `groupby`, `value_counts`, and `dt.hour` run across the entire dataset in a single pass rather than looping row by row. It also handles timestamp parsing natively and sorts chronologically with a single call. The trade-off is that DataFrames have more overhead than a simple list, but for any realistic transaction volume that's irrelevant.

The ticker index dict was a deliberate add-on. `get_transactions_by_ticker()` would otherwise have to scan every row on every call. By building a dict at initialization that maps `"AAPL" → [0, 3, 7, ...]` (row positions), lookups are O(1) regardless of how many rows are in the dataset.

The deque was the right choice for FIFO matching because `popleft()` is O(1) — far better than popping from the front of a list which shifts every remaining element. This matters when a trader has many open buy lots.

**3. Where did you use different structures and why?**

- **DataFrame** for bulk storage and any operation that touches the full dataset (filtering, grouping, sorting)
- **Dict (`ticker_index`)** for single-ticker lookups where speed matters
- **Deque** inside `_match_trades_fifo()` for the buy queue — needs efficient removal from the front
- **Mutable lists `[price, qty]`** as the items inside the deque — I needed to reduce `qty` in place for partial fills without creating a new object each time
- **Dicts** for all analytics return values — consistent, easy to iterate, and compatible with both `pd.Series()` (for charts) and f-string formatting (for the prompt)

---

## Data Processing

**1. How did you process the CSV file?**

I used `pd.read_csv()` to load the file, then funneled it through a shared `_clean()` function that all three loaders (CSV, API, database) call. This means the cleaning logic lives in one place — if I need to change it, I change it once. The steps in order:

1. Validate that all 6 required columns are present (raise a `ValueError` with the missing column names if not)
2. Trim the DataFrame to only the 6 required columns — so if someone uploads a file with 50 extra columns, those are silently dropped rather than causing problems downstream
3. Drop exact duplicate rows
4. Fill missing `trader_id` values with `"Unknown"`
5. Parse the `timestamp` column from string to `datetime` with `pd.to_datetime()`
6. Sort by timestamp and reset the index

**2. Did you encounter any issues with the data?**

Yes — three:

- **30 exact duplicate rows** in the raw CSV. I dropped them. Keeping duplicates would inflate every aggregate (volume, P&L, concentration percentages) and make the insights misleading.
- **51 rows with missing `trader_id`**. I filled them with `"Unknown"` rather than dropping the rows. The transaction itself is still valid market activity — removing it would undercount volume and distort P&L calculations. Keeping it as "Unknown" lets a compliance team see that unattributed trades exist, which is itself a finding.
- **Timestamps stored as strings**. `pd.to_datetime()` handles this cleanly. Parsing at load time means every downstream operation can use `.dt.hour`, `.dt.date`, etc. without worrying about type.

**3. What assumptions did you make?**

- `BUY` and `SELL` are the only valid action values — I didn't add validation for this since the data was consistent, but it's worth noting for production use
- The `Unknown` trader category represents genuinely unattributed trades, not a specific named trader
- All timestamps are from a single timezone (unknown which one). This matters — see the Additional Notes section on after-hours analysis

---

## LLM Integration

**1. How did you integrate the LLM API?**

I used the Anthropic Python SDK with `claude-sonnet-4-6`. The API key is loaded from a `.env` file using `python-dotenv` — it's never hardcoded anywhere. `build_prompt()` in `insights_generator.py` takes the pre-computed analytics as arguments and formats them into a structured text prompt. `generate_insights()` sends that prompt to the API and returns the response text.

**2. How do you handle API responses?**

The response comes back as `response.content[0].text` — a plain string. I store it in Streamlit's `st.session_state.insights` so the result persists across page interactions without re-calling the API. Before displaying it, I run it through `clean_insights_text()` which handles a few Streamlit-specific rendering issues: dollar signs before numbers trigger LaTeX math mode (I escape them), and diff-style code blocks turn text red (I strip them).

**3. Did you implement any cost optimizations?**

Yes, and this was a deliberate architectural decision. Instead of sending the raw CSV data to the API (1,000+ rows × 6 columns = a huge token count), I pre-compute all the analytics in Python and send only the compact summary — volume per ticker, net positions, P&L breakdown, concentration metrics, etc. The prompt is roughly 600–800 tokens. Sending the raw data would be 10–15x more expensive and give Claude less useful information (aggregates are more informative than raw rows for the findings we care about).

I also cache the result in session state so clicking "Generate Insights" multiple times doesn't make multiple API calls for the same dataset.

---

## AI Tools Used

**1. Did you use any AI tools?**

Yes — Claude Code (Claude Sonnet 4.6) throughout the entire project.

**2. What did I use it for?**

I used it as a pair programmer and technical collaborator. Before writing any code, we spent significant time discussing the architecture — I asked about trade-offs between data structures, whether to use Flask vs Streamlit, how to structure the three files, and what analytics would be most meaningful to a real financial professional. Claude explained every decision before writing it, which was important to me because I needed to be able to defend every line in the follow-up interview.

Specific areas where I relied on it heavily: the FIFO matching algorithm (which requires careful handling of partial fills across multiple buy lots), the HHI concentration metric (which I wasn't familiar with before this), and the Streamlit dashboard layout.

**3. Did you modify or review the AI's suggestions?**

Yes — and this was a real back-and-forth, not just accepting output. The clearest example: when Claude first wrote `get_buy_sell_ratio()`, it sorted tickers by `abs(ratio - 1.0)`. I questioned this and realized it was asymmetric — a ratio of 5.0 scores 4.0 but a ratio of 0.2 (which is the same 5:1 imbalance in the other direction) only scores 0.8. That's wrong. We fixed it by using `abs(log(ratio))` instead, which correctly treats equal imbalances symmetrically regardless of direction.

I also pushed back on the prompt design several times — moving the team P&L from the market section to the trader section, deprioritizing timing anomalies (which Claude kept flagging as critical when they're almost certainly a timezone issue), and cutting sections that were obvious or unremarkable.

**4. Sequence of prompts (high level):**

1. Read the assignment and plan the architecture — chose Streamlit over React/Flask, chose pandas over a database
2. Discussed data structure trade-offs before writing any code
3. Wrote and reviewed the three loader functions and `_clean()` one at a time
4. Built `TransactionStore` — started with the required analytics, then added `get_buy_sell_ratio()`, `get_trader_concentration()` (with HHI), and `_match_trades_fifo()` after consulting with finance professionals about what would actually matter to an analyst
5. Caught and fixed the buy/sell ratio sorting bug
6. Designed the LLM prompt structure — iterated on it several times to get the two-section market/trader format and remove findings that weren't genuinely meaningful
7. Built the Streamlit dashboard and went through multiple rounds of visual refinement
8. Fixed a series of Streamlit-specific rendering issues (LaTeX math mode, diff coloring, italic collapsing)
9. Wrote tests and submission documentation

---

## Challenges & Learnings

**1. What was the most challenging part?**

The FIFO trade matching algorithm. Matching each SELL against the oldest available BUY across every trader/ticker combination requires tracking remaining quantity across multiple buy lots, handling partial fills where one sell spans two or more buy lots, and distinguishing between positions that are simply unmatched (unrealized) versus short positions (sold without a preceding buy). The edge case I specifically walked through: two buys of 100 and 50 shares, followed by a sell of 80 and then a sell of 50 — the second sell crosses the boundary between the first and second buy lot. Getting the queue logic right for that case took careful thought.

**2. What would I do differently with more time?**

The biggest gap is timezone normalization. All timestamps in the dataset fall outside US market hours (9:30 AM–4:00 PM ET), which the AI flags as anomalous. But without knowing the timezone of the source system, I can't correct for it — assuming ET when the data might be in UTC or another timezone would produce wrong conclusions. With more time I'd get the timezone confirmed and add proper after-hours analysis. I made a deliberate decision NOT to implement it with unverified assumptions, and documented that reasoning in the code.

I'd also add analytics-level unit tests, not just loader tests. The P&L calculations and FIFO matching have real edge cases that deserve dedicated test coverage.

**3. Did you learn anything new?**

Several things: the HHI (Herfindahl-Hirschman Index) as a regulatory concentration metric, FIFO as the standard accounting method for realized P&L in equity trading, the asymmetry of linear vs log-scale sorting for ratios, and how Streamlit handles LaTeX math mode (not something you'd ever expect to encounter in a financial dashboard but definitely something I won't forget).

---

## Testing

**1. How did you test your solution?**

I wrote unit tests in `test_loaders.py` covering all three data loaders:

- **`TestCSVLoader`** — uses `io.StringIO` to create in-memory CSVs with controlled data, so tests don't depend on the real sample file for things like duplicate-dropping and missing trader_id handling. One test does use the real file to confirm end-to-end loading works.
- **`TestAPILoader`** — uses `unittest.mock` to replace `requests.get` with a fake that returns controlled JSON. This means the tests never make real HTTP calls, so they're fast, deterministic, and don't require network access.
- **`TestDatabaseLoader`** — creates a real temporary SQLite file in `setUp()` with known data, runs the tests, then deletes the file in `tearDown()`. A real file is necessary because `load_from_database()` takes a file path, not a connection object.

All 8 tests pass. Run them with: `python -m unittest test_loaders.py -v`

**2. What edge cases did you consider?**

- Files with extra columns beyond the required 6 (they get silently trimmed, not rejected)
- Missing `trader_id` values (filled with "Unknown", not dropped)
- Exact duplicate rows (dropped)
- Tickers not found in the index (returns an empty DataFrame rather than raising an exception)
- A SELL with no matching BUY (treated as a short position with unrealized P&L estimated from last known price)
- Partial FIFO fills where one SELL spans multiple BUY lots

---

## Additional Notes

**On after-hours analysis:**
After reviewing the timestamp distribution, I noticed all 1,000 transactions fall outside standard US market hours. I considered implementing an after-hours flag but decided against it. The timestamps carry no timezone information, and assuming ET when the source system might use UTC (or another timezone) would either falsely flag normal trading as suspicious or miss genuinely unusual activity. I documented this decision in a comment block in `transaction_processor.py` and included a disclaimer in the LLM prompt so Claude treats timing observations as preliminary. If the timezone is confirmed, this feature would be straightforward to add.

**On supporting three data sources:**
The assignment only required loading from CSV. I added REST API and SQLite database loaders because it made the `TransactionStore` design cleaner — if the class doesn't care where its data came from, it's more reusable. All three loaders funnel through the same `_clean()` function, so data quality guarantees hold regardless of source.

**On the buy/sell ratio sorting:**
The initial implementation sorted by `abs(ratio - 1.0)`, which is asymmetric — a 5:1 buy skew scores 4.0 but a 1:5 sell skew (the same magnitude of imbalance) only scores 0.8. I caught this and we corrected it to `abs(log(ratio))`, which treats equal-magnitude imbalances symmetrically regardless of direction. I want to flag this because it's a subtle bug that would be easy to miss but meaningfully affects which tickers appear as most imbalanced in both the dashboard and the AI prompt.
