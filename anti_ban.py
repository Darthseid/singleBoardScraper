"""
anti_ban.py
-----------
Politeness and anti-ban helpers: User-Agent rotation, realistic request
headers, and the rate-limit / retry / back-off logic used around each
HTTP request.
"""

import random
import time
import requests

_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
]


def random_user_agent() -> str:
    """Returns a random desktop/mobile User-Agent string."""
    return random.choice(_USER_AGENTS)


def get_headers() -> dict:
    """
    Builds a realistic header set with a randomly rotated User-Agent,
    intended to make each request look like an ordinary browser visit.
    """
    return {
        "User-Agent": random_user_agent(),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "DNT": "1",
    }


def polite_delay(min_delay: float, max_delay: float) -> None:
    """Sleeps a randomised amount of time between min_delay and max_delay."""
    time.sleep(random.uniform(min_delay, max_delay))


def fetch_with_retries(
    session: requests.Session,
    url: str,
    max_retries: int = 3,
    timeout: int = 12,
):
    """
    Performs a GET request with rate-limit awareness and retry/back-off on
    connection errors and timeouts.

    Returns the `requests.Response` on success, or None if every attempt
    failed (callers should check for None and skip that page).
    """
    attempt = 0
    response = None

    while attempt < max_retries:
        try:
            response = session.get(url, headers=get_headers(), timeout=timeout)
            if response.status_code == 429:
                wait = int(response.headers.get("Retry-After", 30))
                print(f"  [429] Rate limited at {url}. Waiting {wait}s …")
                time.sleep(wait)
                attempt += 1
                continue
            response.raise_for_status()
            return response

        except requests.exceptions.ConnectionError:
            attempt += 1
            print(f"  [ERR] Connection error at {url} "
                  f"(attempt {attempt}/{max_retries}). Retrying …")
            time.sleep(10)
        except requests.exceptions.Timeout:
            attempt += 1
            print(f"  [ERR] Timeout at {url} "
                  f"(attempt {attempt}/{max_retries}). Retrying …")
            time.sleep(8)
        except requests.exceptions.HTTPError as e:
            print(f"  [ERR] HTTP {e.response.status_code} at {url}. Skipping.")
            return None

    return None
