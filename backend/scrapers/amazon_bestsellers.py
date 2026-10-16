"""
Amazon UK bestseller scraper.
Scrapes product names, prices, and ratings from bestseller lists — NOT review pages.
Light-weight: just titles + metadata, no bot-detection issues.

Categories covered:
  Pet Supplies, Home & Kitchen, Baby, Sports & Outdoors,
  Health & Personal Care, Toys & Games, Kitchen & Dining,
  Garden & Outdoors, DIY & Tools, Electronics (accessories only)
"""
import time
import random
import re
import requests
from bs4 import BeautifulSoup
from .models import Review

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-GB,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
}

# Amazon UK bestseller page slugs
BESTSELLER_CATEGORIES = {
    "pet-supplies":     "https://www.amazon.co.uk/Best-Sellers-Pet-Supplies/zgbs/pets",
    "home-kitchen":     "https://www.amazon.co.uk/Best-Sellers-Kitchen-Home/zgbs/kitchen",
    "baby":             "https://www.amazon.co.uk/Best-Sellers-Baby/zgbs/baby",
    "sports-outdoors":  "https://www.amazon.co.uk/Best-Sellers-Sports-Outdoors/zgbs/sports",
    "health-beauty":    "https://www.amazon.co.uk/Best-Sellers-Health-Personal-Care/zgbs/drugstore",
    "toys-games":       "https://www.amazon.co.uk/Best-Sellers-Toys-Games/zgbs/toys",
    "garden-outdoors":  "https://www.amazon.co.uk/Best-Sellers-Garden-Outdoors/zgbs/lawn-garden",
    "diy-tools":        "https://www.amazon.co.uk/Best-Sellers-DIY-Tools/zgbs/diy",
}


def _scrape_bestseller_page(url: str, category: str) -> list[Review]:
    """Scrape one bestseller page and return product-description Reviews."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return []
    except Exception:
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    reviews = []

    # Each bestseller item
    for item in soup.select("div.zg-grid-general-faceout, div[class*='zg-item']"):
        name_el = item.select_one("div._cDEzb_p13n-sc-css-line-clamp-1_1Fn1y, span.zg-text-center-align a, .p13n-sc-truncate-desktop-type2")
        if not name_el:
            name_el = item.select_one("a span")
        if not name_el:
            continue

        name = name_el.get_text(strip=True)
        if len(name) < 5:
            continue

        # Price
        price_el = item.select_one(".p13n-sc-price, span._cDEzb_p13n-sc-price_3mJ9Z")
        price = price_el.get_text(strip=True) if price_el else ""

        # Rating
        rating_el = item.select_one("span.a-icon-alt")
        rating_text = rating_el.get_text(strip=True) if rating_el else ""
        rating = None
        if rating_text:
            m = re.search(r"(\d+\.?\d*)", rating_text)
            rating = float(m.group(1)) if m else None

        # Review count
        count_el = item.select_one("span.a-size-small")
        review_count = count_el.get_text(strip=True) if count_el else ""

        # Compose a structured text that the embedding model can work with
        text = f"Bestselling product in {category}: {name}. Price: {price}. {review_count} reviews."
        if len(text) > 20:
            reviews.append(Review(
                source="amazon_bestseller",
                product_name=name,
                text=text,
                rating=rating,
                date=None,
                helpful_votes=0,
                url=url,
            ))

    return reviews


def scrape_amazon_bestsellers(
    categories: list[str] | None = None,
    progress_fn=None,
) -> list[Review]:
    """
    Scrape Amazon UK bestsellers across all (or specified) categories.
    Returns product metadata as Review objects for the discovery pipeline.
    """
    cats = categories or list(BESTSELLER_CATEGORIES.keys())
    all_reviews: list[Review] = []

    for i, cat in enumerate(cats):
        if cat not in BESTSELLER_CATEGORIES:
            continue
        url = BESTSELLER_CATEGORIES[cat]
        if progress_fn:
            progress_fn(i + 1, len(cats), cat)

        items = _scrape_bestseller_page(url, cat)
        all_reviews.extend(items)
        time.sleep(random.uniform(1.5, 3.0))  # polite delay

    return all_reviews


# Amazon UK Movers & Shakers — products with fastest rising sales rank
MOVERS_CATEGORIES = {
    "pet-supplies":    "https://www.amazon.co.uk/gp/movers-and-shakers/pets",
    "home-kitchen":    "https://www.amazon.co.uk/gp/movers-and-shakers/kitchen",
    "baby":            "https://www.amazon.co.uk/gp/movers-and-shakers/baby",
    "sports-outdoors": "https://www.amazon.co.uk/gp/movers-and-shakers/sports",
    "health-beauty":   "https://www.amazon.co.uk/gp/movers-and-shakers/drugstore",
    "toys-games":      "https://www.amazon.co.uk/gp/movers-and-shakers/toys",
    "garden":          "https://www.amazon.co.uk/gp/movers-and-shakers/lawn-garden",
    "diy-tools":       "https://www.amazon.co.uk/gp/movers-and-shakers/diy",
}


def _scrape_movers_page(url: str, category: str) -> list[Review]:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return []
    except Exception:
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    reviews = []

    for item in soup.select("div.zg-grid-general-faceout, div[class*='zg-item']"):
        name_el = item.select_one("div._cDEzb_p13n-sc-css-line-clamp-1_1Fn1y, span.zg-text-center-align a, a span")
        if not name_el:
            continue
        name = name_el.get_text(strip=True)
        if len(name) < 5:
            continue

        # Rank change percentage
        pct_el = item.select_one(".zg-percent-change, [class*='percent']")
        pct = pct_el.get_text(strip=True) if pct_el else ""

        price_el = item.select_one(".p13n-sc-price, span._cDEzb_p13n-sc-price_3mJ9Z")
        price = price_el.get_text(strip=True) if price_el else ""

        text = (
            f"Amazon UK Movers & Shakers in {category}: '{name}' is rapidly rising in sales rank"
            + (f" ({pct} rank improvement)" if pct else "")
            + (f". Price: {price}." if price else ".")
            + " This indicates sudden surge in UK consumer demand."
        )

        reviews.append(Review(
            source="amazon_movers_uk",
            product_name=name,
            text=text,
            rating=None,
            date="current",
            helpful_votes=0,
            url=url,
        ))

    return reviews


def scrape_amazon_movers(progress_fn=None) -> list[Review]:
    """Scrape Amazon UK Movers & Shakers — products with rapidly rising sales rank."""
    all_reviews: list[Review] = []
    cats = list(MOVERS_CATEGORIES.items())

    for i, (cat, url) in enumerate(cats):
        if progress_fn:
            progress_fn(i + 1, len(cats), cat)
        items = _scrape_movers_page(url, cat)
        all_reviews.extend(items)
        time.sleep(random.uniform(2.0, 3.5))

    return all_reviews
