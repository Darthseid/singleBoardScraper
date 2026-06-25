import random
import time
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from models import JobListing
from extraction import extract_job_info, extract_jobs_from_soup
from anti_ban import random_user_agent, fetch_with_retries, polite_delay

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

_playwright_warning_shown = False

JS_WAIT_SECONDS = 6.0
SCROLL_NO_NEW_CONTENT_LIMIT = 2
VALID_PAGINATION_TYPES = ("page", "offset", "from", "next", "scroll")


def _build_page_values(
    pagination_type: str,
    start_value: int,
    stop_value: int,
    step: int,
) -> list[int]:
    """
    Generates the sequence of values to append to base_url for each request,
    based on the pagination scheme.
    """
    if pagination_type == "page":
        return list(range(start_value, stop_value + 1, 1))
    elif pagination_type in ("offset", "from"):
        if step <= 0:
            raise ValueError("step must be a positive integer for offset/from pagination")
        return list(range(start_value, stop_value + 1, step))
    else:
        raise ValueError(
            f"Invalid pagination_type '{pagination_type}'. "
            f"Must be one of {VALID_PAGINATION_TYPES}."
        )


def _build_url(base_url: str, pagination_type: str, value: int) -> str:
    """Builds the final request URL for a given pagination value."""
    url = f"{base_url}{value}"
    if pagination_type == "from":
        url += "&s=1"
    return url


def render_with_browser(
    url: str,
    class_selector: Optional[str],
    timeout_ms: int = 20000,
) -> Optional[str]:
    """
    Loads a page in a headless Chromium browser and waits for JavaScript
    to populate the DOM before returning the rendered HTML.
    """
    global _playwright_warning_shown

    if not PLAYWRIGHT_AVAILABLE:
        if not _playwright_warning_shown:
            print(
                "  ⚠ Zero listings found and this looks like it may be a \n JavaScript-rendered page, but Playwright isn't installed. "
            )
            _playwright_warning_shown = True
        return None

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=random_user_agent(),
                viewport={"width": 1366, "height": 900},
            )
            page = context.new_page()
            page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")

            selector_found = False
            if class_selector:
                primary_class = class_selector.split()[0]
                try:
                    page.wait_for_selector(f".{primary_class}", timeout=timeout_ms)
                    selector_found = True
                except Exception:
                    pass

            if not selector_found:
                page.wait_for_timeout(JS_WAIT_SECONDS * 1000)

            html = page.content()
            browser.close()
            return html

    except Exception as e:
        print(f"  [ERR] Headless browser render failed for {url}: {e}")
        return None


def _scrape_next_button_pagination(
    base_url: str,
    class_selector: Optional[str],
    next_selector: str,
    start_value: int,
    stop_value: int,
    min_delay: float,
    max_delay: float,
    base_domain: str,
) -> list[JobListing]:
    """
    Handles job boards where clicking a "Next" / "Load more" button mutates
    the DOM in place rather than navigating to a new URL.
    """
    if not PLAYWRIGHT_AVAILABLE:
        raise RuntimeError( "pagination_type='next' requires Playwright, since clicking a button needs a real browser. ")
    all_jobs: list[JobListing] = []
    seen_keys = set()
    total_scans = stop_value - start_value + 1

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=random_user_agent(),
            viewport={"width": 1366, "height": 900},
        )
        page = context.new_page()
        page.goto(base_url, timeout=20000, wait_until="domcontentloaded")
        page.wait_for_timeout(JS_WAIT_SECONDS * 1000)

        for idx, value in enumerate(range(start_value, stop_value + 1)):
            if idx > 0:
                next_locator = page.locator(next_selector).first
                if next_locator.count() == 0:
                    print(f"  [STOP] Next selector '{next_selector}' not found on the page "
                          f"after scan {value - 1}. Assuming end of listings.")
                    break
                try:
                    if not next_locator.is_enabled():
                        print(f"  [STOP] Next selector '{next_selector}' is disabled after "
                              f"scan {value - 1}. Assuming end of listings.")
                        break
                    next_locator.click(timeout=10000)
                except Exception as e:
                    print(f"  [ERR] Failed clicking '{next_selector}' after scan "
                          f"{value - 1}: {e}. Stopping.")
                    break

                page.wait_for_timeout(JS_WAIT_SECONDS * 1000)

            html = page.content()
            soup = BeautifulSoup(html, "html.parser")
            scan_jobs = extract_jobs_from_soup(soup, class_selector, value, base_domain)

            new_jobs = []
            for j in scan_jobs:
                key = (j.title, j.company, j.url)
                if key not in seen_keys:
                    seen_keys.add(key)
                    new_jobs.append(j)

            all_jobs.extend(new_jobs)
            print(f"  [{idx+1:>3}/{total_scans}] scan={value:<6} Found {len(new_jobs):>3} new listings "
                  f"(total so far: {len(all_jobs)})")

            if idx < total_scans - 1:
                polite_delay(min_delay, max_delay)

        browser.close()

    return all_jobs


def _scrape_scroll_pagination(
    base_url: str,
    class_selector: Optional[str],
    start_value: int,
    stop_value: int,
    min_delay: float,
    max_delay: float,
    base_domain: str,
) -> list[JobListing]:
    """
    Handles infinite-scroll job boards: scrolls to the bottom of the page,
    waits for more listings to load, scans, and repeats.
    """
    if not PLAYWRIGHT_AVAILABLE:
        raise RuntimeError( "pagination_type='scroll' requires Playwright, since scrolling needs a real browser. ")

    all_jobs: list[JobListing] = []
    seen_keys = set()
    consecutive_no_new = 0
    total_scans = stop_value - start_value + 1

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=random_user_agent(),
            viewport={"width": 1366, "height": 900},
        )
        page = context.new_page()
        page.goto(base_url, timeout=20000, wait_until="domcontentloaded")
        page.wait_for_timeout(JS_WAIT_SECONDS * 1000)

        for idx, value in enumerate(range(start_value, stop_value + 1)):
            if idx > 0:
                try:
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                except Exception as e:
                    print(f"  [ERR] Failed to scroll after scan {value - 1}: {e}. Stopping.")
                    break

                page.wait_for_timeout(JS_WAIT_SECONDS * 1000)

            html = page.content()
            soup = BeautifulSoup(html, "html.parser")
            scan_jobs = extract_jobs_from_soup(soup, class_selector, value, base_domain)

            new_jobs = []
            for j in scan_jobs:
                key = (j.title, j.company, j.url)
                if key not in seen_keys:
                    seen_keys.add(key)
                    new_jobs.append(j)

            all_jobs.extend(new_jobs)
            print(f"  [{idx+1:>3}/{total_scans}] scroll={value:<6} Found {len(new_jobs):>3} new listings "
                  f"(total so far: {len(all_jobs)})")

            if len(new_jobs) == 0:
                consecutive_no_new += 1
                if consecutive_no_new >= SCROLL_NO_NEW_CONTENT_LIMIT:
                    print(f"  [STOP] {SCROLL_NO_NEW_CONTENT_LIMIT} consecutive scrolls with no new "
                          f"listings. Assuming end of feed.")
                    break
            else:
                consecutive_no_new = 0

            if idx < total_scans - 1:
                polite_delay(min_delay, max_delay)

        browser.close()

    return all_jobs


def scrape_jobs(
    base_url: str,
    class_selector: Optional[str] = None,
    pagination_type: str = "page",
    start_value: int = 1,
    stop_value: int = 10,
    step: int = 10,
    next_selector: Optional[str] = None,
    min_delay: float = 2.0,
    max_delay: float = 5.5,
    max_retries: int = 3,
    use_js_fallback: bool = True,
) -> list[JobListing]:
    if pagination_type not in VALID_PAGINATION_TYPES:
        raise ValueError(
            f"Invalid pagination_type '{pagination_type}'. "
            f"Must be one of {VALID_PAGINATION_TYPES}."
        )

    parsed = urlparse(base_url)
    base_domain = f"{parsed.scheme}://{parsed.netloc}"

   
    if pagination_type == "next": 
        if not next_selector:  # --- "next" pagination: DOM-mutating button-click flow ---
            raise ValueError(
                "next_selector is required when pagination_type='next' "
                "(e.g. next_selector=\"button.next-page\")."
            )

        print(f"\n{'='*60}")
        print(f"  Job Board Scraper")
        print(f"  Target          : {base_url}")
        print(f"  Pagination type : next  (click-based, same page)")
        print(f"  Next selector   : {next_selector}")
        print(f"  Class selector  : {class_selector or '(auto-detect <ul>/<li>)'}")
        print(f"  Scans planned   : {start_value} → {stop_value} "
              f"({stop_value - start_value + 1} scans)")
        print(f"  Started         : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*60}\n")

        all_jobs = _scrape_next_button_pagination(
            base_url=base_url,
            class_selector=class_selector,
            next_selector=next_selector,
            start_value=start_value,
            stop_value=stop_value,
            min_delay=min_delay,
            max_delay=max_delay,
            base_domain=base_domain,
        )

        print(f"\n  Scraping complete. {len(all_jobs)} total listings collected.\n")

        if len(all_jobs) == 0:
            print(f"  ⚠ No listings found. Double-check that '{class_selector}' is the "
                  f"correct class name and that '{next_selector}' actually matches the "
                  f"Next/Load-more button.\n")

        return all_jobs

    if pagination_type == "scroll":
        print(f"\n{'='*60}")  # --- "scroll" pagination: infinite-scroll flow ---
        print(f"  Job Board Scraper")
        print(f"  Target          : {base_url}")
        print(f"  Pagination type : scroll  (infinite-scroll, same page)")
        print(f"  Class selector  : {class_selector or '(auto-detect <ul>/<li>)'}")
        print(f"  Scrolls planned : {start_value} → {stop_value} "
              f"({stop_value - start_value + 1} scrolls, or until no new jobs load)")
        print(f"  Started         : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*60}\n")

        all_jobs = _scrape_scroll_pagination(
            base_url=base_url,
            class_selector=class_selector,
            start_value=start_value,
            stop_value=stop_value,
            min_delay=min_delay,
            max_delay=max_delay,
            base_domain=base_domain,
        )

        print(f"\n  Scraping complete. {len(all_jobs)} total listings collected.\n")

        if len(all_jobs) == 0:
            print(f"  ⚠ No listings found. Double-check that '{class_selector}' is the "
                  f"correct class name.\n")

        return all_jobs

    session = requests.Session() # --- "page" / "offset" / "from" pagination: independent HTTP requests ---
    all_jobs: list[JobListing] = []
    page_values = _build_page_values(pagination_type, start_value, stop_value, step)

    print(f"\n{'='*60}")
    print(f"  Job Board Scraper")
    print(f"  Target          : {base_url}<value>")
    print(f"  Pagination type : {pagination_type}")
    print(f"  Class selector  : {class_selector or '(auto-detect <ul>/<li>)'}")
    print(f"  Values to fetch : {page_values[0]} → {page_values[-1]} "
          f"({len(page_values)} requests, step={step if pagination_type != 'page' else 1})")
    print(f"  Started         : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")

    for idx, value in enumerate(page_values):
        url = _build_url(base_url, pagination_type, value)
        response = fetch_with_retries(session, url, max_retries=max_retries)

        if response is None:
            print(f"  [SKIP] value={value} skipped after {max_retries} attempts.\n")
            continue

        soup = BeautifulSoup(response.text, "html.parser")
        page_jobs = extract_jobs_from_soup(soup, class_selector, value, base_domain)

        # --- JS-rendering fallback ---
        used_js_fallback = False
        if len(page_jobs) == 0 and use_js_fallback:
            print(f"  [{idx+1:>3}/{len(page_values)}] value={value:<6} "
                  f"0 listings in static HTML — retrying with headless browser …")

            rendered_html = render_with_browser(url, class_selector)

            if rendered_html:
                used_js_fallback = True
                soup = BeautifulSoup(rendered_html, "html.parser")
                page_jobs = extract_jobs_from_soup(soup, class_selector, value, base_domain)

        all_jobs.extend(page_jobs)
        fallback_note = "  (via headless browser)" if used_js_fallback else ""
        print(f"  [{idx+1:>3}/{len(page_values)}] value={value:<6} Found {len(page_jobs):>3} listings  "
              f"(total so far: {len(all_jobs)}){fallback_note}")

        if idx < len(page_values) - 1:
            polite_delay(min_delay, max_delay)

    print(f"\n  Scraping complete. {len(all_jobs)} total listings collected.\n")

    if class_selector and len(all_jobs) == 0:
        if use_js_fallback and not PLAYWRIGHT_AVAILABLE:
            print(f"  ⚠ No listings found!")
        else:
            print(f"  ⚠ No listings found even after the JS-rendering fallback. Double-check that '{class_selector}' is the correct class name.\n ")
    return all_jobs
