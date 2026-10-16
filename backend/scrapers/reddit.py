"""
Reddit scraper using PRAW (OAuth read-only).
Requires REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET in .env

UK-relevant subreddits for product discovery:
  r/CasualUK, r/britishproblems, r/AskUK
  r/cats, r/dogs, r/Pets
  r/DIYUK, r/HomeImprovement
  r/BabyBumps, r/UKParenting
  r/GardeningUK
  r/running, r/cycling
"""
import os
import time
from .models import Review

UK_SUBREDDITS = [
    # General UK
    "CasualUK", "AskUK", "britishproblems", "UKPersonalFinance",
    # Pets
    "cats", "dogs", "Pets", "CatsUK",
    # Home / DIY
    "DIYUK", "HomeImprovement", "malelivingspace",
    # Baby / family
    "BabyBumps", "Parenting",
    # Garden / outdoors
    "GardeningUK", "running",
    # Tech / gadgets
    "gadgets", "BuyItForLife",
]

PRODUCT_SEARCH_TERMS = [
    "recommend buy",
    "bought review",
    "best worst disappointed",
    "broke stopped working",
    "alternative recommend instead",
    "anyone use",
]


def _is_available() -> bool:
    return bool(os.getenv("REDDIT_CLIENT_ID") and os.getenv("REDDIT_CLIENT_SECRET"))


def scrape_reddit(
    max_posts_per_sub: int = 30,
    max_comments_per_post: int = 10,
    progress_fn=None,
) -> list[Review]:
    """
    Broad scrape of UK subreddits for product discussions.
    Returns empty list if REDDIT credentials not configured.
    """
    if not _is_available():
        print("    Reddit: REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET not set — skipping")
        return []

    try:
        import praw
    except ImportError:
        print("    Reddit: praw not installed — run: pip install praw")
        return []

    reddit = praw.Reddit(
        client_id=os.getenv("REDDIT_CLIENT_ID"),
        client_secret=os.getenv("REDDIT_CLIENT_SECRET"),
        user_agent="product-finder-uk:v1.0",
    )

    all_reviews: list[Review] = []
    total = len(UK_SUBREDDITS)

    for i, sub_name in enumerate(UK_SUBREDDITS):
        if progress_fn:
            progress_fn(i + 1, total, sub_name)

        try:
            sub = reddit.subreddit(sub_name)

            # Hot + new posts
            posts = list(sub.hot(limit=max_posts_per_sub // 2)) + \
                    list(sub.new(limit=max_posts_per_sub // 2))

            for post in posts:
                title = post.title or ""
                body = post.selftext or ""
                text = f"{title}. {body}".strip(". ")

                if len(text) > 30:
                    all_reviews.append(Review(
                        source="reddit",
                        product_name=sub_name,
                        text=text[:700],
                        rating=None,
                        date=None,
                        helpful_votes=post.score,
                        url=f"https://reddit.com{post.permalink}",
                    ))

                # Top comments
                try:
                    post.comments.replace_more(limit=0)
                    for comment in list(post.comments)[:max_comments_per_post]:
                        body = getattr(comment, "body", "")
                        if body and len(body) > 40 and body not in ("[deleted]", "[removed]"):
                            all_reviews.append(Review(
                                source="reddit",
                                product_name=sub_name,
                                text=body[:500],
                                rating=None,
                                date=None,
                                helpful_votes=comment.score,
                                url=f"https://reddit.com{post.permalink}",
                            ))
                except Exception:
                    pass

            time.sleep(0.5)

        except Exception as e:
            print(f"    Reddit r/{sub_name} error: {e}")
            continue

    return all_reviews
