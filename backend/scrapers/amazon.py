"""
Amazon UK review scraper using Playwright.
Searches amazon.co.uk, extracts ASINs, then scrapes review pages.
"""
import asyncio
import random
import re
from playwright.async_api import async_playwright, Page
from bs4 import BeautifulSoup
from .models import Review

BASE_URL = "https://www.amazon.co.uk"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


async def _delay(lo=1.5, hi=3.5):
    await asyncio.sleep(random.uniform(lo, hi))


async def _get_asins(page: Page, query: str, max_products: int) -> list[tuple[str, str]]:
    """Returns list of (asin, product_name) from search results."""
    url = f"{BASE_URL}/s?k={query.replace(' ', '+')}"
    await page.goto(url, wait_until="domcontentloaded")
    await _delay()

    soup = BeautifulSoup(await page.content(), "lxml")
    seen = set()
    results = []

    for item in soup.select("[data-asin]"):
        asin = item.get("data-asin", "").strip()
        if not asin or len(asin) != 10 or asin in seen:
            continue
        seen.add(asin)

        name_el = item.select_one("h2 a span") or item.select_one(".a-text-normal")
        name = name_el.get_text(strip=True) if name_el else asin

        results.append((asin, name))
        if len(results) >= max_products:
            break

    return results


async def _scrape_reviews(page: Page, asin: str, product_name: str, max_pages: int) -> list[Review]:
    reviews = []

    for page_num in range(1, max_pages + 1):
        url = f"{BASE_URL}/product-reviews/{asin}?pageNumber={page_num}&sortBy=recent"
        try:
            await page.goto(url, wait_until="domcontentloaded")
        except Exception:
            break
        await _delay(1.0, 2.5)

        soup = BeautifulSoup(await page.content(), "lxml")
        elements = soup.select("[data-hook='review']")
        if not elements:
            break

        for el in elements:
            rating_el = el.select_one("[data-hook='review-star-rating'] .a-icon-alt") or \
                        el.select_one("[data-hook='cmps-review-star-rating'] .a-icon-alt")
            rating = None
            if rating_el:
                m = re.search(r"(\d+\.?\d*)", rating_el.text)
                rating = float(m.group(1)) if m else None

            title_el = el.select_one("[data-hook='review-title'] span:not(.a-icon-alt)")
            title = title_el.get_text(strip=True) if title_el else ""

            body_el = el.select_one("[data-hook='review-body'] span")
            body = body_el.get_text(strip=True) if body_el else ""

            date_el = el.select_one("[data-hook='review-date']")
            date = date_el.get_text(strip=True) if date_el else ""

            helpful_el = el.select_one("[data-hook='helpful-vote-statement']")
            helpful = 0
            if helpful_el:
                m = re.search(r"(\d+)", helpful_el.text)
                helpful = int(m.group(1)) if m else 0

            text = f"{title}. {body}".strip(". ")
            if text and len(text) > 20:
                reviews.append(Review(
                    source="amazon_uk",
                    product_name=product_name,
                    text=text,
                    rating=rating,
                    date=date,
                    helpful_votes=helpful,
                    url=f"{BASE_URL}/product-reviews/{asin}",
                ))

    return reviews


async def scrape_amazon(query: str, max_products: int = 8, max_pages_per_product: int = 5) -> list[Review]:
    all_reviews = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(
            user_agent=UA,
            locale="en-GB",
            extra_http_headers={"Accept-Language": "en-GB,en;q=0.9"},
        )
        page = await ctx.new_page()

        print(f"    Searching Amazon UK: {query}")
        asins = await _get_asins(page, query, max_products)
        print(f"    Found {len(asins)} products")

        for i, (asin, name) in enumerate(asins):
            short_name = name[:55] + "..." if len(name) > 55 else name
            print(f"    [{i+1}/{len(asins)}] {short_name}")
            reviews = await _scrape_reviews(page, asin, name, max_pages_per_product)
            all_reviews.extend(reviews)
            print(f"           -> {len(reviews)} reviews")

        await browser.close()

    return all_reviews
