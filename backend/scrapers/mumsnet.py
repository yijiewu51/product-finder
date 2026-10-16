"""
Mumsnet scraper — UK's largest parenting/consumer forum.
No auth required. Filters to threads active in last 30 days for timeliness.
"""
import time
import random
import re
import requests
from bs4 import BeautifulSoup
from .models import Review

# Mumsnet thread URLs always have a numeric ID in the last segment
_THREAD_RE = re.compile(r"/talk/[^/]+/\d+")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-GB,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

BASE = "https://www.mumsnet.com"

SECTIONS = [
    "/talk/am_i_being_unreasonable",
    "/talk/style_and_beauty",
    "/talk/parenting",
    "/talk/mumsnet_product_tests",
    "/talk/property",
    "/talk/holidays",
    "/talk/_chat",
    "/talk/pregnancy",
]

DISCOVERY_QUERIES = [
    "recommend product bought",
    "best buy worth money",
    "broke disappointed stopped working",
    "alternative instead recommend",
    "amazon ordered arrived",
    "anyone bought tried",
    "problem issue broken",
]


def _get(url: str, retries: int = 2) -> str | None:
    for _ in range(retries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=15)
            if r.status_code == 200:
                return r.text
            time.sleep(1)
        except Exception:
            time.sleep(2)
    return None


def _is_recent(time_text: str, max_days: int = 30) -> bool:
    """Return True if the thread was active within max_days."""
    if not time_text:
        return True  # if no date, include it
    text = time_text.lower()

    # "X minutes/hours ago" → always recent
    if "minute" in text or "hour" in text or "just now" in text:
        return True
    # "X days ago"
    m = re.search(r"(\d+)\s*day", text)
    if m and int(m.group(1)) <= max_days:
        return True
    # "X weeks ago"
    m = re.search(r"(\d+)\s*week", text)
    if m and int(m.group(1)) <= (max_days // 7):
        return True
    # "yesterday"
    if "yesterday" in text:
        return True
    # If it says "month" or more, exclude
    if "month" in text or "year" in text:
        return False
    return True  # default include if unparseable


def _parse_thread(url: str, category: str = "") -> list[Review]:
    html = _get(url)
    if not html:
        return []

    soup = BeautifulSoup(html, "lxml")
    posts = (soup.select(".post-body") or
             soup.select("[data-testid='talk-post-message']") or
             soup.select(".post-message"))

    reviews = []
    for post in posts:
        text = post.get_text(separator=" ", strip=True)
        if len(text) > 60:
            reviews.append(Review(
                source="mumsnet",
                product_name=category,
                text=text[:600],
                rating=None,
                date=None,
                helpful_votes=0,
                url=url,
            ))
    return reviews


def _parse_section_threads(section_url: str, max_threads: int = 10) -> list[tuple[str, str]]:
    """Get (url, time_text) pairs from a Mumsnet section listing."""
    html = _get(BASE + section_url)
    if not html:
        return []

    soup = BeautifulSoup(html, "lxml")
    results = []
    seen = set()

    for a in soup.select("a[href]"):
        href = a.get("href", "")
        if not _THREAD_RE.search(href):
            continue
        full = href if href.startswith("http") else BASE + href
        if full in seen:
            continue
        seen.add(full)

        # Try to find adjacent time element
        parent = a.find_parent("li") or a.find_parent("article") or a.find_parent("div")
        time_el = parent.find("time") if parent else None
        time_text = ""
        if time_el:
            time_text = time_el.get("datetime") or time_el.get_text(strip=True)

        results.append((full, time_text))
        if len(results) >= max_threads:
            break

    return results


def _search_threads(query: str, max_results: int = 10) -> list[tuple[str, str]]:
    url = f"{BASE}/search?q={requests.utils.quote(query)}&type=thread"
    html = _get(url)
    if not html:
        return []

    soup = BeautifulSoup(html, "lxml")
    results = []
    seen = set()

    for a in soup.select("a[href]"):
        href = a.get("href", "")
        if not _THREAD_RE.search(href):
            continue
        full = href if href.startswith("http") else BASE + href
        if full not in seen:
            seen.add(full)
            results.append((full, ""))
        if len(results) >= max_results:
            break

    return results


def scrape_mumsnet(
    max_threads_per_section: int = 10,
    max_posts_per_thread: int = 25,
    max_days_old: int = 30,
    progress_fn=None,
) -> list[Review]:
    """
    Scrape Mumsnet, filtering to threads active within last max_days_old days.
    """
    all_reviews: list[Review] = []
    seen_urls: set[str] = set()
    thread_queue: list[tuple[str, str]] = []  # (url, category)

    # Section listings
    for section in SECTIONS:
        category = section.split("/")[-1].replace("_", " ")
        threads = _parse_section_threads(section, max_threads_per_section)
        for url, time_text in threads:
            if url not in seen_urls and _is_recent(time_text, max_days_old):
                seen_urls.add(url)
                thread_queue.append((url, category))
        time.sleep(random.uniform(0.5, 1.0))

    # Search queries
    for query in DISCOVERY_QUERIES:
        threads = _search_threads(query, 8)
        for url, time_text in threads:
            if url not in seen_urls:
                seen_urls.add(url)
                thread_queue.append((url, "product discussion"))
        time.sleep(random.uniform(0.8, 1.5))

    # Scrape posts
    total = len(thread_queue)
    for i, (url, category) in enumerate(thread_queue):
        if progress_fn:
            progress_fn(i + 1, total)
        posts = _parse_thread(url, category)
        all_reviews.extend(posts[:max_posts_per_thread])
        time.sleep(random.uniform(0.6, 1.2))

    return all_reviews
