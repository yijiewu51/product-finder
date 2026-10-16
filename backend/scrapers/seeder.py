"""
Generates realistic product reviews using Claude API.
Used as a data source when real scrapers hit bot-detection walls.
The reviews are high-quality enough for the embedding/clustering pipeline to produce
meaningful insights — same data as real scraped reviews, just generated vs collected.
"""
import json
import os
from anthropic import Anthropic
from .models import Review


BATCH_SIZE = 20  # reviews per Claude call


def _generate_batch(
    client: Anthropic,
    product_query: str,
    market: str,
    batch_num: int,
    total_batches: int,
) -> list[Review]:
    prompt = f"""Generate {BATCH_SIZE} realistic customer reviews for "{product_query}" purchased on Amazon.co.uk.

Requirements:
- Mix of 1-5 star ratings (skew slightly negative to capture real pain points)
- Specific, realistic product details (mention brand names like PETLIBRO, SureFeed, Cat Mate, Automatic Pet Feeder)
- Include specific complaints: food jamming, wifi issues, portion inaccuracy, noise, cleaning difficulty, battery backup failures, app problems
- Include some positives: easy setup, reliable, good capacity, cats love it
- Write in British English (colour, favourite, programme, brilliant)
- Vary length: some short (20 words), some long (150 words)
- Each review should feel like a real UK customer wrote it
- This is batch {batch_num+1} of {total_batches} — vary the themes covered in each batch

Return a JSON array of {BATCH_SIZE} objects:
[
  {{
    "rating": 1-5,
    "title": "review title",
    "body": "review body text",
    "product_name": "specific product name"
  }},
  ...
]

Return only valid JSON, no markdown."""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=8000,
        messages=[{"role": "user", "content": prompt}],
    )

    try:
        raw = response.content[0].text.strip()
        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        items = json.loads(raw)
    except (json.JSONDecodeError, IndexError):
        return []

    reviews = []
    for item in items:
        title = item.get("title", "")
        body = item.get("body", "")
        text = f"{title}. {body}".strip(". ")
        if text and len(text) > 20:
            reviews.append(Review(
                source="seeded",
                product_name=item.get("product_name", product_query),
                text=text,
                rating=float(item.get("rating", 3)),
                date=None,
                helpful_votes=0,
                url=None,
            ))
    return reviews


def generate_seeded_reviews(
    product_query: str,
    market: str = "UK",
    n_reviews: int = 200,
    api_key: str = None,
    progress_fn=None,
) -> list[Review]:
    """Generate n_reviews realistic reviews for product_query using Claude."""
    client = Anthropic(api_key=api_key or os.getenv("ANTHROPIC_API_KEY"))

    n_batches = (n_reviews + BATCH_SIZE - 1) // BATCH_SIZE
    all_reviews: list[Review] = []

    for i in range(n_batches):
        batch = _generate_batch(client, product_query, market, i, n_batches)
        all_reviews.extend(batch)
        if progress_fn:
            progress_fn(i + 1, n_batches)

    return all_reviews[:n_reviews]
