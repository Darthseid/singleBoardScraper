"""
output.py
---------
Converts scraped JobListing objects into pandas DataFrames, prints a
formatted table, and exports to CSV/Excel.
"""

from typing import Optional

import pandas as pd

from models import JobListing


def jobs_to_dataframe(jobs: list[JobListing]) -> pd.DataFrame:
    """
    Converts a list of JobListing objects into a pandas DataFrame.

    Columns: title, company, location, salary, job_type, date_posted,
             url, tags, page_found, raw_text
    """
    records = [
        {
            "title":       job.title or "N/A",
            "company":     job.company or "N/A",
            "location":    job.location or "N/A",
            "salary":      job.salary or "N/A",
            "job_type":    job.job_type or "N/A",
            "date_posted": job.date_posted or "N/A",
            "url":         job.url or "N/A",
            "tags":        "|".join(job.tags) if job.tags else "",
            "page_found":  job.page_found,
            "raw_text":    job.raw_text,
        }
        for job in jobs
    ]

    df = pd.DataFrame(records, columns=[
        "title", "company", "location", "salary", "job_type",
        "date_posted", "url", "tags", "page_found", "raw_text",
    ])
    return df


def display_jobs(
    jobs: list[JobListing],
    filter_keyword: Optional[str] = None,
    sort_by: str = "page",
    show_raw_text: bool = False,
    max_col_width: int = 40,
) -> pd.DataFrame:
    """
    Builds a pandas DataFrame from scraped jobs, optionally filters and
    sorts it, prints it, and returns it for further use.

    Args:
        jobs:            Output of scrape_jobs().
        filter_keyword:  If provided, only keep rows whose raw text
                         contains this keyword (case-insensitive).
        sort_by:         Column to sort by: "page" | "title" | "company" | "location".
        show_raw_text:   If True, includes the full raw_text column.
        max_col_width:   Truncates long text columns when printing.

    Returns:
        A pandas DataFrame containing all (filtered) jobs.
    """
    df = jobs_to_dataframe(jobs)

    if filter_keyword:
        kw = filter_keyword.lower()
        mask = df["raw_text"].str.lower().str.contains(kw, na=False)
        df = df[mask]
        print(f"  Filtered to listings containing '{filter_keyword}': {len(df)} results\n")

    sort_column_map = {
        "page":     "page_found",
        "title":    "title",
        "company":  "company",
        "location": "location",
    }
    sort_col = sort_column_map.get(sort_by, "page_found")
    if sort_col in ("title", "company", "location"):
        df = df.iloc[df[sort_col].str.lower().argsort()]
    else:
        df = df.sort_values(by=sort_col)

    df = df.reset_index(drop=True)

    print_cols = [c for c in df.columns if c != "raw_text" or show_raw_text]
    print_df = df[print_cols].copy()

    for col in print_df.columns:
        if print_df[col].dtype == object:
            print_df[col] = print_df[col].astype(str).apply(
                lambda s: s if len(s) <= max_col_width else s[: max_col_width - 1] + "…"
            )

    with pd.option_context(
        "display.max_rows", None,
        "display.max_columns", None,
        "display.width", 200,
        "display.colheader_justify", "left",
    ):
        print(f"\n{'='*60}")
        print(f"  JOB LISTINGS  ({len(df)} positions)")
        print(f"{'='*60}\n")
        print(print_df)
        print(f"\n{'='*60}")
        print(f"  {len(df)} total positions displayed.")
        print(f"{'='*60}\n")

    return df


def export_to_csv(jobs, filepath: str = "jobs.csv") -> pd.DataFrame:
    """
    Save all scraped jobs to a CSV file.

    Accepts either a list[JobListing] or an already-built DataFrame.
    """
    df = jobs if isinstance(jobs, pd.DataFrame) else jobs_to_dataframe(jobs)
    df.to_csv(filepath, index=False, encoding="utf-8")
    print(f"  Exported {len(df)} jobs to {filepath}")
    return df


def export_to_excel(jobs, filepath: str = "jobs.xlsx") -> pd.DataFrame:
    """
    Save all scraped jobs to an Excel (.xlsx) file.

    Accepts either a list[JobListing] or an already-built DataFrame.
    Requires: pip install openpyxl
    """
    df = jobs if isinstance(jobs, pd.DataFrame) else jobs_to_dataframe(jobs)
    df.to_excel(filepath, index=False)
    print(f"  Exported {len(df)} jobs to {filepath}")
    return df
