"""
websiteKeyword.py
------------------
Searches paginated web pages for a keyword, using the same pagination
strategies as the job board scraper (page / offset / from / next / scroll).

Reuses anti_ban.py for headers/retries/delays and pagination.py's browser
helpers for the JS-driven modes, so the anti-ban and pagination logic stays
in one place rather than being duplicated here.

Usage:
    python websiteKeyword.py

Or import directly:
    from websiteKeyword import search_keyword_across_pages
"""

import time
from typing import Optional

import requests
from bs4 import BeautifulSoup

from anti_ban import fetch_with_retries, polite_delay, random_user_agent
from pagination import (
    VALID_PAGINATION_TYPES,
    JS_WAIT_SECONDS,
    PLAYWRIGHT_AVAILABLE,
    _build_page_values,
    _build_url,
    render_with_browser,
)

if PLAYWRIGHT_AVAILABLE:
    from playwright.sync_api import sync_playwright


def _page_contains_keyword(html: str, keyword_lower: str) -> bool:
    soup = BeautifulSoup(html, "html.parser")
    return keyword_lower in soup.get_text().lower()


def _search_next_button(
    base_url: str,
    keyword_lower: str,
    next_selector: str,
    start_value: int,
    stop_value: int,
    min_delay: float,
    max_delay: float,
) -> None:
    """Click-based pagination: same URL, clicks next_selector between scans."""
    if not PLAYWRIGHT_AVAILABLE:
        raise RuntimeError(
            "pagination_type='next' requires Playwright. Install it with:\n"
            "    pip install playwright\n"
            "    playwright install chromium"
        )

    total_scans = stop_value - start_value + 1

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent=random_user_agent())
        page = context.new_page()
        page.goto(base_url, timeout=20000, wait_until="domcontentloaded")
        page.wait_for_timeout(JS_WAIT_SECONDS * 1000)

        for idx, value in enumerate(range(start_value, stop_value + 1)):
            if idx > 0:
                next_locator = page.locator(next_selector).first
                if next_locator.count() == 0:
                    print(f"  [STOP] Next selector '{next_selector}' not found after "
                          f"scan {value - 1}. Assuming end of pages.")
                    break
                try:
                    if not next_locator.is_enabled():
                        print(f"  [STOP] Next selector '{next_selector}' disabled after "
                              f"scan {value - 1}. Assuming end of pages.")
                        break
                    next_locator.click(timeout=10000)
                except Exception as e:
                    print(f"  [ERR] Failed clicking '{next_selector}' after scan "
                          f"{value - 1}: {e}. Stopping.")
                    break
                page.wait_for_timeout(JS_WAIT_SECONDS * 1000)

            html = page.content()
            if _page_contains_keyword(html, keyword_lower):
                print(f"[FOUND] '{keyword_lower}' found on scan {value} → {base_url}")
            else:
                print(f"[  --  ] Scan {value}: keyword not found.")

            if idx < total_scans - 1:
                polite_delay(min_delay, max_delay)

        browser.close()


def _search_scroll(
    base_url: str,
    keyword_lower: str,
    start_value: int,
    stop_value: int,
    min_delay: float,
    max_delay: float,
) -> None:
    """Infinite-scroll pagination: same URL, scrolls to bottom between scans."""
    if not PLAYWRIGHT_AVAILABLE:
        raise RuntimeError(
            "pagination_type='scroll' requires Playwright."
        )

    total_scans = stop_value - start_value + 1

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent=random_user_agent())
        page = context.new_page()
        page.goto(base_url, timeout=20000, wait_until="domcontentloaded")
        page.wait_for_timeout(JS_WAIT_SECONDS * 1000)

        prev_height = None
        for idx, value in enumerate(range(start_value, stop_value + 1)):
            if idx > 0:
                try:
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                except Exception as e:
                    print(f"  [ERR] Failed to scroll after scan {value - 1}: {e}. Stopping.")
                    break
                page.wait_for_timeout(JS_WAIT_SECONDS * 1000)

            html = page.content()
            new_height = page.evaluate("document.body.scrollHeight")

            if _page_contains_keyword(html, keyword_lower):
                print(f"[FOUND] '{keyword_lower}' found on scroll {value} → {base_url}")
            else:
                print(f"[  --  ] Scroll {value}: keyword not found.")

            if prev_height is not None and new_height == prev_height and idx > 0:
                print(f"  [STOP] Page height stopped changing after scroll {value}. "
                      f"Assuming end of feed.")
                break
            prev_height = new_height

            if idx < total_scans - 1:
                polite_delay(min_delay, max_delay)

        browser.close()


def search_keyword_across_pages(
    base_url: str,
    keyword: str,
    pagination_type: str = "page",
    start_value: int = 1,
    stop_value: int = 10,
    step: int = 10,
    next_selector: Optional[str] = None,
    min_delay: float = 1.0,
    max_delay: float = 4.5,
    max_retries: int = 3,
    use_js_fallback: bool = True,
) -> None:

    if pagination_type not in VALID_PAGINATION_TYPES:
        raise ValueError(
            f"Invalid pagination_type '{pagination_type}'. "
            f"Must be one of {VALID_PAGINATION_TYPES}."
        )

    keyword_lower = keyword.lower()

    print(f"\n{'='*60}")
    print(f"  Keyword Search Scraper")
    print(f"  Target          : {base_url}")
    print(f"  Pagination type : {pagination_type}")
    print(f"  Keyword         : '{keyword}'")
    print(f"{'='*60}\n")
    
    if pagination_type == "next": # --- "next" pagination: click-based, same page ---
        if not next_selector:
            raise ValueError(
                "next_selector is required when pagination_type='next' "
                "(e.g. next_selector=\"button.next-page\")."
            )
        _search_next_button(
            base_url, keyword_lower, next_selector,
            start_value, stop_value, min_delay, max_delay,
        )
        return

   
    if pagination_type == "scroll":  # --- "scroll" pagination: infinite scroll, same page ---
        _search_scroll(
            base_url, keyword_lower,
            start_value, stop_value, min_delay, max_delay,
        )
        return

   
    session = requests.Session()  # --- "page" / "offset" / "from" pagination: independent HTTP requests ---
    page_values = _build_page_values(pagination_type, start_value, stop_value, step)

    for idx, value in enumerate(page_values):
        url = _build_url(base_url, pagination_type, value)
        response = fetch_with_retries(session, url, max_retries=max_retries)

        if response is None:
            print(f"[SKIP] value={value} skipped after {max_retries} attempts.")
            if idx < len(page_values) - 1:
                polite_delay(min_delay, max_delay)
            continue

        html = response.text
        found = _page_contains_keyword(html, keyword_lower)

        used_js_fallback = False   # If not found in static HTML, optionally retry with a headless browser in case the page renders its content via JavaScript.
        if not found and use_js_fallback:
            rendered_html = render_with_browser(url, class_selector=None)
            if rendered_html:
                used_js_fallback = True
                found = _page_contains_keyword(rendered_html, keyword_lower)

        fallback_note = "  (via headless browser)" if used_js_fallback else ""
        if found:
            print(f"[FOUND] '{keyword}' found on page {value} → {url}{fallback_note}")
        else:
            print(f"[  --  ] Page {value}: keyword not found.{fallback_note}")

        if idx < len(page_values) - 1:
            polite_delay(min_delay, max_delay)

    print(f"\n  Search complete.\n")


if __name__ == "__main__":
    search_keyword_across_pages(
        base_url= "https://web.archive.org/web/20170616151024/http://forums.steampowered.com/forums/forumdisplay.php?f=80&pp=25&sort=lastpost&order=desc&daysprune=-1&page=",
        keyword="SPUF",
        pagination_type="page",
        start_value=1,
        stop_value=4, 
                             )