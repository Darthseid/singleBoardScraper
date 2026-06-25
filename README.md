# Job Board & Website Scraper Suite

A modular, generalized web scraper built in Python that handles multiple pagination strategies, JavaScript-rendered content, and anti-ban politeness measures. Includes a job board aggregator and a keyword search utility.

## Features

### Pagination Types

The scraper supports **five different pagination strategies** to handle the vast majority of job boards and websites:

- **`page`** — Traditional page numbers in the URL (e.g., `?page=1`, `?page=2`)
- **`offset`** — Offset/limit pagination (e.g., `?offset=0`, `?offset=10`, increments by `step`)
- **`from`** — Same as offset, but appends `&s=1` to each URL (common in legacy boards)
- **`next`** — DOM-mutating "Next" / "Load more" buttons (same URL, clicks trigger JS updates)
- **`scroll`** — Infinite-scroll feeds (no button; page loads more as you scroll)

### Smart Content Extraction

Scrapes job listings using flexible heuristics:
- **Class-based selector** — you specify the CSS class wrapping each job card (works on `<div>`, `<li>`, `<article>`, etc.)
- **Auto-detection fallback** — if no class selector is given, automatically detects and scores `<ul>`/`<li>` lists by text density
- **Field extraction** — pulls title, company, location, salary, job type, posting date, URLs, and tags from semantic HTML class hints and regex patterns

### JavaScript Rendering

- Automatically retries pages that return zero listings with a **headless Chromium browser** (via Playwright)
- For click-based ("next") and scroll-based pagination, uses Playwright throughout (no static HTML fallback)
- Fixed 6-second wait time for JS to render; adjust `JS_WAIT_SECONDS` in `pagination.py` if needed

### Anti-Ban Politeness

- Rotating User-Agent strings (desktop & mobile)
- Realistic request headers (Accept, Accept-Language, DNT, etc.)
- Randomized 2–5.5 second delays between requests (user-configurable)
- Automatic retry with exponential back-off on connection errors and timeouts
- Rate-limit awareness (respects `Retry-After` headers on 429 responses)
- Deduplication of listings across scans (for click/scroll modes)

### Output Formats

Results are presented as **pandas DataFrames** for easy filtering, sorting, and analysis:
- Print a formatted table to the console
- Filter by keyword
- Sort by page found, title, company, or location
- Export to CSV or Excel (`.xlsx`)
- Keep the DataFrame in memory for further processing in Python

## Installation

### Requirements

```bash
pip install requests beautifulsoup4 pandas
```

### For JavaScript-Rendered Pages

If you're using "next", "scroll", or the JS fallback for "page"/"offset"/"from":

```bash
pip install playwright
playwright install chromium
```

## Quick Start

### Job Board Scraper

```python
from pagination import scrape_jobs
from output import display_jobs

jobs = scrape_jobs(
    base_url="https://jobs.apple.com/en-us/search?location=united-states-USA&page=",
    class_selector=None,              # auto-detect <ul>/<li>
    pagination_type="page",
    start_value=1,
    stop_value=10,
)

df = display_jobs(jobs, filter_keyword="engineer", sort_by="company")
df.to_csv("apple_jobs.csv", index=False)
```

### Keyword Search Scraper

```python
from websiteKeyword import search_keyword_across_pages

search_keyword_across_pages(
    base_url="https://forums.example.com/search?page=",
    keyword="python",
    pagination_type="page",
    start_value=1,
    stop_value=50,
)
```

### Click-Based Pagination (Next Button)

```python
jobs = scrape_jobs(
    base_url="https://example.com/careers",
    class_selector="job-card",
    pagination_type="next",
    next_selector="button.load-more",  # or "a[aria-label='Next']"
    start_value=1,
    stop_value=15,
)
```

### Infinite Scroll

```python
jobs = scrape_jobs(
    base_url="https://example.com/jobs",
    class_selector="job-listing",
    pagination_type="scroll",
    start_value=1,
    stop_value=7,  # scroll to bottom up to 7 times
)
```

## Project Structure

```
.
├── models.py              # JobListing dataclass (zero dependencies)
├── extraction.py          # Heuristic field extraction from HTML
├── anti_ban.py            # User-Agent rotation, headers, retry logic
├── pagination.py          # All 5 pagination strategies + scrape_jobs()
├── output.py              # DataFrame display/export functions
├── run_scraper.py         # CLI entry point for job board scraper
├── websiteKeyword.py      # Keyword search utility (reuses pagination)
└── README.md              # This file
```

### Dependency Flow (One Direction)

```
anti_ban.py ──┐
models.py  ───┼──→ extraction.py ──→ pagination.py ──→ run_scraper.py
              └─────────────────────────→ output.py ──┘

websiteKeyword.py imports: anti_ban, pagination, models
```

All imports are **top-level** (e.g., `from pagination import scrape_jobs`), not package-relative.

## API Reference

### `pagination.py`

**`scrape_jobs(base_url, class_selector=None, pagination_type="page", start_value=1, stop_value=10, step=10, next_selector=None, min_delay=2.0, max_delay=5.5, max_retries=3, use_js_fallback=True)`**

Scrapes job listings across paginated pages.

**Parameters:**
- `base_url` (str) — URL prefix (append value directly). For "next"/"scroll", just the literal page URL.
- `class_selector` (str, optional) — CSS class wrapping each job card. If None, auto-detects `<ul>`/`<li>`.
- `pagination_type` (str) — One of `"page"`, `"offset"`, `"from"`, `"next"`, `"scroll"`.
- `start_value`, `stop_value` (int) — Starting and ending page/offset/scan number.
- `step` (int) — Increment for "offset"/"from" pagination (default 10).
- `next_selector` (str) — Required for "next"; CSS selector for the button to click.
- `min_delay`, `max_delay` (float) — Randomized delay between requests (seconds).
- `max_retries` (int) — Retry attempts for failed HTTP requests.
- `use_js_fallback` (bool) — Retry with headless browser when static HTML returns 0 listings.

**Returns:** `list[JobListing]`

---

### `output.py`

**`display_jobs(jobs, filter_keyword=None, sort_by="page", show_raw_text=False, max_col_width=40)`**

Converts job listings to a pandas DataFrame, prints a formatted table, and returns the DataFrame.

**Parameters:**
- `jobs` (list[JobListing]) — Output of `scrape_jobs()`.
- `filter_keyword` (str, optional) — Only show listings whose raw text contains this keyword (case-insensitive).
- `sort_by` (str) — Sort by `"page"`, `"title"`, `"company"`, or `"location"`.
- `show_raw_text` (bool) — Include the full raw_text column in printed output.
- `max_col_width` (int) — Truncate long columns when printing (doesn't affect the returned DataFrame).

**Returns:** `pd.DataFrame`

**`export_to_csv(jobs, filepath="jobs.csv")`** / **`export_to_excel(jobs, filepath="jobs.xlsx")`**

Save jobs to a file. Accept either `list[JobListing]` or an already-built DataFrame.

**Returns:** `pd.DataFrame`

---

### `websiteKeyword.py`

**`search_keyword_across_pages(base_url, keyword, pagination_type="page", start_value=1, stop_value=10, step=10, next_selector=None, min_delay=1.0, max_delay=4.5, max_retries=3, use_js_fallback=True)`**

Searches paginated pages for a keyword using any pagination strategy.

**Parameters:** Same as `scrape_jobs()`, but `keyword` (str) replaces `class_selector`.

**Prints:** `[FOUND]` or `[  --  ]` for each page, indicating whether the keyword was found.

---

## Configuration

Edit the config section at the top of `run_scraper.py` to point to your target job board:

```python
BASE_URL = "https://jobs.example.com/search?page="
PAGINATION_TYPE = "page"
START_VALUE = 1
STOP_VALUE = 50
CLASS_SELECTOR = "job-card"
```

Or pass parameters programmatically when importing.

## Tips for Finding the Right Settings

### Finding the Class Selector

1. Open your browser's **DevTools** (`F12`)
2. Right-click a job card → **Inspect**
3. Look at the `<div>` (or `<li>`, `<article>`) wrapping the entire card
4. Note its `class` attribute — e.g., `class="job-card"` → use `class_selector="job-card"`

### Finding the Pagination Type

1. Look at the **Next page URL** in the address bar
2. If it changes like `?page=1` → `?page=2` → use `"page"`
3. If it changes like `?offset=0` → `?offset=10` → use `"offset"`
4. If it's the same URL but a button appears → use `"next"` and inspect the button for its CSS selector
5. If new jobs appear as you scroll down → use `"scroll"`

### Finding the Next Selector

1. Right-click the "Next" / "Load more" button → **Inspect**
2. Look for a unique `id` or `class`
3. Examples:
   - `<button id="load-more">` → use `next_selector="#load-more"`
   - `<a class="btn-next">` → use `next_selector="a.btn-next"`
   - `<button aria-label="Next">` → use `next_selector="button[aria-label='Next']"`

## Common Issues

### "No listings found"

**Problem:** The scraper returned 0 jobs despite seeing them on the page.

**Solutions:**
1. Verify `class_selector` is correct (inspect a job card in DevTools)
2. If the board is React/Vue/Angular-based, enable `use_js_fallback=True` (requires Playwright)
3. For "next"/"scroll" modes, increase `JS_WAIT_SECONDS` in `pagination.py` if the page loads very slowly

### "Playwright isn't installed"

**Solution:**
```bash
pip install playwright
playwright install chromium
```

### Rate limiting / 429 errors

**Problem:** Too many requests too fast.

**Solutions:**
1. Increase `min_delay` and `max_delay` (e.g., `min_delay=5.0, max_delay=10.0`)
2. Reduce `stop_value` to scrape fewer pages
3. Wait a few hours before retrying (the site may have temporarily blocked your IP)

### JavaScript content not loading

**Problem:** Using `pagination_type="page"` but content is still empty after JS fallback.

**Solutions:**
1. Try `pagination_type="next"` or `"scroll"` if the site uses those patterns
2. Increase `JS_WAIT_SECONDS` (edit in `pagination.py`, default is 6 seconds)
3. Some sites may require a real browser (Playwright in headless mode might not be enough; check for JavaScript errors in DevTools)

## Examples

### Scrape Apple's job board (pages 1–3)

```bash
python run_scraper.py
```

Or:

```python
from pagination import scrape_jobs
from output import display_jobs, export_to_csv

jobs = scrape_jobs(
    base_url="https://jobs.apple.com/en-us/search?location=united-states-USA&page=",
    class_selector=None,
    pagination_type="page",
    start_value=1,
    stop_value=3,
)

df = display_jobs(jobs)
export_to_csv(df, "apple_jobs.csv")
```

### Search a forum for mentions of "Python" (10 pages)

```python
from websiteKeyword import search_keyword_across_pages

search_keyword_across_pages(
    base_url="https://forums.example.com/search?q=&page=",
    keyword="Python",
    pagination_type="page",
    start_value=1,
    stop_value=10,
)
```

### Scrape an infinite-scroll site (up to 7 scrolls)

```python
from pagination import scrape_jobs
from output import display_jobs

jobs = scrape_jobs(
    base_url="https://jobboard.example.com/search",
    class_selector="job-tile",
    pagination_type="scroll",
    start_value=1,
    stop_value=7,
)

df = display_jobs(jobs, sort_by="company")
```

## Rate Limiting & Ethics

This scraper is designed to be **respectful of server resources**:

- ✅ Randomized delays between requests
- ✅ Realistic User-Agent strings
- ✅ Automatic back-off on errors and rate limits
- ✅ Respects `Retry-After` headers

**Before scraping any site, check its `robots.txt` and Terms of Service.** Some job boards explicitly forbid scraping; others allow it under certain conditions (e.g., attribution, non-commercial use).

## Architecture Notes

### Why Modular?

The original monolithic file grew to ~1100 lines and became hard to maintain. Splitting into 6 focused modules:

1. **models.py** — Zero dependencies; easy to test and reuse
2. **extraction.py** — Pure parsing logic; testable in isolation
3. **anti_ban.py** — Shared politeness helpers (no scraping logic)
4. **pagination.py** — All 5 pagination strategies + orchestrator
5. **output.py** — Display and export (depends only on models)
6. **run_scraper.py** / **websiteKeyword.py** — CLI entry points

Each file has a **single responsibility**, and imports flow in one direction, making the codebase easy to extend.

### Why Top-Level Imports?

All imports are `from pagination import scrape_jobs` (not `from .pagination import ...`), which means:
- No package directory needed — just drop the files together
- Easier to run directly (`python run_scraper.py`)
- Simpler for users to install (no `pip install -e .` or `__init__.py` setup)

## Future Enhancements

Potential improvements (out of scope for this project):

- [ ] Distributed scraping (multiple machines / IP rotation)
- [ ] Proxy support (for high-volume scraping)
- [ ] Database backend (store results in SQLite / PostgreSQL instead of CSV)
- [ ] Webhook notifications (alert when new listings matching criteria appear)
- [ ] Job board-specific plugins (some boards have unique structures warranting custom parsers)
- [ ] Browser fingerprint evasion (more sophisticated anti-detection for highly protected sites)

## License

No license specified. Use as you wish, but respect the websites you scrape and their terms of service.

## Questions?

Refer to the docstrings in each Python file for more detailed API docs. Each function has a comprehensive docstring explaining its parameters and behavior.

---

**Built with**: Python, requests, BeautifulSoup4, pandas, Playwright (optional)

**Last updated**: June 2026
