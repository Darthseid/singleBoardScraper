"""
run_scraper.py
---------------
CLI entry point for the job board scraper. Configure your target site
below and run:

    python run_scraper.py

Or import directly from the modules:

    from pagination import scrape_jobs
    from output import display_jobs

    jobs = scrape_jobs(
        base_url="https://example.com/jobs?page=",
        class_selector="job-card",
        pagination_type="page",
        start_value=1,
        stop_value=10,
    )
    df = display_jobs(jobs)
"""

from pagination import scrape_jobs
from output import display_jobs, export_to_csv, export_to_excel


def main():
    BASE_URL = "https://jobs.example.com/search?page="
 
    PAGINATION_TYPE = "page"  # "page" | "offset" | "from" | "next" | "scroll"
 
    START_VALUE = 1 # Starting value (page number, starting offset/from index, or scan/scroll number)

    STOP_VALUE = 3 # Last value to fetch

    STEP = 10  # Increment size — only used for "offset" / "from" pagination

    NEXT_SELECTOR = None # Required ONLY when PAGINATION_TYPE = "next"
    
    CLASS_SELECTOR = None # The class name that wraps each individual job listing

    FILTER_KEYWORD = None # Optional: only show listings containing this word after scraping

    SORT_BY = "page"     # Sort results: "page" | "title" | "company" | "location"
 
    USE_JS_FALLBACK = True   # Auto-retry with headless browser when page returns 0 listings

    jobs = scrape_jobs(
        base_url=BASE_URL,
        class_selector=CLASS_SELECTOR,
        pagination_type=PAGINATION_TYPE,
        start_value=START_VALUE,
        stop_value=STOP_VALUE,
        step=STEP,
        next_selector=NEXT_SELECTOR,
        min_delay=2.0,
        max_delay=5.5,
        use_js_fallback=USE_JS_FALLBACK,
    )

    df = display_jobs(jobs, filter_keyword=FILTER_KEYWORD, sort_by=SORT_BY)
    # export_to_csv(df, "jobs.csv")

    return df

if __name__ == "__main__":
    main()
