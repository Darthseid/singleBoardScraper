"""
extraction.py
-------------
Heuristic extraction of structured job fields (title, company, location,
salary, etc.) from a single HTML element representing one job listing.
"""

import re
from typing import Optional

from models import JobListing

_SALARY_RE = re.compile(
    r"[\$£€₹][\d,\.]+(?:[kK])?(?:\s*[-–]\s*[\$£€₹]?[\d,\.]+[kK]?)?"
    r"|[\d,\.]+\s*(?:[kK])?\s*(?:USD|GBP|EUR|per\s+(?:year|annum|hour|hr|month))",
    re.IGNORECASE,
) # Salary: £40,000 | $80k-$100k | €50,000 pa | 50,000 – 70,000 USD


_DATE_RE = re.compile(
    r"\b(?:posted\s+)?(?:\d+\s+(?:day|hour|week|month)s?\s+ago"
    r"|\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4}"
    r"|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4})\b",
    re.IGNORECASE,
) # Date patterns: "Posted 3 days ago" | "Jun 12, 2025" | "2025-06-12"


_TYPE_KEYWORDS = [
    "full-time", "full time", "part-time", "part time",
    "contract", "freelance", "temporary", "internship",
    "permanent", "remote", "hybrid", "on-site", "onsite",
] # Employment type keywords

_NOISE = re.compile(r"\s+", re.S)
MIN_RAW_TEXT_LENGTH = 30 # Listings with less raw text than this are treated as nav/sidebar noise

def _clean(text: str) -> str:
    return _NOISE.sub(" ", text).strip()

def extract_job_info(item, page_marker, base_domain: str = "") -> JobListing:
    """
    Pull structured fields out of a single job-listing element using
    heuristics. `item` can be a <div>, <li>, <article>, or any tag.
    """
    raw = _clean(item.get_text(separator=" "))
    job = JobListing(page_found=page_marker, raw_text=raw)

    anchor = item.find("a", href=True)
    if anchor:  # --- URL ---
        href = anchor["href"]
        job.url = href if href.startswith("http") else base_domain.rstrip("/") + "/" + href.lstrip("/")

    for tag in ("h1", "h2", "h3", "h4", "h5", "a"):
        el = item.find(tag)  # --- Title: first heading tag, falling back to the anchor text ---
        if el and el.get_text(strip=True):
            candidate = _clean(el.get_text())
            if len(candidate) > 3:
                job.title = candidate
                break
 
    def _find_by_class(*keywords: str) -> Optional[str]:
        for kw in keywords:
            el = item.find(class_=re.compile(kw, re.I))
            if el:   # --- Common semantic class / attribute hints ---
                return _clean(el.get_text())
        return None

    job.company  = _find_by_class("company", "employer", "org", "organisation")
    job.location = _find_by_class("location", "city", "place", "geo", "region")
    job.salary   = _find_by_class("salary", "pay", "compensation", "wage") or \
                   (m.group() if (m := _SALARY_RE.search(raw)) else None)
    job.date_posted = _find_by_class("date", "posted", "time", "ago") or \
                      (m.group() if (m := _DATE_RE.search(raw)) else None)

    raw_lower = raw.lower()
    for kw in _TYPE_KEYWORDS:
        if kw in raw_lower:
            job.job_type = kw.title()
            break # --- Job type from text ---
    
    tag_els = item.find_all(["span", "a"], class_=re.compile(r"tag|badge|skill|label|pill", re.I))
    job.tags = [_clean(t.get_text()) for t in tag_els if _clean(t.get_text())] # --- Tags: small <span>/<a> elements that look like badges ---

    if not job.title and raw:    # --- Fallback: if title still empty, use first chunk of raw text ---
        job.title = raw.split(".")[0][:80]

    return job

def find_job_lists(soup) -> list:
    """
    Fallback auto-detection used only when no class_selector is supplied.
    Locates the <ul>/<ol> most likely to contain job listings by scoring
    text density per <li> child.
    """
    candidates = []
    for ul in soup.find_all(["ul", "ol"]):
        items = ul.find_all("li", recursive=False)
        if len(items) < 2:
            continue
        avg_len = sum(len(li.get_text()) for li in items) / len(items)
        candidates.append((avg_len, items))

    if candidates:
        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1]

    return soup.find_all("li")

def find_job_items(soup, class_selector: Optional[str]) -> list:
    """
    Single entry point to find job elements on a page, given either an
    explicit class_selector or None (auto-detect mode).
    """
    if class_selector:
        return soup.find_all(class_=class_selector)
    return find_job_lists(soup)

def extract_jobs_from_soup(soup, class_selector: Optional[str], page_marker, base_domain: str = "") -> list[JobListing]:
    """
    Convenience wrapper: finds job elements on a parsed page and extracts a
    JobListing from each, filtering out anything too short.
    """
    job_items = find_job_items(soup, class_selector)
    jobs = [extract_job_info(item, page_marker, base_domain) for item in job_items]
    return [j for j in jobs if len(j.raw_text) > MIN_RAW_TEXT_LENGTH]
