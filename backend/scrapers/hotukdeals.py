"""
HotUKDeals scraper — UK's largest deal/discount community.
No auth needed. Real-time signal of what UK consumers are actively buying.

"Temperature" score = number of upvotes from UK shoppers = purchase intent signal.
High temp deals = product with strong UK demand RIGHT NOW.

URL: https://www.hotukdeals.com/deals
"""
import json
import time
import random
import requests
from bs4 import BeautifulSoup
from .models import Review

BASE = "https://www.hotukdeals.com"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-GB,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://www.hotukdeals.com/",
}

# Category tag pages (covers physical products, excludes pure services/codes)
CATEGORY_URLS = [
    "/tag/pets",
    "/tag/baby",
    "/tag/sports-fitness",
    "/tag/wellness-and-health",
    "/tag/electronics",
    "/tag/diy",
]



def _parse_deals_page(url: str) -> list[Review]:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return []
    except Exception:
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    reviews = []

    # HotUKDeals renders via Vue3 — product data is in data-vue3 JSON attribute
    # Only parse the main thread normalizer divs (not image/vote/etc components)
    for div in soup.select("div.js-vue3[data-vue3]"):
        if "ThreadMainListItemNormalizer" not in div.get("data-vue3", ""):
            continue
        try:
            data = json.loads(div.get("data-vue3", "{}"))
        except (json.JSONDecodeError, ValueError):
            continue

        thread = data.get("props", {}).get("thread", {})
        title = thread.get("title", "").strip()
        if len(title) < 5:
            continue

        temperature = thread.get("temperature", 0) or 0
        price_raw = thread.get("price", 0) or 0
        price = f"£{price_raw:.2f}" if price_raw else ""
        merchant = (thread.get("merchant") or {}).get("merchantName", "")
        description = thread.get("description", "") or ""
        posted = thread.get("publishedAt", "") or ""

        parts = [f"UK deal: {title}."]
        if description:
            parts.append(str(description)[:300])
        if merchant:
            parts.append(f"Sold at {merchant}.")
        if price:
            parts.append(f"Price: {price}.")
        if temperature > 0:
            parts.append(f"{int(temperature):,} UK shoppers upvoted this deal.")
        text = " ".join(parts)

        reviews.append(Review(
            source="hotukdeals",
            product_name=title,
            text=text,
            rating=None,
            date=str(posted),
            helpful_votes=int(temperature),
            url=url,
        ))

    return reviews


def scrape_hotukdeals(
    n_pages: int = 3,
    min_temperature: int = 50,
    progress_fn=None,
) -> list[Review]:
    """
    Scrape HotUKDeals across categories + hot deals pages.
    min_temperature filters out low-interest deals.
    """
    all_reviews: list[Review] = []
    seen_titles: set[str] = set()

    # Scrape category pages
    sources = CATEGORY_URLS.copy()

    # Add paginated main hot deals feed
    for page in range(1, n_pages + 1):
        sources.append(f"/hot-deals{'?p=' + str(page) if page > 1 else ''}")

    total = len(sources)
    for i, path in enumerate(sources):
        if progress_fn:
            progress_fn(i + 1, total, path.split("/")[-1])

        url = BASE + path
        deals = _parse_deals_page(url)

        for deal in deals:
            key = deal.product_name[:60].lower()
            if key not in seen_titles and deal.helpful_votes >= min_temperature:
                seen_titles.add(key)
                all_reviews.append(deal)

        time.sleep(random.uniform(1.0, 2.0))

    return all_reviews
