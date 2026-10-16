"""
Google Trends UK — rising searches by category over last 30 days.
Uses pytrends (no API key needed, but rate-limited by Google).

Gives timeliness: what UK consumers are searching MORE than usual RIGHT NOW.
"""
import time
from .models import Review

# Google Trends category IDs (UK-relevant product categories)
CATEGORIES = {
    "Pets & Animals":           64,
    "Home & Garden":            11,
    "Sports & Fitness":         18,
    "Baby & Toddler":           69,
    "Health":                   45,
    "Toys":                     185,
    "Kitchen & Dining":         632,
    "DIY & Tools":              727,
    "Beauty & Personal Care":   44,
    "Electronics Accessories":  78,
}


def _safe_rising(pytrends, cat_id: int, cat_name: str, retries: int = 2) -> list[str]:
    """Get rising related queries for a category. Returns list of query strings."""
    for attempt in range(retries):
        try:
            pytrends.build_payload(
                kw_list=[""],
                cat=cat_id,
                timeframe="today 1-m",
                geo="GB",
            )
            related = pytrends.related_queries()
            rising_df = related.get("", {}).get("rising")
            if rising_df is not None and not rising_df.empty:
                return rising_df["query"].tolist()[:15]
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(10)
            else:
                print(f"    Trends [{cat_name}]: {e}")
    return []


def scrape_google_trends(progress_fn=None) -> list[Review]:
    """
    Pull rising UK search queries for each product category.
    Each rising query becomes a Review with the trend signal as text.
    """
    try:
        from pytrends.request import TrendReq
    except ImportError:
        print("    Google Trends: pytrends not installed")
        return []

    pytrends = TrendReq(hl="en-GB", tz=0, timeout=(10, 25), retries=2, backoff_factor=0.5)
    reviews = []
    categories = list(CATEGORIES.items())

    for i, (cat_name, cat_id) in enumerate(categories):
        if progress_fn:
            progress_fn(i + 1, len(categories), cat_name)

        rising_queries = _safe_rising(pytrends, cat_id, cat_name)

        for query in rising_queries:
            # Format as a signal text the embedder can use
            text = (
                f"UK consumers are increasingly searching for: '{query}'. "
                f"This is a rising search trend in the '{cat_name}' category in the UK over the last 30 days. "
                f"Rising search volume indicates growing consumer demand or unmet need."
            )
            reviews.append(Review(
                source="google_trends_uk",
                product_name=query,
                text=text,
                rating=None,
                date="last_30_days",
                helpful_votes=0,
                url=f"https://trends.google.com/trends/explore?geo=GB&cat={cat_id}",
            ))

        time.sleep(5)  # Google rate limit: be polite

    return reviews
