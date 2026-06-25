"""
models.py
---------
The core data model for scraped job listings.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class JobListing:
    page_found: int          # page number / offset / from-value / scan number where it was found
    raw_text: str
    title: Optional[str] = None
    company: Optional[str] = None
    location: Optional[str] = None
    salary: Optional[str] = None
    job_type: Optional[str] = None        # Full-time / Part-time / Contract …
    date_posted: Optional[str] = None
    url: Optional[str] = None
    tags: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        lines = []
        lines.append(f"  {'Title:':<14} {self.title or 'N/A'}")
        lines.append(f"  {'Company:':<14} {self.company or 'N/A'}")
        lines.append(f"  {'Location:':<14} {self.location or 'N/A'}")
        lines.append(f"  {'Salary:':<14} {self.salary or 'N/A'}")
        lines.append(f"  {'Type:':<14} {self.job_type or 'N/A'}")
        lines.append(f"  {'Posted:':<14} {self.date_posted or 'N/A'}")
        if self.tags:
            lines.append(f"  {'Tags:':<14} {', '.join(self.tags)}")
        if self.url:
            lines.append(f"  {'URL:':<14} {self.url}")
        lines.append(f"  {'Found at:':<14} {self.page_found}")
        return "\n".join(lines)
